"""Catalogue tests: seed shape, search semantics, derived stock, order totals."""

from __future__ import annotations

from app.catalog import build_catalog


def test_seed_catalog_is_small_and_internally_consistent():
    """8-12 products, every SKU stocked, every order line referencing a real SKU."""
    catalog = build_catalog()
    products = catalog.list_products(limit=50)

    assert 8 <= len(products) <= 12
    assert catalog.product_count() == len(products)

    skus = {p.sku for p in products}
    for product in products:
        assert product.name and product.description
        assert product.price > 0
        assert catalog.check_inventory(product.sku) is not None, product.sku

    order = catalog.get_order_status("ORD-1001")
    assert order is not None
    assert {line.sku for line in order.lines} <= skus

    # Lookups normalise case and whitespace, and miss cleanly.
    assert catalog.get_product("sku-001") is not None
    assert catalog.get_product(" SKU-002 ").name == "Nimbus Bluetooth Earbuds"
    assert catalog.get_product("SKU-999") is None


def test_search_matches_name_description_and_tags():
    """Every significant token must hit; tags are part of the haystack."""
    catalog = build_catalog()

    assert [p.sku for p in catalog.search_products("headphones")] == ["SKU-001"]

    assert {p.sku for p in catalog.search_products("wireless")} == {
        "SKU-001",
        "SKU-002",
        "SKU-005",
    }

    assert "SKU-010" in {p.sku for p in catalog.search_products("noise cancelling")}
    assert {p.sku for p in catalog.search_products("hub")} == {"SKU-009"}


def test_search_respects_max_price_tags_and_limit():
    catalog = build_catalog()

    cheap = catalog.search_products("", max_price=50.0, limit=20)
    assert [p.sku for p in cheap] == ["SKU-009", "SKU-005", "SKU-007"]  # price ascending

    audio = catalog.search_products("", tags=["audio"], limit=20)
    assert {p.sku for p in audio} == {"SKU-001", "SKU-002", "SKU-010", "SKU-011"}

    assert len(catalog.search_products("wireless", limit=1)) == 1
    assert catalog.search_products("quantum teleporter") == []


def test_inventory_derives_availability_and_flags_out_of_stock():
    """``available``/``in_stock`` are computed, so they cannot disagree with quantity."""
    catalog = build_catalog()

    scarce = catalog.check_inventory("SKU-012")
    assert scarce is not None
    assert (scarce.quantity, scarce.reserved, scarce.available) == (3, 2, 1)
    assert scarce.in_stock is True

    empty = catalog.check_inventory("SKU-006")
    assert empty is not None
    assert empty.available == 0
    assert empty.in_stock is False
    assert empty.restock_eta_days == 7

    assert catalog.check_inventory("SKU-999") is None


def test_order_status_totals_lines_and_unknown_orders_are_none():
    catalog = build_catalog()

    order = catalog.get_order_status("ord-1001")
    assert order is not None
    assert order.status == "shipped"
    assert order.carrier == "FedEx"
    assert order.total == 149.48  # 1 x 79.50 + 2 x 34.99
    assert order.lines[0].line_total == 79.50

    assert catalog.get_order_status("ORD-9999") is None
