"""
wallet.py - SafeAgentWallet Implementation and Payment Execution
SafeAgent Wallet - CommitCon Hackathon

This module implements the SafeAgentWallet class with full enforcement of:
- Virtual balance ($100 initial) and lifetime spending limit ($80 max).
- Automatic threshold ($10 inclusive) and human approval requirements.
- Rate limiting (max 3 payment requests per rolling 60 seconds).
- Invalid human-authorization protection (lock after 3 failed attempts).
- Normal human rejection handling (does NOT count as invalid authorization).
- Duplicate transaction prevention using unique transaction IDs.
- Comprehensive transaction recording for both successes and rejections.
- Zero/negative balance prevention and Decimal accuracy.
- Strict security check enforcement (human approval cannot bypass any checks).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import uuid

from config import (
    AUTO_PAYMENT_THRESHOLD,
    DEFAULT_AUTH_TOKEN,
    INITIAL_BALANCE,
    LIFETIME_SPENDING_LIMIT,
    STATUS_REJECTED,
    STATUS_SUCCESS,
    TRANSACTIONS_FILE,
)
from security import AuthorizationGuard, RateLimiter, validate_amount
from transactions import Transaction, TransactionManager


@dataclass
class PaymentResult:
    """Outcome of a payment execution attempt."""

    success: bool
    transaction_id: str
    amount: Decimal
    recipient: str
    status: str
    reason: str
    balance: Decimal
    total_spent: Decimal
    remaining_spending_limit: Decimal
    requires_human_approval: bool
    human_approved: Optional[bool]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a dictionary."""
        return {
            "success": self.success,
            "transaction_id": self.transaction_id,
            "amount": str(self.amount),
            "recipient": self.recipient,
            "status": self.status,
            "reason": self.reason,
            "balance": str(self.balance),
            "total_spent": str(self.total_spent),
            "remaining_spending_limit": str(self.remaining_spending_limit),
            "requires_human_approval": self.requires_human_approval,
            "human_approved": self.human_approved,
            "timestamp": self.timestamp,
        }

    def __getitem__(self, item: str) -> Any:
        """Allow dict-style indexing for backwards-compatibility and convenience."""
        return self.to_dict()[item]


class SafeAgentWallet:
    """
    Simulated AI-agent wallet with multi-layered security controls.

    Key Parameters:
        initial_balance: Starting virtual funds (default: $100.00).
        spending_limit: Maximum cumulative spending allowed (default: $80.00).
        auto_threshold: Maximum amount processed automatically (default: $10.00).
        transactions_file: Path to JSON transaction log file.
        auth_token: Secret token required for human approval.
        load_existing: Whether to recalculate balance from existing transaction log.
    """

    def __init__(
        self,
        initial_balance: Decimal = INITIAL_BALANCE,
        spending_limit: Decimal = LIFETIME_SPENDING_LIMIT,
        auto_threshold: Decimal = AUTO_PAYMENT_THRESHOLD,
        transactions_file: Path = TRANSACTIONS_FILE,
        auth_token: str = DEFAULT_AUTH_TOKEN,
        load_existing: bool = True,
    ):
        self._initial_balance = Decimal(str(initial_balance))
        self._spending_limit = Decimal(str(spending_limit))
        self._auto_threshold = Decimal(str(auto_threshold))
        self._auth_token = auth_token

        self._lock = threading.RLock()
        self._rate_limiter = RateLimiter()
        self._auth_guard = AuthorizationGuard(expected_token=auth_token)
        self._transaction_manager = TransactionManager(file_path=transactions_file)

        # State tracking
        self._total_spent = Decimal("0.00")
        self._balance = self._initial_balance

        if load_existing:
            self._recalculate_from_history()

    def _recalculate_from_history(self) -> None:
        """Recalculates balance and spent amounts from persisted successful transactions."""
        successful = self._transaction_manager.get_successful_transactions()
        spent = sum(Decimal(tx.amount) for tx in successful)
        self._total_spent = spent
        self._balance = max(Decimal("0.00"), self._initial_balance - spent)

    @property
    def balance(self) -> Decimal:
        """Current available wallet balance."""
        with self._lock:
            return self._balance

    @property
    def total_spent(self) -> Decimal:
        """Cumulative lifetime spending."""
        with self._lock:
            return self._total_spent

    @property
    def remaining_spending_limit(self) -> Decimal:
        """Remaining allowance within the lifetime spending limit."""
        with self._lock:
            return max(Decimal("0.00"), self._spending_limit - self._total_spent)

    @property
    def is_locked(self) -> bool:
        """Whether the wallet is currently locked due to failed authorization attempts."""
        return self._auth_guard.is_locked

    @property
    def invalid_auth_attempts(self) -> int:
        """Number of failed human-authorization attempts."""
        return self._auth_guard.invalid_attempts

    @property
    def auto_threshold(self) -> Decimal:
        """Automatic payment threshold (inclusive)."""
        return self._auto_threshold

    @property
    def spending_limit(self) -> Decimal:
        """Lifetime spending limit."""
        return self._spending_limit

    def requires_human_approval(self, amount: Any) -> bool:
        """
        Helper method to check if a specific payment amount requires human approval.
        Amounts <= $10.00 are automatic. Amounts > $10.00 require human approval.
        """
        is_valid, validated_amount, _ = validate_amount(amount)
        if not is_valid or validated_amount is None:
            return False
        return validated_amount > self._auto_threshold

    def _generate_tx_id(self) -> str:
        """Generates a unique transaction identifier."""
        return f"tx_{uuid.uuid4().hex[:12]}"

    def _record_result(
        self,
        tx_id: str,
        amount: Decimal,
        recipient: str,
        status: str,
        reason: str,
        requires_approval: bool,
        human_approved: Optional[bool],
        timestamp: str,
    ) -> PaymentResult:
        """Helper to create Transaction record and return PaymentResult."""
        tx = Transaction(
            transaction_id=tx_id,
            timestamp=timestamp,
            amount=f"{amount:.2f}",
            recipient=recipient,
            status=status,
            reason=reason,
            balance_after=f"{self._balance:.2f}",
            lifetime_spent_after=f"{self._total_spent:.2f}",
            requires_human_approval=requires_approval,
            human_approved=human_approved,
        )
        self._transaction_manager.record_transaction(tx)

        return PaymentResult(
            success=(status == STATUS_SUCCESS),
            transaction_id=tx_id,
            amount=amount,
            recipient=recipient,
            status=status,
            reason=reason,
            balance=self._balance,
            total_spent=self._total_spent,
            remaining_spending_limit=self.remaining_spending_limit,
            requires_human_approval=requires_approval,
            human_approved=human_approved,
            timestamp=timestamp,
        )

    def execute_payment(
        self,
        amount: Any,
        recipient: str,
        transaction_id: Optional[str] = None,
        human_approved: Optional[bool] = None,
        auth_token: Optional[str] = DEFAULT_AUTH_TOKEN,
    ) -> PaymentResult:
        """
        Executes a payment request with full security validation.

        Parameters:
            amount: Payment amount (Decimal, float, int, str).
            recipient: Payment recipient/vendor description.
            transaction_id: Optional unique identifier. If omitted, one is generated.
            human_approved:
                - None: No human decision provided yet.
                - False: Human reviewer explicitly rejected the request.
                - True: Human reviewer approved the request.
            auth_token: Credential token used to verify human authorization.
                        Defaults to DEFAULT_AUTH_TOKEN when human_approved is True.

        Returns:
            PaymentResult containing transaction status and wallet state.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            # -------------------------------------------------------------
            # STEP 1: Rate Limiting Check (Requirement 7)
            # Maximum 3 payment requests per rolling 60 seconds.
            # Count rejected requests too!
            # -------------------------------------------------------------
            rate_ok, rate_msg = self._rate_limiter.check_and_record()
            tx_id = transaction_id or self._generate_tx_id()

            if not rate_ok:
                return self._record_result(
                    tx_id=tx_id,
                    amount=Decimal("0.00"),
                    recipient=recipient,
                    status=STATUS_REJECTED,
                    reason=rate_msg or "Rate limit exceeded.",
                    requires_approval=False,
                    human_approved=human_approved,
                    timestamp=now_iso,
                )

            # -------------------------------------------------------------
            # STEP 2: Lock Status Check (Requirement 8)
            # Lock the wallet after 3 invalid human-authorization attempts.
            # -------------------------------------------------------------
            if self._auth_guard.is_locked:
                return self._record_result(
                    tx_id=tx_id,
                    amount=Decimal("0.00"),
                    recipient=recipient,
                    status=STATUS_REJECTED,
                    reason="Wallet is locked due to 3 invalid authorization attempts. All payments are halted.",
                    requires_approval=False,
                    human_approved=human_approved,
                    timestamp=now_iso,
                )

            # -------------------------------------------------------------
            # STEP 3: Prevent Duplicate Transaction Execution (Requirement 10)
            # Prevent duplicate transaction execution using unique transaction IDs.
            # -------------------------------------------------------------
            if transaction_id is not None and self._transaction_manager.has_transaction_id(transaction_id):
                # Reject duplicate execution attempt immediately
                return PaymentResult(
                    success=False,
                    transaction_id=transaction_id,
                    amount=Decimal("0.00"),
                    recipient=recipient,
                    status=STATUS_REJECTED,
                    reason=f"Duplicate transaction ID: transaction '{transaction_id}' has already been processed.",
                    balance=self._balance,
                    total_spent=self._total_spent,
                    remaining_spending_limit=self.remaining_spending_limit,
                    requires_human_approval=False,
                    human_approved=human_approved,
                    timestamp=now_iso,
                )

            # -------------------------------------------------------------
            # STEP 4: Amount Validation (Technical Requirement)
            # Validate amounts and reject zero or negative values.
            # -------------------------------------------------------------
            is_valid_amount, validated_amount, amount_err = validate_amount(amount)
            if not is_valid_amount or validated_amount is None:
                return self._record_result(
                    tx_id=tx_id,
                    amount=Decimal("0.00"),
                    recipient=recipient,
                    status=STATUS_REJECTED,
                    reason=amount_err or "Invalid payment amount.",
                    requires_approval=False,
                    human_approved=human_approved,
                    timestamp=now_iso,
                )

            # -------------------------------------------------------------
            # STEP 5: Human Approval Verification (Requirements 3, 4, 8, 9)
            # Automatic payment threshold: $10 (inclusive).
            # Payments above $10 must require human approval.
            # -------------------------------------------------------------
            requires_approval = validated_amount > self._auto_threshold

            if requires_approval:
                if human_approved is None:
                    # Not yet approved by human
                    return self._record_result(
                        tx_id=tx_id,
                        amount=validated_amount,
                        recipient=recipient,
                        status=STATUS_REJECTED,
                        reason=(
                            f"Human approval required: payment of ${validated_amount:.2f} "
                            f"exceeds automatic threshold of ${self._auto_threshold:.2f}."
                        ),
                        requires_approval=True,
                        human_approved=None,
                        timestamp=now_iso,
                    )

                if human_approved is False:
                    # Requirement 9: Normal human rejection must NOT count as invalid auth attempt!
                    rejection_msg = self._auth_guard.record_human_rejection()
                    return self._record_result(
                        tx_id=tx_id,
                        amount=validated_amount,
                        recipient=recipient,
                        status=STATUS_REJECTED,
                        reason=rejection_msg,
                        requires_approval=True,
                        human_approved=False,
                        timestamp=now_iso,
                    )

                if human_approved is True:
                    # Verify human authorization token / credentials
                    auth_ok, auth_msg = self._auth_guard.verify_authorization(auth_token)
                    if not auth_ok:
                        # Requirement 8: Invalid authorization attempt!
                        return self._record_result(
                            tx_id=tx_id,
                            amount=validated_amount,
                            recipient=recipient,
                            status=STATUS_REJECTED,
                            reason=auth_msg,
                            requires_approval=True,
                            human_approved=True,
                            timestamp=now_iso,
                        )

            # -------------------------------------------------------------
            # STEP 6: Check Available Wallet Balance (Requirements 5, 12, 13)
            # Reject payments when balance is insufficient.
            # Never allow a negative balance.
            # Human approval must not bypass any security checks.
            # -------------------------------------------------------------
            if validated_amount > self._balance:
                return self._record_result(
                    tx_id=tx_id,
                    amount=validated_amount,
                    recipient=recipient,
                    status=STATUS_REJECTED,
                    reason=(
                        f"Insufficient wallet balance: payment of ${validated_amount:.2f} "
                        f"exceeds available balance of ${self._balance:.2f}."
                    ),
                    requires_approval=requires_approval,
                    human_approved=human_approved,
                    timestamp=now_iso,
                )

            # -------------------------------------------------------------
            # STEP 7: Check Lifetime Spending Limit (Requirements 2, 6, 13)
            # Maximum lifetime spending limit: $80.
            # Reject payments that exceed the remaining $80 spending allowance.
            # Human approval must not bypass any security checks.
            # -------------------------------------------------------------
            remaining_allowance = self.remaining_spending_limit
            if (self._total_spent + validated_amount) > self._spending_limit:
                return self._record_result(
                    tx_id=tx_id,
                    amount=validated_amount,
                    recipient=recipient,
                    status=STATUS_REJECTED,
                    reason=(
                        f"Lifetime spending limit exceeded: payment of ${validated_amount:.2f} "
                        f"exceeds remaining allowance of ${remaining_allowance:.2f} "
                        f"(lifetime limit: ${self._spending_limit:.2f})."
                    ),
                    requires_approval=requires_approval,
                    human_approved=human_approved,
                    timestamp=now_iso,
                )

            # -------------------------------------------------------------
            # STEP 8: Execute Payment (Requirements 1, 11, 12)
            # Deduct balance, update lifetime spent, record success.
            # -------------------------------------------------------------
            self._balance -= validated_amount
            self._total_spent += validated_amount

            return self._record_result(
                tx_id=tx_id,
                amount=validated_amount,
                recipient=recipient,
                status=STATUS_SUCCESS,
                reason="Payment executed successfully.",
                requires_approval=requires_approval,
                human_approved=human_approved,
                timestamp=now_iso,
            )

    def pay(
        self,
        amount: Any,
        recipient: str,
        transaction_id: Optional[str] = None,
        human_approved: Optional[bool] = None,
        auth_token: Optional[str] = DEFAULT_AUTH_TOKEN,
    ) -> PaymentResult:
        """Convenience alias for execute_payment."""
        return self.execute_payment(
            amount=amount,
            recipient=recipient,
            transaction_id=transaction_id,
            human_approved=human_approved,
            auth_token=auth_token,
        )

    def get_transaction_history(self) -> List[Dict[str, Any]]:
        """Returns all recorded transactions as dictionaries."""
        with self._lock:
            return [tx.to_dict() for tx in self._transaction_manager.get_all_transactions()]

    def unlock(self) -> None:
        """Administrative unlock for the wallet."""
        with self._lock:
            self._auth_guard.unlock()

    def lock(self) -> None:
        """Administrative lock for the wallet."""
        with self._lock:
            self._auth_guard.lock()

    def reset_rate_limiter(self) -> None:
        """Resets the rate limiter window."""
        with self._lock:
            self._rate_limiter.reset()

    def reset(self) -> None:
        """
        Resets wallet to pristine initial state:
        $100.00 balance, $0.00 spent, unlocked, empty history, reset rate limiter.
        """
        with self._lock:
            self._balance = self._initial_balance
            self._total_spent = Decimal("0.00")
            self._auth_guard.unlock()
            self._rate_limiter.reset()
            self._transaction_manager.clear()
