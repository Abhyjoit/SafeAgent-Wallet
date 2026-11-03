"""
marketplace.py - Simulated Multi-Agent Marketplace Catalog
SafeAgent Wallet - CommitCon Hackathon

Defines the marketplace catalog and initial products:
1. USB-C Cable: $4.50 (Seller: seller_cables)
2. Wireless Mouse: $9.00 (Seller: seller_mouse)
3. Bluetooth Headphones: $15.00 (Seller: seller_audio)
"""

from dataclasses import asdict, dataclass
from decimal import Decimal
import re
from typing import Any, Dict, List, Optional


@dataclass
class Product:
    """Represents a product listed in the simulated marketplace."""

    product_id: str
    name: str
    description: str
    price: Decimal
    seller_id: str
    availability: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert product to dictionary format."""
        return {
            "product_id": self.product_id,
            "name": self.name,
            "description": self.description,
            "price": str(self.price),
            "seller_id": self.seller_id,
            "availability": self.availability,
        }


# Initial 3 marketplace products per CommitCon specifications
INITIAL_PRODUCTS: List[Product] = [
    Product(
        product_id="prod_usbc",
        name="USB-C Cable",
        description="High-speed durable 1m braided USB-C charging and data sync cable.",
        price=Decimal("4.50"),
        seller_id="seller_cables",
        availability=True,
    ),
    Product(
        product_id="prod_mouse",
        name="Wireless Mouse",
        description="Ergonomic 2.4GHz optical wireless mouse with silent click switches.",
        price=Decimal("9.00"),
        seller_id="seller_mouse",
        availability=True,
    ),
    Product(
        product_id="prod_headphones",
        name="Bluetooth Headphones",
        description="Wireless over-ear stereo headphones with active noise isolation.",
        price=Decimal("15.00"),
        seller_id="seller_audio",
        availability=True,
    ),
]


class Marketplace:
    """
    Manages marketplace product listings, catalog searches, and availability state.
    """

    def __init__(self, products: Optional[List[Product]] = None):
        self._products: Dict[str, Product] = {}
        if products is None:
            self.reset_catalog()
        else:
            for p in products:
                self.add_product(p)

    def reset_catalog(self) -> None:
        """Resets the catalog back to the initial 3 CommitCon products."""
        self._products.clear()
        for p in INITIAL_PRODUCTS:
            self._products[p.product_id] = Product(
                product_id=p.product_id,
                name=p.name,
                description=p.description,
                price=Decimal(str(p.price)),
                seller_id=p.seller_id,
                availability=p.availability,
            )

    def add_product(self, product: Product) -> None:
        """Adds or updates a product in the catalog."""
        self._products[product.product_id] = product

    def get_product(self, product_id: str) -> Optional[Product]:
        """Retrieves a product by exact product ID."""
        return self._products.get(product_id)

    def get_all_products(self) -> List[Product]:
        """Returns all products currently listed in the marketplace."""
        return list(self._products.values())

    def set_availability(self, product_id: str, available: bool) -> bool:
        """Updates product availability status."""
        prod = self._products.get(product_id)
        if prod:
            prod.availability = available
            return True
        return False

    def search_products(self, query: str) -> List[Product]:
        """
        Searches products by matching query keywords against name and description.
        Case-insensitive and handles multi-word fuzzy matching.
        """
        if not query or not query.strip():
            return []

        cleaned_query = query.strip().lower()
        # Remove common conversational command prefixes
        cleaned_query = re.sub(
            r"^(buy|purchase|order|get|find|i want|please buy|need)\s+",
            "",
            cleaned_query,
        ).strip()

        tokens = [t for t in re.split(r"[\s,\-\_]+", cleaned_query) if len(t) > 1]
        matches: List[Product] = []

        for prod in self._products.values():
            prod_name_lower = prod.name.lower()
            prod_desc_lower = prod.description.lower()

            # Exact or substring match in name
            if cleaned_query in prod_name_lower or prod_name_lower in cleaned_query:
                matches.append(prod)
                continue

            # Token overlap match
            if tokens and any(t in prod_name_lower for t in tokens):
                matches.append(prod)
                continue

            # Description match
            if tokens and any(t in prod_desc_lower for t in tokens):
                matches.append(prod)

        return matches
