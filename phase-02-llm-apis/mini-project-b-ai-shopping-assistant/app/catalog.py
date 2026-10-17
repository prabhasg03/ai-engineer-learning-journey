"""Deterministic seed catalogue: products, inventory, orders.

This is the *system of record* the assistant is allowed to talk about.  It is
pure Python with no IO and no randomness, which is deliberate:

* a shopper-facing assistant must never invent prices or stock levels, so the
  only source of truth is a lookup in here;
* tests can assert exact answers because the data never changes between runs.

The ``Catalog`` class is intentionally tiny - its job is to be obviously
correct, not to be a database.  In a real service these three dictionaries
would be three tables (or three HTTP calls) and this class would be the
repository that hides which one it is.
"""

from __future__ import annotations

from .models import Inventory, OrderLine, OrderStatus, Product

__all__ = ["Catalog", "build_catalog"]


# --------------------------------------------------------------------------- #
# Seed data
# --------------------------------------------------------------------------- #

#: ``sku -> (name, description, price, tags)``
_PRODUCTS: dict[str, tuple[str, str, float, list[str]]] = {
    "SKU-001": (
        "Aurora Wireless Headphones",
        "Over-ear Bluetooth headphones with 40 h battery life and active noise cancelling.",
        129.99,
        ["audio", "headphones", "wireless", "over-ear"],
    ),
    "SKU-002": (
        "Nimbus Bluetooth Earbuds",
        "Compact true-wireless earbuds with a charging case and IPX5 sweat resistance.",
        79.50,
        ["audio", "earbuds", "wireless", "portable"],
    ),
    "SKU-003": (
        "Vertex 27-inch 4K Monitor",
        "27-inch 4K IPS display with USB-C power delivery and a height-adjustable stand.",
        349.00,
        ["displays", "monitor", "4k", "usb-c"],
    ),
    "SKU-004": (
        "Compact Mechanical Keyboard",
        "Tenkeyless mechanical keyboard with hot-swappable switches and a detachable cable.",
        89.00,
        ["keyboard", "mechanical", "compact", "desk"],
    ),
    "SKU-005": (
        "Precision Wireless Mouse",
        "Ergonomic wireless mouse with an adjustable 16000-DPI sensor and silent switches.",
        39.95,
        ["mouse", "wireless", "ergonomic", "desk"],
    ),
    "SKU-006": (
        "Trailblazer Laptop Backpack",
        "28 L water-resistant backpack with a padded 16-inch laptop sleeve.",
        64.00,
        ["bag", "backpack", "travel", "commute"],
    ),
    "SKU-007": (
        "Volt 20000mAh Power Bank",
        "20 000 mAh power bank with 65 W USB-C output that charges a laptop.",
        45.50,
        ["power", "charger", "portable", "usb-c"],
    ),
    "SKU-008": (
        "Lumen Smart Desk Lamp",
        "Dimmable desk lamp with adjustable colour temperature and a USB charging port.",
        58.75,
        ["lamp", "lighting", "desk", "smart"],
    ),
    "SKU-009": (
        "Echo USB-C Hub 7-in-1",
        "Seven-port USB-C hub with HDMI 4K, card readers, and 100 W pass-through charging.",
        34.99,
        ["hub", "usb-c", "adapter", "desk"],
    ),
    "SKU-010": (
        "Stratus Noise-Cancelling Headset",
        "Wired headset with a boom microphone and passive noise isolation for calls.",
        199.00,
        ["audio", "headset", "noise-cancelling", "business"],
    ),
    "SKU-011": (
        "Cascade Bluetooth Speaker",
        "Portable waterproof speaker with 12 h playback and stereo pairing.",
        74.25,
        ["audio", "speaker", "portable", "waterproof"],
    ),
    "SKU-012": (
        "Meridian Ergonomic Office Chair",
        "Adjustable lumbar support, 4D armrests, and a breathable mesh back.",
        429.00,
        ["furniture", "chair", "office", "ergonomic"],
    ),
}

#: ``sku -> (quantity, reserved, warehouse, restock_eta_days)``
_INVENTORY: dict[str, tuple[int, int, str, int | None]] = {
    "SKU-001": (12, 2, "WH-EAST", None),
    "SKU-002": (40, 5, "WH-EAST", None),
    "SKU-003": (6, 1, "WH-WEST", None),
    "SKU-004": (25, 0, "WH-EAST", None),
    "SKU-005": (60, 8, "WH-WEST", None),
    "SKU-006": (0, 0, "WH-EAST", 7),      # out of stock -> restock in a week
    "SKU-007": (18, 3, "WH-WEST", None),
    "SKU-008": (9, 1, "WH-EAST", None),
    "SKU-009": (33, 4, "WH-WEST", None),
    "SKU-010": (4, 1, "WH-EAST", None),
    "SKU-011": (21, 2, "WH-WEST", None),
    "SKU-012": (3, 2, "WH-EAST", 21),     # only one unit genuinely available
}

#: ``order_id -> (status, placed_at, eta, carrier, [(sku, quantity), ...])``
_ORDERS: dict[str, tuple[str, str, str | None, str | None, list[tuple[str, int]]]] = {
    "ORD-1001": (
        "shipped",
        "2026-10-12",
        "2026-10-20",
        "FedEx",
        [("SKU-002", 1), ("SKU-009", 2)],
    ),
    "ORD-1002": (
        "processing",
        "2026-10-15",
        "2026-10-24",
        None,
        [("SKU-003", 1)],
    ),
    "ORD-1003": (
        "delivered",
        "2026-10-02",
        None,
        "UPS",
        [("SKU-001", 1), ("SKU-005", 1)],
    ),
    "ORD-1004": (
        "cancelled",
        "2026-10-05",
        None,
        None,
        [("SKU-012", 1)],
    ),
    "ORD-1005": (
        "shipped",
        "2026-10-11",
        "2026-10-18",
        "DHL",
        [("SKU-007", 2)],
    ),
}


# --------------------------------------------------------------------------- #
# The catalogue
# --------------------------------------------------------------------------- #


class Catalog:
    """Read-only view over the seed data plus the search used by the agent."""

    def __init__(
        self,
        products: dict[str, Product] | None = None,
        inventory: dict[str, Inventory] | None = None,
        orders: dict[str, OrderStatus] | None = None,
    ) -> None:
        self._products = products if products is not None else _seed_products()
        self._inventory = inventory if inventory is not None else _seed_inventory()
        self._orders = orders if orders is not None else _seed_orders()

    # -- products ---------------------------------------------------------- #

    def list_products(
        self,
        query: str | None = None,
        max_price: float | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[Product]:
        """Shared entry point for ``GET /products`` and the search tool."""
        items = list(self._products.values())
        if query:
            items = [p for p in items if _matches(p, query)]
        if max_price is not None:
            items = [p for p in items if p.price <= max_price]
        if tags:
            wanted = {t.lower() for t in tags}
            items = [p for p in items if wanted & {t.lower() for t in p.tags}]
        items.sort(key=lambda p: (p.price, p.sku))
        return items[: max(0, limit)]

    def search_products(
        self,
        query: str,
        max_price: float | None = None,
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[Product]:
        """Free-text product search used by the ``search_products`` tool.

        Matching is deliberately simple: every significant query token must
        appear somewhere in the name, description or tags.  A real shop would
        use BM25 or an embedding index (phase 3), but the *shape* is the same -
        retrieve a ranked shortlist, then let the model talk about it.
        """
        return self.list_products(query=query, max_price=max_price, tags=tags, limit=limit)

    def get_product(self, sku: str) -> Product | None:
        """Look up one product by SKU (``None`` when unknown)."""
        return self._products.get(sku.strip().upper())

    def product_count(self) -> int:
        return len(self._products)

    # -- inventory --------------------------------------------------------- #

    def check_inventory(self, sku: str) -> Inventory | None:
        """Stock for one SKU (``None`` when the SKU is not stocked)."""
        return self._inventory.get(sku.strip().upper())

    # -- orders ------------------------------------------------------------ #

    def get_order_status(self, order_id: str) -> OrderStatus | None:
        """Order tracking for one order id (``None`` when unknown)."""
        return self._orders.get(order_id.strip().upper())


# --------------------------------------------------------------------------- #
# Search helper
# --------------------------------------------------------------------------- #

#: Words that carry no retrieval signal in a shopping query.
_STOPWORDS = frozenset(
    """
    a an the do does did you your i me my we our is are was were be been
    have has had any some of for to with and or in on at from
    find show me give list search look looking want need buy get please
    product products item items thing things that this these those
    under below less than cheaper about around max maximum up over
    stock stocks inventory available availability in-stock
    """.split()
)


def _tokens(text: str) -> list[str]:
    """Lower-case alphanumeric tokens with stopwords and single letters removed.

    Single characters are dropped because substring matching would otherwise let
    a token like the ``c`` in ``usb-c`` match almost any product.
    """
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text.lower())
    return [tok for tok in cleaned.split() if len(tok) > 1 and tok not in _STOPWORDS]


def _matches(product: Product, query: str) -> bool:
    """True when *every* significant query token hits the product's haystack."""
    tokens = _tokens(query)
    if not tokens:
        return True
    haystack = " ".join([product.name, product.description, " ".join(product.tags)]).lower()
    return all(tok in haystack for tok in tokens)


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #


def _seed_products() -> dict[str, Product]:
    return {
        sku: Product(sku=sku, name=name, description=desc, price=price, tags=list(tags))
        for sku, (name, desc, price, tags) in _PRODUCTS.items()
    }


def _seed_inventory() -> dict[str, Inventory]:
    return {
        sku: Inventory(sku=sku, quantity=qty, reserved=reserved, warehouse=wh, restock_eta_days=eta)
        for sku, (qty, reserved, wh, eta) in _INVENTORY.items()
    }


def _seed_orders() -> dict[str, OrderStatus]:
    products = _seed_products()
    orders: dict[str, OrderStatus] = {}
    for order_id, (status, placed_at, eta, carrier, lines) in _ORDERS.items():
        orders[order_id] = OrderStatus(
            order_id=order_id,
            status=status,  # type: ignore[arg-type]
            placed_at=placed_at,
            eta=eta,
            carrier=carrier,
            lines=[
                OrderLine(
                    sku=sku,
                    name=products[sku].name,
                    quantity=qty,
                    unit_price=products[sku].price,
                )
                for sku, qty in lines
            ],
        )
    return orders


def build_catalog() -> Catalog:
    """Return a freshly seeded catalogue (a new instance every call).

    Tests build a fresh one per test so no test can mutate state another test
    depends on.  The running app builds one and shares it through a dependency.
    """
    return Catalog()
