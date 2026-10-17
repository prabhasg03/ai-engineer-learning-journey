# Topic 13 — Python Unassisted #3: Async and Await

## 1. Purpose of This Topic

You have been writing synchronous Python. LLM API calls are **I/O-bound** — your program spends most of its time waiting for the network. `async`/`await` lets you run multiple calls concurrently without threads.

This topic gives you the mental model and the patterns you need for:
- Topic 14: Streaming
- Topic 16: FastAPI (async routes)
- Topic 42+: Multi-agent tool loops

---

## 2. Prerequisites

**Before: Topic 5 — Python unassisted #1**

You should be comfortable with:
- Functions, dictionaries, JSON
- Writing pytest tests
- Virtual environments

---

## 3. The Core Mental Model

### Synchronous (blocking)

```text
Task 1: ████████████ (wait for HTTP)
Task 2: ████████████ (wait for HTTP)
Task 3: ████████████ (wait for HTTP)
Total: 30 seconds
```

### Asynchronous (concurrent)

```text
Task 1: ████████████
Task 2: ████████████
Task 3: ████████████
Total: 10 seconds (all wait at once)
```

The event loop runs one task until it hits `await` (I/O wait), then switches to another task.

---

## 4. Key Concepts

### 4.1 Coroutine Function vs Coroutine vs Task

```python
async def fetch_data(url: str) -> dict:
    # This is a COROUTINE FUNCTION (defines the work)
    ...

# Calling it returns a COROUTINE OBJECT (not yet running)
coro = fetch_data("http://example.com")

# Scheduling it creates a TASK (managed by event loop)
task = asyncio.create_task(fetch_data("http://example.com"))
```

| Term | What it is |
|------|------------|
| `async def` | Defines a coroutine function |
| `coro = func()` | Returns a coroutine object (paused at start) |
| `await coro` | Runs until next await, yields control |
| `asyncio.create_task(coro)` | Schedules coroutine on event loop, returns Task |
| `asyncio.gather(*tasks)` | Runs multiple tasks concurrently, waits for all |

### 4.2 What `await` Does

```python
async def example():
    print("Before await")
    await asyncio.sleep(1)  # Yields control to event loop for 1 second
    print("After await")
```

`await` means: **"Pause here until this completes. In the meantime, let the event loop run other tasks."**

It does NOT mean "run in parallel" — it means "yield at this point."

### 4.3 The Event Loop

```text
Event Loop:
  while tasks exist:
      pick a ready task
      run until await
      put back in queue
```

Only **one** task runs at a time (single-threaded). Concurrency comes from interleaving at `await` points.

---

## 5. Running Async Code

```python
import asyncio

async def main():
    await do_something()

# Entry point
asyncio.run(main())
```

`asyncio.run()` creates a new event loop, runs the coroutine, closes the loop.

---

## 6. Concurrent API Calls with `asyncio.gather`

```python
import aiohttp  # async HTTP client
import asyncio

async def fetch(session: aiohttp.ClientSession, url: str) -> dict:
    async with session.get(url) as response:
        return await response.json()

async def fetch_all(urls: list[str]) -> list[dict]:
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, url) for url in urls]
        return await asyncio.gather(*tasks)

# Usage
urls = ["http://api.example.com/1", "http://api.example.com/2", "http://api.example.com/3"]
results = asyncio.run(fetch_all(urls))
```

All three requests are in flight simultaneously. Total time ≈ slowest request.

---

## 7. Error Handling in Concurrent Code

```python
async def fetch_safe(session: aiohttp.ClientSession, url: str) -> dict | None:
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()
    except aiohttp.ClientError as e:
        print(f"Failed {url}: {e}")
        return None

async def fetch_all(urls: list[str]) -> list[dict]:
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_safe(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]
```

---

## 8. Blocking the Loop (The #1 Pitfall)

```python
# BAD: synchronous call inside async function
async def bad_example():
    response = requests.get(url)  # BLOCKS THE ENTIRE EVENT LOOP
    return response.json()

# GOOD: use async client
async def good_example():
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
```

**Rule:** Never call blocking I/O (requests, time.sleep, file I/O, psycopg2) inside async code. Use async equivalents.

---

## 9. Async Context Managers

```python
class AsyncDatabase:
    async def __aenter__(self):
        self.pool = await asyncpg.create_pool(...)
        return self
    
    async def __aexit__(self, *args):
        await self.pool.close()

async def main():
    async with AsyncDatabase() as db:
        await db.query(...)
```

---

## 10. Running Sync Code in Thread Pool (When Necessary)

```python
import asyncio
import requests  # sync library

async def run_sync_in_thread():
    loop = asyncio.get_event_loop()
    # Runs requests.get in a thread pool
    response = await loop.run_in_executor(None, requests.get, url)
    return response.json()
```

Use sparingly — threads have overhead and GIL limits.

---

## 11. Structured Concurrency (Python 3.11+)

```python
async def main():
    async with asyncio.TaskGroup() as tg:
        task1 = tg.create_task(fetch(url1))
        task2 = tg.create_task(fetch(url2))
        task3 = tg.create_task(fetch(url3))
    # All tasks completed or first exception raised
    results = [task1.result(), task2.result(), task3.result()]
```

`TaskGroup` ensures:
- All tasks cleaned up on exception
- No orphaned tasks
- Clear semantics

---

## 12. Type Hints for Async

```python
from typing import Coroutine, Awaitable

# Function returning a coroutine
async def fetch(url: str) -> dict: ...

# Accepts any awaitable
async def process(awaitable: Awaitable[dict]) -> dict:
    return await awaitable
```

---

## 13. Done-When Checklist

From the syllabus:

- [ ] Event-loop mental model; coroutine functions vs coroutines vs tasks
- [ ] What `await` suspends and resumes; `asyncio.gather` for concurrency
- [ ] Why IO-bound LLM calls are the ideal async workload
- [ ] Blocking-the-loop pitfalls (sync calls inside async routes)

---

## 14. Sources

- [Real Python — async IO walkthrough](https://realpython.com/async-io-python/)
- [Python.org — conceptual overview of asyncio](https://docs.python.org/3/howto/a-conceptual-overview-of-asyncio.html)
- [aiohttp docs](https://docs.aiohttp.org/)