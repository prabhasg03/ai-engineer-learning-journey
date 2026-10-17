# Topic 11 — Python Unassisted #2: Type Hints and Pydantic Models

## 1. Purpose of This Topic

You have been writing Python that works at runtime. Now you need Python that documents and enforces its contracts statically.

This topic bridges the gap between:

```text
Topic 5: functions, dicts, JSON
                    ↓
Topic 11: type hints, Pydantic
                    ↓
Topic 12: structured output
```

You cannot build reliable structured-output pipelines without understanding:
- How to model API payloads as typed data
- How validation fails at the boundary
- Why typed I/O is non-negotiable once another system consumes your output

---

## 2. Prerequisites

**Before: Topic 5 — Python unassisted #1**

You should already be comfortable writing:
- Functions with docstrings
- Dictionary/list manipulation
- `json.load` / `json.dump`
- A pytest suite you run yourself

---

## 3. Why Type Hints Exist

Python is dynamically typed. At runtime, a variable can hold anything.

```python
x = 42
x = "forty-two"
x = [1, 2, 3]
```

This flexibility is useful for scripts. It becomes dangerous at system boundaries.

```python
# Function signature without types
def process_invoice(data):
    # What keys exist? What types? What is required?
    return data["total"] * 1.2
```

Type hints make the contract explicit **before** the code runs.

```python
# Function signature with types
def process_invoice(data: dict[str, float]) -> float:
    return data["total"] * 1.2
```

The second version tells you:
- Input: a dict with string keys and float values
- Output: a float
- If you pass the wrong shape, a static checker catches it

---

## 4. Type Hint Syntax You Need

### 4.1 Primitive Types

```python
name: str = "invoice"
count: int = 5
ratio: float = 1.2
active: bool = True
nothing: None = None
```

### 4.2 Collections (modern syntax, Python 3.9+)

```python
ids: list[int] = [1, 2, 3]
tags: set[str] = {"a", "b"}
mapping: dict[str, int] = {"a": 1}
```

### 4.3 Optional and Union

```python
from typing import Optional, Union

# Optional[T] means T | None
name: Optional[str] = None  # str | None

# Union for multiple possible types
value: Union[int, float] = 42  # int | float
```

### 4.4 Type Aliases

```python
from typing import TypeAlias

InvoiceID: TypeAlias = str
LineItems: TypeAlias = list[dict[str, float]]
```

### 4.5 Callable Types

```python
from typing import Callable

Transformer: TypeAlias = Callable[[dict], dict]
```

---

## 5. Pydantic: Runtime Validation with Type Hints

Type hints are **static** (checked by mypy). Pydantic adds **runtime** validation.

```python
from pydantic import BaseModel, Field
from typing import Optional

class Invoice(BaseModel):
    invoice_number: str
    date: str  # YYYY-MM-DD
    total: float = Field(gt=0)  # must be positive
    vendor: Optional[str] = None
```

### 5.1 What This Gives You

```python
# Valid input
invoice = Invoice(
    invoice_number="INV-001",
    date="2024-01-15",
    total=1234.56,
    vendor="Acme Corp"
)

# Invalid input - raises ValidationError immediately
try:
    bad = Invoice(invoice_number="INV-002", date="2024-01-15", total=-100)
except ValidationError as e:
    print(e.errors())
    # [{'type': 'greater_than', 'loc': ('total',), 'msg': 'Input should be greater than 0', ...}]
```

### 5.2 Serialization

```python
# Model → dict (for JSON)
data = invoice.model_dump()
# {'invoice_number': 'INV-001', 'date': '2024-01-15', 'total': 1234.56, 'vendor': 'Acme Corp'}

# Model → JSON string
json_str = invoice.model_dump_json()
# '{"invoice_number":"INV-001","date":"2024-01-15","total":1234.56,"vendor":"Acme Corp"}'

# dict → Model (validates)
invoice2 = Invoice.model_validate(data)
```

### 5.3 Nested Models

```python
class LineItem(BaseModel):
    description: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(gt=0)

class Invoice(BaseModel):
    invoice_number: str
    date: str
    items: list[LineItem]
    total: float = Field(gt=0)
```

---

## 6. Validation at the Boundary

The most important principle:

> **Validate once, at the boundary. Never trust external data.**

```
External input (HTTP, file, env)
         ↓
    Pydantic model
         ↓
Internal code (trusted, typed)
```

Do not validate repeatedly inside your code. Do not use `assert` for validation. Let the model be the contract.

```python
# Bad: scattered validation
def process(data: dict):
    assert "total" in data
    assert isinstance(data["total"], (int, float))
    assert data["total"] > 0

# Good: single model at boundary
def process(invoice: Invoice) -> float:
    return invoice.total * 1.2
```

---

## 7. Why Typed I/O Is Non-Negotiable

When another system consumes your output (another service, a database, a CLI tool):

```
Your service
     │
     │ JSON output (must match schema)
     ↓
Consumer service
     │
     │ Expects exact shape
     ↓
Failure if shape differs
```

Typed I/O means:
- Your output is a contract, not an accident
- Consumers can generate their own clients from your schema
- Breaking changes are visible at the type level
- You can evolve the schema with versioning

---

## 8. Key Pydantic Concepts for This Course

| Concept | Purpose |
|---------|---------|
| `BaseModel` | Base class for validated models |
| `Field` | Constraints (gt, lt, min_length, pattern, etc.) |
| `model_validate()` | Parse + validate from dict |
| `model_validate_json()` | Parse + validate from JSON string |
| `model_dump()` | Model → dict |
| `model_dump_json()` | Model → JSON string |
| `ValidationError` | Raised when input violates schema |
| `ConfigDict` | Model configuration (extra fields, frozen, etc.) |

---

## 9. Common Patterns You'll Use

### 9.1 Optional Fields with Defaults

```python
class Config(BaseModel):
    api_url: str = "http://localhost:8080/v1"
    timeout: float = 30.0
    max_retries: int = 3
```

### 9.2 Discriminated Unions (for tool calls, structured output)

```python
from typing import Literal

class ToolCall(BaseModel):
    type: Literal["function"]
    name: str
    arguments: dict

class ToolResult(BaseModel):
    type: Literal["result"]
    tool_call_id: str
    content: str
```

### 9.3 Excluding Extra Fields

```python
class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

# This raises ValidationError
StrictModel(known_field="ok", unknown_field="bad")
```

---

## 10. Mypy: The Static Checker

Run `mypy --strict` on your code. It catches:
- Missing type annotations
- Incompatible types
- Unused ignores
- Missing return types

Example workflow:
```bash
# 1. Write code with type hints
# 2. Run mypy
python -m mypy --strict my_module.py
# 3. Fix errors
# 4. Run tests
python -m pytest
```

---

## 11. Done-When Checklist

From the syllabus:

- [ ] Annotations for primitives, `Optional`/`Union`, containers
- [ ] Pydantic `BaseModel`: field types, validators, `.model_validate()` / `.model_dump()`
- [ ] Validation errors as contracts failing loudly at the boundary
- [ ] Why typed I/O is non-negotiable once another system consumes your output

---

## 12. Sources

- [Pydantic v2 docs](https://docs.pydantic.dev/latest/)
- [Real Python — dataclasses](https://realpython.com/python-data-classes/)
- [Adam Johnson — type hints](https://adamj.eu/tech/2021/05/11/python-type-hints-args-and-kwargs/)
- [mypy — Getting Started](https://mypy.readthedocs.io/en/stable/getting_started.html)