"""
seller_agent.py - Seller Agent Implementation
SafeAgent Wallet - CommitCon Hackathon

Requirements:
1. Implement seller agent functionality.
2. Each seller represents a marketplace product.
3. Sellers respond to buyer purchase inquiries.
4. Return product info, price, availability, and a payment-required response.
5. Sellers must NEVER directly access or modify the wallet balance.
"""

from decimal import Decimal
from typing import Dict, Optional
import uuid

from marketplace import Marketplace, Product
from purchase import SellerResponse


class SellerAgent:
    """
    Represents an independent merchant/seller agent in the marketplace.

    Important Security Constraint:
    A SellerAgent has NO reference to SafeAgentWallet and cannot access or modify balances.
    It purely quotes prices, verifies inventory, and issues payment invoices.
    """

    def __init__(self, seller_id: str, name: str, product_id: str):
        self.seller_id = seller_id
        self.name = name
        self.product_id = product_id

    def handle_purchase_request(self, product: Product) -> SellerResponse:
        """
        Processes a purchase inquiry for this seller's product.
        Returns a SellerResponse detailing availability and payment requirement.
        """
        # Validate that the seller actually offers this product
        if product.seller_id != self.seller_id or product.product_id != self.product_id:
            return SellerResponse(
                order_id=f"err_{uuid.uuid4().hex[:6]}",
                seller_id=self.seller_id,
                product_id=product.product_id,
                product_name=product.name,
                price=product.price,
                available=False,
                status="PRODUCT_MISMATCH",
                message=f"Seller '{self.name}' does not stock product ID '{product.product_id}'.",
            )

        # Check inventory availability
        if not product.availability:
            return SellerResponse(
                order_id=f"unavail_{uuid.uuid4().hex[:6]}",
                seller_id=self.seller_id,
                product_id=product.product_id,
                product_name=product.name,
                price=product.price,
                available=False,
                status="OUT_OF_STOCK",
                message=f"Product '{product.name}' is currently out of stock with seller {self.name}.",
            )

        # Generate payment-required invoice
        order_id = f"ord_{self.seller_id[:6]}_{uuid.uuid4().hex[:6]}"
        return SellerResponse(
            order_id=order_id,
            seller_id=self.seller_id,
            product_id=product.product_id,
            product_name=product.name,
            price=product.price,
            available=True,
            status="PAYMENT_REQUIRED",
            message=(
                f"Invoice #{order_id} issued by {self.name}. Payment of "
                f"${product.price:.2f} is required to fulfill order."
            ),
        )


def create_default_sellers() -> Dict[str, SellerAgent]:
    """
    Factory function creating the three dedicated seller agents:
    1. CableCraft Direct (USB-C Cable)
    2. ErgoGear Tech (Wireless Mouse)
    3. SoundWave Audio (Bluetooth Headphones)
    """
    return {
        "seller_cables": SellerAgent(
            seller_id="seller_cables",
            name="CableCraft Direct",
            product_id="prod_usbc",
        ),
        "seller_mouse": SellerAgent(
            seller_id="seller_mouse",
            name="ErgoGear Tech",
            product_id="prod_mouse",
        ),
        "seller_audio": SellerAgent(
            seller_id="seller_audio",
            name="SoundWave Audio",
            product_id="prod_headphones",
        ),
    }
