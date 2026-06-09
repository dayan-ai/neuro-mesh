"""Pydantic data models and enums for the NEURO-MESH API Gateway.

This module defines:
- HealthStatus enum (Alive/Dead)
- ServerProfile model for backend server records
- Request/Response schemas for proxy and health endpoints
"""

from enum import Enum

from pydantic import BaseModel


class HealthStatus(str, Enum):
    """Health status for backend servers.

    Uses str mixin to enable direct JSON serialization of enum values.
    """

    ALIVE = "Alive"
    DEAD = "Dead"


class ServerProfile(BaseModel):
    """Data model representing a registered backend server.

    Attributes:
        server_id: Unique identifier for the server (e.g., "primary", "fallback").
        address: Network address of the backend server.
        status: Current health status of the server.
    """

    server_id: str
    address: str
    status: HealthStatus


class HealthUpdateRequest(BaseModel):
    """Request body for updating a server's health status.

    Attributes:
        status: The new health status value. Must be "Alive" or "Dead".
    """

    status: str


class ProxySuccessResponse(BaseModel):
    """Response body for a successful proxy routing decision.

    Attributes:
        server: The identifier of the selected backend server.
        destination: The resolved route destination service name.
        params: Dictionary of extracted dynamic path parameters.
        routing_decision: Rationale string explaining the routing choice.
        timestamp: ISO 8601 formatted timestamp of the routing decision.
    """

    server: str
    destination: str
    params: dict[str, str]
    routing_decision: str
    timestamp: str


class ProxyErrorResponse(BaseModel):
    """Response body for proxy error responses (400, 404, 503).

    Attributes:
        error: Description of the error that occurred.
        path: The original request path that triggered the error.
    """

    error: str
    path: str


class HealthListResponse(BaseModel):
    """Response body for GET /health listing all registered servers.

    Attributes:
        servers: Mapping of server_id to a dictionary containing
                 the server's address and current health status.
    """

    servers: dict[str, dict[str, str]]


class HealthUpdateResponse(BaseModel):
    """Response body for a successful health status update.

    Attributes:
        server_id: The identifier of the updated server.
        status: The new health status value after the update.
    """

    server_id: str
    status: str