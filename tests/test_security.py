"""
tests/test_security.py - Security controls and anti-tamper lockout tests
SafeAgent Wallet - CommitCon Hackathon (Hour 16–18)

Covers:
- Anti-tamper lockout after 3 invalid authorization attempts.
- Normal human rejection isolation (does not count as invalid auth).
- Strict locked wallet enforcement across all payment amounts and human authorizations.
- Administrative lock and unlock operations.
- Security bypass prevention (human approval cannot bypass balance, spending limits, locks).
"""

from decimal import Decimal
import pytest

import config
from wallet import SafeAgentWallet


class TestAntiTamperLockout:
    """Tests 3-strike invalid authorization attempt lockout."""

    def test_three_invalid_auth_attempts_locks_wallet(self, wallet: SafeAgentWallet):
        """
        Submitting payments requiring approval with invalid tokens increments strike counter.
        On 3rd strike, wallet is automatically locked.
        """
        assert wallet.invalid_auth_attempts == 0
        assert wallet.is_locked is False

        # Strike 1
        res1 = wallet.execute_payment(
            amount=Decimal("15.00"),
            recipient="Audio Store",
            human_approved=True,
            auth_token="BAD_TOKEN_1",
        )
        assert res1.success is False
        assert wallet.invalid_auth_attempts == 1
        assert wallet.is_locked is False

        # Strike 2
        res2 = wallet.execute_payment(
            amount=Decimal("15.00"),
            recipient="Audio Store",
            human_approved=True,
            auth_token="BAD_TOKEN_2",
        )
        assert res2.success is False
        assert wallet.invalid_auth_attempts == 2
        assert wallet.is_locked is False

        # Strike 3 -> Automatic Lockout
        res3 = wallet.execute_payment(
            amount=Decimal("15.00"),
            recipient="Audio Store",
            human_approved=True,
            auth_token="BAD_TOKEN_3",
        )
        assert res3.success is False
        assert wallet.invalid_auth_attempts == 3
        assert wallet.is_locked is True

        # Strike 4 -> Immediately rejected due to locked wallet
        res4 = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="Small Cable",
            is_agent_attempt=False,
        )
        assert res4.success is False
        assert config.REASON_WALLET_LOCKED in res4.reason

    def test_normal_human_rejection_does_not_count_as_invalid_auth(self, wallet: SafeAgentWallet):
        """
        Normal human rejection (human_approved=False) must NEVER count
        as an invalid authorization attempt or lock the wallet.
        """
        for i in range(5):
            wallet.reset_rate_limiter()
            res = wallet.execute_payment(
                amount=Decimal("15.00"),
                recipient="Item",
                human_approved=False,
            )
            assert res.success is False
            assert "rejected by human reviewer" in res.reason.lower()

        assert wallet.invalid_auth_attempts == 0
        assert wallet.is_locked is False
        assert wallet.balance == Decimal("100.00")


class TestLockedWalletEnforcement:
    """Tests that locked wallet halts all financial activity."""

    def test_locked_wallet_rejects_under_threshold_payments(self, wallet: SafeAgentWallet):
        """Locked wallet rejects even small automatic payments under $10."""
        wallet.lock(reason="Security Audit")
        assert wallet.is_locked is True

        res = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            is_agent_attempt=False,
        )
        assert res.success is False
        assert config.REASON_WALLET_LOCKED in res.reason
        assert wallet.balance == Decimal("100.00")

    def test_locked_wallet_rejects_human_approved_payments(self, wallet: SafeAgentWallet):
        """Locked wallet cannot execute payments even with valid human approval token."""
        wallet.lock(reason=config.REASON_RATE_LIMIT_EXCEEDED)
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
        assert wallet.balance == Decimal("100.00")

    def test_administrative_lock_and_unlock(self, wallet: SafeAgentWallet):
        """Administrative unlock clears lock state and resets invalid auth counter."""
        wallet.lock(reason="Manual lock")
        assert wallet.is_locked is True

        wallet.unlock()
        assert wallet.is_locked is False
        assert wallet.invalid_auth_attempts == 0

        # Normal payment now succeeds
        res = wallet.execute_payment(Decimal("4.50"), "USB-C Cable")
        assert res.success is True
        assert wallet.balance == Decimal("95.50")


class TestSecurityBypassPrevention:
    """Verifies that human approval cannot bypass any underlying wallet invariants."""

    def test_human_approval_cannot_bypass_insufficient_balance(self, wallet: SafeAgentWallet):
        """Human approval cannot execute payment when funds are insufficient."""
        res = wallet.execute_payment(
            amount=Decimal("150.00"),
            recipient="Server",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        assert res.success is False
        assert "Insufficient wallet balance" in res.reason
        assert wallet.balance == Decimal("100.00")

    def test_human_approval_cannot_bypass_spending_limit(self, wallet: SafeAgentWallet):
        """Human approval cannot exceed $80.00 lifetime spending limit."""
        # Spend $75
        wallet.execute_payment(
            Decimal("75.00"), "Batch 1", human_approved=True, auth_token=config.DEFAULT_AUTH_TOKEN
        )
        assert wallet.remaining_spending_limit == Decimal("5.00")

        # Try $10 with human approval
        res = wallet.execute_payment(
            Decimal("10.00"), "Batch 2", human_approved=True, auth_token=config.DEFAULT_AUTH_TOKEN
        )
        assert res.success is False
        assert "Lifetime spending limit exceeded" in res.reason
        assert wallet.total_spent == Decimal("75.00")

    def test_human_approval_cannot_bypass_duplicate_tx_id(self, wallet: SafeAgentWallet):
        """Human approval cannot re-execute an already processed transaction ID."""
        tx_id = "tx_approval_double_check"
        res1 = wallet.execute_payment(
            Decimal("15.00"), "Item", transaction_id=tx_id,
            human_approved=True, auth_token=config.DEFAULT_AUTH_TOKEN
        )
        assert res1.success is True

        # Second execution with same transaction ID
        res2 = wallet.execute_payment(
            Decimal("15.00"), "Item", transaction_id=tx_id,
            human_approved=True, auth_token=config.DEFAULT_AUTH_TOKEN
        )
        assert res2.success is False
        assert "Duplicate transaction ID" in res2.reason
        assert wallet.balance == Decimal("85.00")
