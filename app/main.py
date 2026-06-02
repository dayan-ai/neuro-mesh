"""NEURO-MESH Phase 1: Fault-Tolerant API Gateway application entry point.

This module wires together the Trie router, State Manager, and route handlers
into a single FastAPI application instance. It configures startup events,
global exception handling, and route registration.

Implementation:
- FastAPI app instantiation with lifespan context manager
- Pre-configured route registration in the Trie at startup
- Global exception handler for unhandled errors (logs details, returns generic 500)
- Configurable host (default 0.0.0.0) and port (default 8000)
"""

import logging
import traceback
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.health_routes import health_router
from app.routes import router as proxy_router
from app.state_manager import StateManager
from app.trie import Trie
import app.health_routes as health_routes_module
import app.routes as routes_module

logger = logging.getLogger(__name__)

# Configuration defaults
DEFAULT_HOST: str = "0.0.0.0"
DEFAULT_PORT: int = 8000

# Pre-configured routes registered at startup (pattern, destination)
STARTUP_ROUTES: list[tuple[str, str]] = [
    ("/api/v1/users", "user-service"),
    ("/api/v1/users/{id}", "user-service"),
    ("/api/v1/orders", "order-service"),
    ("/api/v1/orders/{id}", "order-service"),
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events.

    On startup:
    - Creates Trie and StateManager instances
    - Registers pre-configured routes in the Trie
    - Wires module-level globals in routes and health_routes modules
    - Logs host and port configuration
    """
    # Create shared instances
    trie = Trie()
    state_manager = StateManager()

    # Register pre-configured routes
    for pattern, destination in STARTUP_ROUTES:
        trie.insert(pattern, destination)

    # Wire module-level globals used by route handlers
    routes_module.trie = trie
    routes_module.state_manager = state_manager
    health_routes_module.state_manager = state_manager

    # Store on app state for access if needed
    app.state.trie = trie
    app.state.state_manager = state_manager

    logger.info("Gateway started on %s:%d", DEFAULT_HOST, DEFAULT_PORT)

    yield

    # Shutdown
    logger.info("Gateway shutting down")


app = FastAPI(title="NEURO-MESH API Gateway", lifespan=lifespan)

# Include routers
app.include_router(proxy_router)
app.include_router(health_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch all unhandled exceptions.

    Logs the exception type, message, and full stack trace internally.
    Returns a generic 500 response with no internal details exposed.
    """
    logger.error(
        "Unhandled exception: type=%s message=%s\n%s",
        type(exc).__name__,
        str(exc),
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT)
