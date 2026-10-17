# Topic 15 — Python Unassisted #4: Decorators

## 1. Purpose of This Topic

You have used decorators (`@app.get`, `@dataclass`, `@property`) without fully understanding how they work. This topic builds decorators from first principles so FastAPI stops being magic.

---

## 2. Prerequisites

**Before: Topic 5 — Python unassisted #1**

You need:
- Functions as first-class objects
- Closures
- `*args`, `**kwargs`
- Type hints

---

## 3. The Core Idea

A **decorator** is a function that takes a function and returns a new function.

```python
def my_decorator(func):
    def wrapper(*args, **kwargs):
        print("Before call")
        result = func(*args, **kwargs)
        print("After call")
        return result
    return wrapper

@my_decorator
def greet(name):
    return f"Hello, {name}"

# Equivalent to:
# greet = my_decorator(greet)
```

When you call `greet("Alice")`:
1. `wrapper("Alice")` runs
2. Prints "Before call"
3. Calls original `greet("Alice")`
4. Prints "After call"
5. Returns result

---

## 4. Closures — The Mechanism

```python
def make_multiplier(factor):
    def multiplier(x):
        return x * factor  # 'factor' captured from enclosing scope
    return multiplier

times3 = make_multiplier(3)
times5 = make_multiplier(5)

print(times3(4))  # 12
print(times5(4))  # 20
```

The inner function `multiplier` **closes over** `factor`. It remembers the environment where it was created.

Decorators use this same mechanism:
- Outer function receives the decorated function
- Inner function (wrapper) closes over it
- Wrapper is returned and replaces the original

---

## 5. Basic Decorator Pattern

```python
def decorator(func):
    def wrapper(*args, **kwargs):
        # Pre-processing
        result = func(*args, **kwargs)
        # Post-processing
        return result
    return wrapper
```

### 5.1 Preserving Metadata with `functools.wraps`

```python
from functools import wraps

def my_decorator(func):
    @wraps(func)  # Copies __name__, __doc__, __annotations__, etc.
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper
```

Without `@wraps`, the decorated function loses its identity:
```python
@my_decorator
def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}"

print(greet.__name__)  # 'wrapper' without @wraps, 'greet' with @wraps
print(greet.__doc__)   # None without @wraps
```

---

## 6. Decorators That Take Arguments

```python
def repeat(times: int):
    """Decorator factory: returns a decorator."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            results = []
            for _ in range(times):
                results.append(func(*args, **kwargs))
            return results
        return wrapper
    return decorator

@repeat(3)
def say_hello(name):
    return f"Hello, {name}"

print(say_hello("Alice"))
# ['Hello, Alice', 'Hello, Alice', 'Hello, Alice']
```

Three layers:
1. `repeat(3)` → returns `decorator`
2. `decorator(say_hello)` → returns `wrapper`
3. `wrapper` replaces `say_hello`

---

## 7. Stacking Decorators

```python
@decorator_a
@decorator_b
def func():
    pass

# Equivalent to:
# func = decorator_a(decorator_b(func))
# Order: decorator_b applied FIRST, then decorator_a
```

Bottom decorator runs first (closest to function).

---

## 8. Class-Based Decorators

```python
class CountCalls:
    def __init__(self, func):
        self.func = func
        self.count = 0
        wraps(func)(self)
    
    def __call__(self, *args, **kwargs):
        self.count += 1
        print(f"Call {self.count} to {self.func.__name__}")
        return self.func(*args, **kwargs)

@CountCalls
def greet(name):
    return f"Hello, {name}"

greet("Alice")  # Call 1 to greet
greet("Bob")    # Call 2 to greet
```

---

## 9. Practical Patterns for LLM Engineering

### 9.1 Retry Decorator

```python
import asyncio
from functools import wraps
from typing import Callable, TypeVar

T = TypeVar("T")

def retry(max_attempts: int = 3, base_delay: float = 1.0):
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff
                        await asyncio.sleep(delay)
            raise last_exception
        return wrapper
    return decorator

@retry(max_attempts=3, base_delay=0.5)
async def call_llm(prompt: str) -> str:
    ...
```

### 9.2 Timing Decorator

```python
import time
from functools import wraps

def timed(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper
```

### 9.3 Validation Decorator

```python
from pydantic import BaseModel, ValidationError

def validate_input(model_class: type[BaseModel]):
    def decorator(func):
        @wraps(func)
        def wrapper(data: dict):
            validated = model_class.model_validate(data)
            return func(validated)
        return wrapper
    return decorator

class InvoiceInput(BaseModel):
    invoice_number: str
    total: float = Field(gt=0)

@validate_input(InvoiceInput)
def process_invoice(invoice: InvoiceInput) -> float:
    return invoice.total * 1.2
```

---

## 10. FastAPI Connection

FastAPI route decorators are exactly this pattern:

```python
# What you write:
@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}

# What it does (simplified):
def get(path: str):
    def decorator(func):
        # Register route in FastAPI's router
        router.add_route(path, func, methods=["GET"])
        return func
    return decorator
```

The decorator:
1. Registers the function in the router
2. Returns the original function (or wrapped version)
3. Uses type hints for request parsing, validation, docs

---

## 11. Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| Forgetting `@wraps` | Always use `@wraps(func)` |
| Not returning wrapper | Ensure outer function returns inner |
| Mutable default in decorator | Use `None` and create inside |
| Breaking function signature | Use `*args, **kwargs` and preserve annotations |

---

## 12. Done-When Checklist

From the syllabus:

- [ ] Closures → wrapper functions → `@` syntax
- [ ] `functools.wraps`; decorators that take arguments; stacking order
- [ ] Goal: FastAPI's route decorators stop being magic

---

## 13. Sources

- [Real Python — decorators primer](https://realpython.com/primer-on-python-decorators/)
- [Trey Hunner — decorators track](https://www.pythonmorsels.com/screencasts/decorators/)
- [functools.wraps docs](https://docs.python.org/3/library/functools.html#functools.wraps)