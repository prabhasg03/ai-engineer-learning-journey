"""Shared fixtures.

The suite must run with **no network and no API key**, so every fixture builds
a fresh, deterministic catalogue and a deterministic ``MockLLM``.  The project
root is put on ``sys.path`` so the tests work whether they are launched with
``python -m pytest`` (which already adds the cwd) or a bare ``pytest``.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.catalog import Catalog, build_catalog  # noqa: E402
from app.config import Settings  # noqa: E402
from app.llm import MockLLM  # noqa: E402
from app.main import app, get_llm, get_store  # noqa: E402


@pytest.fixture
def catalog() -> Catalog:
    """A fresh catalogue per test so no test can leak state into another."""
    return build_catalog()


@pytest.fixture
def settings() -> Settings:
    """Default settings: mock model, no network."""
    return Settings()


@pytest.fixture
def mock_llm() -> MockLLM:
    """A fresh deterministic model per test."""
    return MockLLM()


@pytest.fixture
def client(catalog: Catalog, mock_llm: MockLLM):
    """A TestClient whose store and model are swapped for fresh, offline ones."""
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_store] = lambda: catalog
    app.dependency_overrides[get_llm] = lambda: mock_llm
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
