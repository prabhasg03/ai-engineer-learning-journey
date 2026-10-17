"""AI Shopping Assistant - Phase 2 capstone (mini-project B).

A hand-written FastAPI service that runs a tool-calling agent over a small
in-memory product catalogue.  The LLM is behind a small protocol so the whole
service is deterministic (and testable) offline with ``MockLLM``; a real
OpenAI-compatible HTTP client is available for hands-on use.

Modules
-------
config      settings (endpoint, model, timeouts, retry policy, mock switch)
catalog     deterministic seed data: products, inventory, orders
models      Pydantic contracts for every boundary
retry       hand-written exponential backoff + jitter honouring Retry-After
tools       JSON-schema tool definitions + typed argument models
llm         LLMClient protocol, MockLLM, OpenAI-compatible HTTP client
agent       the hand-written tool-call loop (structured + streaming)
main        FastAPI routes
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
