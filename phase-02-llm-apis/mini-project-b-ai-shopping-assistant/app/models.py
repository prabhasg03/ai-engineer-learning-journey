"""Pydantic contracts for every boundary of the service (topics 11 and 12).

Three boundaries need types:

1. **HTTP** - ``AssistantRequest`` in, ``AssistantResponse`` out.  FastAPI
   validates the body before our code runs and serialises the response model
   afterwards, so a malformed request can never reach the agent loop.
2. **LLM** - ``ToolCall`` and ``Usage`` model what a provider returns.  Tool
   arguments come back as an untyped JSON string, which is exactly the
   "argument hallucination" surface from topic 17 - the typed ``*Args`` models
   below are the validator that stands between the model and our catalogue.
3. **Streaming** - ``StreamEvent`` is the wire shape of one Server-Sent Event,
   including the final structured event that ends a stream.

Nothing in this module does IO; it is the shared vocabulary for everything
else.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

#: SKUs look like ``SKU-001``; order ids look like ``ORD-1001``.
SKU_PATTERN = r"^SKU-\d{3}$"
ORDER_ID_PATTERN = r"^ORD-\d{4}$"

__all__ = [
    "AssistantRequest",
    "AssistantResponse",
    "ChatTurn",
    "CheckInventoryArgs",
    "GetOrderStatusArgs",
    "HealthResponse",
    "Inventory",
    "OrderLine",
    "OrderStatus",
    "Product",
    "SearchProductsArgs",
    "StreamEvent",
    "ToolCall",
    "ToolCallRecord",
    "Usage",
]


# --------------------------------------------------------------------------- #
# Catalogue vocabulary
# --------------------------------------------------------------------------- #


class Product(BaseModel):
    """One catalogue item as shown to a shopper."""

    sku: str = Field(..., pattern=SKU_PATTERN, description="Stable product id, e.g. SKU-001.")
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1, max_length=400)
    price: float = Field(..., ge=0, le=100_000, description="Unit price in USD.")
    tags: list[str] = Field(default_factory=list, max_length=12)


class Inventory(BaseModel):
    """Stock level for one SKU.

    ``available`` is derived (``quantity - reserved``) rather than stored, so it
    is impossible for a caller to see an inconsistent pair of numbers.
    """

    sku: str = Field(..., pattern=SKU_PATTERN)
    quantity: int = Field(..., ge=0, description="Physical units on the shelf.")
    reserved: int = Field(default=0, ge=0, description="Units already allocated to open orders.")
    warehouse: str = Field(..., min_length=1, max_length=32)
    restock_eta_days: int | None = Field(default=None, ge=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def available(self) -> int:
        """Units a new order can actually take."""
        return max(0, self.quantity - self.reserved)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def in_stock(self) -> bool:
        """True when at least one unit can be sold right now."""
        return self.available > 0


class OrderLine(BaseModel):
    """One line of an order; ``line_total`` is derived, never sent by the client."""

    sku: str = Field(..., pattern=SKU_PATTERN)
    name: str = Field(..., min_length=1, max_length=120)
    quantity: int = Field(..., ge=1, le=100)
    unit_price: float = Field(..., ge=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def line_total(self) -> float:
        return round(self.quantity * self.unit_price, 2)


class OrderStatus(BaseModel):
    """Order tracking payload returned by the order-status tool."""

    order_id: str = Field(..., pattern=ORDER_ID_PATTERN)
    status: Literal["processing", "shipped", "delivered", "cancelled"]
    placed_at: str = Field(..., description="ISO-8601 date the order was placed.")
    eta: str | None = Field(default=None, description="ISO-8601 delivery estimate, if any.")
    carrier: str | None = Field(default=None, max_length=40)
    lines: list[OrderLine] = Field(default_factory=list, max_length=50)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> float:
        return round(sum(line.line_total for line in self.lines), 2)


# --------------------------------------------------------------------------- #
# Tool-call boundary
# --------------------------------------------------------------------------- #


class SearchProductsArgs(BaseModel):
    """Typed arguments for ``search_products``.

    Field constraints double as the contract: a model that asks for ``limit=99``
    gets a validation error fed back to it instead of a 99-item answer.
    """

    query: str = Field(..., min_length=1, max_length=200, description="Free-text search terms.")
    max_price: float | None = Field(default=None, ge=0, le=100_000)
    tags: list[str] | None = Field(default=None, max_length=8)
    limit: int = Field(default=5, ge=1, le=20)


class CheckInventoryArgs(BaseModel):
    """Typed arguments for ``check_inventory``."""

    sku: str = Field(..., pattern=SKU_PATTERN)

    @field_validator("sku", mode="before")
    @classmethod
    def _normalise(cls, value: Any) -> Any:
        """Accept ``sku-1`` / `` sku-001 `` and repair it to canonical form.

        This is the cheapest hallucination fix: models routinely change the case
        of an identifier, and rejecting that would burn an extra round trip.
        """
        if isinstance(value, str):
            return value.strip().upper()
        return value


class GetOrderStatusArgs(BaseModel):
    """Typed arguments for ``get_order_status``."""

    order_id: str = Field(..., pattern=ORDER_ID_PATTERN)

    @field_validator("order_id", mode="before")
    @classmethod
    def _normalise(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class ToolCall(BaseModel):
    """A tool-call *request* emitted by the model (the model never executes it)."""

    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    """The audit record of one executed tool call, including failures."""

    tool_call_id: str = Field(default="", max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _exactly_one_payload(self) -> "ToolCallRecord":
        if self.ok and self.result is None:
            raise ValueError("a successful tool call must carry a result")
        if not self.ok and not self.error:
            raise ValueError("a failed tool call must carry an error message")
        return self


class Usage(BaseModel):
    """Token accounting, summed across every LLM round trip of one request."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _fill_total(self) -> "Usage":
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens
        return self

    def __add__(self, other: "Usage") -> "Usage":
        """Accumulate usage across the iterations of one agent run."""
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )


# --------------------------------------------------------------------------- #
# HTTP boundary
# --------------------------------------------------------------------------- #


class ChatTurn(BaseModel):
    """One prior turn supplied by the client (the API itself is stateless)."""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4_000)


class AssistantRequest(BaseModel):
    """Body of ``POST /assistant`` and ``POST /assistant/stream``."""

    message: str = Field(..., min_length=1, max_length=2_000, description="The shopper's message.")
    conversation: list[ChatTurn] = Field(
        default_factory=list,
        max_length=24,
        description="Prior turns, oldest first. The server keeps no session state.",
    )
    max_iterations: int | None = Field(
        default=None,
        ge=1,
        le=8,
        description="Optional override of the tool-call iteration budget.",
    )


class AssistantResponse(BaseModel):
    """The structured answer: prose plus every artefact the loop produced."""

    answer: str = Field(..., min_length=1, description="The assistant's natural-language answer.")
    products: list[Product] = Field(default_factory=list, description="Products found by tools.")
    order_status: OrderStatus | None = Field(default=None, description="Order, if one was looked up.")
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    model: str = Field(..., min_length=1)
    usage: Usage = Field(default_factory=Usage)
    iterations: int = Field(default=0, ge=0, description="LLM round trips used.")
    stop_reason: Literal["final", "max_iterations", "no_content"] = "final"


class HealthResponse(BaseModel):
    """Body of ``GET /health``."""

    status: Literal["ok"] = "ok"
    version: str
    model: str
    use_mock_llm: bool
    product_count: int = Field(..., ge=0)


class StreamEvent(BaseModel):
    """One Server-Sent Event on ``POST /assistant/stream``.

    ``event`` is the SSE event name; ``data`` is the JSON payload.  ``seq`` is a
    monotonic counter so a client can detect a dropped chunk.
    """

    event: Literal["start", "token", "tool_call", "final", "error"]
    seq: int = Field(..., ge=0)
    data: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Render as one SSE frame (``event:`` line, ``data:`` line, blank line)."""
        import json

        payload = json.dumps(self.data, separators=(",", ":"), default=str)
        return f"event: {self.event}\ndata: {payload}\n\n"
