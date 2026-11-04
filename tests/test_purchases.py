"""
tests/test_purchases.py - Tests for multi-agent purchase flow
SafeAgent Wallet - CommitCon Hackathon (Hour 16–18)

Covers:
- Buyer Agent search and purchase orchestration.
- Automatic execution for items <= $10.00.
- Automatic human approval queueing for items > $10.00.
- Out of stock, missing products, and seller quote price mismatches.
- Multi-agent communication trace completeness.
"""

from decimal import Decimal
import pytest

from buyer_agent import BuyerAgent
import config
from marketplace import Marketplace, Product
from purchase import ApprovalCenter, PurchaseFlowResult
from wallet import SafeAgentWallet


class TestBuyerAgentPurchaseFlow:
    """Tests BuyerAgent interactions with Marketplace, Sellers, and SafeAgentWallet."""

    def test_automatic_purchase_usbc_cable(self, buyer_agent: BuyerAgent, wallet: SafeAgentWallet):
        """
        User requests 'Buy a durable USB-C charging cable'.
        BuyerAgent finds product ($4.50), seller confirms availability,
        SafeAgentWallet executes payment without human approval.
        """
        res: PurchaseFlowResult = buyer_agent.execute_purchase("Buy a durable USB-C charging cable")

        assert res.success is True
        assert res.status == "COMPLETED"
        assert res.product is not None
        assert res.product.name == "USB-C Cable"
        assert res.product.price == Decimal("4.50")
        assert res.wallet_result is not None
        assert res.wallet_result.success is True
        assert res.wallet_result.amount == Decimal("4.50")
        assert res.wallet_result.balance == Decimal("95.50")
        assert wallet.balance == Decimal("95.50")
        assert wallet.total_spent == Decimal("4.50")

        # Verify trace
        trace_actions = [t.action for t in res.trace]
        assert "Request Ingested" in trace_actions
        assert "Product Matched" in trace_actions
        assert "Contact Seller" in trace_actions
        assert "Payment Required Response" in trace_actions
        assert "Payment Executed (SUCCESS)" in trace_actions

    def test_automatic_purchase_wireless_mouse(self, buyer_agent: BuyerAgent, wallet: SafeAgentWallet):
        """
        User requests 'I need a wireless mouse'.
        Product is $9.00 <= $10.00, executes automatically.
        """
        res: PurchaseFlowResult = buyer_agent.execute_purchase("I need a wireless mouse")

        assert res.success is True
        assert res.status == "COMPLETED"
        assert res.product.name == "Wireless Mouse"
        assert res.product.price == Decimal("9.00")
        assert wallet.balance == Decimal("91.00")
        assert wallet.total_spent == Decimal("9.00")

    def test_purchase_above_threshold_requires_approval(
        self,
        buyer_agent: BuyerAgent,
        wallet: SafeAgentWallet,
        approval_center: ApprovalCenter,
    ):
        """
        User requests 'Bluetooth Headphones' ($15.00).
        Strictly > $10.00 threshold: flagged for human approval,
        automatically enqueued in ApprovalCenter, $0 deducted.
        """
        res: PurchaseFlowResult = buyer_agent.execute_purchase("Order Bluetooth Headphones")

        assert res.success is False
        assert res.status == "AWAITING_APPROVAL"
        assert res.requires_human_approval is True
        assert res.product.name == "Bluetooth Headphones"
        assert res.product.price == Decimal("15.00")

        # Wallet funds must remain untouched
        assert wallet.balance == Decimal("100.00")
        assert wallet.total_spent == Decimal("0.00")

        # Pending approval created in ApprovalCenter
        assert approval_center.get_pending_count() == 1
        pending = approval_center.get_pending_requests()[0]
        assert pending.amount == Decimal("15.00")
        assert pending.product_name == "Bluetooth Headphones"
        assert pending.status == "PENDING"

    def test_product_not_found(self, buyer_agent: BuyerAgent, wallet: SafeAgentWallet):
        """User requests non-existent product in catalog."""
        res: PurchaseFlowResult = buyer_agent.execute_purchase("Buy Standing Desk Converter")

        assert res.success is False
        assert res.status == "NOT_FOUND"
        assert res.product is None
        assert res.wallet_result is None
        assert wallet.balance == Decimal("100.00")
        assert "not found" in res.summary_message.lower()

    def test_product_out_of_stock(
        self,
        buyer_agent: BuyerAgent,
        marketplace: Marketplace,
        wallet: SafeAgentWallet,
    ):
        """When catalog product is out of stock, seller agent rejects quote."""
        prod = marketplace.get_product("prod_usbc")
        assert prod is not None
        prod.availability = False

        res: PurchaseFlowResult = buyer_agent.execute_purchase("Buy USB-C Cable")

        assert res.success is False
        assert res.status == "UNAVAILABLE"
        assert wallet.balance == Decimal("100.00")
        assert "out of stock" in res.summary_message.lower()

    def test_seller_quote_price_mismatch(
        self,
        buyer_agent: BuyerAgent,
        marketplace: Marketplace,
        wallet: SafeAgentWallet,
    ):
        """
        If a malicious or misconfigured seller quotes a higher price than
        the catalog price, Buyer Agent halts purchase before wallet charging.
        """
        # Patch seller to return tampered price
        cable_seller = buyer_agent.sellers["seller_cables"]
        original_handle = cable_seller.handle_purchase_request

        def tampered_handle(product: Product):
            resp = original_handle(product)
            resp.price = Decimal("25.00")  # Price hiked above catalog $4.50
            return resp

        cable_seller.handle_purchase_request = tampered_handle

        res: PurchaseFlowResult = buyer_agent.execute_purchase("Buy USB-C Cable")

        assert res.success is False
        assert res.status == "PRICE_MISMATCH"
        assert "Price mismatch detected" in res.summary_message
        assert wallet.balance == Decimal("100.00")
        assert wallet.total_spent == Decimal("0.00")
