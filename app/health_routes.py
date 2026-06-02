"""Health management route handlers for the NEURO-MESH API Gateway.

This module defines the FastAPI route handlers for:
- GET /health - Server health listing (all registered servers)
- PUT /health/{server_id} - Server health update with validation

The health_router is an APIRouter that gets included into the main FastAPI app.
The module-level state_manager reference is set during app initialization.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models import HealthStatus, HealthUpdateRequest
from app.state_manager import StateManager

health_router = APIRouter()

# Module-level reference set during app initialization
state_manager: StateManager | None = None


@health_router.get("/health")
async def health_list() -> JSONResponse:
    """Return health status of all registered servers.

    Returns a JSON response with all servers' id, address, and status.
    Response format:
        {"servers": {"primary": {"address": "...", "status": "Alive"}, ...}}
    """
    if state_manager is None:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    servers = await state_manager.list_all()
    servers_dict: dict[str, dict[str, str]] = {}
    for server_id, profile in servers.items():
        servers_dict[server_id] = {
            "address": profile.address,
            "status": profile.status.value,
        }

    return JSONResponse(status_code=200, content={"servers": servers_dict})


@health_router.put("/health/{server_id}")
async def health_update(server_id: str, request: Request) -> JSONResponse:
    """Update health status of a server.

    Validates:
    - Request body is valid JSON with a 'status' field
    - server_id exists in the State Manager
    - status value is "Alive" or "Dead"

    Args:
        server_id: The identifier of the server to update.
        request: The raw request to parse JSON body from.

    Returns:
        200 with {"server_id": "...", "status": "..."} on success.
        404 if server_id not found.
        422 if status is invalid or body is malformed.
    """
    if state_manager is None:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    # Parse and validate request body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=422,
            content={"error": "Expected JSON body with 'status' field"},
        )

    if not isinstance(body, dict) or "status" not in body:
        return JSONResponse(
            status_code=422,
            content={"error": "Expected JSON body with 'status' field"},
        )

    status_value = body["status"]

    # Validate status value before hitting state manager
    if status_value not in ("Alive", "Dead"):
        return JSONResponse(
            status_code=422,
            content={"error": "Status must be 'Alive' or 'Dead'"},
        )

    # Attempt to update the state manager
    try:
        health_status = HealthStatus(status_value)
        updated_profile = await state_manager.set_status(server_id, health_status)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={"error": f"Server not found: {server_id}"},
        )
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"error": "Status must be 'Alive' or 'Dead'"},
        )

    return JSONResponse(
        status_code=200,
        content={"server_id": server_id, "status": updated_profile.status.value},
    )
