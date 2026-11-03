"""
purchase.py - Purchase Request Creation and Flow Protocols
SafeAgent Wallet - CommitCon Hackathon

Defines the message structures, seller response models, agent activity trace,
and purchase pipeline between Buyer Agent, Seller Agents, and SafeAgentWallet.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid

from marketplace import Product
from wallet import PaymentResult


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
