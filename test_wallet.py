"""
test_wallet.py - Comprehensive Unit Tests for SafeAgent Wallet Logic
SafeAgent Wallet - CommitCon Hackathon

Verifies all 13 core requirements and technical constraints:
1. Initial virtual wallet balance: $100.
2. Maximum lifetime spending limit: $80.
3. Automatic payment threshold: $10 (inclusive).
4. Payments above $10 must require human approval.
5. Reject payments when balance is insufficient.
6. Reject payments that exceed the remaining $80 spending allowance.
7. Rate limit: maximum 3 payment requests per rolling 60 seconds. Count rejected requests too.
8. Lock the wallet after 3 invalid human-authorization attempts.
9. A normal human rejection must not count as an invalid authorization attempt.
10. Prevent duplicate transaction execution using unique transaction IDs.
11. Record successful and rejected transactions.
12. Never allow a negative balance.
13. Human approval must not bypass any security checks.
"""

from decimal import Decimal
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest

import config
from security import AuthorizationGuard, RateLimiter, validate_amount
from transactions import Transaction, TransactionManager
from wallet import PaymentResult, SafeAgentWallet


class TestSafeAgentWallet(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory and temporary transactions file for isolated testing
        self.test_dir = tempfile.mkdtemp()
        self.temp_transactions_file = Path(self.test_dir) / "test_transactions.json"
        self.wallet = SafeAgentWallet(
            transactions_file=self.temp_transactions_file,
            load_existing=False,
        )

    def tearDown(self):
        # Clean up temporary test files
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Requirement 1: Initial virtual wallet balance: $100.
    # -------------------------------------------------------------------------
    def test_req_01_initial_balance(self):
        self.assertEqual(self.wallet.balance, Decimal("100.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("0.00"))
        self.assertEqual(self.wallet.remaining_spending_limit, Decimal("80.00"))
        self.assertFalse(self.wallet.is_locked)

    # -------------------------------------------------------------------------
    # Requirement 2 & 6: Lifetime spending limit: $80. Reject payments exceeding it.
    # -------------------------------------------------------------------------
    def test_req_02_and_06_lifetime_spending_limit(self):
        # Spend up to $80 across requests
        # Note: reset rate limiter to isolate spending limit tests
        res1 = self.wallet.execute_payment(
            amount=Decimal("10.00"), recipient="Vendor A"
        )
        self.assertTrue(res1.success)
        self.assertEqual(self.wallet.balance, Decimal("90.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("10.00"))
        self.assertEqual(self.wallet.remaining_spending_limit, Decimal("70.00"))

        res2 = self.wallet.execute_payment(
            amount=Decimal("10.00"), recipient="Vendor B"
        )
        self.assertTrue(res2.success)
        self.assertEqual(self.wallet.balance, Decimal("80.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("20.00"))
        self.assertEqual(self.wallet.remaining_spending_limit, Decimal("60.00"))

        # Advance / reset rate limiter for next batch
        self.wallet.reset_rate_limiter()

        # Approve a $60 transaction (total spent becomes $80, balance becomes $20)
        res3 = self.wallet.execute_payment(
            amount=Decimal("60.00"),
            recipient="Cloud Server",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        self.assertTrue(res3.success)
        self.assertEqual(self.wallet.balance, Decimal("20.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("80.00"))
        self.assertEqual(self.wallet.remaining_spending_limit, Decimal("0.00"))

        # Next payment of even $0.01 must be rejected due to spending limit,
        # even though balance has $20.00 remaining!
        self.wallet.reset_rate_limiter()
        res4 = self.wallet.execute_payment(
            amount=Decimal("0.01"), recipient="Extra Service"
        )
        self.assertFalse(res4.success)
        self.assertEqual(res4.status, config.STATUS_REJECTED)
        self.assertIn("Lifetime spending limit exceeded", res4.reason)
        # Balance must remain unchanged
        self.assertEqual(self.wallet.balance, Decimal("20.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("80.00"))

    # -------------------------------------------------------------------------
    # Requirement 3: Automatic payment threshold: $10 (inclusive).
    # -------------------------------------------------------------------------
    def test_req_03_automatic_threshold_inclusive(self):
        # Exactly $10.00 should execute automatically without human approval
        res = self.wallet.execute_payment(
            amount=Decimal("10.00"), recipient="API Subscription"
        )
        self.assertTrue(res.success)
        self.assertEqual(res.status, config.STATUS_SUCCESS)
        self.assertFalse(res.requires_human_approval)
        self.assertEqual(self.wallet.balance, Decimal("90.00"))

        # Amount < $10.00 should also execute automatically
        res_small = self.wallet.execute_payment(
            amount=Decimal("4.50"), recipient="Domain Name"
        )
        self.assertTrue(res_small.success)
        self.assertFalse(res_small.requires_human_approval)
        self.assertEqual(self.wallet.balance, Decimal("85.50"))

    # -------------------------------------------------------------------------
    # Requirement 4: Payments above $10 must require human approval.
    # -------------------------------------------------------------------------
    def test_req_04_payments_above_10_require_human_approval(self):
        # $10.01 without human approval must be rejected
        res = self.wallet.execute_payment(
            amount=Decimal("10.01"), recipient="Micro Service"
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, config.STATUS_REJECTED)
        self.assertTrue(res.requires_human_approval)
        self.assertIn("Human approval required", res.reason)
        # Balance must not be deducted
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

    # -------------------------------------------------------------------------
    # Requirement 5 & 12: Reject payments when balance is insufficient & never negative.
    # -------------------------------------------------------------------------
    def test_req_05_and_12_insufficient_balance_never_negative(self):
        # Attempt to spend $150 when balance is $100
        res = self.wallet.execute_payment(
            amount=Decimal("150.00"),
            recipient="Big Server",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, config.STATUS_REJECTED)
        self.assertIn("Insufficient wallet balance", res.reason)
        self.assertGreaterEqual(self.wallet.balance, Decimal("0.00"))
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

    # -------------------------------------------------------------------------
    # Requirement 7: Rate limit: max 3 payment requests per rolling 60 seconds.
    # Count rejected requests too.
    # -------------------------------------------------------------------------
    def test_req_07_rate_limit_and_count_rejected(self):
        # Request 1: Valid ($5)
        res1 = self.wallet.execute_payment(Decimal("5.00"), "Vendor 1")
        self.assertTrue(res1.success)

        # Request 2: Rejected due to amount > $10 without approval
        res2 = self.wallet.execute_payment(Decimal("15.00"), "Vendor 2")
        self.assertFalse(res2.success)
        self.assertIn("Human approval required", res2.reason)

        # Request 3: Valid ($2)
        res3 = self.wallet.execute_payment(Decimal("2.00"), "Vendor 3")
        self.assertTrue(res3.success)

        # Request 4 within 60s: Must be rate limited!
        # Because request 2 (which was rejected) ALSO counted!
        res4 = self.wallet.execute_payment(Decimal("1.00"), "Vendor 4")
        self.assertFalse(res4.success)
        self.assertIn("Rate limit exceeded", res4.reason)

    # -------------------------------------------------------------------------
    # Requirement 8: Lock wallet after 3 invalid human-authorization attempts.
    # -------------------------------------------------------------------------
    def test_req_08_lock_after_three_invalid_auth_attempts(self):
        self.assertFalse(self.wallet.is_locked)
        self.assertEqual(self.wallet.invalid_auth_attempts, 0)

        # Attempt 1: Invalid auth token
        res1 = self.wallet.execute_payment(
            amount=Decimal("15.00"),
            recipient="Vendor",
            human_approved=True,
            auth_token="WRONG_TOKEN_1",
        )
        self.assertFalse(res1.success)
        self.assertFalse(self.wallet.is_locked)
        self.assertEqual(self.wallet.invalid_auth_attempts, 1)

        # Attempt 2: Invalid auth token
        res2 = self.wallet.execute_payment(
            amount=Decimal("15.00"),
            recipient="Vendor",
            human_approved=True,
            auth_token="WRONG_TOKEN_2",
        )
        self.assertFalse(res2.success)
        self.assertFalse(self.wallet.is_locked)
        self.assertEqual(self.wallet.invalid_auth_attempts, 2)

        # Attempt 3: Invalid auth token -> Should LOCK the wallet!
        res3 = self.wallet.execute_payment(
            amount=Decimal("15.00"),
            recipient="Vendor",
            human_approved=True,
            auth_token="WRONG_TOKEN_3",
        )
        self.assertFalse(res3.success)
        self.assertTrue(self.wallet.is_locked)
        self.assertEqual(self.wallet.invalid_auth_attempts, 3)
        self.assertIn("Wallet locked", res3.reason)

        # Subsequent automatic payment must also be rejected while wallet is locked
        self.wallet.reset_rate_limiter()
        res_after_lock = self.wallet.execute_payment(
            amount=Decimal("1.00"), recipient="Vendor"
        )
        self.assertFalse(res_after_lock.success)
        self.assertIn("Wallet is locked", res_after_lock.reason)

    # -------------------------------------------------------------------------
    # Requirement 9: A normal human rejection must not count as an invalid
    # authorization attempt.
    # -------------------------------------------------------------------------
    def test_req_09_normal_human_rejection_does_not_count_as_invalid_auth(self):
        self.assertEqual(self.wallet.invalid_auth_attempts, 0)

        # Human explicitly rejects ($20 payment, human_approved=False)
        for i in range(5):
            self.wallet.reset_rate_limiter()
            res = self.wallet.execute_payment(
                amount=Decimal("20.00"),
                recipient="Vendor",
                human_approved=False,
            )
            self.assertFalse(res.success)
            self.assertEqual(res.status, config.STATUS_REJECTED)
            self.assertIn("rejected by human reviewer", res.reason)
            # Crucial assertion: invalid_auth_attempts must stay 0!
            self.assertEqual(self.wallet.invalid_auth_attempts, 0)
            self.assertFalse(self.wallet.is_locked)

    # -------------------------------------------------------------------------
    # Requirement 10: Prevent duplicate transaction execution using unique IDs.
    # -------------------------------------------------------------------------
    def test_req_10_prevent_duplicate_transaction_ids(self):
        tx_id = "test_unique_tx_001"

        # Execute transaction first time
        res1 = self.wallet.execute_payment(
            amount=Decimal("5.00"),
            recipient="Vendor",
            transaction_id=tx_id,
        )
        self.assertTrue(res1.success)
        self.assertEqual(self.wallet.balance, Decimal("95.00"))

        # Attempt to execute same transaction_id again
        res2 = self.wallet.execute_payment(
            amount=Decimal("5.00"),
            recipient="Vendor",
            transaction_id=tx_id,
        )
        self.assertFalse(res2.success)
        self.assertEqual(res2.status, config.STATUS_REJECTED)
        self.assertIn("Duplicate transaction ID", res2.reason)
        # Balance must not be deducted a second time
        self.assertEqual(self.wallet.balance, Decimal("95.00"))

    # -------------------------------------------------------------------------
    # Requirement 11: Record successful and rejected transactions.
    # -------------------------------------------------------------------------
    def test_req_11_record_successful_and_rejected_transactions(self):
        # Successful transaction
        self.wallet.execute_payment(Decimal("5.00"), "Vendor A")

        # Rejected: amount > 10 unapproved
        self.wallet.execute_payment(Decimal("25.00"), "Vendor B")

        history = self.wallet.get_transaction_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["status"], config.STATUS_SUCCESS)
        self.assertEqual(history[1]["status"], config.STATUS_REJECTED)

        # Verify JSON persistence on disk
        with open(self.temp_transactions_file, "r", encoding="utf-8") as f:
            persisted = json.load(f)
        self.assertEqual(len(persisted), 2)
        self.assertEqual(persisted[0]["status"], config.STATUS_SUCCESS)
        self.assertEqual(persisted[1]["status"], config.STATUS_REJECTED)

    # -------------------------------------------------------------------------
    # Requirement 13: Human approval must not bypass any security checks.
    # -------------------------------------------------------------------------
    def test_req_13_human_approval_does_not_bypass_security_checks(self):
        # 1. Human approved, but balance insufficient ($150)
        res_bal = self.wallet.execute_payment(
            amount=Decimal("150.00"),
            recipient="Server",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        self.assertFalse(res_bal.success)
        self.assertIn("Insufficient wallet balance", res_bal.reason)

        # 2. Human approved, but spending limit exceeded ($85)
        self.wallet.reset_rate_limiter()
        res_limit = self.wallet.execute_payment(
            amount=Decimal("85.00"),
            recipient="Server",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        self.assertFalse(res_limit.success)
        self.assertIn("spending limit exceeded", res_limit.reason.lower())

        # 3. Human approved, but duplicate transaction ID
        self.wallet.reset_rate_limiter()
        tx_id = "human_approved_tx_1"
        res_dup1 = self.wallet.execute_payment(
            amount=Decimal("15.00"),
            recipient="Server",
            transaction_id=tx_id,
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        self.assertTrue(res_dup1.success)

        res_dup2 = self.wallet.execute_payment(
            amount=Decimal("15.00"),
            recipient="Server",
            transaction_id=tx_id,
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        self.assertFalse(res_dup2.success)
        self.assertIn("Duplicate transaction ID", res_dup2.reason)

        # 4. Human approved, but rate limit exceeded
        self.wallet.reset_rate_limiter()
        for i in range(3):
            self.wallet.execute_payment(
                amount=Decimal("1.00"), recipient=f"Vendor {i}"
            )
        res_rate = self.wallet.execute_payment(
            amount=Decimal("15.00"),
            recipient="Server",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        self.assertFalse(res_rate.success)
        self.assertIn("Rate limit exceeded", res_rate.reason)

    # -------------------------------------------------------------------------
    # Technical Requirements: Amount validation & Zero/Negative rejection
    # -------------------------------------------------------------------------
    def test_amount_validation_rejects_zero_and_negative(self):
        # Zero amount
        res_zero = self.wallet.execute_payment(
            Decimal("0.00"), recipient="Free Thing"
        )
        self.assertFalse(res_zero.success)
        self.assertIn("must be positive and greater than zero", res_zero.reason)

        # Negative amount
        self.wallet.reset_rate_limiter()
        res_neg = self.wallet.execute_payment(
            Decimal("-10.00"), recipient="Hack Attempt"
        )
        self.assertFalse(res_neg.success)
        self.assertIn("must be positive and greater than zero", res_neg.reason)

        # Invalid string
        self.wallet.reset_rate_limiter()
        res_str = self.wallet.execute_payment("not_a_number", recipient="Hacker")
        self.assertFalse(res_str.success)
        self.assertIn("not a valid number", res_str.reason)

    # -------------------------------------------------------------------------
    # Concurrency Protection: Thread-safe payment execution
    # -------------------------------------------------------------------------
    def test_concurrent_payment_execution(self):
        # Simulate 10 concurrent threads attempting payments
        # Total available balance is $100.
        # Each thread attempts $10. With 10 threads, at most 8 could succeed
        # because lifetime spending limit is $80!
        # And rate limiter allows max 3 per 60s, so concurrency must not race.
        results = []
        threads = []

        # Temporarily increase rate limiter for concurrency test
        self.wallet._rate_limiter.max_requests = 20

        def worker(thread_idx: int):
            res = self.wallet.execute_payment(
                amount=Decimal("10.00"),
                recipient=f"Worker {thread_idx}",
                transaction_id=f"concurrent_tx_{thread_idx}",
            )
            results.append(res)

        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successful = [r for r in results if r.success]
        # Max lifetime spending is $80, so exactly 8 transactions must succeed ($80 total),
        # and remaining 2 must be rejected due to spending limit!
        self.assertEqual(len(successful), 8)
        self.assertEqual(self.wallet.total_spent, Decimal("80.00"))
        self.assertEqual(self.wallet.balance, Decimal("20.00"))
        self.assertGreaterEqual(self.wallet.balance, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # Persistence & Reloading: State restoration across restarts
    # -------------------------------------------------------------------------
    def test_persistence_and_wallet_reload(self):
        # Execute 2 payments
        res1 = self.wallet.execute_payment(Decimal("10.00"), "Merchant 1", transaction_id="reload_tx_1")
        self.assertTrue(res1.success)

        res2 = self.wallet.execute_payment(Decimal("5.00"), "Merchant 2", transaction_id="reload_tx_2")
        self.assertTrue(res2.success)

        # Create a new wallet instance pointing to the same transactions file
        reloaded_wallet = SafeAgentWallet(
            transactions_file=self.temp_transactions_file,
            load_existing=True,
        )

        # Check restored state
        self.assertEqual(reloaded_wallet.balance, Decimal("85.00"))
        self.assertEqual(reloaded_wallet.total_spent, Decimal("15.00"))
        self.assertEqual(reloaded_wallet.remaining_spending_limit, Decimal("65.00"))

        # Check that previous transaction IDs are still blocked from duplicate execution
        res_dup = reloaded_wallet.execute_payment(Decimal("5.00"), "Merchant 2", transaction_id="reload_tx_1")
        self.assertFalse(res_dup.success)
        self.assertIn("Duplicate transaction ID", res_dup.reason)

    # -------------------------------------------------------------------------
    # Rate Limiter Rolling Window: Simulated time expiry
    # -------------------------------------------------------------------------
    def test_rate_limiter_rolling_window_expiry(self):
        rl = RateLimiter(max_requests=3, window_seconds=60.0)

        # t=100s: 3 requests
        ok1, _ = rl.check_and_record(current_time=100.0)
        ok2, _ = rl.check_and_record(current_time=110.0)
        ok3, _ = rl.check_and_record(current_time=120.0)
        self.assertTrue(ok1 and ok2 and ok3)

        # 4th request at t=130s (< 60s from t=100s) -> Rejected!
        ok4, err4 = rl.check_and_record(current_time=130.0)
        self.assertFalse(ok4)
        self.assertIn("Rate limit exceeded", err4)

        # 5th request at t=161s (> 60s from t=100s)
        # Note: at t=161s, t=100s is outside the 60s window (161 - 60 = 101).
        # t=110, t=120, t=130 are still in window (3 requests).
        # So at t=161s, still rate-limited:
        ok5, _ = rl.check_and_record(current_time=161.0)
        self.assertFalse(ok5)

        # At t=191s (> 60s from t=130s), all previous timestamps rolled out!
        ok6, _ = rl.check_and_record(current_time=191.0)
        self.assertTrue(ok6)

    # -------------------------------------------------------------------------
    # Dict-like access on PaymentResult
    # -------------------------------------------------------------------------
    def test_payment_result_dict_access(self):
        res = self.wallet.execute_payment(Decimal("5.00"), "Subscription")
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], config.STATUS_SUCCESS)
        self.assertEqual(res["amount"], "5.00")
        self.assertEqual(res["balance"], "95.00")


if __name__ == "__main__":
    unittest.main()
