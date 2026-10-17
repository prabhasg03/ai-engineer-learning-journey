"""Tool tests: schemas, happy paths, and the "never raises" trust boundary."""

from __future__ import annotations

import json

from app.tools import ARG_MODELS, HANDLERS, TOOL_NAMES, TOOL_SCHEMAS, execute_tool, tool_schema


def test_tool_schemas_match_the_typed_argument_models():
    """The three required tools, and no drift between schema and validator."""
    assert [schema["function"]["name"] for schema in TOOL_SCHEMAS] == list(TOOL_NAMES)
    assert set(TOOL_NAMES) == {"search_products", "check_inventory", "get_order_status"}
    assert set(HANDLERS) == set(ARG_MODELS) == set(TOOL_NAMES)

    for name in TOOL_NAMES:
        function = tool_schema(name)["function"]
        parameters = function["parameters"]
        assert function["description"]
        assert parameters["type"] == "object"
        assert parameters["additionalProperties"] is False
        assert parameters["required"], name
        assert set(parameters["properties"]) <= set(ARG_MODELS[name].model_fields)
        assert set(parameters["required"]) <= set(ARG_MODELS[name].model_fields)


def test_search_products_returns_catalogue_rows(catalog):
    record = execute_tool("search_products", {"query": "wireless headphones"}, catalog)

    assert record.ok is True
    assert record.error is None
    assert record.result is not None
    assert record.result["count"] == 1
    assert record.result["products"][0]["sku"] == "SKU-001"
    assert record.duration_ms >= 0


def test_check_inventory_reports_availability(catalog):
    record = execute_tool("check_inventory", {"sku": "SKU-002"}, catalog)

    assert record.ok is True
    assert record.result is not None
    assert record.result["available"] == 35
    assert record.result["in_stock"] is True
    assert "35 unit" in record.result["message"]


def test_get_order_status_returns_the_order(catalog):
    record = execute_tool("get_order_status", {"order_id": "ORD-1003"}, catalog)

    assert record.ok is True
    assert record.result is not None
    assert record.result["order"]["status"] == "delivered"
    assert record.result["order"]["total"] == 169.94  # 129.99 + 39.95

    # Providers send ``arguments`` as a JSON string, so the executor must decode it.
    as_string = execute_tool("get_order_status", json.dumps({"order_id": "ORD-1001"}), catalog)
    assert as_string.ok is True
    assert as_string.result is not None
    assert as_string.result["order"]["order_id"] == "ORD-1001"


def test_unknown_tools_and_bad_arguments_are_reported_not_raised(catalog):
    """Every failure becomes a record the model can read, never an exception."""
    unknown = execute_tool("delete_everything", {"confirm": True}, catalog)
    assert unknown.ok is False
    assert unknown.result is None
    assert "unknown tool" in (unknown.error or "")

    missing = execute_tool("search_products", {"max_price": 10}, catalog)
    assert missing.ok is False
    assert "invalid arguments" in (missing.error or "")
    assert "query" in (missing.error or "")

    broken = execute_tool("get_order_status", "{not json", catalog)
    assert broken.ok is False
    assert "not valid JSON" in (broken.error or "")


def test_hallucinated_arguments_are_coerced_before_execution(catalog):
    """String numbers and lower-case identifiers are the common hallucinations.

    Pydantic's lax coercion repairs ``"80"`` and ``"2"``; the before-validator
    on the SKU repairs ``sku-001``.  Repairing is cheaper than another round trip.
    """
    record = execute_tool(
        "search_products",
        {"query": "wireless", "max_price": "80", "limit": "2"},
        catalog,
    )
    assert record.ok is True
    assert record.arguments["max_price"] == "80"  # raw args are logged as sent
    assert record.arguments["limit"] == "2"
    assert record.result is not None
    # The string was coerced to a number and actually applied: two products cost
    # 80.00 or less and the limit of "2" was honoured.
    assert record.result["count"] == 2
    assert {p["sku"] for p in record.result["products"]} == {"SKU-002", "SKU-005"}

    sku_record = execute_tool("check_inventory", {"sku": " sku-001 "}, catalog)
    assert sku_record.ok is True
    assert sku_record.result is not None
    assert sku_record.result["sku"] == "SKU-001"


def test_unknown_sku_and_unknown_order_return_found_false(catalog):
    """A well-formed request for a non-existent row is data, not an error."""
    inventory = execute_tool("check_inventory", {"sku": "SKU-999"}, catalog)
    assert inventory.ok is True
    assert inventory.result is not None
    assert inventory.result["found"] is False

    order = execute_tool("get_order_status", {"order_id": "ORD-9999"}, catalog)
    assert order.ok is True
    assert order.result is not None
    assert order.result["found"] is False
