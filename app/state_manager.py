"""Hash-map-based State Manager for server health tracking.

This module implements the StateManager class that maintains real-time
health status for registered backend servers using Python dictionaries
for O(1) lookup performance.

Implementation:
- StateManager class with dict-backed storage
- asyncio.Lock for concurrent access serialization
- get_status(), set_status(), list_all() async methods
- Initialized with primary (Alive) and fallback (Alive) servers
- KeyError for unknown server identifiers
- ValueError for invalid status values
"""

import asyncio

from app.models import HealthStatus, ServerProfile


class StateManager:
    """Hash-map-based server health tracker with concurrency control.

    Uses Python dictionaries for O(1) amortized lookup by server identifier.
    All read and write operations acquire an asyncio.Lock to prevent
    partial-update observation under concurrency.

    Attributes:
        _servers: Dictionary mapping server_id to ServerProfile.
        _lock: asyncio.Lock serializing all state access.
    """

    _servers: dict[str, ServerProfile]
    _lock: asyncio.Lock

    def __init__(self) -> None:
        """Initialize StateManager with primary and fallback servers both Alive."""
        self._servers = {
            "primary": ServerProfile(
                server_id="primary",
                address="http://primary:8001",
                status=HealthStatus.ALIVE,
            ),
            "fallback": ServerProfile(
                server_id="fallback",
                address="http://fallback:8002",
                status=HealthStatus.ALIVE,
            ),
        }
        self._lock = asyncio.Lock()

    async def get_status(self, server_id: str) -> HealthStatus:
        """Retrieve the current health status of a server by its identifier.

        O(1) lookup via dictionary access.

        Args:
            server_id: The unique identifier of the server to query.

        Returns:
            The current HealthStatus of the specified server.

        Raises:
            KeyError: If server_id is not a registered server identifier.
        """
        async with self._lock:
            if server_id not in self._servers:
                raise KeyError(f"Server not found: {server_id}")
            return self._servers[server_id].status

    async def set_status(self, server_id: str, status: HealthStatus) -> ServerProfile:
        """Update the health status of a server by its identifier.

        Validates that the status is a valid HealthStatus enum value and
        that the server_id exists in the registry.

        Args:
            server_id: The unique identifier of the server to update.
            status: The new HealthStatus value (must be Alive or Dead).

        Returns:
            The updated ServerProfile after the status change.

        Raises:
            KeyError: If server_id is not a registered server identifier.
            ValueError: If status is not a valid HealthStatus value.
        """
        async with self._lock:
            if not isinstance(status, HealthStatus):
                try:
                    status = HealthStatus(status)
                except ValueError:
                    raise ValueError(
                        f"Invalid status value: {status!r}. Must be 'Alive' or 'Dead'."
                    )
            if server_id not in self._servers:
                raise KeyError(f"Server not found: {server_id}")
            self._servers[server_id] = self._servers[server_id].model_copy(
                update={"status": status}
            )
            return self._servers[server_id]

    async def list_all(self) -> dict[str, ServerProfile]:
        """Return a snapshot of all registered servers.

        Returns a shallow copy of the internal dictionary so callers cannot
        mutate the manager's state directly.

        Returns:
            Dictionary mapping server_id to ServerProfile for all servers.
        """
        async with self._lock:
            return dict(self._servers)
