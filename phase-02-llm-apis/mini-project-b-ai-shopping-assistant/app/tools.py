"""Tool definitions and the safe executor (topic 17).

Two halves:

**Declaration.**  ``TOOL_SCHEMAS`` is the JSON-Schema array sent to the model on
every request.  The schemas are written out by hand rather than generated from
the Pydantic models for one reason: a provider reads the *descriptions*, and
those descriptions are prompt engineering.  The typed ``*Args`` models in
``app.models`` remain the single source of truth for validation, so the schema
and the model can drift - which is why a test asserts they agree on the
required fields.

**Execution.**  ``execute_tool`` sits between the model's *request* and our
catalogue.  It is the trust boundary, and its most important property is that
**it never raises**: a hallucinated SKU, a malformed argument blob or an
unknown tool name all become an ordinary ``ToolCallRecord`` with ``ok=False``
and an error message, which the agent feeds back to the model.  That turns a
crash into a self-correction opportunity.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .catalog import Catalog
from .models import (
    CheckInventoryArgs,
    GetOrderStatusArgs,
    SearchProductsArgs,
    ToolCallRecord,
)

__all__ = [
    "ARG_MODELS",
    "HANDLERS",
    "TOOL_NAMES",
    "TOOL_SCHEMAS",
    "execute_tool",
    "tool_schema",
]


# --------------------------------------------------------------------------- #
# Declarations
# --------------------------------------------------------------------------- #

_SEARCH_PRODUCTS = {
    "type": "function",
    "function": {
        "name": "search_products",
        "description": (
            "Search the product catalogue for items matching a free-text query. "
            "Use this whenever the shopper describes what they want. Returns up to "
            "`limit` products with sku, name, price and tags. Never invent products: "
            "only mention what this tool returned."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search terms, e.g. 'wireless headphones' or 'usb-c hub'.",
                },
                "max_price": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Inclusive maximum unit price in USD.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tag filters; a product must carry at least one.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "Maximum number of products to return (default 5).",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

_CHECK_INVENTORY = {
    "type": "function",
    "function": {
        "name": "check_inventory",
        "description": (
            "Check live stock for one product SKU (for example SKU-001). Use this "
            "after search_products when the shopper asks whether something is in "
            "stock, how many are left, or when it will be restocked."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "pattern": "^SKU-[0-9]{3}$",
                    "description": "Product SKU, e.g. 'SKU-001'.",
                },
            },
            "required": ["sku"],
            "additionalProperties": False,
        },
    },
}

_GET_ORDER_STATUS = {
    "type": "function",
    "function": {
        "name": "get_order_status",
        "description": (
            "Look up the status, delivery estimate and contents of one order by its "
            "order id (for example ORD-1001). Use this whenever the shopper asks "
            "where an order is or what it contains."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "pattern": "^ORD-[0-9]{4}$",
                    "description": "Order id, e.g. 'ORD-1001'.",
                },
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
}

#: Every tool offered to the model, in a stable order.
TOOL_SCHEMAS: list[dict[str, Any]] = [_SEARCH_PRODUCTS, _CHECK_INVENTORY, _GET_ORDER_STATUS]

#: ``name -> arguments model``: the validator used before anything executes.
ARG_MODELS: dict[str, type[BaseModel]] = {
    "search_products": SearchProductsArgs,
    "check_inventory": CheckInventoryArgs,
    "get_order_status": GetOrderStatusArgs,
}

TOOL_NAMES: tuple[str, ...] = tuple(ARG_MODELS)


def tool_schema(name: str) -> dict[str, Any]:
    """Return the schema for one tool (raises ``KeyError`` when unknown)."""
    for schema in TOOL_SCHEMAS:
        if schema["function"]["name"] == name:
            return schema
    raise KeyError(name)


# --------------------------------------------------------------------------- #
# Handlers: catalogue-backed, return JSON-serialisable payloads
# --------------------------------------------------------------------------- #


def _search_products(args: SearchProductsArgs, catalog: Catalog) -> dict[str, Any]:
    products = catalog.search_products(
        query=args.query, max_price=args.max_price, tags=args.tags, limit=args.limit
    )
    return {
        "query": args.query,
        "count": len(products),
        "products": [p.model_dump(mode="json") for p in products],
    }


def _check_inventory(args: CheckInventoryArgs, catalog: Catalog) -> dict[str, Any]:
    inventory = catalog.check_inventory(args.sku)
    if inventory is None:
        return {
            "sku": args.sku,
            "found": False,
            "message": f"No catalogue entry for {args.sku}.",
        }
    payload = inventory.model_dump(mode="json")
    payload["found"] = True
    if payload["available"] == 0 and payload.get("restock_eta_days") is not None:
        payload["message"] = (
            f"{args.sku} is out of stock; expected back in "
            f"{payload['restock_eta_days']} day(s)."
        )
    elif payload["available"] == 0:
        payload["message"] = f"{args.sku} is out of stock."
    else:
        payload["message"] = (
            f"{payload['available']} unit(s) available at {payload['warehouse']}."
        )
    return payload


def _get_order_status(args: GetOrderStatusArgs, catalog: Catalog) -> dict[str, Any]:
    order = catalog.get_order_status(args.order_id)
    if order is None:
        return {
            "order_id": args.order_id,
            "found": False,
            "message": f"No order {args.order_id} on record.",
        }
    return {"found": True, "order": order.model_dump(mode="json")}


HANDLERS: dict[str, Callable[[Any, Catalog], dict[str, Any]]] = {
    "search_products": _search_products,
    "check_inventory": _check_inventory,
    "get_order_status": _get_order_status,
}


# --------------------------------------------------------------------------- #
# The executor
# --------------------------------------------------------------------------- #


def _error_payload(kind: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": kind, "message": message}
    payload.update(extra)
    return payload


def _coerce_arguments(raw_args: "dict[str, Any] | str | None") -> dict[str, Any] | None:
    """Normalise the model's ``arguments`` field.

    Providers send arguments as a JSON *string*; some send an object already;
    a confused model occasionally sends a double-encoded string.  Anything that
    cannot become a dict returns ``None`` so the caller can report it.
    """
    if raw_args is None:
        return {}
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        text = raw_args.strip()
        if not text:
            return {}
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(decoded, dict):
            return decoded
        if isinstance(decoded, str):
            # Double-encoded: the model serialised a string containing JSON.
            try:
                inner = json.loads(decoded)
            except json.JSONDecodeError:
                return None
            return inner if isinstance(inner, dict) else None
        return None
    return None


def execute_tool(
    name: str,
    raw_args: "dict[str, Any] | str | None",
    catalog: Catalog,
    tool_call_id: str = "",
) -> ToolCallRecord:
    """Validate ``raw_args`` then run the tool.  **Never raises.**

    Failure modes are all converted into a record the model can read:

    * unknown tool name -> ``error="unknown_tool"``;
    * unparseable argument blob -> ``error="invalid_arguments"``;
    * arguments that fail the Pydantic contract -> ``error="invalid_arguments"``
      with the per-field detail attached;
    * a handler that blows up -> ``error="tool_failed"``.

    Pydantic's lax coercion is doing real work here: ``"19.99"`` becomes
    ``19.99`` and ``"3"`` becomes ``3``, so a merely *sloppy* argument (the
    common hallucination) is silently repaired rather than rejected.
    """
    started = time.perf_counter()
    arguments = _coerce_arguments(raw_args)

    def _finish(ok: bool, result: dict[str, Any] | None, error: str | None) -> ToolCallRecord:
        return ToolCallRecord(
            tool_call_id=tool_call_id,
            name=name,
            arguments=arguments if isinstance(arguments, dict) else {},
            ok=ok,
            result=result,
            error=error,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    if name not in HANDLERS:
        return _finish(
            False,
            None,
            f"unknown tool {name!r}; available tools: {', '.join(TOOL_NAMES)}",
        )

    if arguments is None:
        return _finish(False, None, "arguments were not valid JSON")

    model = ARG_MODELS[name]
    try:
        validated = model.model_validate(arguments)
    except ValidationError as exc:
        detail = [
            {"field": ".".join(str(part) for part in err["loc"]), "problem": err["msg"]}
            for err in exc.errors()
        ]
        return _finish(
            False,
            None,
            f"invalid arguments for {name}: "
            + "; ".join(f"{d['field']} {d['problem']}" for d in detail),
        )

    try:
        result = HANDLERS[name](validated, catalog)
    except Exception as exc:  # a handler bug must not break the loop
        return _finish(False, None, f"tool {name} failed: {exc}")

    return _finish(True, result, None)
