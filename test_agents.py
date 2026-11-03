"""
test_agents.py - Multi-Agent Marketplace & Buyer/Seller Integration Tests
SafeAgent Wallet - CommitCon Hackathon (Hours 7–10)

Tests the 10 core scenarios:
1. Buy USB-C Cable for $4.50 (Automatic payment <= $10).
2. Buy Wireless Mouse for $9.00 (Automatic payment <= $10).
3. Buy Bluetooth Headphones for $15.00 (Triggers human approval > $10).
4. Request an unavailable product (Seller reports out of stock).
5. Request an invalid product (Marketplace returns not found).
6. Insufficient balance (Payment rejected when price exceeds balance).
7. Payment approval (Valid human approval executes payment).
8. Payment rejection (Normal human rejection does not lock wallet).
9. Duplicate purchase prevention (Duplicate transaction ID rejected).
10. Wallet spending limit protection (Lifetime limit of $80 strictly enforced).
"""

from decimal import Decimal
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from buyer_agent import BuyerAgent
import config
from marketplace import Marketplace, Product
from purchase import ApprovalCenter, ApprovalRequest, PurchaseFlowResult
from seller_agent import SellerAgent, create_default_sellers
from wallet import SafeAgentWallet


class TestMultiAgentMarketplace(unittest.TestCase):

    def setUp(self):
        # Create temporary isolated test directory for transactions
        self.test_dir = tempfile.mkdtemp()
        self.test_tx_file = Path(self.test_dir) / "test_agent_tx.json"

        # Initialize fresh wallet, marketplace, sellers, and buyer agent
        self.wallet = SafeAgentWallet(
            transactions_file=self.test_tx_file,
            load_existing=False,
        )
        self.marketplace = Marketplace()
        self.sellers = create_default_sellers()
        self.buyer = BuyerAgent(
            marketplace=self.marketplace,
            wallet=self.wallet,
            sellers=self.sellers,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Scenario 1: Buy USB-C Cable for $4.50 (Automatic execution <= $10)
    # -------------------------------------------------------------------------
    def test_scenario_01_buy_usbc_cable_automatic(self):
        res: PurchaseFlowResult = self.buyer.execute_purchase("Buy USB-C Cable")

        self.assertTrue(res.success)
        self.assertEqual(res.status, "COMPLETED")
        self.assertIsNotNone(res.product)
        self.assertEqual(res.product.name, "USB-C Cable")
        self.assertEqual(res.product.price, Decimal("4.50"))
        self.assertEqual(res.wallet_result.status, config.STATUS_SUCCESS)
        self.assertEqual(self.wallet.balance, Decimal("95.50"))
        self.assertEqual(self.wallet.total_spent, Decimal("4.50"))

        # Verify trace has all agent steps
        agents_in_trace = [t.agent for t in res.trace]
        self.assertIn("Buyer Agent", agents_in_trace)
        self.assertTrue(any("Seller Agent" in a for a in agents_in_trace))
        self.assertIn("SafeAgent Wallet", agents_in_trace)

    # -------------------------------------------------------------------------
    # Scenario 2: Buy Wireless Mouse for $9.00 (Automatic execution <= $10)
    # -------------------------------------------------------------------------
    def test_scenario_02_buy_wireless_mouse_automatic(self):
        res: PurchaseFlowResult = self.buyer.execute_purchase(
            "I would like to purchase a Wireless Mouse"
        )

        self.assertTrue(res.success)
        self.assertEqual(res.status, "COMPLETED")
        self.assertEqual(res.product.name, "Wireless Mouse")
        self.assertEqual(res.product.price, Decimal("9.00"))
        self.assertEqual(self.wallet.balance, Decimal("91.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("9.00"))

    # -------------------------------------------------------------------------
    # Scenario 3: Buy Bluetooth Headphones for $15.00 (Triggers approval requirement)
    # -------------------------------------------------------------------------
    def test_scenario_03_buy_bluetooth_headphones_requires_approval(self):
        # Buying > $10 without approval must be flagged for human review
        res: PurchaseFlowResult = self.buyer.execute_purchase("Buy Bluetooth Headphones")

        self.assertFalse(res.success)
        self.assertEqual(res.status, "AWAITING_APPROVAL")
        self.assertTrue(res.requires_human_approval)
        self.assertEqual(res.product.name, "Bluetooth Headphones")
        self.assertEqual(res.product.price, Decimal("15.00"))
        self.assertIn("Human approval required", res.summary_message)
        # Balance must remain untouched
        self.assertEqual(self.wallet.balance, Decimal("100.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # Scenario 4: Request an unavailable product (Out of stock)
    # -------------------------------------------------------------------------
    def test_scenario_04_request_unavailable_product(self):
        # Mark USB-C cable as unavailable in marketplace
        self.marketplace.set_availability("prod_usbc", False)

        res: PurchaseFlowResult = self.buyer.execute_purchase("Buy USB-C Cable")

        self.assertFalse(res.success)
        self.assertEqual(res.status, "UNAVAILABLE")
        self.assertIn("out of stock", res.summary_message.lower())
        # SafeAgentWallet must never be charged
        self.assertIsNone(res.wallet_result)
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

    # -------------------------------------------------------------------------
    # Scenario 5: Request an invalid product (Not in catalog)
    # -------------------------------------------------------------------------
    def test_scenario_05_request_invalid_product(self):
        res: PurchaseFlowResult = self.buyer.execute_purchase(
            "Buy Standing Desk Converter"
        )

        self.assertFalse(res.success)
        self.assertEqual(res.status, "NOT_FOUND")
        self.assertIsNone(res.product)
        self.assertIsNone(res.wallet_result)
        self.assertIn("not found in marketplace", res.summary_message.lower())
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

    # -------------------------------------------------------------------------
    # Scenario 6: Insufficient balance
    # -------------------------------------------------------------------------
    def test_scenario_06_insufficient_balance(self):
        # Set wallet balance artificially low ($10.00) with spending limit ($80)
        self.wallet._balance = Decimal("10.00")

        # Attempt to buy $15.00 headphones with human approval
        res: PurchaseFlowResult = self.buyer.execute_purchase(
            "Buy Bluetooth Headphones",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )

        self.assertFalse(res.success)
        self.assertEqual(res.status, "REJECTED")
        self.assertIn("Insufficient wallet balance", res.summary_message)
        self.assertEqual(self.wallet.balance, Decimal("10.00"))

    # -------------------------------------------------------------------------
    # Scenario 7: Payment approval
    # -------------------------------------------------------------------------
    def test_scenario_07_payment_approval(self):
        # Buyer requests $15 headphones with valid human approval token
        res: PurchaseFlowResult = self.buyer.execute_purchase(
            "Buy Bluetooth Headphones",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )

        self.assertTrue(res.success)
        self.assertEqual(res.status, "COMPLETED")
        self.assertEqual(res.wallet_result.status, config.STATUS_SUCCESS)
        self.assertEqual(self.wallet.balance, Decimal("85.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("15.00"))

    # -------------------------------------------------------------------------
    # Scenario 8: Payment rejection
    # -------------------------------------------------------------------------
    def test_scenario_08_payment_rejection_does_not_lock_wallet(self):
        # Buyer requests $15 headphones but human rejects (human_approved=False)
        res: PurchaseFlowResult = self.buyer.execute_purchase(
            "Buy Bluetooth Headphones",
            human_approved=False,
        )

        self.assertFalse(res.success)
        self.assertEqual(res.status, "REJECTED")
        self.assertIn("rejected by human reviewer", res.summary_message.lower())
        # Crucial check: wallet invalid_auth_attempts MUST stay 0 and NOT lock!
        self.assertEqual(self.wallet.invalid_auth_attempts, 0)
        self.assertFalse(self.wallet.is_locked)
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

    # -------------------------------------------------------------------------
    # Scenario 9: Duplicate purchase prevention
    # -------------------------------------------------------------------------
    def test_scenario_09_duplicate_purchase_prevention(self):
        custom_tx_id = "test_duplicate_agent_tx_001"

        # First purchase succeeds
        res1: PurchaseFlowResult = self.buyer.execute_purchase(
            "Buy USB-C Cable",
            transaction_id=custom_tx_id,
        )
        self.assertTrue(res1.success)
        self.assertEqual(self.wallet.balance, Decimal("95.50"))

        # Second purchase with identical transaction ID must be rejected by wallet
        res2: PurchaseFlowResult = self.buyer.execute_purchase(
            "Buy USB-C Cable",
            transaction_id=custom_tx_id,
        )
        self.assertFalse(res2.success)
        self.assertEqual(res2.status, "REJECTED")
        self.assertIn("Duplicate transaction ID", res2.summary_message)
        # Balance must NOT be deducted a second time
        self.assertEqual(self.wallet.balance, Decimal("95.50"))

    # -------------------------------------------------------------------------
    # Scenario 10: Wallet spending limit protection
    # -------------------------------------------------------------------------
    def test_scenario_10_wallet_spending_limit_protection(self):
        # Spend up to the $80 lifetime limit
        # 1. Buy $15 Headphones (Spent: $15)
        self.buyer.execute_purchase(
            "Buy Bluetooth Headphones",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )

        # Reset rate limiter between calls to isolate spending limit
        self.wallet.reset_rate_limiter()

        # 2. Buy $15 Headphones again (Spent: $30)
        self.buyer.execute_purchase(
            "Buy Bluetooth Headphones",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )

        self.wallet.reset_rate_limiter()

        # 3. Directly record spending up to $78.00
        self.wallet._total_spent = Decimal("78.00")
        self.wallet._balance = Decimal("22.00")

        # Remaining spending limit is $80 - $78 = $2.00
        self.assertEqual(self.wallet.remaining_spending_limit, Decimal("2.00"))

        # Now attempt to purchase a USB-C Cable ($4.50)
        # Even though balance is $22.00, $4.50 exceeds the remaining $2.00 allowance!
        self.wallet.reset_rate_limiter()
        res_limit: PurchaseFlowResult = self.buyer.execute_purchase("Buy USB-C Cable")

        self.assertFalse(res_limit.success)
        self.assertEqual(res_limit.status, "REJECTED")
        self.assertIn("spending limit exceeded", res_limit.summary_message.lower())
        # Balance must remain untouched
        self.assertEqual(self.wallet.balance, Decimal("22.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("78.00"))


class TestHumanApprovalCenter(unittest.TestCase):
    """
    Verifies all 10 core Human Approval Center security criteria:
    1. A $15 headphone purchase appears in Pending Approvals.
    2. Approving it deducts exactly $15 once.
    3. Rejecting it deducts $0.
    4. Clicking Approve twice does not create duplicate payments.
    5. An unavailable product cannot be approved.
    6. Insufficient balance prevents payment.
    7. Spending limit prevents payment.
    8. Locked wallet prevents payment.
    9. Rate limit is enforced.
    10. Pending requests and transaction history remain consistent.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_tx_file = Path(self.test_dir) / "test_approval_tx.json"

        self.wallet = SafeAgentWallet(
            transactions_file=self.test_tx_file,
            load_existing=False,
        )
        self.marketplace = Marketplace()
        self.sellers = create_default_sellers()
        self.approval_center = ApprovalCenter()
        self.buyer = BuyerAgent(
            marketplace=self.marketplace,
            wallet=self.wallet,
            sellers=self.sellers,
            approval_center=self.approval_center,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_fifteen_dollar_purchase_appears_in_pending_approvals(self):
        self.assertEqual(self.approval_center.get_pending_count(), 0)

        res = self.buyer.execute_purchase("Buy Bluetooth Headphones")

        self.assertFalse(res.success)
        self.assertEqual(res.status, "AWAITING_APPROVAL")
        self.assertTrue(res.requires_human_approval)

        self.assertEqual(self.approval_center.get_pending_count(), 1)
        pending = self.approval_center.get_pending_requests()
        self.assertEqual(len(pending), 1)

        req: ApprovalRequest = pending[0]
        self.assertEqual(req.product_name, "Bluetooth Headphones")
        self.assertEqual(req.amount, Decimal("15.00"))
        self.assertEqual(req.seller_name, "SoundWave Audio")
        self.assertEqual(req.status, "PENDING")
        self.assertIn("exceeds the $10.00 automatic", req.reason)

    def test_02_approving_deducts_exactly_fifteen_once(self):
        self.buyer.execute_purchase("Buy Bluetooth Headphones")
        req = self.approval_center.get_pending_requests()[0]

        ok, msg, wallet_res = self.approval_center.approve_request(
            request_id=req.request_id,
            wallet=self.wallet,
            marketplace=self.marketplace,
        )

        self.assertTrue(ok)
        self.assertIsNotNone(wallet_res)
        self.assertTrue(wallet_res.success)
        self.assertEqual(self.wallet.balance, Decimal("85.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("15.00"))
        self.assertEqual(req.status, "APPROVED")
        self.assertEqual(self.approval_center.get_pending_count(), 0)

    def test_03_rejecting_deducts_zero_dollars(self):
        self.buyer.execute_purchase("Buy Bluetooth Headphones")
        req = self.approval_center.get_pending_requests()[0]

        initial_balance = self.wallet.balance
        ok, msg = self.approval_center.reject_request(
            request_id=req.request_id,
            wallet=self.wallet,
            reason="User decided not to purchase.",
        )

        self.assertTrue(ok)
        self.assertEqual(self.wallet.balance, initial_balance)
        self.assertEqual(self.wallet.total_spent, Decimal("0.00"))
        self.assertEqual(req.status, "REJECTED")
        self.assertEqual(self.approval_center.get_pending_count(), 0)
        self.assertEqual(self.wallet.invalid_auth_attempts, 0)
        self.assertFalse(self.wallet.is_locked)

    def test_04_double_approve_prevents_duplicate_payments(self):
        self.buyer.execute_purchase("Buy Bluetooth Headphones")
        req = self.approval_center.get_pending_requests()[0]

        ok1, _, _ = self.approval_center.approve_request(
            request_id=req.request_id,
            wallet=self.wallet,
            marketplace=self.marketplace,
        )
        self.assertTrue(ok1)
        self.assertEqual(self.wallet.balance, Decimal("85.00"))

        ok2, err_msg, _ = self.approval_center.approve_request(
            request_id=req.request_id,
            wallet=self.wallet,
            marketplace=self.marketplace,
        )
        self.assertFalse(ok2)
        self.assertIn("already been processed", err_msg)
        self.assertEqual(self.wallet.balance, Decimal("85.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("15.00"))

    def test_05_unavailable_product_cannot_be_approved(self):
        self.buyer.execute_purchase("Buy Bluetooth Headphones")
        req = self.approval_center.get_pending_requests()[0]

        self.marketplace.set_availability("prod_headphones", False)

        ok, err_msg, _ = self.approval_center.approve_request(
            request_id=req.request_id,
            wallet=self.wallet,
            marketplace=self.marketplace,
        )
        self.assertFalse(ok)
        self.assertIn("out of stock", err_msg.lower())
        self.assertEqual(self.wallet.balance, Decimal("100.00"))
        self.assertEqual(req.status, "FAILED")

    def test_06_insufficient_balance_prevents_payment(self):
        self.buyer.execute_purchase("Buy Bluetooth Headphones")
        req = self.approval_center.get_pending_requests()[0]

        self.wallet._balance = Decimal("5.00")

        ok, err_msg, _ = self.approval_center.approve_request(
            request_id=req.request_id,
            wallet=self.wallet,
            marketplace=self.marketplace,
        )
        self.assertFalse(ok)
        self.assertIn("Insufficient wallet balance", err_msg)
        self.assertEqual(self.wallet.balance, Decimal("5.00"))
        self.assertEqual(req.status, "FAILED")

    def test_07_spending_limit_prevents_payment(self):
        self.buyer.execute_purchase("Buy Bluetooth Headphones")
        req = self.approval_center.get_pending_requests()[0]

        self.wallet._total_spent = Decimal("75.00")
        self.wallet._balance = Decimal("25.00")

        ok, err_msg, _ = self.approval_center.approve_request(
            request_id=req.request_id,
            wallet=self.wallet,
            marketplace=self.marketplace,
        )
        self.assertFalse(ok)
        self.assertIn("spending limit exceeded", err_msg.lower())
        self.assertEqual(self.wallet.balance, Decimal("25.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("75.00"))
        self.assertEqual(req.status, "FAILED")

    def test_08_locked_wallet_prevents_payment(self):
        self.buyer.execute_purchase("Buy Bluetooth Headphones")
        req = self.approval_center.get_pending_requests()[0]

        self.wallet.lock()
        self.assertTrue(self.wallet.is_locked)

        ok, err_msg, _ = self.approval_center.approve_request(
            request_id=req.request_id,
            wallet=self.wallet,
            marketplace=self.marketplace,
        )
        self.assertFalse(ok)
        self.assertIn("locked", err_msg.lower())
        self.assertEqual(self.wallet.balance, Decimal("100.00"))
        self.assertEqual(req.status, "FAILED")

    def test_09_rate_limit_is_enforced(self):
        self.buyer.execute_purchase("Buy Bluetooth Headphones")
        req = self.approval_center.get_pending_requests()[0]

        for i in range(3):
            self.wallet.execute_payment(amount=Decimal("1.00"), recipient=f"Vendor {i}")

        ok, err_msg, _ = self.approval_center.approve_request(
            request_id=req.request_id,
            wallet=self.wallet,
            marketplace=self.marketplace,
        )
        self.assertFalse(ok)
        self.assertIn("Rate limit exceeded", err_msg)
        self.assertEqual(req.status, "FAILED")

    def test_10_consistency_between_pending_and_history(self):
        self.buyer.execute_purchase("Buy Bluetooth Headphones")
        req = self.approval_center.get_pending_requests()[0]

        self.wallet.reset_rate_limiter()
        self.approval_center.approve_request(req.request_id, self.wallet, self.marketplace)

        history = self.wallet.get_transaction_history()
        self.assertTrue(len(history) >= 1)
        latest_tx = history[-1]
        self.assertEqual(latest_tx["status"], config.STATUS_SUCCESS)
        self.assertEqual(Decimal(latest_tx["amount"]), Decimal("15.00"))
        self.assertTrue(latest_tx["requires_human_approval"])
        self.assertTrue(latest_tx["human_approved"])

        self.assertEqual(self.approval_center.get_pending_count(), 0)

    def test_11_attempt_to_approve_already_rejected_request(self):
        """Verifies an already rejected request cannot subsequently be approved."""
        self.buyer.execute_purchase("Buy Bluetooth Headphones")
        req = self.approval_center.get_pending_requests()[0]

        # 1. Reject request
        ok_rej, msg_rej = self.approval_center.reject_request(
            request_id=req.request_id,
            wallet=self.wallet,
            reason="Declined by user.",
        )
        self.assertTrue(ok_rej)
        self.assertEqual(req.status, "REJECTED")
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

        # 2. Attempt to approve rejected request -> must be rejected
        ok_appr, msg_appr, wallet_res = self.approval_center.approve_request(
            request_id=req.request_id,
            wallet=self.wallet,
            marketplace=self.marketplace,
        )
        self.assertFalse(ok_appr)
        self.assertIsNone(wallet_res)
        self.assertIn("already been processed", msg_appr.lower())
        self.assertEqual(self.wallet.balance, Decimal("100.00"))
        self.assertEqual(self.wallet.total_spent, Decimal("0.00"))

    def test_12_attempt_execution_without_human_authorization(self):
        """Verifies execution without valid human authorization is strictly rejected."""
        self.buyer.execute_purchase("Buy Bluetooth Headphones")
        req = self.approval_center.get_pending_requests()[0]

        # 1. Missing token
        ok_empty, msg_empty, _ = self.approval_center.approve_request(
            request_id=req.request_id,
            wallet=self.wallet,
            marketplace=self.marketplace,
            auth_token="",
        )
        self.assertFalse(ok_empty)
        self.assertIn("missing", msg_empty.lower())
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

        # 2. Invalid token
        ok_wrong, msg_wrong, _ = self.approval_center.approve_request(
            request_id=req.request_id,
            wallet=self.wallet,
            marketplace=self.marketplace,
            auth_token="INVALID-PIN-1234",
        )
        self.assertFalse(ok_wrong)
        self.assertIn("failed", msg_wrong.lower())
        self.assertEqual(self.wallet.invalid_auth_attempts, 1)
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

        # 3. Direct unapproved payment exceeding $10 must be blocked by wallet
        res = self.wallet.execute_payment(
            amount=Decimal("15.00"),
            recipient="Direct Vendor Bypass",
            human_approved=False,
        )
        self.assertFalse(res.success)
        self.assertEqual(self.wallet.balance, Decimal("100.00"))


if __name__ == "__main__":
    unittest.main()
