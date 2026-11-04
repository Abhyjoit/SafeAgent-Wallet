"""
buyer_agent.py - Buyer Agent Implementation
SafeAgent Wallet - CommitCon Hackathon

Requirements:
1. Accept user purchase requests.
2. Search the marketplace for matching products.
3. Identify the correct seller.
4. Send a purchase request to that seller.
5. Receive the seller's response.
6. Pass the payment request to SafeAgentWallet.
7. Display / return the payment result and agent communication trace.
"""

from decimal import Decimal
import re
from typing import Any, Dict, List, Optional
import uuid

import config
from marketplace import Marketplace, Product
from purchase import (
    AgentTraceStep,
    ApprovalCenter,
    ApprovalRequest,
    PurchaseFlowResult,
    SellerResponse,
)
from seller_agent import SellerAgent, create_default_sellers
from wallet import PaymentResult, SafeAgentWallet


class BuyerAgent:
    """
    Autonomous Buyer Agent acting on behalf of the user to search, negotiate,
    and initiate purchases through the marketplace and SafeAgentWallet.

    Security Guarantee:
    All payments initiated by the BuyerAgent MUST flow strictly through
    SafeAgentWallet and are subject to all balance, spending limit, threshold,
    rate limit, and human authorization checks.
    """

    def __init__(
        self,
        marketplace: Optional[Marketplace] = None,
        wallet: Optional[SafeAgentWallet] = None,
        sellers: Optional[Dict[str, SellerAgent]] = None,
        approval_center: Optional[Any] = None,
    ):
        self.marketplace = marketplace or Marketplace()
        self.wallet = wallet or SafeAgentWallet(load_existing=True)
        self.sellers = sellers or create_default_sellers()
        self.approval_center = approval_center

    def find_product(self, query: str) -> Optional[Product]:
        """Searches the marketplace for a product matching the query."""
        results = self.marketplace.search_products(query)
        return results[0] if results else None

    def execute_purchase(
        self,
        user_request: str,
        human_approved: Optional[bool] = None,
        auth_token: Optional[str] = config.DEFAULT_AUTH_TOKEN,
        transaction_id: Optional[str] = None,
    ) -> PurchaseFlowResult:
        """
        Orchestrates the complete multi-agent purchase flow:
        1. Ingests user request and parses search intent.
        2. Searches the marketplace catalog.
        3. Identifies the responsible seller agent.
        4. Transmits purchase request to seller agent.
        5. Receives seller response (availability & payment requirement).
        6. Submits payment to SafeAgentWallet with full security controls.
        7. Returns comprehensive PurchaseFlowResult and agent trace.
        """
        trace: List[AgentTraceStep] = []

        # -----------------------------------------------------------------
        # STEP 1: Ingest User Request
        # -----------------------------------------------------------------
        trace.append(
            AgentTraceStep(
                agent="Buyer Agent",
                action="Request Ingested",
                details=f"Received user purchase directive: '{user_request}'",
            )
        )

        # -----------------------------------------------------------------
        # STEP 2: Marketplace Search
        # -----------------------------------------------------------------
        product = self.find_product(user_request)

        if not product:
            trace.append(
                AgentTraceStep(
                    agent="Buyer Agent",
                    action="Search Failed",
                    details=f"No matching product found in marketplace for query: '{user_request}'.",
                )
            )
            return PurchaseFlowResult(
                success=False,
                status="NOT_FOUND",
                product=None,
                seller_response=None,
                wallet_result=None,
                trace=trace,
                summary_message=f"Product not found in marketplace for request '{user_request}'.",
                requires_human_approval=False,
            )

        trace.append(
            AgentTraceStep(
                agent="Buyer Agent",
                action="Product Matched",
                details=(
                    f"Matched product: '{product.name}' (ID: {product.product_id}) | "
                    f"Catalog Price: ${product.price:.2f} | Seller ID: {product.seller_id}"
                ),
            )
        )

        # -----------------------------------------------------------------
        # STEP 3: Identify & Contact Seller Agent
        # -----------------------------------------------------------------
        seller = self.sellers.get(product.seller_id)
        if not seller:
            trace.append(
                AgentTraceStep(
                    agent="Buyer Agent",
                    action="Seller Error",
                    details=f"No active seller agent registered for seller ID: '{product.seller_id}'.",
                )
            )
            return PurchaseFlowResult(
                success=False,
                status="SELLER_ERROR",
                product=product,
                seller_response=None,
                wallet_result=None,
                trace=trace,
                summary_message=f"Seller '{product.seller_id}' is not reachable.",
                requires_human_approval=False,
            )

        trace.append(
            AgentTraceStep(
                agent="Buyer Agent",
                action="Contact Seller",
                details=f"Transmitting purchase request to seller agent '{seller.name}' ({seller.seller_id}).",
            )
        )

        # -----------------------------------------------------------------
        # STEP 4: Seller Agent Evaluates Request & Responds
        # -----------------------------------------------------------------
        seller_response: SellerResponse = seller.handle_purchase_request(product)

        if not seller_response.available or seller_response.status != "PAYMENT_REQUIRED":
            trace.append(
                AgentTraceStep(
                    agent=f"Seller Agent ({seller.name})",
                    action="Inventory Check: Unavailable",
                    details=seller_response.message,
                )
            )
            return PurchaseFlowResult(
                success=False,
                status="UNAVAILABLE",
                product=product,
                seller_response=seller_response,
                wallet_result=None,
                trace=trace,
                summary_message=seller_response.message,
                requires_human_approval=False,
            )

        trace.append(
            AgentTraceStep(
                agent=f"Seller Agent ({seller.name})",
                action="Payment Required Response",
                details=(
                    f"Order #{seller_response.order_id} generated. "
                    f"Payment of ${seller_response.price:.2f} required for {seller_response.product_name}."
                ),
            )
        )

        # -----------------------------------------------------------------
        # STEP 5: Buyer Agent Validates Seller Quote
        # -----------------------------------------------------------------
        if seller_response.price != product.price:
            trace.append(
                AgentTraceStep(
                    agent="Buyer Agent",
                    action="Price Mismatch Error",
                    details=(
                        f"Seller price ${seller_response.price:.2f} does not match "
                        f"catalog price ${product.price:.2f}. Aborting purchase."
                    ),
                )
            )
            return PurchaseFlowResult(
                success=False,
                status="PRICE_MISMATCH",
                product=product,
                seller_response=seller_response,
                wallet_result=None,
                trace=trace,
                summary_message="Price mismatch detected between catalog and seller quote.",
                requires_human_approval=False,
            )

        # -----------------------------------------------------------------
        # STEP 6: Forward Payment Request to SafeAgentWallet
        # (CRITICAL: Buyer Agent never bypasses wallet security!)
        # -----------------------------------------------------------------
        trace.append(
            AgentTraceStep(
                agent="Buyer Agent",
                action="Submit to Wallet",
                details=(
                    f"Forwarding payment of ${seller_response.price:.2f} to SafeAgentWallet "
                    f"for recipient '{seller_response.product_name} ({seller.name})'."
                ),
            )
        )

        tx_id = transaction_id or f"tx_{seller_response.order_id}_{uuid.uuid4().hex[:6]}"
        wallet_res: PaymentResult = self.wallet.execute_payment(
            amount=seller_response.price,
            recipient=f"{seller_response.product_name} ({seller.name})",
            transaction_id=tx_id,
            human_approved=human_approved,
            auth_token=auth_token,
            agent_id="SafeAgent Buyer Bot v1.0",
            request_id=seller_response.order_id,
        )

        # -----------------------------------------------------------------
        # STEP 7: Process SafeAgentWallet Security Decision
        # -----------------------------------------------------------------
        if wallet_res.success:
            trace.append(
                AgentTraceStep(
                    agent="SafeAgent Wallet",
                    action="Payment Executed (SUCCESS)",
                    details=(
                        f"Transaction {wallet_res.transaction_id} approved and executed. "
                        f"Amount: ${wallet_res.amount:.2f} | Remaining Balance: ${wallet_res.balance:.2f} | "
                        f"Spent: ${wallet_res.total_spent:.2f}"
                    ),
                )
            )
            return PurchaseFlowResult(
                success=True,
                status="COMPLETED",
                product=product,
                seller_response=seller_response,
                wallet_result=wallet_res,
                trace=trace,
                summary_message=(
                    f"Purchase successful! Bought {product.name} for ${product.price:.2f}. "
                    f"Remaining wallet balance: ${wallet_res.balance:.2f}."
                ),
                requires_human_approval=False,
                order_id=seller_response.order_id,
            )

        # Payment was rejected or flagged by wallet
        if wallet_res.requires_human_approval and human_approved is None:
            trace.append(
                AgentTraceStep(
                    agent="SafeAgent Wallet",
                    action="Security Intercept: Approval Required",
                    details=(
                        f"Payment of ${wallet_res.amount:.2f} exceeds automatic threshold of $10.00. "
                        f"Awaiting human approval before execution."
                    ),
                )
            )
            appr_id = None
            if self.approval_center:
                appr_req = self.approval_center.create_request(
                    product=product,
                    seller=seller,
                    user_query=user_request,
                    order_id=seller_response.order_id,
                )
                appr_id = appr_req.request_id

            return PurchaseFlowResult(
                success=False,
                status="AWAITING_APPROVAL",
                product=product,
                seller_response=seller_response,
                wallet_result=wallet_res,
                trace=trace,
                summary_message=(
                    f"Human approval required: payment of ${wallet_res.amount:.2f} for {product.name} "
                    f"exceeds the $10.00 automatic threshold."
                ),
                requires_human_approval=True,
                order_id=seller_response.order_id,
                approval_request_id=appr_id,
            )

        # Blocked by runaway agent rate-limit or locked wallet
        if wallet_res.status == config.STATUS_BLOCKED:
            trace.append(
                AgentTraceStep(
                    agent="SafeAgent Wallet",
                    action="Security Intercept: Payment Blocked",
                    details=f"Payment blocked by security policy: {wallet_res.reason}",
                )
            )
            return PurchaseFlowResult(
                success=False,
                status="BLOCKED",
                product=product,
                seller_response=seller_response,
                wallet_result=wallet_res,
                trace=trace,
                summary_message=wallet_res.reason,
                requires_human_approval=False,
                order_id=seller_response.order_id,
            )

        # Other wallet rejection (insufficient balance, limit exceeded, locked, invalid auth, etc.)
        trace.append(
            AgentTraceStep(
                agent="SafeAgent Wallet",
                action="Payment Rejected",
                details=f"Payment rejected by wallet: {wallet_res.reason}",
            )
        )
        return PurchaseFlowResult(
            success=False,
            status="REJECTED",
            product=product,
            seller_response=seller_response,
            wallet_result=wallet_res,
            trace=trace,
            summary_message=wallet_res.reason,
            requires_human_approval=wallet_res.requires_human_approval,
            order_id=seller_response.order_id,
        )

    def buy(
        self,
        user_request: str,
        human_approved: Optional[bool] = None,
        auth_token: Optional[str] = config.DEFAULT_AUTH_TOKEN,
        transaction_id: Optional[str] = None,
    ) -> PurchaseFlowResult:
        """Convenience alias for execute_purchase."""
        return self.execute_purchase(
            user_request=user_request,
            human_approved=human_approved,
            auth_token=auth_token,
            transaction_id=transaction_id,
        )
