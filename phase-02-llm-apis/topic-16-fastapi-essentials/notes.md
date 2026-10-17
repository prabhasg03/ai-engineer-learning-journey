# Topic 16 — FastAPI Essentials

## 1. Purpose of This Topic

Build a small FastAPI service that exposes typed routes, uses dependency injection, validates I/O with Pydantic models, and returns correct HTTP status codes.

This topic connects:

```text
Topic 11: type hints + Pydantic
Topic 15: decorators as wrappers
                    ↓
Topic 16: FastAPI routes, dependencies, TestClient
```

**Done when:** a small service runs with typed routes, one dependency, and a passing TestClient test.

---

## 2. Prerequisites

**Before: Topic 11 (type hints + Pydantic), Topic 15 (decorators)**

You need:
- Pydantic models for request/response validation
- Decorator pattern understanding (`@wraps`, decorator factories)
- Async/await basics (Topic 13) — FastAPI supports both `async def` and `def` routes

---

## 3. FastAPI Core Mental Model

FastAPI is a web framework that:

1. **Defines routes** with decorators (`@app.get`, `@app.post`)
2. **Validates request bodies** via Pydantic models
3. **Validates query/path parameters** via type annotations
4. **Injects dependencies** via `Depends()`
5. **Serializes responses** via `response_model`
6. **Auto-generates docs** at `/docs` (Swagger UI) and `/openapi.json`

The framework infers almost everything from **type annotations** — no separate schema files needed.

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.post("/items")
async def create_item(item: Item):
    return item
```

Everything typed — `item` is validated as `Item`, response is serialized back to JSON.

---

## 4. Path and Query Parameters

### 4.1 Path parameters

```python
@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}
```

`item_id` is extracted from the URL path and type-checked as `int`. FastAPI returns `422 Unprocessable Entity` if it's not an int.

### 4.2 Query parameters

```python
@app.get("/search")
async def search(q: str | None = None, limit: int = 10):
    return {"q": q, "limit": limit}
```

Query params default to `None` (optional) or a default value. FastAPI uses `None` as the sentinel for optional.

### 4.3 Request body as Pydantic model

```python
class Invoice(BaseModel):
    invoice_number: str
    total: float

@app.post("/invoices")
async def create_invoice(invoice: Invoice):
    return invoice
```

FastAPI reads the JSON body, validates it against `Invoice`, passes the parsed object to your function.

---

## 5. Response Models and Status Codes

### 5.1 Response models

Declaring `response_model` tells FastAPI to validate and **filter** the output — only declared fields are returned.

```python
class UserOut(BaseModel):
    username: str
    email: str

@app.post("/users", response_model=UserOut, status_code=201)
async def create_user(user: UserIn):
    # password_hash is in UserIn but NOT in UserOut → filtered out
    return user
```

This prevents accidentally leaking sensitive fields (passwords, internal IDs) to clients.

### 5.2 Status codes

```python
from fastapi import status

@app.post("/items", status_code=status.HTTP_201_CREATED)
async def create_item(item: Item):
    return item

@app.get("/items/{item_id}", status_code=status.HTTP_200_OK)
async def read_item(item_id: int):
    return {"item_id": item_id}
```

Common codes:
- `200 OK` — default GET
- `201 Created` — default POST
- `204 No Content` — DELETE / successful update with no body
- `400 Bad Request`, `401 Unauthorized`, `404 Not Found`, `422 Unprocessable Entity`

---

## 6. Dependency Injection

`Depends()` lets you declare dependencies that FastAPI resolves before calling your route function.

```python
from fastapi import Depends, FastAPI
from typing import Annotated

app = FastAPI()

async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/items/")
async def read_items(db: Annotated[Session, Depends(get_db)]):
    return db.query(Item).all()
```

The dependency:
1. Runs before the route function
2. Can have setup/teardown (the `yield` pattern)
3. Is shared across routes that declare it
4. Can itself have dependencies (nested `Depends`)

### 6.1 Dependency with parameters

```python
def common_parameters(q: str | None = None, skip: int = 0, limit: int = 100):
    return {"q": q, "skip": skip, "limit": limit}

@app.get("/items/")
async def read_items(commons: Annotated[dict, Depends(common_parameters)]):
    return commons
```

---

## 7. Async Routes

FastAPI routes can be `async def` or `def`:

- `async def` — awaited on the event loop; use for I/O-bound work (HTTP calls, DB queries with async drivers)
- `def` — run in a threadpool; use for blocking work (CPU-heavy, sync DB drivers)

Mixing is fine — FastAPI handles both.

```python
@app.get("/sync")
def sync_route():
    return {"type": "blocking"}

@app.get("/async")
async def async_route():
    return {"type": "non-blocking"}
```

---

## 8. Automatic Documentation

FastAPI generates:
- `/docs` — Swagger UI (interactive, try-it-out)
- `/redoc` — ReDoc (reference-style)
- `/openapi.json` — machine-readable schema

No extra work — enabled by default.

---

## 9. TestClient

FastAPI provides `TestClient` (built on `httpx`) for testing routes without a running server:

```python
from fastapi.testclient import TestClient

client = TestClient(app)

def test_read_item():
    response = client.get("/items/42")
    assert response.status_code == 200
    assert response.json() == {"item_id": 42}

def test_create_item():
    response = client.post("/items", json={"name": "widget", "price": 9.99})
    assert response.status_code == 201
    assert response.json()["name"] == "widget"
```

This extends the Topic 5 pytest habit — tests are plain functions with `assert`, no network needed.

---

## 10. Error Handling

FastAPI returns `422` automatically when request validation fails. For custom errors, raise `HTTPException`:

```python
from fastapi import HTTPException

items_db = {1: {"name": "widget"}}

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    return items_db[item_id]
```

---

## 11. Done-When Checklist

From the syllabus:

- [ ] Path/query parameters; request bodies as Pydantic models
- [ ] Response models, status codes, dependency injection
- [ ] Async routes; automatic docs
- [ ] TestClient basics — extending the topic 5 testing habit

---

## 12. Sources

- [FastAPI tutorial — User Guide](https://fastapi.tiangolo.com/tutorial/)
- [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices)
- [FastAPI TestClient docs](https://fastapi.tiangolo.com/tutorial/testing/)