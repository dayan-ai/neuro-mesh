"""Unit tests for the universal proxy endpoint (POST /proxy/{path:path}).

Tests cover:
- Successful route resolution and response format
- Primary server routing when alive
- Fallback server routing when primary is dead
- HTTP 503 when all servers are dead
- HTTP 404 when route not found
- HTTP 400 for empty/whitespace paths
- HTTP 400 for invalid path characters
- Routing decision logging
"""

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from app.models import HealthStatus
from app.routes import router
from app.state_manager import StateManager
from app.trie import Trie
import app.routes as routes_module


@pytest.fixture
def trie_with_routes() -> Trie:
    """Create a Trie pre-loaded with test routes."""
    t = Trie()
    t.insert("/api/v1/users", "user-service")
    t.insert("/api/v1/users/{id}", "user-service")
    t.insert("/api/v1/orders", "order-service")
    t.insert("/api/v1/orders/{id}", "order-service")
    return t


@pytest.fixture
def state_mgr() -> StateManager:
    """Create a fresh StateManager with default (both Alive) state."""
    return StateManager()


@pytest.fixture
def app(trie_with_routes: Trie, state_mgr: StateManager) -> FastAPI:
    """Create a FastAPI app with routes wired to test Trie and StateManager."""
    test_app = FastAPI()
    test_app.include_router(router)
    # Set module-level globals for the route handler
    routes_module.trie = trie_with_routes
    routes_module.state_manager = state_mgr
    return test_app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_proxy_primary_alive(client: AsyncClient) -> None:
    """When primary is alive, proxy routes to primary server."""
    response = await client.post("/proxy/api/v1/users")
    assert response.status_code == 200
    data = response.json()
    assert data["server"] == "primary"
    assert data["destination"] == "user-service"
    assert data["params"] == {}
    assert data["routing_decision"] == "Primary server selected: server is healthy"
    assert "timestamp" in data
    # Verify timestamp is valid ISO 8601
    datetime.fromisoformat(data["timestamp"])


@pytest.mark.asyncio
async def test_proxy_with_dynamic_params(client: AsyncClient) -> None:
    """Proxy correctly extracts dynamic path parameters."""
    response = await client.post("/proxy/api/v1/users/42")
    assert response.status_code == 200
    data = response.json()
    assert data["server"] == "primary"
    assert data["destination"] == "user-service"
    assert data["params"] == {"id": "42"}
    assert data["routing_decision"] == "Primary server selected: server is healthy"


@pytest.mark.asyncio
async def test_proxy_fallback_when_primary_dead(
    client: AsyncClient, state_mgr: StateManager
) -> None:
    """When primary is dead but fallback is alive, routes to fallback."""
    await state_mgr.set_status("primary", HealthStatus.DEAD)
    response = await client.post("/proxy/api/v1/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["server"] == "fallback"
    assert data["destination"] == "order-service"
    assert data["params"] == {}
    assert (
        data["routing_decision"]
        == "Fallback server selected: primary server is unhealthy"
    )


@pytest.mark.asyncio
async def test_proxy_503_both_servers_dead(
    client: AsyncClient, state_mgr: StateManager
) -> None:
    """When both servers are dead, returns 503."""
    await state_mgr.set_status("primary", HealthStatus.DEAD)
    await state_mgr.set_status("fallback", HealthStatus.DEAD)
    response = await client.post("/proxy/api/v1/users")
    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "No healthy servers available"
    assert data["path"] == "api/v1/users"


@pytest.mark.asyncio
async def test_proxy_404_no_route_matched(client: AsyncClient) -> None:
    """When no route matches the path, returns 404."""
    response = await client.post("/proxy/api/v1/unknown")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "No route matched"
    assert data["path"] == "api/v1/unknown"


@pytest.mark.asyncio
async def test_proxy_400_empty_path(app: FastAPI) -> None:
    """When path is whitespace only, returns 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/proxy/ ")
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Request path must not be empty"
        assert data["path"] == " "


@pytest.mark.asyncio
async def test_proxy_400_invalid_characters(client: AsyncClient) -> None:
    """When path has invalid characters, returns 400 listing them."""
    response = await client.post("/proxy/api/@!/test")
    assert response.status_code == 400
    data = response.json()
    assert "Invalid characters in path" in data["error"]
    assert "@" in data["error"]
    assert "!" in data["error"]
    assert data["path"] == "api/@!/test"


@pytest.mark.asyncio
async def test_proxy_400_whitespace_path(client: AsyncClient) -> None:
    """Whitespace-only path returns 400."""
    response = await client.post("/proxy/   ")
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "Request path must not be empty"


@pytest.mark.asyncio
async def test_proxy_success_response_has_iso_timestamp(
    client: AsyncClient,
) -> None:
    """Successful response timestamp is in ISO 8601 format with timezone."""
    response = await client.post("/proxy/api/v1/users")
    assert response.status_code == 200
    data = response.json()
    ts = datetime.fromisoformat(data["timestamp"])
    assert ts.tzinfo is not None


@pytest.mark.asyncio
async def test_proxy_routing_decision_logged(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Routing decisions are logged with required fields."""
    with caplog.at_level(logging.INFO, logger="app.routes"):
        response = await client.post("/proxy/api/v1/users/99")
    assert response.status_code == 200
    assert any("Routing decision" in record.message for record in caplog.records)
    log_msg = next(
        r.message for r in caplog.records if "Routing decision" in r.message
    )
    assert "api/v1/users/99" in log_msg
    assert "user-service" in log_msg
    assert "primary" in log_msg


@pytest.mark.asyncio
async def test_proxy_orders_with_id(client: AsyncClient) -> None:
    """Proxy resolves order routes with dynamic id parameter."""
    response = await client.post("/proxy/api/v1/orders/123")
    assert response.status_code == 200
    data = response.json()
    assert data["destination"] == "order-service"
    assert data["params"] == {"id": "123"}


@pytest.mark.asyncio
async def test_proxy_fallback_routing_logged(
    client: AsyncClient,
    state_mgr: StateManager,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fallback routing decision is logged correctly."""
    await state_mgr.set_status("primary", HealthStatus.DEAD)
    with caplog.at_level(logging.INFO, logger="app.routes"):
        response = await client.post("/proxy/api/v1/users")
    assert response.status_code == 200
    log_msg = next(
        r.message for r in caplog.records if "Routing decision" in r.message
    )
    assert "fallback" in log_msg
