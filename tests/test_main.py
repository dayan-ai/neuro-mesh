"""Unit tests for app/main.py — application wiring, lifespan, and exception handler.

Tests cover:
- Global exception handler catches unhandled exceptions (Req 5.2)
- Returns 500 with generic error message, no internal details leaked
- Logs exception type, message, and stack trace
- Startup registers routes in the Trie (Req 1.1, 1.2)
- Startup logs host and port configuration (Req 1.5)
- Default host/port configuration (Req 1.3)
- Both routers are included and functional
"""

import logging
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    STARTUP_ROUTES,
    app,
)


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client that triggers the app lifespan."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestConfiguration:
    """Tests for application configuration defaults."""

    def test_default_host(self) -> None:
        """Default host is 0.0.0.0."""
        assert DEFAULT_HOST == "0.0.0.0"

    def test_default_port(self) -> None:
        """Default port is 8000."""
        assert DEFAULT_PORT == 8000

    def test_startup_routes_registered(self) -> None:
        """Pre-configured routes match the design specification."""
        expected = [
            ("/api/v1/users", "user-service"),
            ("/api/v1/users/{id}", "user-service"),
            ("/api/v1/orders", "order-service"),
            ("/api/v1/orders/{id}", "order-service"),
        ]
        assert STARTUP_ROUTES == expected


class TestLifespan:
    """Tests for application lifespan startup and shutdown."""

    @pytest.mark.asyncio
    async def test_startup_logs_host_and_port(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Startup event logs the configured host and port."""
        from app.main import lifespan, app as main_app
        from app.trie import Trie
        from app.state_manager import StateManager
        import app.routes as routes_mod

        with caplog.at_level(logging.INFO, logger="app.main"):
            async with lifespan(main_app):
                pass

        startup_msgs = [
            r.message for r in caplog.records if "Gateway started" in r.message
        ]
        assert len(startup_msgs) >= 1
        assert "0.0.0.0" in startup_msgs[0]
        assert "8000" in startup_msgs[0]

    @pytest.mark.asyncio
    async def test_lifespan_wires_trie_and_state_manager(self) -> None:
        """Lifespan wires Trie and StateManager into route modules."""
        from app.main import lifespan, app as main_app
        import app.routes as routes_mod
        import app.health_routes as health_mod

        async with lifespan(main_app):
            assert routes_mod.trie is not None
            assert routes_mod.state_manager is not None
            assert health_mod.state_manager is not None

    @pytest.mark.asyncio
    async def test_lifespan_registers_startup_routes(self) -> None:
        """Lifespan registers all pre-configured routes in the Trie."""
        from app.main import lifespan, app as main_app
        import app.routes as routes_mod

        async with lifespan(main_app):
            trie = routes_mod.trie
            assert trie is not None
            # Verify routes are resolvable
            result = trie.resolve("api/v1/users")
            assert result is not None
            assert result[0] == "user-service"

            result = trie.resolve("api/v1/users/42")
            assert result is not None
            assert result == ("user-service", {"id": "42"})

            result = trie.resolve("api/v1/orders")
            assert result is not None
            assert result[0] == "order-service"

            result = trie.resolve("api/v1/orders/99")
            assert result is not None
            assert result == ("order-service", {"id": "99"})

    @pytest.mark.asyncio
    async def test_routes_are_functional_after_startup(
        self, client: AsyncClient
    ) -> None:
        """Pre-configured routes resolve correctly after startup."""
        response = await client.post("/proxy/api/v1/users")
        assert response.status_code == 200
        data = response.json()
        assert data["destination"] == "user-service"

    @pytest.mark.asyncio
    async def test_orders_route_functional(self, client: AsyncClient) -> None:
        """Order routes resolve after startup."""
        response = await client.post("/proxy/api/v1/orders/55")
        assert response.status_code == 200
        data = response.json()
        assert data["destination"] == "order-service"
        assert data["params"] == {"id": "55"}

    @pytest.mark.asyncio
    async def test_health_router_included(self, client: AsyncClient) -> None:
        """Health router is included and functional."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "servers" in data


class TestGlobalExceptionHandler:
    """Tests for the global exception handler (Req 5.2)."""

    @pytest.mark.asyncio
    async def test_unhandled_exception_returns_500(self) -> None:
        """Unhandled exceptions return 500 with generic message."""
        from fastapi import FastAPI

        from app.main import global_exception_handler

        # Create a test app with debug=False so exceptions hit the handler
        test_app = FastAPI(debug=False)

        @test_app.get("/crash")
        async def crash_endpoint() -> None:
            raise RuntimeError("Something broke internally")

        test_app.add_exception_handler(Exception, global_exception_handler)

        transport = ASGITransport(app=test_app, raise_app_exceptions=False)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            response = await ac.get("/crash")

        assert response.status_code == 500
        data = response.json()
        assert data == {"error": "Internal server error"}

    @pytest.mark.asyncio
    async def test_exception_handler_no_internal_details(self) -> None:
        """Response does not leak exception message or traceback."""
        from fastapi import FastAPI

        from app.main import global_exception_handler

        test_app = FastAPI(debug=False)

        @test_app.get("/secret-crash")
        async def secret_crash() -> None:
            raise ValueError("super secret database password 12345")

        test_app.add_exception_handler(Exception, global_exception_handler)

        transport = ASGITransport(app=test_app, raise_app_exceptions=False)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            response = await ac.get("/secret-crash")

        assert response.status_code == 500
        body = response.text
        assert "super secret" not in body
        assert "database password" not in body
        assert "12345" not in body
        assert response.json() == {"error": "Internal server error"}

    @pytest.mark.asyncio
    async def test_exception_handler_logs_details(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Exception handler logs type, message, and traceback."""
        from fastapi import FastAPI

        from app.main import global_exception_handler

        test_app = FastAPI(debug=False)

        @test_app.get("/log-crash")
        async def log_crash() -> None:
            raise TypeError("test error for logging")

        test_app.add_exception_handler(Exception, global_exception_handler)

        transport = ASGITransport(app=test_app, raise_app_exceptions=False)
        with caplog.at_level(logging.ERROR, logger="app.main"):
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as ac:
                await ac.get("/log-crash")

        error_records = [
            r for r in caplog.records if "Unhandled exception" in r.message
        ]
        assert len(error_records) >= 1
        msg = error_records[0].message
        assert "TypeError" in msg
        assert "test error for logging" in msg
