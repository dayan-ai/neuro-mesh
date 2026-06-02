"""End-to-end integration tests for the NEURO-MESH API Gateway.

Tests cover:
- Full proxy request lifecycle (route resolution → health evaluation → response)
- Complete failover scenario (primary → fallback → 503 → recovery)
- Health endpoint integration with proxy routing
- Concurrent access safety under load
- Error handling across the full stack

Validates: Requirements 4.1–4.10, 5.4, 6.1–6.5
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app, STARTUP_ROUTES
from app.state_manager import StateManager
from app.trie import Trie
import app.routes as routes_module
import app.health_routes as health_routes_module


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client with properly initialized app state.

    Manually initializes the Trie and StateManager (replicating the lifespan)
    so that all route handlers function correctly during testing.
    """
    # Initialize shared state (replicates lifespan startup logic)
    trie = Trie()
    state_manager = StateManager()

    for pattern, destination in STARTUP_ROUTES:
        trie.insert(pattern, destination)

    # Wire module-level globals
    routes_module.trie = trie
    routes_module.state_manager = state_manager
    health_routes_module.state_manager = state_manager

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup: reset module-level globals
    routes_module.trie = None
    routes_module.state_manager = None
    health_routes_module.state_manager = None


@pytest.mark.asyncio
async def test_full_proxy_lifecycle(client: AsyncClient) -> None:
    """Full lifecycle: proxy request resolves route, evaluates health, returns response.

    Validates: Requirements 4.1, 4.2, 4.4, 4.5, 4.8
    """
    response = await client.post("/proxy/api/v1/users")
    assert response.status_code == 200
    data = response.json()

    # Verify complete response structure
    assert data["server"] == "primary"
    assert data["destination"] == "user-service"
    assert data["params"] == {}
    assert "routing_decision" in data
    assert "Primary server selected" in data["routing_decision"]
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_dynamic_route_resolution_multiple_routes(client: AsyncClient) -> None:
    """Verify path params are extracted correctly across multiple routes.

    Validates: Requirements 2.4, 4.2, 4.8
    """
    # Users with dynamic id
    response = await client.post("/proxy/api/v1/users/42")
    assert response.status_code == 200
    data = response.json()
    assert data["destination"] == "user-service"
    assert data["params"] == {"id": "42"}

    # Orders with dynamic id
    response = await client.post("/proxy/api/v1/orders/789")
    assert response.status_code == 200
    data = response.json()
    assert data["destination"] == "order-service"
    assert data["params"] == {"id": "789"}


@pytest.mark.asyncio
async def test_complete_failover_scenario(client: AsyncClient) -> None:
    """Full failover: primary → fallback → 503 → recovery.

    Validates: Requirements 4.5, 4.6, 4.7, 6.2
    """
    # Step 1: Primary responds normally
    response = await client.post("/proxy/api/v1/users")
    assert response.status_code == 200
    data = response.json()
    assert data["server"] == "primary"

    # Step 2: Mark primary dead
    response = await client.put(
        "/health/primary", json={"status": "Dead"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Dead"

    # Step 3: Fallback serves traffic
    response = await client.post("/proxy/api/v1/users")
    assert response.status_code == 200
    data = response.json()
    assert data["server"] == "fallback"
    assert "Fallback server selected" in data["routing_decision"]

    # Step 4: Mark fallback dead → 503
    response = await client.put(
        "/health/fallback", json={"status": "Dead"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Dead"

    response = await client.post("/proxy/api/v1/users")
    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "No healthy servers available"
    assert data["path"] == "api/v1/users"

    # Step 5: Recovery – bring primary back
    response = await client.put(
        "/health/primary", json={"status": "Alive"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Alive"

    # Step 6: Primary serves traffic again
    response = await client.post("/proxy/api/v1/users")
    assert response.status_code == 200
    data = response.json()
    assert data["server"] == "primary"


@pytest.mark.asyncio
async def test_health_state_visibility(client: AsyncClient) -> None:
    """GET /health reflects changes made by PUT /health/{server_id}.

    Validates: Requirements 6.1, 6.2
    """
    # Initial state: both alive
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["servers"]["primary"]["status"] == "Alive"
    assert data["servers"]["fallback"]["status"] == "Alive"
    assert "address" in data["servers"]["primary"]
    assert "address" in data["servers"]["fallback"]

    # Update primary to Dead
    await client.put("/health/primary", json={"status": "Dead"})

    # Verify GET reflects the change
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["servers"]["primary"]["status"] == "Dead"
    assert data["servers"]["fallback"]["status"] == "Alive"


@pytest.mark.asyncio
async def test_concurrent_proxy_requests_with_health_toggle(
    client: AsyncClient,
) -> None:
    """Launch 50+ concurrent proxy requests while toggling health state.

    All responses must be valid (200 or 503, never corrupted).

    Validates: Requirements 5.4
    """

    async def send_proxy_request() -> int:
        """Send a proxy request and return status code."""
        resp = await client.post("/proxy/api/v1/users")
        data = resp.json()
        # Every response must be well-formed
        if resp.status_code == 200:
            assert "server" in data
            assert "destination" in data
            assert "params" in data
            assert "routing_decision" in data
            assert "timestamp" in data
            assert data["server"] in ("primary", "fallback")
        elif resp.status_code == 503:
            assert "error" in data
            assert data["error"] == "No healthy servers available"
        else:
            pytest.fail(f"Unexpected status code: {resp.status_code}")
        return resp.status_code

    async def toggle_health() -> None:
        """Toggle primary server health status rapidly."""
        for _ in range(10):
            await client.put("/health/primary", json={"status": "Dead"})
            await asyncio.sleep(0.001)
            await client.put("/health/primary", json={"status": "Alive"})
            await asyncio.sleep(0.001)

    # Launch 50 proxy requests concurrently with health toggling
    proxy_tasks = [send_proxy_request() for _ in range(50)]
    toggle_task = toggle_health()

    results = await asyncio.gather(*proxy_tasks, toggle_task, return_exceptions=True)

    # Check no exceptions were raised
    for result in results:
        if isinstance(result, Exception):
            pytest.fail(f"Concurrent operation raised exception: {result}")

    # All proxy results (first 50) should be valid status codes
    status_codes = [r for r in results[:50] if isinstance(r, int)]
    assert len(status_codes) == 50
    for code in status_codes:
        assert code in (200, 503)


@pytest.mark.asyncio
async def test_concurrent_health_updates(client: AsyncClient) -> None:
    """Multiple concurrent PUT requests to toggle health; state is always consistent.

    Validates: Requirements 5.4, 6.2
    """

    async def set_primary_dead() -> None:
        resp = await client.put("/health/primary", json={"status": "Dead"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "Dead"

    async def set_primary_alive() -> None:
        resp = await client.put("/health/primary", json={"status": "Alive"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "Alive"

    # Launch many concurrent health updates
    tasks = []
    for i in range(25):
        if i % 2 == 0:
            tasks.append(set_primary_dead())
        else:
            tasks.append(set_primary_alive())

    await asyncio.gather(*tasks)

    # After all updates, state must be one of the valid values
    response = await client.get("/health")
    assert response.status_code == 200
    status = response.json()["servers"]["primary"]["status"]
    assert status in ("Alive", "Dead")


@pytest.mark.asyncio
async def test_404_flow_unregistered_path(client: AsyncClient) -> None:
    """Unregistered paths return proper 404 through full stack.

    Validates: Requirements 4.3, 4.10
    """
    response = await client.post("/proxy/api/v1/unknown/path")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "No route matched"
    assert data["path"] == "api/v1/unknown/path"


@pytest.mark.asyncio
async def test_400_flow_invalid_path(client: AsyncClient) -> None:
    """Invalid paths return 400 through full stack.

    Validates: Requirements 5.1, 5.3
    """
    # Empty/whitespace path
    response = await client.post("/proxy/ ")
    assert response.status_code == 400
    data = response.json()
    assert "Request path must not be empty" in data["error"]

    # Invalid characters
    response = await client.post("/proxy/api/<script>alert</script>")
    assert response.status_code == 400
    data = response.json()
    assert "Invalid characters in path" in data["error"]


@pytest.mark.asyncio
async def test_all_registered_routes_work(client: AsyncClient) -> None:
    """Test each of the 4 pre-configured startup routes.

    Validates: Requirements 4.1, 4.2, 4.8
    """
    # Route 1: /api/v1/users (static)
    response = await client.post("/proxy/api/v1/users")
    assert response.status_code == 200
    data = response.json()
    assert data["destination"] == "user-service"
    assert data["params"] == {}

    # Route 2: /api/v1/users/{id} (dynamic)
    response = await client.post("/proxy/api/v1/users/100")
    assert response.status_code == 200
    data = response.json()
    assert data["destination"] == "user-service"
    assert data["params"] == {"id": "100"}

    # Route 3: /api/v1/orders (static)
    response = await client.post("/proxy/api/v1/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["destination"] == "order-service"
    assert data["params"] == {}

    # Route 4: /api/v1/orders/{id} (dynamic)
    response = await client.post("/proxy/api/v1/orders/555")
    assert response.status_code == 200
    data = response.json()
    assert data["destination"] == "order-service"
    assert data["params"] == {"id": "555"}
