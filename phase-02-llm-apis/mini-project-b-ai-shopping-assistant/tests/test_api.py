"""API tests through FastAPI's TestClient - no server, no network.

The ``client`` fixture swaps in a fresh catalogue and a fresh ``MockLLM``, so
these tests exercise the real routes, the real agent loop and the real tool
executor, just with a deterministic model behind them.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """Decode an SSE body into ``[(event_name, data), ...]``."""
    frames: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event_name = ""
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        payload = json.loads("\n".join(data_lines)) if data_lines else {}
        frames.append((event_name, payload))
    return frames


def test_health_reports_the_offline_mock_mode_and_the_openapi_schema_exists(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["use_mock_llm"] is True
    assert body["product_count"] == 12
    assert body["model"]

    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    for path in (
        "/health",
        "/products",
        "/products/{sku}",
        "/orders/{order_id}",
        "/assistant",
        "/assistant/stream",
    ):
        assert path in paths


def test_products_endpoint_supports_query_price_and_tag_filters(client: TestClient):
    everything = client.get("/products")
    assert everything.status_code == 200
    assert len(everything.json()) == 10  # default limit

    filtered = client.get("/products", params={"tag": "audio", "max_price": 100})
    assert filtered.status_code == 200
    assert [row["sku"] for row in filtered.json()] == ["SKU-011", "SKU-002"]

    searched = client.get("/products", params={"q": "mechanical keyboard", "limit": 3})
    assert searched.status_code == 200
    assert [row["sku"] for row in searched.json()] == ["SKU-004"]

    assert client.get("/products", params={"limit": 0}).status_code == 422


def test_product_and_order_lookups_return_data_or_404(client: TestClient):
    found = client.get("/products/SKU-003")
    assert found.status_code == 200
    assert found.json()["name"] == "Vertex 27-inch 4K Monitor"

    missing = client.get("/products/SKU-999")
    assert missing.status_code == 404
    assert "SKU-999" in missing.json()["detail"]

    order = client.get("/orders/ORD-1001")
    assert order.status_code == 200
    body = order.json()
    assert body["status"] == "shipped"
    assert body["total"] == 149.48
    assert len(body["lines"]) == 2

    assert client.get("/orders/ORD-9999").status_code == 404


def test_assistant_returns_a_structured_answer(client: TestClient):
    response = client.post(
        "/assistant",
        json={"message": "show me wireless headphones under $150"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert [p["sku"] for p in body["products"]] == ["SKU-001"]
    assert body["order_status"] is None
    assert body["model"] == "mock-shopping-llm"
    assert body["stop_reason"] == "final"
    assert body["iterations"] >= 1
    assert body["usage"]["total_tokens"] > 0

    called = body["tool_calls"]
    assert [call["name"] for call in called] == ["search_products"]
    assert called[0]["ok"] is True
    assert called[0]["arguments"]["max_price"] == 150.0

    # Request validation is enforced by the response/request models (topic 11).
    assert client.post("/assistant", json={"message": ""}).status_code == 422
    assert client.post("/assistant", json={}).status_code == 422
    assert client.post("/assistant", json={"message": "hi", "max_iterations": 99}).status_code == 422
    assert (
        client.post(
            "/assistant",
            json={"message": "hi", "conversation": [{"role": "system", "content": "x"}]},
        ).status_code
        == 422
    )


def test_assistant_returns_order_status_and_conversation_is_accepted(client: TestClient):
    response = client.post(
        "/assistant",
        json={
            "message": "and when will it arrive? ORD-1001",
            "conversation": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "Hi! What can I help you find?"},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["order_status"]["order_id"] == "ORD-1001"
    assert body["order_status"]["status"] == "shipped"


def test_streaming_endpoint_streams_tool_events_tokens_and_a_final_result(
    client: TestClient,
):
    response = client.post(
        "/assistant/stream",
        json={"message": "show me wireless headphones under $150"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"

    frames = _parse_sse(response.text)
    names = [name for name, _ in frames]
    assert names[0] == "start"
    assert names[-1] == "final"
    assert "token" in names
    assert "tool_call" in names

    tokens = "".join(data["text"] for name, data in frames if name == "token")
    final = frames[-1][1]
    assert tokens == final["answer"]  # deltas reassemble to the final answer
    assert final["answer"]
    assert [p["sku"] for p in final["products"]] == ["SKU-001"]
    assert final["stop_reason"] == "final"

    tool_events = [data for name, data in frames if name == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0]["name"] == "search_products"
    assert tool_events[0]["arguments"]["max_price"] == 150.0
    assert tool_events[0]["ok"] is True
    assert tool_events[0]["error"] is None

    # A second stream, for an order question, puts the order in the final event.
    order_frames = _parse_sse(
        client.post("/assistant/stream", json={"message": "where is ORD-1002?"}).text
    )
    order_tools = [data for name, data in order_frames if name == "tool_call"]
    assert [event["name"] for event in order_tools] == ["get_order_status"]
    assert order_tools[0]["arguments"]["order_id"] == "ORD-1002"
    order_final = order_frames[-1][1]
    assert order_final["order_status"]["order_id"] == "ORD-1002"
    assert order_final["order_status"]["status"] == "processing"
