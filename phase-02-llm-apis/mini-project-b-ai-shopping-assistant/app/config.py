"""Settings for the service, read once from the environment.

Everything that might differ between a laptop and a deployment lives here:
the optional OpenAI-compatible endpoint, the model name, timeouts, the
iteration budget, and the retry policy.

The single most important default is ``use_mock_llm=True``.  It means the
project runs, streams and answers with **no API key, no network and no model
server**, which is what makes the test suite deterministic and what makes
"runs on a fresh machine from the README alone" true.  Point it at a real
server by setting ``SHOPPING_USE_MOCK_LLM=0`` plus a base URL and model.

Environment variables (all optional):

============================  ==========================  ==============================
Variable                      Default                     Meaning
============================  ==========================  ==============================
SHOPPING_USE_MOCK_LLM         ``1``                       ``0`` to use the live client
SHOPPING_LLM_BASE_URL         ``http://127.0.0.1:8080/v1``  OpenAI-compatible base URL
SHOPPING_LLM_MODEL            ``local-openai-compatible`` model id sent in the payload
SHOPPING_LLM_API_KEY          ``not-needed``              bearer token for the endpoint
SHOPPING_LLM_TIMEOUT_S        ``30``                      per-request timeout, seconds
SHOPPING_TEMPERATURE          ``0.2``                     sampling temperature
SHOPPING_MAX_ITERATIONS       ``4``                       tool-call round trips per request
============================  ==========================  ==============================
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from .retry import RetryPolicy

__all__ = ["Settings", "get_settings", "reset_settings_cache"]


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_num(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    return int(_env_num(name, float(default)))


@dataclass(frozen=True)
class Settings:
    """Immutable configuration object.

    Frozen on purpose: it is created once and handed to every layer, so a
    request cannot quietly change global behaviour halfway through.
    """

    app_name: str = "AI Shopping Assistant"
    version: str = "1.0.0"

    # -- LLM endpoint ------------------------------------------------------ #
    llm_base_url: str = "http://127.0.0.1:8080/v1"
    llm_model: str = "local-openai-compatible"
    llm_api_key: str = "not-needed"
    llm_timeout_s: float = 30.0
    temperature: float = 0.2           # extraction-flavoured task: stay boring

    # -- agent loop -------------------------------------------------------- #
    max_iterations: int = 4            # tool-call round trips before we stop
    max_tool_output_chars: int = 6_000  # guard against a huge tool payload

    # -- offline switch ---------------------------------------------------- #
    use_mock_llm: bool = True

    # -- reliability ------------------------------------------------------- #
    retry: RetryPolicy = field(
        default_factory=lambda: RetryPolicy(
            max_attempts=3,
            base=0.5,
            multiplier=2.0,
            max_delay=8.0,
            jitter="full",
            max_elapsed=20.0,
        )
    )

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from the environment, falling back to the defaults."""
        return cls(
            llm_base_url=_env_str("SHOPPING_LLM_BASE_URL", cls.llm_base_url),
            llm_model=_env_str("SHOPPING_LLM_MODEL", cls.llm_model),
            llm_api_key=_env_str("SHOPPING_LLM_API_KEY", cls.llm_api_key),
            llm_timeout_s=_env_num("SHOPPING_LLM_TIMEOUT_S", cls.llm_timeout_s),
            temperature=_env_num("SHOPPING_TEMPERATURE", cls.temperature),
            max_iterations=_env_int("SHOPPING_MAX_ITERATIONS", cls.max_iterations),
            use_mock_llm=_env_bool("SHOPPING_USE_MOCK_LLM", cls.use_mock_llm),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached process-wide settings (call :func:`reset_settings_cache` in tests)."""
    return Settings.from_env()


def reset_settings_cache() -> None:
    """Drop the cached settings so the next ``get_settings()`` re-reads env vars."""
    get_settings.cache_clear()
