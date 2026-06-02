"""Unit tests for the server health management endpoints.

Tests cover:
- GET /health response format and content
- PUT /health/{server_id} with valid data (primary and fallback)
- PUT with unknown server_id returns 404
- PUT with invalid status value returns 422
- PUT with malformed/missing body returns 422
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from app.health_routes import health_router
from app.state_manager import StateManager
import app.health_routes as health_routes_module


@pytest.fixture
def app_with_health() -> FastAPI:
    """Build a minimal FastAPI app with the health router wired to a real StateManager."""
    app = FastAPI()
    sm = StateManager()
    health_routes_module.state_manager = sm
    app.include_router(health_router)
    return app


@pytest_asyncio.fixture
async def client(app_with_health: FastAPI) -> AsyncClient:
    """Create an httpx AsyncClient bound to the test app."""
    transport = ASGITransport(app=app_with_health)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_health_returns_all_servers(client: AsyncClient) -> None:
    """GET /health returns both servers with correct structure."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "servers" in data
    servers = data["servers"]
    assert "primary" in servers
    assert "fallback" in servers
    assert servers["primary"]["address"] == "http://primary:8001"
    assert servers["primary"]["status"] == "Alive"
    assert servers["fallback"]["address"] == "http://fallback:8002"
    assert servers["fallback"]["status"] == "Alive"


@pytest.mark.asyncio
async def test_put_health_primary_valid(client: AsyncClient) -> None:
    """PUT /health/primary with valid status returns 200."""
    response = await client.put(
        "/health/primary",
        json={"status": "Dead"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["server_id"] == "primary"
    assert data["status"] == "Dead"


@pytest.mark.asyncio
async def test_put_health_fallback_valid(client: AsyncClient) -> None:
    """PUT /health/fallback with valid status returns 200."""
    response = await client.put(
        "/health/fallback",
        json={"status": "Dead"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["server_id"] == "fallback"
    assert data["status"] == "Dead"


@pytest.mark.asyncio
async def test_put_health_toggle_alive(client: AsyncClient) -> None:
    """PUT /health/primary with Alive status returns 200."""
    # Set to Dead first
    await client.put("/health/primary", json={"status": "Dead"})
    # Toggle back to Alive
    response = await client.put(
        "/health/primary",
        json={"status": "Alive"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["server_id"] == "primary"
    assert data["status"] == "Alive"


@pytest.mark.asyncio
async def test_put_health_unknown_server_returns_404(client: AsyncClient) -> None:
    """PUT /health/unknown_id returns 404 with error message."""
    response = await client.put(
        "/health/unknown_id",
        json={"status": "Alive"},
    )
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "Server not found: unknown_id"


@pytest.mark.asyncio
async def test_put_health_invalid_status_returns_422(client: AsyncClient) -> None:
    """PUT /health/primary with invalid status returns 422."""
    response = await client.put(
        "/health/primary",
        json={"status": "Unknown"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "Status must be 'Alive' or 'Dead'"


@pytest.mark.asyncio
async def test_put_health_empty_status_returns_422(client: AsyncClient) -> None:
    """PUT /health/primary with empty string status returns 422."""
    response = await client.put(
        "/health/primary",
        json={"status": ""},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "Status must be 'Alive' or 'Dead'"


@pytest.mark.asyncio
async def test_put_health_missing_status_field_returns_422(client: AsyncClient) -> None:
    """PUT /health/primary with missing status field returns 422."""
    response = await client.put(
        "/health/primary",
        json={"other_field": "value"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "Expected JSON body with 'status' field"


@pytest.mark.asyncio
async def test_put_health_malformed_body_returns_422(client: AsyncClient) -> None:
    """PUT /health/primary with non-JSON body returns 422."""
    response = await client.put(
        "/health/primary",
        content=b"not json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "Expected JSON body with 'status' field"


@pytest.mark.asyncio
async def test_get_health_reflects_status_changes(client: AsyncClient) -> None:
    """GET /health reflects status changes made via PUT."""
    # Change primary to Dead
    await client.put("/health/primary", json={"status": "Dead"})
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["servers"]["primary"]["status"] == "Dead"
    assert data["servers"]["fallback"]["status"] == "Alive"
