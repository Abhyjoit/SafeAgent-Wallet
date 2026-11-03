"""
purchase.py - Purchase Request Creation, Protocols, and Human Approval Center
SafeAgent Wallet - CommitCon Hackathon

Defines the message structures, seller response models, agent activity trace,
purchase pipeline, and Human Approval Center between Buyer Agent, Seller Agents,
and SafeAgentWallet.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import threading
from typing import Any, Dict, List, Optional, Tuple
import uuid

import config
from marketplace import Marketplace, Product
from wallet import PaymentResult, SafeAgentWallet


@dataclass
class PurchaseRequest:
    """Represents an incoming purchase request from a user or client."""

    user_query: str
    request_id: str = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:8]}")
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class SellerResponse:
    """Represents a seller agent's quote/invoice response to a purchase request."""

    order_id: str
    seller_id: str
    product_id: str
    product_name: str
    price: Decimal
    available: bool
    status: str  # "PAYMENT_REQUIRED", "OUT_OF_STOCK", "PRODUCT_NOT_FOUND"
    message: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "seller_id": self.seller_id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "price": str(self.price),
            "available": self.available,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class AgentTraceStep:
    """A single discrete step in the multi-agent purchase interaction trace."""

    agent: str  # e.g., "Buyer Agent", "Seller Agent", "SafeAgent Wallet"
    action: str  # e.g., "Marketplace Search", "Invoice Issued", "Security Evaluation"
    details: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%H:%M:%S")
    )


@dataclass
class PurchaseFlowResult:
    """Complete outcome of a multi-agent purchase attempt."""

    success: bool
    status: str  # "COMPLETED", "AWAITING_APPROVAL", "REJECTED", "NOT_FOUND", "UNAVAILABLE"
    product: Optional[Product]
    seller_response: Optional[SellerResponse]
    wallet_result: Optional[PaymentResult]
    trace: List[AgentTraceStep]
    summary_message: str
    requires_human_approval: bool = False
    order_id: Optional[str] = None
    approval_request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "product": self.product.to_dict() if self.product else None,
            "seller_response": self.seller_response.to_dict()
            if self.seller_response
            else None,
            "wallet_result": self.wallet_result.to_dict()
            if self.wallet_result
            else None,
            "summary_message": self.summary_message,
            "requires_human_approval": self.requires_human_approval,
            "order_id": self.order_id,
            "approval_request_id": self.approval_request_id,
            "trace": [
                {
                    "agent": t.agent,
                    "action": t.action,
                    "details": t.details,
                    "timestamp": t.timestamp,
                }
                for t in self.trace
            ],
        }


@dataclass
class ApprovalRequest:
    """Represents a purchase request queued for human review and authorization."""

    request_id: str
    product_id: str
    product_name: str
    amount: Decimal
    buyer_agent: str
    seller_id: str
    seller_name: str
    reason: str
    timestamp: str
    status: str = "PENDING"  # "PENDING", "APPROVED", "REJECTED", "FAILED"
    description: str = ""
    order_id: str = ""
    user_query: str = ""
    image_icon: str = "🎧"
    decision_timestamp: Optional[str] = None
    decision_reason: Optional[str] = None
    transaction_id: Optional[str] = None
    is_processed: bool = False  # Guards against duplicate execution

    def to_dict(self) -> Dict[str, Any]:
        """Converts request to dictionary format."""
        return {
            "request_id": self.request_id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "amount": str(self.amount),
            "description": self.description,
            "buyer_agent": self.buyer_agent,
            "seller_id": self.seller_id,
            "seller_name": self.seller_name,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "status": self.status,
            "order_id": self.order_id,
            "user_query": self.user_query,
            "image_icon": self.image_icon,
            "decision_timestamp": self.decision_timestamp,
            "decision_reason": self.decision_reason,
            "transaction_id": self.transaction_id,
            "is_processed": self.is_processed,
        }


class ApprovalCenter:
    """
    Thread-safe Human Approval Center managing pending approvals,
    verifying security criteria, and orchestrating authorization executions.
    """

    def __init__(self):
        self._requests: Dict[str, ApprovalRequest] = {}
        self._executed_request_ids: set = set()
        self._lock = threading.RLock()

    def create_request(
        self,
        product: Product,
        seller: Any,
        user_query: str,
        order_id: str = "",
        buyer_agent_name: str = "SafeAgent Buyer Bot v1.0",
        reason: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Creates and enqueues a new pending human approval request.
        """
        with self._lock:
            # Check if there is already an active pending request for this exact order_id
            if order_id:
                for req in self._requests.values():
                    if req.order_id == order_id and req.status == "PENDING":
                        return req

            req_id = f"apr_{product.seller_id[:6]}_{uuid.uuid4().hex[:8]}"
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            icon = "🎧"
            if "Cable" in product.name:
                icon = "🔌"
            elif "Mouse" in product.name:
                icon = "🖱️"

            auto_thresh = config.AUTO_PAYMENT_THRESHOLD
            default_reason = (
                f"Payment amount of ${product.price:.2f} strictly exceeds the "
                f"${auto_thresh:.2f} automatic payment threshold. Explicit human approval required."
            )

            req = ApprovalRequest(
                request_id=req_id,
                product_id=product.product_id,
                product_name=product.name,
                description=getattr(product, "description", ""),
                amount=product.price,
                buyer_agent=buyer_agent_name,
                seller_id=getattr(seller, "seller_id", str(seller)),
                seller_name=getattr(seller, "name", str(seller)),
                reason=reason or default_reason,
                timestamp=now_iso,
                status="PENDING",
                order_id=order_id,
                user_query=user_query,
                image_icon=icon,
                is_processed=False,
            )

            self._requests[req_id] = req
            return req

    def get_pending_requests(self) -> List[ApprovalRequest]:
        """Returns all currently pending approval requests in reverse chronological order."""
        with self._lock:
            pending = [r for r in self._requests.values() if r.status == "PENDING"]
            return sorted(pending, key=lambda x: x.timestamp, reverse=True)

    def get_pending_count(self) -> int:
        """Returns the number of pending approvals."""
        with self._lock:
            return sum(1 for r in self._requests.values() if r.status == "PENDING")

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Retrieves a specific request by ID."""
        with self._lock:
            return self._requests.get(request_id)

    def get_all_requests(self) -> List[ApprovalRequest]:
        """Returns all approval requests regardless of status."""
        with self._lock:
            return list(self._requests.values())

    def approve_request(
        self,
        request_id: str,
        wallet: SafeAgentWallet,
        marketplace: Optional[Marketplace] = None,
        auth_token: str = config.DEFAULT_AUTH_TOKEN,
    ) -> Tuple[bool, str, Optional[PaymentResult]]:
        """
        Authorizes and executes a pending approval request.

        Final Authorization Checks (Section 4 & 5):
        1. Request exists.
        2. Request has not already been executed (Duplicate Payment Prevention).
        3. Request is still pending (cannot approve already processed or rejected requests).
        4. Human authorization exists and token is valid.
        5. Wallet has sufficient funds.
        6. Payment amount matches original request and product catalog price.
        7. Product availability is rechecked.
        8. SafeAgentWallet re-evaluates balance, lifetime limit, lock status, rate limit.
        9. Deducts amount exactly once and updates status to APPROVED only upon successful payment.
        """
        with self._lock:
            # Check 1: Request exists
            req = self._requests.get(request_id)
            if not req:
                return False, f"Approval request '{request_id}' not found.", None

            # Check 2: Request has not already been executed
            if request_id in self._executed_request_ids:
                return (
                    False,
                    f"Duplicate execution blocked: Request '{request_id}' has already been processed and executed.",
                    None,
                )

            # Check 3: Request is still pending
            if req.is_processed or req.status != "PENDING":
                return (
                    False,
                    f"Request '{request_id}' cannot be approved because it has already been processed with status: {req.status}.",
                    None,
                )

            # Check 4: Human authorization exists
            if not auth_token or not auth_token.strip():
                return (
                    False,
                    "Human authorization missing: An authorization token is required to approve transactions.",
                    None,
                )

            # Check 5: Wallet has sufficient funds
            if wallet.balance < req.amount:
                req.is_processed = True
                req.status = "FAILED"
                req.decision_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                req.decision_reason = (
                    f"Insufficient wallet balance: available ${wallet.balance:.2f}, required ${req.amount:.2f}."
                )
                return False, f"Insufficient wallet balance: {req.decision_reason}", None

            # Check 6 & 7: Recheck product availability and price match
            if marketplace:
                prod = marketplace.get_product(req.product_id)
                if prod:
                    if not prod.availability:
                        req.is_processed = True
                        req.status = "FAILED"
                        req.decision_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                        req.decision_reason = "Product is out of stock in marketplace."
                        return (
                            False,
                            f"Cannot approve: '{req.product_name}' is currently out of stock or unavailable.",
                            None,
                        )
                    if prod.price != req.amount:
                        req.is_processed = True
                        req.status = "FAILED"
                        req.decision_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                        req.decision_reason = f"Price mismatch: request amount ${req.amount:.2f} != catalog ${prod.price:.2f}."
                        return (
                            False,
                            f"Cannot approve: Price mismatch detected against catalog.",
                            None,
                        )

            # Mark processed immediately to prevent concurrent duplicate execution
            req.is_processed = True

            # Generate unique transaction ID for this human approval execution
            tx_id = f"tx_appr_{req.order_id}_{uuid.uuid4().hex[:6]}" if req.order_id else f"tx_appr_{req.request_id}_{uuid.uuid4().hex[:6]}"

            # Forward execution to SafeAgentWallet
            wallet_res: PaymentResult = wallet.execute_payment(
                amount=req.amount,
                recipient=f"{req.product_name} ({req.seller_name})",
                transaction_id=tx_id,
                human_approved=True,
                auth_token=auth_token,
                agent_id=req.buyer_agent,
                is_agent_attempt=False,
            )

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            req.decision_timestamp = now_iso

            if wallet_res.success:
                req.status = "APPROVED"
                self._executed_request_ids.add(request_id)
                req.transaction_id = wallet_res.transaction_id
                req.decision_reason = "Authorized by human reviewer."
                return True, "Payment authorized and executed successfully.", wallet_res

            # Payment failed security verification in wallet
            req.status = "FAILED"
            req.decision_reason = wallet_res.reason
            return False, f"Payment authorization failed: {wallet_res.reason}", wallet_res

    def reject_request(
        self,
        request_id: str,
        wallet: SafeAgentWallet,
        reason: str = "Declined by human reviewer.",
    ) -> Tuple[bool, str]:
        """
        Rejects a pending purchase request.
        Does NOT deduct any money from the wallet.
        Records the rejection safely in the wallet transaction history.
        """
        with self._lock:
            req = self._requests.get(request_id)
            if not req:
                return False, f"Approval request '{request_id}' not found."

            if req.is_processed or req.status != "PENDING":
                return (
                    False,
                    f"Request '{request_id}' has already been processed with status: {req.status}.",
                )

            # Mark as processed
            req.is_processed = True
            req.status = "REJECTED"
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            req.decision_timestamp = now_iso
            req.decision_reason = reason

            # Record formal human rejection in wallet (deducts $0, does not count as invalid attempt)
            tx_id = f"tx_rej_{req.order_id}_{uuid.uuid4().hex[:6]}" if req.order_id else f"tx_rej_{req.request_id}_{uuid.uuid4().hex[:6]}"
            wallet.execute_payment(
                amount=req.amount,
                recipient=f"{req.product_name} ({req.seller_name})",
                transaction_id=tx_id,
                human_approved=False,
                agent_id=req.buyer_agent,
                is_agent_attempt=False,
            )

            return True, f"Request '{request_id}' rejected successfully. No funds were deducted."

    def clear(self) -> None:
        """Clears all approval requests (used during full wallet reset)."""
        with self._lock:
            self._requests.clear()
            self._executed_request_ids.clear()
