"""
tests/test_rate_limiter.py - Tests for rolling 60-second rate limiter and runaway agent defense
SafeAgent Wallet - CommitCon Hackathon (Hour 16–18)

Covers:
- Rolling 60-second sliding time window rate limiter.
- Sequence of attempts 1–3 allowed, attempt 4 locks and blocks, attempts 5–10 blocked.
- Mockable clock for deterministic rolling window expiration (no sleep).
- Zero fund deduction for all blocked attempts.
- Runaway agent alert payload and audit logging.
- Locked wallet persistence across time until administrative unlock.
"""

from decimal import Decimal
import pytest

import config
from tests.conftest import MockClock
from wallet import PaymentResult, SafeAgentWallet


class TestRunawayAgentProtection:
    """Tests the rolling 60-second rate limiter and runaway agent mitigation."""

    def test_attempt_1_to_3_allowed_attempt_4_locks_wallet(
        self,
        wallet: SafeAgentWallet,
        mock_clock: MockClock,
    ):
        """
        Attempts 1, 2, 3 within 60s succeed.
        Attempt 4 breaches the rate limit, immediately locks the wallet,
        and returns status BLOCKED with RATE_LIMIT_EXCEEDED.
        """
        base_t = mock_clock.time()

        # Attempt 1: Allowed
        res1 = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            agent_id="RunawayBot",
            attempt_number=1,
            current_time=base_t + 1.0,
        )
        assert res1.success is True
        assert res1.status == config.STATUS_SUCCESS
        assert wallet.balance == Decimal("95.50")
        assert wallet.is_locked is False

        # Attempt 2: Allowed
        res2 = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            agent_id="RunawayBot",
            attempt_number=2,
            current_time=base_t + 2.0,
        )
        assert res2.success is True
        assert wallet.balance == Decimal("91.00")
        assert wallet.is_locked is False

        # Attempt 3: Allowed
        res3 = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            agent_id="RunawayBot",
            attempt_number=3,
            current_time=base_t + 3.0,
        )
        assert res3.success is True
        assert wallet.balance == Decimal("86.50")
        assert wallet.is_locked is False

        # Attempt 4: Breach!
        res4 = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            agent_id="RunawayBot",
            attempt_number=4,
            current_time=base_t + 4.0,
        )
        assert res4.success is False
        assert res4.status == config.STATUS_BLOCKED
        assert config.REASON_RATE_LIMIT_EXCEEDED in res4.reason
        assert res4.event_type == config.EVENT_RUNAWAY_BLOCKED
        assert wallet.is_locked is True
        # Funds untouched for 4th attempt
        assert wallet.balance == Decimal("86.50")

    def test_attempts_5_through_10_blocked_by_locked_wallet(
        self,
        wallet: SafeAgentWallet,
        mock_clock: MockClock,
    ):
        """
        After wallet is auto-locked on attempt 4, subsequent attempts 5–10
        are halted by the locked wallet check (STATUS_BLOCKED, WALLET_LOCKED).
        No money is deducted.
        """
        base_t = mock_clock.time()

        # Trigger rate limit lock on 4th attempt
        for i in range(1, 5):
            wallet.execute_payment(
                amount=Decimal("4.50"),
                recipient="USB-C Cable",
                attempt_number=i,
                current_time=base_t + float(i),
            )
        assert wallet.is_locked is True
        bal_after_4 = wallet.balance  # $86.50

        # Attempts 5 through 10
        for i in range(5, 11):
            res = wallet.execute_payment(
                amount=Decimal("4.50"),
                recipient="USB-C Cable",
                attempt_number=i,
                current_time=base_t + float(i),
                is_agent_attempt=True,
            )
            assert res.success is False
            assert res.status == config.STATUS_BLOCKED
            assert config.REASON_WALLET_LOCKED in res.reason
            assert res.event_type == config.EVENT_RUNAWAY_BLOCKED
            # Invariant: Never deduct money on blocked attempts
            assert wallet.balance == bal_after_4

        assert wallet.blocked_attempts_count >= 7

    def test_simulate_runaway_agent_attack_helper(self, wallet: SafeAgentWallet):
        """
        Tests the 10-attempt controlled simulation helper:
        - Exactly 3 succeed ($13.50 total deducted, leaving $86.50).
        - Exactly 7 are blocked (1 rate limit breach + 6 locked wallet blocks).
        - Final wallet status is LOCKED with runaway alert.
        """
        results = wallet.simulate_runaway_agent_attack(
            attempts=10,
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            agent_id="SimulatedRunawayAgent",
        )

        assert len(results) == 10
        allowed = [r for r in results if r.success]
        blocked = [r for r in results if not r.success]

        assert len(allowed) == 3
        assert len(blocked) == 7

        assert wallet.balance == Decimal("86.50")
        assert wallet.total_spent == Decimal("13.50")
        assert wallet.is_locked is True
        assert wallet.runaway_alert is not None
        assert wallet.runaway_alert["status"] == "LOCKED"

    def test_rolling_window_expiration_with_mock_clock(
        self,
        wallet: SafeAgentWallet,
        mock_clock: MockClock,
    ):
        """
        Attempts older than 60 seconds expire from the sliding window.
        - 3 attempts at t = 1000s
        - Advance mock clock to t = 1065s (>60s)
        - Since 3 attempts expired, a 4th attempt at t = 1065s does NOT trigger rate limit.
        """
        t0 = 1000.0
        # 3 attempts at t0
        for i in range(3):
            wallet._rate_limiter.record_attempt(current_time=t0 + i)

        assert wallet._rate_limiter.get_request_count(current_time=t0 + 5.0) == 3

        # Advance time by 65 seconds
        t1 = t0 + 65.0
        # Window expired
        assert wallet._rate_limiter.get_request_count(current_time=t1) == 0

        # Now an attempt at t1 passes rate limit
        rate_ok, msg = wallet._rate_limiter.check_and_record(current_time=t1)
        assert rate_ok is True
        assert wallet._rate_limiter.get_request_count(current_time=t1) == 1

    def test_locked_wallet_rejects_human_approval(
        self,
        wallet: SafeAgentWallet,
        mock_clock: MockClock,
    ):
        """
        When the wallet is locked due to a runaway agent attack,
        even valid human approvals are blocked until administrative unlock.
        """
        wallet.simulate_runaway_agent_attack(attempts=5)
        assert wallet.is_locked is True

        res = wallet.execute_payment(
            amount=Decimal("15.00"),
            recipient="Headphones",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
            is_agent_attempt=False,
        )
        assert res.success is False
        assert config.REASON_WALLET_LOCKED in res.reason
        assert wallet.balance == Decimal("86.50")
