"""Unit tests for the hash-map State Manager.

Tests cover:
- Initialization with primary and fallback servers
- Health status get/set operations
- Unknown server identifier error handling
- Invalid status value error handling
- Concurrent access safety
"""

import asyncio

import pytest
import pytest_asyncio

from app.models import HealthStatus, ServerProfile
from app.state_manager import StateManager


@pytest_asyncio.fixture
async def state_manager() -> StateManager:
    """Create a fresh StateManager instance for each test."""
    return StateManager()


class TestInitialization:
    """Tests for StateManager initial state."""

    @pytest.mark.asyncio
    async def test_initial_primary_server_alive(self, state_manager: StateManager) -> None:
        """Primary server should be initialized with Alive status."""
        status = await state_manager.get_status("primary")
        assert status == HealthStatus.ALIVE

    @pytest.mark.asyncio
    async def test_initial_fallback_server_alive(self, state_manager: StateManager) -> None:
        """Fallback server should be initialized with Alive status."""
        status = await state_manager.get_status("fallback")
        assert status == HealthStatus.ALIVE

    @pytest.mark.asyncio
    async def test_initial_list_all_contains_both_servers(self, state_manager: StateManager) -> None:
        """list_all should return both primary and fallback servers."""
        servers = await state_manager.list_all()
        assert "primary" in servers
        assert "fallback" in servers
        assert len(servers) == 2

    @pytest.mark.asyncio
    async def test_initial_primary_address(self, state_manager: StateManager) -> None:
        """Primary server should have correct address."""
        servers = await state_manager.list_all()
        assert servers["primary"].address == "http://primary:8001"

    @pytest.mark.asyncio
    async def test_initial_fallback_address(self, state_manager: StateManager) -> None:
        """Fallback server should have correct address."""
        servers = await state_manager.list_all()
        assert servers["fallback"].address == "http://fallback:8002"


class TestGetStatus:
    """Tests for get_status method."""

    @pytest.mark.asyncio
    async def test_get_status_primary(self, state_manager: StateManager) -> None:
        """get_status should return HealthStatus for a valid server."""
        status = await state_manager.get_status("primary")
        assert isinstance(status, HealthStatus)
        assert status == HealthStatus.ALIVE

    @pytest.mark.asyncio
    async def test_get_status_fallback(self, state_manager: StateManager) -> None:
        """get_status should return HealthStatus for fallback server."""
        status = await state_manager.get_status("fallback")
        assert isinstance(status, HealthStatus)
        assert status == HealthStatus.ALIVE

    @pytest.mark.asyncio
    async def test_get_status_unknown_server_raises_key_error(self, state_manager: StateManager) -> None:
        """get_status should raise KeyError for unknown server_id."""
        with pytest.raises(KeyError):
            await state_manager.get_status("unknown_server")

    @pytest.mark.asyncio
    async def test_get_status_empty_string_raises_key_error(self, state_manager: StateManager) -> None:
        """get_status should raise KeyError for empty string server_id."""
        with pytest.raises(KeyError):
            await state_manager.get_status("")


class TestSetStatus:
    """Tests for set_status method."""

    @pytest.mark.asyncio
    async def test_set_status_to_dead(self, state_manager: StateManager) -> None:
        """set_status should update server status to Dead."""
        result = await state_manager.set_status("primary", HealthStatus.DEAD)
        assert result.status == HealthStatus.DEAD
        assert result.server_id == "primary"

    @pytest.mark.asyncio
    async def test_set_status_to_alive(self, state_manager: StateManager) -> None:
        """set_status should update server status to Alive."""
        await state_manager.set_status("primary", HealthStatus.DEAD)
        result = await state_manager.set_status("primary", HealthStatus.ALIVE)
        assert result.status == HealthStatus.ALIVE

    @pytest.mark.asyncio
    async def test_set_status_returns_updated_profile(self, state_manager: StateManager) -> None:
        """set_status should return the full updated ServerProfile."""
        result = await state_manager.set_status("fallback", HealthStatus.DEAD)
        assert isinstance(result, ServerProfile)
        assert result.server_id == "fallback"
        assert result.address == "http://fallback:8002"
        assert result.status == HealthStatus.DEAD

    @pytest.mark.asyncio
    async def test_set_status_persists(self, state_manager: StateManager) -> None:
        """set_status changes should be observable via get_status."""
        await state_manager.set_status("primary", HealthStatus.DEAD)
        status = await state_manager.get_status("primary")
        assert status == HealthStatus.DEAD

    @pytest.mark.asyncio
    async def test_set_status_unknown_server_raises_key_error(self, state_manager: StateManager) -> None:
        """set_status should raise KeyError for unknown server_id."""
        with pytest.raises(KeyError):
            await state_manager.set_status("nonexistent", HealthStatus.ALIVE)

    @pytest.mark.asyncio
    async def test_set_status_invalid_status_raises_value_error(self, state_manager: StateManager) -> None:
        """set_status should raise ValueError for invalid status value."""
        with pytest.raises(ValueError):
            await state_manager.set_status("primary", "Invalid")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_set_status_random_string_raises_value_error(self, state_manager: StateManager) -> None:
        """set_status should raise ValueError for random string status."""
        with pytest.raises(ValueError):
            await state_manager.set_status("primary", "Running")  # type: ignore[arg-type]


class TestListAll:
    """Tests for list_all method."""

    @pytest.mark.asyncio
    async def test_list_all_returns_dict(self, state_manager: StateManager) -> None:
        """list_all should return a dictionary."""
        result = await state_manager.list_all()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_list_all_returns_snapshot(self, state_manager: StateManager) -> None:
        """list_all should return a snapshot that doesn't affect internal state."""
        snapshot = await state_manager.list_all()
        # Mutate the snapshot
        snapshot.pop("primary", None)
        # Internal state should be unchanged
        servers = await state_manager.list_all()
        assert "primary" in servers

    @pytest.mark.asyncio
    async def test_list_all_reflects_status_changes(self, state_manager: StateManager) -> None:
        """list_all should reflect status changes made via set_status."""
        await state_manager.set_status("primary", HealthStatus.DEAD)
        servers = await state_manager.list_all()
        assert servers["primary"].status == HealthStatus.DEAD
        assert servers["fallback"].status == HealthStatus.ALIVE


class TestConcurrency:
    """Tests for concurrent access safety."""

    @pytest.mark.asyncio
    async def test_concurrent_reads(self, state_manager: StateManager) -> None:
        """Multiple concurrent reads should not raise errors."""
        tasks = [state_manager.get_status("primary") for _ in range(50)]
        results = await asyncio.gather(*tasks)
        assert all(s == HealthStatus.ALIVE for s in results)

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, state_manager: StateManager) -> None:
        """Multiple concurrent writes should not corrupt state."""
        async def toggle(sm: StateManager, status: HealthStatus) -> None:
            await sm.set_status("primary", status)

        tasks = []
        for i in range(50):
            status = HealthStatus.DEAD if i % 2 == 0 else HealthStatus.ALIVE
            tasks.append(toggle(state_manager, status))
        await asyncio.gather(*tasks)

        # After all writes, status should be one of the valid values
        final_status = await state_manager.get_status("primary")
        assert final_status in (HealthStatus.ALIVE, HealthStatus.DEAD)

    @pytest.mark.asyncio
    async def test_concurrent_read_write(self, state_manager: StateManager) -> None:
        """Concurrent reads and writes should not raise or corrupt state."""
        async def reader(sm: StateManager) -> HealthStatus:
            return await sm.get_status("primary")

        async def writer(sm: StateManager) -> None:
            await sm.set_status("primary", HealthStatus.DEAD)

        tasks = []
        for i in range(50):
            if i % 2 == 0:
                tasks.append(reader(state_manager))
            else:
                tasks.append(writer(state_manager))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        # No exceptions should have occurred
        for r in results:
            assert not isinstance(r, Exception)
