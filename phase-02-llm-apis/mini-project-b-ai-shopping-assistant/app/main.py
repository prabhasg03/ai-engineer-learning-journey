"""FastAPI application: typed routes over the catalogue and the agent (topic 16).

Every response goes through a Pydantic ``response_model``, so the contract in
``app.models`` is enforced on the way out just as it is on the way in.  Status
codes are explicit, the docs are automatic (``/docs``), and the catalogue is
injected through a single FastAPI dependency rather than reached as a global.

Route map
---------
``GET  /health``                liveness plus which model mode is active
``GET  /products``              catalogue list (query, price, tag, limit)
``GET  /products/{sku}``        one product, 404 when unknown
``GET  /orders/{order_id}``     one order, 404 when unknown
``POST /assistant``             run the agent, return the structured answer
``POST /assistant/stream``      run the agent, stream SSE, end with the answer
"""

from __future__ import annotations

from functools import lru_cache
from typing import Iterator

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from .agent import run_agent, stream_agent
from .catalog import Catalog, build_catalog
from .config import get_settings
from .llm import LLMError, LLMClient, build_llm
from .models import (
    AssistantRequest,
    AssistantResponse,
    HealthResponse,
    OrderStatus,
    Product,
)
from .tools import TOOL_NAMES

__all__ = ["app", "create_app", "get_store", "get_llm"]


# --------------------------------------------------------------------------- #
# Dependencies
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def _shared_catalog() -> Catalog:
    """One catalogue per process, built once.

    The data is read-only, so sharing is safe; building a fresh one per request
    would be pointless work.  Tests override this dependency.
    """
    return build_catalog()


@lru_cache(maxsize=1)
def _shared_llm() -> LLMClient:
    """One LLM client per process (mock by default, live when configured)."""
    return build_llm(get_settings())


def get_store() -> Catalog:
    """Dependency: the catalogue/store the routes and tools read from."""
    return _shared_catalog()


def get_llm() -> LLMClient:
    """Dependency: the model client the agent talks to."""
    return _shared_llm()


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #


def create_app() -> FastAPI:
    """Build the FastAPI application (a factory keeps testing straightforward)."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        summary="A tool-calling shopping assistant over a product catalogue.",
        description=(
            "Mini-project B of the AI engineering curriculum. Typed routes, "
            "structured outputs, a hand-written tool-call loop, retries with "
            "backoff around every outbound call, and a streaming endpoint.\n\n"
            f"Tools available to the model: {', '.join(TOOL_NAMES)}.\n\n"
            "By default the service runs with a deterministic mock model, so it "
            "needs no API key and no network."
        ),
    )

    @application.exception_handler(LLMError)
    async def _llm_error_handler(_request, exc: LLMError):  # pragma: no cover - trivial
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": f"Upstream model error: {exc}", "attempts": exc.attempts},
        )

    # -- health ------------------------------------------------------------ #

    @application.get(
        "/health",
        response_model=HealthResponse,
        status_code=status.HTTP_200_OK,
        tags=["system"],
        summary="Liveness and current model mode.",
    )
    def health(store: Catalog = Depends(get_store)) -> HealthResponse:
        current = get_settings()
        return HealthResponse(
            version=current.version,
            model=current.llm_model if not current.use_mock_llm else "mock-shopping-llm",
            use_mock_llm=current.use_mock_llm,
            product_count=store.product_count(),
        )

    # -- catalogue --------------------------------------------------------- #

    @application.get(
        "/products",
        response_model=list[Product],
        status_code=status.HTTP_200_OK,
        tags=["catalogue"],
        summary="List or search products.",
    )
    def list_products(
        q: str | None = Query(default=None, max_length=200, description="Free-text search."),
        max_price: float | None = Query(default=None, ge=0, description="Maximum unit price."),
        tag: list[str] | None = Query(default=None, description="Repeatable tag filter."),
        limit: int = Query(default=10, ge=1, le=50, description="Maximum rows returned."),
        store: Catalog = Depends(get_store),
    ) -> list[Product]:
        return store.list_products(query=q, max_price=max_price, tags=tag, limit=limit)

    @application.get(
        "/products/{sku}",
        response_model=Product,
        status_code=status.HTTP_200_OK,
        tags=["catalogue"],
        summary="Fetch one product by SKU.",
    )
    def get_product(sku: str, store: Catalog = Depends(get_store)) -> Product:
        product = store.get_product(sku)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No product with sku {sku!r}",
            )
        return product

    @application.get(
        "/orders/{order_id}",
        response_model=OrderStatus,
        status_code=status.HTTP_200_OK,
        tags=["orders"],
        summary="Fetch one order by id.",
    )
    def get_order(order_id: str, store: Catalog = Depends(get_store)) -> OrderStatus:
        order = store.get_order_status(order_id)
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No order with id {order_id!r}",
            )
        return order

    # -- assistant --------------------------------------------------------- #

    @application.post(
        "/assistant",
        response_model=AssistantResponse,
        status_code=status.HTTP_200_OK,
        tags=["assistant"],
        summary="Ask a shopping question; returns a structured answer.",
    )
    def ask(
        request: AssistantRequest,
        store: Catalog = Depends(get_store),
        llm: LLMClient = Depends(get_llm),
    ) -> AssistantResponse:
        return run_agent(request, store, llm, get_settings())

    @application.post(
        "/assistant/stream",
        status_code=status.HTTP_200_OK,
        tags=["assistant"],
        summary="Ask a shopping question; streams SSE and ends with the structured answer.",
        response_class=StreamingResponse,
        responses={
            200: {
                "description": (
                    "text/event-stream. Events: `start`, `token` (answer deltas), "
                    "`tool_call` (one per executed tool), `final` (the complete "
                    "AssistantResponse), and `error` if the run fails mid-stream."
                ),
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            }
        },
    )
    def ask_stream(
        request: AssistantRequest,
        store: Catalog = Depends(get_store),
        llm: LLMClient = Depends(get_llm),
    ) -> StreamingResponse:
        def event_source() -> Iterator[str]:
            # A sync generator is fine: Starlette will iterate it off the event
            # loop. It also means the retry helper (synchronous) can wrap the
            # LLM call without dragging asyncio into the agent loop.
            for event in stream_agent(request, store, llm, get_settings()):
                yield event.to_sse()

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # stop proxies buffering the stream
            },
        )

    return application


app = create_app()
