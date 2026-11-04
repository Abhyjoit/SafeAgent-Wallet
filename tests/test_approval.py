"""
tests/test_approval.py - Tests for Human Approval Center
SafeAgent Wallet - CommitCon Hackathon (Hour 16–18)

Covers:
- Pending request creation and retrieval.
- Valid human approval execution and single deduction.
- Human rejection (zero deduction, zero invalid auth penalties).
- Missing and invalid authorization tokens.
- Double approval and duplicate execution prevention.
- Rejection permanence (cannot approve rejected requests).
- Execution-time safety checks (insufficient balance, out of stock, price changes).
"""

from decimal import Decimal
import pytest

import config
from marketplace import Marketplace
from purchase import ApprovalCenter, ApprovalRequest
from seller_agent import SellerAgent
from wallet import SafeAgentWallet


class TestHumanApprovalWorkflow:
    """Tests ApprovalCenter lifecycle and final authorization checks."""

    def test_pending_request_creation(
        self,
        approval_center: ApprovalCenter,
        marketplace: Marketplace,
        sellers: dict,
    ):
        """Creates a pending approval request for a $15.00 product and verifies fields."""
        prod = marketplace.get_product("prod_headphones")
        assert prod is not None

        req = approval_center.create_request(
            product=prod,
            seller=sellers[prod.seller_id],
            user_query="buy headphones",
            order_id="ord_test_001",
        )

        assert req.request_id.startswith("apr_")
        assert req.amount == Decimal("15.00")
        assert req.product_name == "Bluetooth Headphones"
        assert req.status == "PENDING"
        assert req.is_processed is False
        assert approval_center.get_pending_count() == 1
        assert approval_center.get_request(req.request_id) == req

    def test_successful_approval_deducts_funds_exactly_once(
        self,
        approval_center: ApprovalCenter,
        marketplace: Marketplace,
        sellers: dict,
        wallet: SafeAgentWallet,
    ):
        """
        Approving a pending request executes payment in SafeAgentWallet,
        deducts exactly $15.00 once, and updates status to APPROVED.
        """
        prod = marketplace.get_product("prod_headphones")
        req = approval_center.create_request(
            product=prod,
            seller=sellers[prod.seller_id],
            user_query="buy headphones",
            order_id="ord_test_002",
        )

        initial_bal = wallet.balance  # $100.00
        ok, msg, wallet_res = approval_center.approve_request(
            request_id=req.request_id,
            wallet=wallet,
            marketplace=marketplace,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )

        assert ok is True
        assert wallet_res is not None
        assert wallet_res.success is True
        assert wallet.balance == initial_bal - Decimal("15.00")
        assert wallet.balance == Decimal("85.00")
        assert wallet.total_spent == Decimal("15.00")

        # Request state updated
        assert req.status == "APPROVED"
        assert req.is_processed is True
        assert approval_center.get_pending_count() == 0

    def test_rejection_deducts_zero_dollars_and_no_penalties(
        self,
        approval_center: ApprovalCenter,
        marketplace: Marketplace,
        sellers: dict,
        wallet: SafeAgentWallet,
    ):
        """
        Rejecting a request updates status to REJECTED, deducts $0.00,
        and does NOT increment the invalid authorization attempt counter.
        """
        prod = marketplace.get_product("prod_headphones")
        req = approval_center.create_request(
            product=prod,
            seller=sellers[prod.seller_id],
            user_query="buy headphones",
            order_id="ord_test_003",
        )

        initial_bal = wallet.balance
        ok, msg = approval_center.reject_request(
            request_id=req.request_id,
            wallet=wallet,
            reason="User decided against this purchase.",
        )

        assert ok is True
        assert req.status == "REJECTED"
        assert req.is_processed is True
        assert wallet.balance == initial_bal
        assert wallet.total_spent == Decimal("0.00")
        assert wallet.invalid_auth_attempts == 0
        assert wallet.is_locked is False

    def test_approval_without_authorization_blocked(
        self,
        approval_center: ApprovalCenter,
        marketplace: Marketplace,
        sellers: dict,
        wallet: SafeAgentWallet,
    ):
        """Attempting to approve without an authorization token is strictly rejected."""
        prod = marketplace.get_product("prod_headphones")
        req = approval_center.create_request(
            product=prod,
            seller=sellers[prod.seller_id],
            user_query="buy headphones",
            order_id="ord_test_004",
        )

        ok, msg, res = approval_center.approve_request(
            request_id=req.request_id,
            wallet=wallet,
            marketplace=marketplace,
            auth_token="",  # Missing token
        )

        assert ok is False
        assert "authorization missing" in msg.lower()
        assert req.status == "PENDING"
        assert wallet.balance == Decimal("100.00")

    def test_approval_with_invalid_authorization_token_fails(
        self,
        approval_center: ApprovalCenter,
        marketplace: Marketplace,
        sellers: dict,
        wallet: SafeAgentWallet,
    ):
        """Attempting to approve with a fraudulent authorization token fails and counts as invalid auth attempt."""
        prod = marketplace.get_product("prod_headphones")
        req = approval_center.create_request(
            product=prod,
            seller=sellers[prod.seller_id],
            user_query="buy headphones",
            order_id="ord_test_005",
        )

        ok, msg, res = approval_center.approve_request(
            request_id=req.request_id,
            wallet=wallet,
            marketplace=marketplace,
            auth_token="FORGED_AUTH_TOKEN_666",
        )

        assert ok is False
        assert req.status == "FAILED"
        assert wallet.invalid_auth_attempts == 1
        assert wallet.balance == Decimal("100.00")

    def test_double_approval_prevents_duplicate_payments(
        self,
        approval_center: ApprovalCenter,
        marketplace: Marketplace,
        sellers: dict,
        wallet: SafeAgentWallet,
    ):
        """
        Simulates double-click or replay of approval:
        First call succeeds and deducts $15.00.
        Second call is blocked, returning duplicate execution error with no extra deduction.
        """
        prod = marketplace.get_product("prod_headphones")
        req = approval_center.create_request(
            product=prod,
            seller=sellers[prod.seller_id],
            user_query="buy headphones",
            order_id="ord_test_006",
        )

        # 1st approval succeeds
        ok1, msg1, res1 = approval_center.approve_request(
            req.request_id, wallet, marketplace, config.DEFAULT_AUTH_TOKEN
        )
        assert ok1 is True
        assert wallet.balance == Decimal("85.00")

        # 2nd approval attempt blocked
        ok2, msg2, res2 = approval_center.approve_request(
            req.request_id, wallet, marketplace, config.DEFAULT_AUTH_TOKEN
        )
        assert ok2 is False
        assert "Duplicate execution blocked" in msg2 or "already been processed" in msg2
        assert wallet.balance == Decimal("85.00")

    def test_cannot_approve_already_rejected_request(
        self,
        approval_center: ApprovalCenter,
        marketplace: Marketplace,
        sellers: dict,
        wallet: SafeAgentWallet,
    ):
        """An already rejected request cannot subsequently be approved."""
        prod = marketplace.get_product("prod_headphones")
        req = approval_center.create_request(
            product=prod,
            seller=sellers[prod.seller_id],
            user_query="buy headphones",
            order_id="ord_test_007",
        )

        # First reject
        ok_rej, msg_rej = approval_center.reject_request(req.request_id, wallet)
        assert ok_rej is True
        assert req.status == "REJECTED"

        # Subsequent approval attempt
        ok_appr, msg_appr, res_appr = approval_center.approve_request(
            req.request_id, wallet, marketplace, config.DEFAULT_AUTH_TOKEN
        )
        assert ok_appr is False
        assert "already been processed" in msg_appr
        assert wallet.balance == Decimal("100.00")

    def test_insufficient_balance_at_execution_time(
        self,
        approval_center: ApprovalCenter,
        marketplace: Marketplace,
        sellers: dict,
        wallet: SafeAgentWallet,
    ):
        """
        If wallet balance drops below request amount between request creation
        and approval time, approval fails safely and status becomes FAILED.
        """
        prod = marketplace.get_product("prod_headphones")
        req = approval_center.create_request(
            product=prod,
            seller=sellers[prod.seller_id],
            user_query="buy headphones",
            order_id="ord_test_008",
        )

        # Drain balance artificially
        wallet._balance = Decimal("5.00")

        ok, msg, res = approval_center.approve_request(
            req.request_id, wallet, marketplace, config.DEFAULT_AUTH_TOKEN
        )
        assert ok is False
        assert "Insufficient wallet balance" in msg
        assert req.status == "FAILED"
        assert wallet.balance == Decimal("5.00")

    def test_unavailable_product_at_execution_time(
        self,
        approval_center: ApprovalCenter,
        marketplace: Marketplace,
        sellers: dict,
        wallet: SafeAgentWallet,
    ):
        """
        If product inventory reaches 0 before human clicks approve,
        approval fails and funds are protected.
        """
        prod = marketplace.get_product("prod_headphones")
        req = approval_center.create_request(
            product=prod,
            seller=sellers[prod.seller_id],
            user_query="buy headphones",
            order_id="ord_test_009",
        )

        # Product goes out of stock
        prod.availability = False

        ok, msg, res = approval_center.approve_request(
            req.request_id, wallet, marketplace, config.DEFAULT_AUTH_TOKEN
        )
        assert ok is False
        assert "out of stock" in msg.lower() or "unavailable" in msg.lower()
        assert req.status == "FAILED"
        assert wallet.balance == Decimal("100.00")
