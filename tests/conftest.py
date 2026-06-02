"""Shared test fixtures and configuration for the NEURO-MESH API Gateway tests.

This module provides pytest fixtures used across test modules, including:
- FastAPI TestClient / httpx AsyncClient setup
- Trie instances pre-loaded with test routes
- StateManager instances in various health configurations
- Hypothesis settings and profiles
"""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Configure pytest-asyncio to use asyncio backend."""
    return "asyncio"
