"""
tests/test_wallet.py - Comprehensive tests for SafeAgentWallet core functionality
SafeAgent Wallet - CommitCon Hackathon (Hour 16–18)

Covers:
- Automatic purchases and threshold enforcement ($10 inclusive).
- Insufficient funds validation (never allow negative balance).
- Zero, negative, and invalid amount rejections.
- Lifetime spending limit enforcement ($80 maximum).
- Duplicate transaction ID prevention.
- Thread-safe concurrent execution.
"""

from decimal import Decimal
import threading
from typing import List
import pytest

import config
from wallet import PaymentResult, SafeAgentWallet


class TestAutomaticPurchases:
    """Tests automatic purchase execution and boundary threshold controls."""

    def test_valid_automatic_purchase_under_threshold(self, wallet: SafeAgentWallet):
        """
        Valid purchase of $4.50 executes automatically without requiring human approval.
        Verifies balance deduction, total spent, and audit event recording.
        """
        res = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            agent_id="BuyerBot",
        )

        assert res.success is True
        assert res.status == config.STATUS_SUCCESS
        assert res.amount == Decimal("4.50")
        assert res.balance == Decimal("95.50")
        assert res.total_spent == Decimal("4.50")
        assert res.remaining_spending_limit == Decimal("75.50")
        assert res.requires_human_approval is False
        assert res.event_type == config.EVENT_PAYMENT_SUCCESS

        # Verify wallet state properties
        assert wallet.balance == Decimal("95.50")
        assert wallet.total_spent == Decimal("4.50")
        assert wallet.remaining_spending_limit == Decimal("75.50")

    def test_automatic_threshold_inclusive_boundary(self, wallet: SafeAgentWallet):
        """
        Automatic payment threshold is $10.00 (inclusive).
        - $9.99: auto-executes without approval.
        - $10.00: auto-executes without approval.
        - $10.01: requires human approval.
        """
        # 1. $9.99 auto-executes
        res_999 = wallet.execute_payment(Decimal("9.99"), recipient="Widget A")
        assert res_999.success is True
        assert res_999.requires_human_approval is False

        # 2. $10.00 auto-executes (inclusive threshold)
        res_1000 = wallet.execute_payment(Decimal("10.00"), recipient="Widget B")
        assert res_1000.success is True
        assert res_1000.requires_human_approval is False

        # 3. $10.01 requires human approval
        res_1001 = wallet.execute_payment(Decimal("10.01"), recipient="Widget C")
        assert res_1001.success is False
        assert res_1001.status == config.STATUS_REJECTED
        assert res_1001.requires_human_approval is True
        assert "Human approval required" in res_1001.reason

    def test_purchase_above_threshold_rejected_without_approval(self, wallet: SafeAgentWallet):
        """Payments above $10.00 are rejected if human approval has not been granted."""
        res = wallet.execute_payment(Decimal("15.00"), recipient="Bluetooth Headphones")
        assert res.success is False
        assert res.status == config.STATUS_REJECTED
        assert res.requires_human_approval is True
        assert wallet.balance == Decimal("100.00")
        assert wallet.total_spent == Decimal("0.00")


class TestInsufficientFundsAndAmountValidation:
    """Tests balance boundaries, zero, negative, and invalid payment amounts."""

    def test_purchase_exceeding_available_balance(self, wallet: SafeAgentWallet):
        """Payments exceeding wallet balance are rejected and never deduct money."""
        res = wallet.execute_payment(
            amount=Decimal("150.00"),
            recipient="High-End Workstation",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )

        assert res.success is False
        assert res.status == config.STATUS_REJECTED
        assert "Insufficient wallet balance" in res.reason
        assert wallet.balance == Decimal("100.00")
        assert wallet.total_spent == Decimal("0.00")

    def test_purchase_equal_to_exact_available_balance(self, wallet: SafeAgentWallet):
        """
        Payment equal to available balance is allowed (with valid human approval if > $10).
        Balance becomes exactly $0.00. Subsequent payment is rejected.
        """
        # Pay $80.00 (reaches spending limit and leaves $20 balance)
        res1 = wallet.execute_payment(
            amount=Decimal("80.00"),
            recipient="Bulk Components",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        assert res1.success is True
        assert res1.balance == Decimal("20.00")
        assert wallet.balance == Decimal("20.00")

    def test_wallet_balance_never_becomes_negative(self, wallet: SafeAgentWallet):
        """Balance must never drop below $0.00 under any circumstances."""
        wallet.execute_payment(Decimal("9.00"), "Item 1")  # Balance: $91.00

        # Attempt to overdraw
        res_over = wallet.execute_payment(
            amount=Decimal("95.00"),
            recipient="Luxury Item",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        assert res_over.success is False
        assert wallet.balance == Decimal("91.00")
        assert wallet.balance >= Decimal("0.00")

    def test_zero_value_purchase_rejected(self, wallet: SafeAgentWallet):
        """Payments of $0.00 are rejected as invalid."""
        res = wallet.execute_payment(Decimal("0.00"), "Free Sample")
        assert res.success is False
        assert res.status == config.STATUS_REJECTED
        assert "greater than zero" in res.reason.lower() or "invalid" in res.reason.lower()
        assert wallet.balance == Decimal("100.00")

    def test_negative_value_purchase_rejected(self, wallet: SafeAgentWallet):
        """Negative payments are strictly rejected."""
        res = wallet.execute_payment(Decimal("-10.00"), "Negative Payment")
        assert res.success is False
        assert res.status == config.STATUS_REJECTED
        assert wallet.balance == Decimal("100.00")

    @pytest.mark.parametrize("invalid_amt", ["abc", "", None, float("nan"), float("inf"), -0.01])
    def test_malformed_amounts_rejected(self, wallet: SafeAgentWallet, invalid_amt):
        """Invalid amount payloads are caught by validation and safely rejected."""
        res = wallet.execute_payment(invalid_amt, "Malformed Transaction")
        assert res.success is False
        assert res.status == config.STATUS_REJECTED
        assert wallet.balance == Decimal("100.00")


class TestSpendingLimits:
    """Tests lifetime cumulative spending limit ($80.00) enforcement."""

    def test_cumulative_spending_reaches_limit(self, wallet: SafeAgentWallet):
        """
        Multiple payments summing to exactly $80.00 succeed when rate limits are satisfied.
        Payments beyond $80.00 are rejected due to the lifetime spending limit.
        """
        # 8 payments of $10.00 spaced 65s apart (to satisfy 60s rate limit)
        for i in range(8):
            sim_time = 1000.0 + (i * 65.0)
            res = wallet.execute_payment(
                amount=Decimal("10.00"),
                recipient=f"Installment {i+1}",
                current_time=sim_time,
            )
            assert res.success is True

        assert wallet.total_spent == Decimal("80.00")
        assert wallet.remaining_spending_limit == Decimal("0.00")
        assert wallet.balance == Decimal("20.00")

        # 9th payment attempted, even for $1.00: rejected due to lifetime limit
        res_exceed = wallet.execute_payment(
            amount=Decimal("1.00"),
            recipient="Post-Limit Item",
            current_time=1000.0 + (9 * 65.0),
        )
        assert res_exceed.success is False
        assert "Lifetime spending limit exceeded" in res_exceed.reason
        assert wallet.balance == Decimal("20.00")
        assert wallet.total_spent == Decimal("80.00")

    def test_human_approval_cannot_bypass_lifetime_limit(self, wallet: SafeAgentWallet):
        """Human approval cannot bypass the $80.00 lifetime spending limit."""
        wallet.execute_payment(
            Decimal("75.00"),
            "Big Item",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        assert wallet.total_spent == Decimal("75.00")
        assert wallet.remaining_spending_limit == Decimal("5.00")

        # Attempt $10.00 with human approval -> exceeds remaining $5.00 allowance
        res = wallet.execute_payment(
            amount=Decimal("10.00"),
            recipient="Extra Item",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        assert res.success is False
        assert "Lifetime spending limit exceeded" in res.reason
        assert wallet.total_spent == Decimal("75.00")


class TestDuplicatePaymentPrevention:
    """Tests duplicate transaction prevention."""

    def test_duplicate_transaction_id_rejected(self, wallet: SafeAgentWallet):
        """A transaction ID cannot be processed more than once."""
        res1 = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            transaction_id="tx_unique_abc_123",
        )
        assert res1.success is True
        assert wallet.balance == Decimal("95.50")

        # Second attempt with identical transaction ID
        res2 = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            transaction_id="tx_unique_abc_123",
        )
        assert res2.success is False
        assert res2.status == config.STATUS_REJECTED
        assert "Duplicate transaction ID" in res2.reason
        # Money was only deducted once
        assert wallet.balance == Decimal("95.50")


class TestConcurrentWalletExecution:
    """Tests multithreaded concurrent payment executions."""

    def test_concurrent_payments_thread_safety(self, wallet: SafeAgentWallet):
        """
        Multiple threads submitting payments concurrently do not corrupt wallet state.
        With max_requests increased for concurrency test, exactly 8 threads succeed
        to reach the $80.00 lifetime limit, and remaining 2 are rejected.
        """
        results: List[PaymentResult] = []
        lock = threading.Lock()
        wallet._rate_limiter.max_requests = 20

        def submit_tx(idx: int):
            res = wallet.execute_payment(
                amount=Decimal("10.00"),
                recipient=f"Worker {idx}",
                transaction_id=f"concurrent_test_tx_{idx}",
            )
            with lock:
                results.append(res)

        threads = [threading.Thread(target=submit_tx, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        successful = [r for r in results if r.success]
        assert len(successful) == 8
        # 8 * $10.00 = $80.00 deducted exactly, wallet balance is $20.00
        assert wallet.balance == Decimal("20.00")
        assert wallet.total_spent == Decimal("80.00")
