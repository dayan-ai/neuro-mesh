"""Route handlers for the NEURO-MESH API Gateway.

This module defines the FastAPI route handler functions for:
- POST /proxy/{path:path} - Universal proxy endpoint
- GET /health - Server health listing
- PUT /health/{server_id} - Server health update

Implementation:
- proxy_handler: validates path, resolves via Trie, evaluates health, routes
- health_list: returns all server statuses
- health_update: updates a server's health status with validation
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models import HealthStatus, ProxyErrorResponse, ProxySuccessResponse
from app.state_manager import StateManager
from app.trie import Trie
from app.validation import validate_path

logger = logging.getLogger(__name__)

# Module-level references set by main.py during app initialization
trie: Trie | None = None
state_manager: StateManager | None = None

router = APIRouter()


@router.post("/proxy/{path:path}")
async def proxy_handler(path: str) -> JSONResponse:
    """Universal proxy endpoint that intercepts requests and performs routing.

    Validates the incoming path, resolves the route via the Trie, evaluates
    backend server health, and returns a routing decision.

    Args:
        path: The request sub-path captured by FastAPI's path converter.

    Returns:
        JSONResponse with appropriate status code and body:
        - 200 with ProxySuccessResponse on successful routing
        - 400 for empty/whitespace or invalid character paths
        - 404 when no route matches
        - 503 when all servers are dead
    """
    # Step 1: Validate path
    validation_error = validate_path(path)
    if validation_error is not None:
        error_response = ProxyErrorResponse(error=validation_error, path=path)
        return JSONResponse(
            status_code=400,
            content=error_response.model_dump(),
        )

    # Step 2: Resolve route via Trie
    assert trie is not None, "Trie not initialized"
    result = trie.resolve(path)
    if result is None:
        error_response = ProxyErrorResponse(error="No route matched", path=path)
        return JSONResponse(
            status_code=404,
            content=error_response.model_dump(),
        )

    destination, params = result

    # Step 3: Evaluate server health and make routing decision
    assert state_manager is not None, "StateManager not initialized"

    primary_status = await state_manager.get_status("primary")

    if primary_status == HealthStatus.ALIVE:
        selected_server = "primary"
        routing_decision = "Primary server selected: server is healthy"
    else:
        fallback_status = await state_manager.get_status("fallback")
        if fallback_status == HealthStatus.ALIVE:
            selected_server = "fallback"
            routing_decision = (
                "Fallback server selected: primary server is unhealthy"
            )
        else:
            error_response = ProxyErrorResponse(
                error="No healthy servers available", path=path
            )
            return JSONResponse(
                status_code=503,
                content=error_response.model_dump(),
            )

    # Step 4: Build success response with ISO 8601 timestamp
    timestamp = datetime.now(timezone.utc).isoformat()

    success_response = ProxySuccessResponse(
        server=selected_server,
        destination=destination,
        params=params,
        routing_decision=routing_decision,
        timestamp=timestamp,
    )

    # Step 5: Log the routing decision
    logger.info(
        "Routing decision: timestamp=%s path=%s destination=%s server=%s",
        timestamp,
        path,
        destination,
        selected_server,
    )

    return JSONResponse(
        status_code=200,
        content=success_response.model_dump(),
    )
