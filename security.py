"""
security.py - Security Validation, Rate Limiting, and Authorization Protection
SafeAgent Wallet - CommitCon Hackathon

This module handles:
1. Amount validation (rejects <= 0, non-numeric, NaN, ensures Decimal precision).
2. Rolling window rate limiting (max 3 requests per 60s, counting rejected requests too).
3. Human authorization protection (locks after 3 invalid attempts, ignores normal rejections).
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import threading
import time
from typing import Any, Callable, Optional, Tuple

from config import (
    MAX_INVALID_AUTH_ATTEMPTS,
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
)


def validate_amount(amount: Any) -> Tuple[bool, Optional[Decimal], Optional[str]]:
    """
    Validates that a payment amount is a positive, non-zero number.
    Converts valid inputs to a 2-decimal-place quantized Decimal.

    Returns:
        (is_valid, validated_amount, error_message)
    """
    if amount is None:
        return False, None, "Payment amount cannot be empty (None)."

    try:
        if isinstance(amount, float):
            dec_amount = Decimal(str(amount))
        elif isinstance(amount, (int, str)):
            dec_amount = Decimal(str(amount).strip())
        elif isinstance(amount, Decimal):
            dec_amount = amount
        else:
            return False, None, f"Unsupported amount type '{type(amount).__name__}'. Use Decimal, float, int, or str."
    except (InvalidOperation, TypeError, ValueError):
        return False, None, f"Invalid amount format: '{amount}' is not a valid number."

    if dec_amount.is_nan() or dec_amount.is_infinite():
        return False, None, "Payment amount must be a finite number."

    if dec_amount <= Decimal("0.00"):
        return False, None, f"Payment amount must be positive and greater than zero (received ${dec_amount})."

    # Quantize to 2 decimal places (standard currency)
    quantized = dec_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return True, quantized, None


class RateLimiter:
    """
    Thread-safe rolling window rate limiter.

    Enforces a maximum number of requests within a rolling time window.
    Crucially: REJECTED and BLOCKED requests are also recorded and counted toward the rate limit.
    Supports a mockable clock for deterministic, sleep-free testing.
    """

    def __init__(
        self,
        max_requests: int = RATE_LIMIT_MAX_REQUESTS,
        window_seconds: float = RATE_LIMIT_WINDOW_SECONDS,
        clock_fn: Optional[Callable[[], float]] = None,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clock_fn: Callable[[], float] = clock_fn or time.time
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def check_and_record(self, current_time: Optional[float] = None) -> Tuple[bool, Optional[str]]:
        """
        Evaluates whether a new request is permitted under the rate limit.
        Whether allowed or rejected, this attempt is recorded into the rolling window.

        Returns:
            (is_allowed, error_message)
        """
        now = self.clock_fn() if current_time is None else current_time

        with self._lock:
            # Purge timestamps outside the rolling window
            cutoff = now - self.window_seconds
            self._timestamps = [t for t in self._timestamps if t > cutoff]

            # Check if current request exceeds allowed threshold
            if len(self._timestamps) >= self.max_requests:
                # Count this rejected/blocked request too!
                self._timestamps.append(now)
                oldest_in_window = self._timestamps[0]
                wait_seconds = max(0.1, round(self.window_seconds - (now - oldest_in_window), 1))
                return (
                    False,
                    f"Rate limit exceeded: maximum {self.max_requests} payment requests allowed "
                    f"per rolling {int(self.window_seconds)} seconds. Try again in {wait_seconds}s.",
                )

            # Allowed: record this request
            self._timestamps.append(now)
            return True, None

    def record_attempt(self, current_time: Optional[float] = None) -> int:
        """
        Records an attempt into the rolling window (e.g. when blocked) and returns count.
        """
        now = self.clock_fn() if current_time is None else current_time
        with self._lock:
            cutoff = now - self.window_seconds
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            self._timestamps.append(now)
            return len(self._timestamps)

    def get_request_count(self, current_time: Optional[float] = None) -> int:
        """Returns the number of requests recorded within the current rolling window."""
        now = self.clock_fn() if current_time is None else current_time
        with self._lock:
            cutoff = now - self.window_seconds
            return len([t for t in self._timestamps if t > cutoff])

    def reset(self) -> None:
        """Clears all recorded timestamps."""
        with self._lock:
            self._timestamps.clear()


class AuthorizationGuard:
    """
    Protects transactions requiring human approval and handles wallet locking.

    Rules:
    - Locks wallet after MAX_INVALID_AUTH_ATTEMPTS (3) failed authorization attempts.
    - Locks wallet immediately upon runaway agent rate limit breach (attempt 4+).
    - A normal human rejection (human says NO) does NOT count as an invalid authorization attempt.
    """

    def __init__(
        self,
        max_invalid_attempts: int = MAX_INVALID_AUTH_ATTEMPTS,
        expected_token: Optional[str] = None,
    ):
        self.max_invalid_attempts = max_invalid_attempts
        self.expected_token = expected_token
        self._invalid_attempts: int = 0
        self._is_locked: bool = False
        self._lock_reason: Optional[str] = None
        self._lock_timestamp: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def is_locked(self) -> bool:
        with self._lock:
            return self._is_locked

    @property
    def lock_reason(self) -> Optional[str]:
        with self._lock:
            return self._lock_reason

    @property
    def lock_timestamp(self) -> Optional[str]:
        with self._lock:
            return self._lock_timestamp

    @property
    def invalid_attempts(self) -> int:
        with self._lock:
            return self._invalid_attempts

    def verify_authorization(self, auth_token: Optional[str]) -> Tuple[bool, str]:
        """
        Validates the human authorization token.

        If valid: returns (True, message) and resets consecutive invalid counter.
        If invalid: increments invalid counter and locks wallet if limit reached.
        """
        with self._lock:
            if self._is_locked:
                return False, "Wallet is locked due to 3 invalid authorization attempts. Operations halted."

            if self.expected_token is not None and auth_token is not None and auth_token == self.expected_token:
                # Reset consecutive invalid attempts upon successful authorization
                self._invalid_attempts = 0
                return True, "Human authorization verified successfully."

            # Invalid authorization attempt!
            self._invalid_attempts += 1
            if self._invalid_attempts >= self.max_invalid_attempts:
                self._is_locked = True
                return (
                    False,
                    f"Invalid human authorization attempt. Wallet locked after "
                    f"{self._invalid_attempts} failed attempts.",
                )

            remaining = self.max_invalid_attempts - self._invalid_attempts
            return (
                False,
                f"Invalid human authorization attempt. {remaining} attempt(s) remaining "
                f"before wallet is locked.",
            )

    def record_human_rejection(self) -> str:
        """
        Records a normal human rejection (reviewer declined the purchase).

        CRUCIAL (Requirement 9):
        A normal human rejection MUST NOT count as an invalid authorization attempt.
        Invalid attempt counter remains unchanged and wallet is NOT locked.
        """
        return "Payment rejected by human reviewer."

    def lock(self, reason: Optional[str] = None) -> None:
        """Explicitly locks the wallet."""
        with self._lock:
            self._is_locked = True
            self._lock_reason = reason or "Wallet is locked."
            self._lock_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def unlock(self) -> None:
        """Unlocks the wallet and resets invalid attempts."""
        with self._lock:
            self._is_locked = False
            self._invalid_attempts = 0
            self._lock_reason = None
            self._lock_timestamp = None
