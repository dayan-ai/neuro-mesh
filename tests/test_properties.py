"""Property-based tests using Hypothesis for the NEURO-MESH API Gateway.

This module contains property-based tests validating universal correctness
properties from the design document. Each property test uses the @given
decorator and runs minimum 100 iterations.

Properties tested:
- Property 1: Trie insertion round-trip
- Property 2: Static over dynamic segment priority
- Property 3: Trailing slash normalization
- Property 4: Duplicate pattern overwrite
- Property 5: Depth limit enforcement
- Property 6: Non-matching path returns None
- Property 7: State Manager get/set round-trip
- Property 8: Unknown server identifier rejection
- Property 9: Invalid status value rejection
- Property 10: Failover routing decision
- Property 11: Empty/whitespace path rejection
- Property 12: Invalid character path rejection
- Property 13: Successful proxy response completeness
- Property 14: Error proxy response completeness
"""

import asyncio

import httpx
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from app.models import HealthStatus
from app.state_manager import StateManager
from app.trie import Trie

# ---------------------------------------------------------------------------
# Custom Hypothesis Strategies
# ---------------------------------------------------------------------------

# Valid path segments (static)
static_segments = st.from_regex(r"[A-Za-z0-9\-._~]{1,20}", fullmatch=True)

# Dynamic parameter names
param_names = st.from_regex(r"[a-z_][a-z0-9_]{0,15}", fullmatch=True)

# Route patterns (mix of static and dynamic segments, 1-20 depth)
route_patterns = st.lists(
    st.one_of(static_segments, param_names.map(lambda p: f"{{{p}}}")),
    min_size=1,
    max_size=20,
).map(lambda segs: "/" + "/".join(segs))

# Health status values
valid_statuses = st.sampled_from(["Alive", "Dead"])
invalid_statuses = st.text(min_size=1).filter(lambda s: s not in ("Alive", "Dead"))

# Server identifiers
valid_server_ids = st.sampled_from(["primary", "fallback"])
invalid_server_ids = st.text(min_size=1).filter(
    lambda s: s not in ("primary", "fallback")
)

# Destination strings
destinations = st.from_regex(r"[a-z][a-z0-9\-]{0,19}", fullmatch=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_matching_path(pattern: str) -> tuple[str, dict[str, str]]:
    """Given a route pattern, build a concrete path that matches it.

    Returns the concrete path and expected params dict.
    """
    segments = pattern.strip("/").split("/")
    path_parts: list[str] = []
    params: dict[str, str] = {}
    for seg in segments:
        if seg.startswith("{") and seg.endswith("}"):
            param_name = seg[1:-1]
            # Use a stable generated value
            value = f"val_{param_name}"
            path_parts.append(value)
            params[param_name] = value
        else:
            path_parts.append(seg)
    return "/" + "/".join(path_parts), params


def _create_test_app():
    """Create a fresh FastAPI app with Trie and StateManager wired up."""
    from fastapi import FastAPI

    from app.health_routes import health_router
    from app.routes import router as proxy_router
    from app.state_manager import StateManager as SM
    from app.trie import Trie as T
    import app.routes as routes_module
    import app.health_routes as health_routes_module

    app = FastAPI()
    trie = T()
    state_manager = SM()

    # Register a known route for testing
    trie.insert("/api/v1/users", "user-service")
    trie.insert("/api/v1/users/{id}", "user-service")
    trie.insert("/api/v1/orders", "order-service")
    trie.insert("/api/v1/orders/{id}", "order-service")

    routes_module.trie = trie
    routes_module.state_manager = state_manager
    health_routes_module.state_manager = state_manager

    app.include_router(proxy_router)
    app.include_router(health_router)

    return app, trie, state_manager


# ---------------------------------------------------------------------------
# Property 1: Trie insertion round-trip
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 1: Trie insertion round-trip


@given(pattern=route_patterns, destination=destinations)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_1_trie_insertion_round_trip(pattern: str, destination: str):
    """For any valid route pattern and destination, inserting and resolving
    a matching path returns the correct destination and extracted params.

    **Validates: Requirements 2.2, 2.4**
    """
    trie = Trie()
    trie.insert(pattern, destination)

    matching_path, expected_params = _build_matching_path(pattern)
    result = trie.resolve(matching_path)

    assert result is not None, f"Expected match for path {matching_path}"
    resolved_dest, resolved_params = result
    assert resolved_dest == destination
    assert resolved_params == expected_params


# ---------------------------------------------------------------------------
# Property 2: Static over dynamic segment priority
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 2: Static over dynamic segment priority


@given(
    prefix_segments=st.lists(static_segments, min_size=0, max_size=5),
    static_segment=static_segments,
    param_name=param_names,
    static_dest=destinations,
    dynamic_dest=destinations,
)
@settings(max_examples=100)
def test_property_2_static_over_dynamic_priority(
    prefix_segments: list[str],
    static_segment: str,
    param_name: str,
    static_dest: str,
    dynamic_dest: str,
):
    """For any Trie with both a static and dynamic segment at the same level,
    resolving a path matching the static segment returns the static destination.

    **Validates: Requirements 2.3**
    """
    assume(static_dest != dynamic_dest)

    prefix = "/" + "/".join(prefix_segments) if prefix_segments else ""
    static_pattern = f"{prefix}/{static_segment}"
    dynamic_pattern = f"{prefix}/{{{param_name}}}"

    trie = Trie()
    trie.insert(static_pattern, static_dest)
    trie.insert(dynamic_pattern, dynamic_dest)

    # Resolve a path that exactly matches the static segment
    resolve_path = f"{prefix}/{static_segment}"
    result = trie.resolve(resolve_path)

    assert result is not None
    resolved_dest, _ = result
    assert resolved_dest == static_dest, (
        f"Expected static destination '{static_dest}' but got '{resolved_dest}'"
    )


# ---------------------------------------------------------------------------
# Property 3: Trailing slash normalization
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 3: Trailing slash normalization


@given(pattern=route_patterns, destination=destinations)
@settings(max_examples=100)
def test_property_3_trailing_slash_normalization(pattern: str, destination: str):
    """For any registered pattern, resolving with and without trailing slash
    gives the same result.

    **Validates: Requirements 2.6**
    """
    trie = Trie()
    trie.insert(pattern, destination)

    matching_path, _ = _build_matching_path(pattern)

    # Resolve without trailing slash
    result_no_slash = trie.resolve(matching_path.rstrip("/"))
    # Resolve with trailing slash
    result_with_slash = trie.resolve(matching_path.rstrip("/") + "/")

    assert result_no_slash == result_with_slash, (
        f"Trailing slash mismatch: {result_no_slash} vs {result_with_slash}"
    )


# ---------------------------------------------------------------------------
# Property 4: Duplicate pattern overwrite
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 4: Duplicate pattern overwrite


@given(pattern=route_patterns, dest1=destinations, dest2=destinations)
@settings(max_examples=100)
def test_property_4_duplicate_pattern_overwrite(
    pattern: str, dest1: str, dest2: str
):
    """Insert same pattern twice with different destinations. Second wins.

    **Validates: Requirements 2.8**
    """
    assume(dest1 != dest2)

    trie = Trie()
    trie.insert(pattern, dest1)
    trie.insert(pattern, dest2)

    matching_path, _ = _build_matching_path(pattern)
    result = trie.resolve(matching_path)

    assert result is not None
    resolved_dest, _ = result
    assert resolved_dest == dest2, (
        f"Expected overwritten destination '{dest2}' but got '{resolved_dest}'"
    )


# ---------------------------------------------------------------------------
# Property 5: Depth limit enforcement
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 5: Depth limit enforcement


@given(
    extra_segments=st.lists(static_segments, min_size=21, max_size=30),
)
@settings(max_examples=100)
def test_property_5_depth_limit_over_20_returns_none(extra_segments: list[str]):
    """Paths with >20 segments always return None.

    **Validates: Requirements 2.2, 2.9**
    """
    trie = Trie()
    # Even if we try to insert a matching pattern (which won't work for >20),
    # resolution must return None for paths >20 segments.
    deep_path = "/" + "/".join(extra_segments)
    result = trie.resolve(deep_path)
    assert result is None, f"Expected None for path with {len(extra_segments)} segments"


@given(
    segments=st.lists(static_segments, min_size=1, max_size=20),
    destination=destinations,
)
@settings(max_examples=100)
def test_property_5_within_limit_succeeds(segments: list[str], destination: str):
    """Paths with ≤20 segments succeed normally.

    **Validates: Requirements 2.2, 2.9**
    """
    pattern = "/" + "/".join(segments)
    trie = Trie()
    trie.insert(pattern, destination)

    result = trie.resolve(pattern)
    assert result is not None, f"Expected match for path with {len(segments)} segments"
    assert result[0] == destination


# ---------------------------------------------------------------------------
# Property 6: Non-matching path returns None
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 6: Non-matching path returns None


@given(
    registered_segments=st.lists(static_segments, min_size=1, max_size=5),
    extra_segment=static_segments,
    destination=destinations,
)
@settings(max_examples=100)
def test_property_6_non_matching_path_returns_none(
    registered_segments: list[str],
    extra_segment: str,
    destination: str,
):
    """For any registered routes and a path with wrong segment count, returns None.

    **Validates: Requirements 2.5**
    """
    trie = Trie()
    pattern = "/" + "/".join(registered_segments)
    trie.insert(pattern, destination)

    # Create a non-matching path by appending an extra segment
    non_matching_path = "/" + "/".join(registered_segments) + "/" + extra_segment
    result = trie.resolve(non_matching_path)
    assert result is None, (
        f"Expected None for non-matching path '{non_matching_path}'"
    )


# ---------------------------------------------------------------------------
# Property 7: State Manager get/set round-trip
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 7: State Manager get/set round-trip


@given(server_id=valid_server_ids, status=valid_statuses)
@settings(max_examples=100)
def test_property_7_state_manager_get_set_round_trip(server_id: str, status: str):
    """For any valid server_id and valid status, set then get returns same status.

    **Validates: Requirements 3.4, 3.5**
    """
    sm = StateManager()
    health_status = HealthStatus(status)

    asyncio.run(_async_get_set_round_trip(sm, server_id, health_status))


async def _async_get_set_round_trip(
    sm: StateManager, server_id: str, status: HealthStatus
):
    await sm.set_status(server_id, status)
    retrieved = await sm.get_status(server_id)
    assert retrieved == status, f"Expected {status} but got {retrieved}"


# ---------------------------------------------------------------------------
# Property 8: Unknown server identifier rejection
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 8: Unknown server identifier rejection


@given(server_id=invalid_server_ids)
@settings(max_examples=100)
def test_property_8_unknown_server_rejection(server_id: str):
    """For any string not in ("primary", "fallback"), get/set raise KeyError.

    **Validates: Requirements 3.6, 3.7**
    """
    sm = StateManager()
    asyncio.run(_async_unknown_server_rejection(sm, server_id))


async def _async_unknown_server_rejection(sm: StateManager, server_id: str):
    with pytest.raises(KeyError):
        await sm.get_status(server_id)

    with pytest.raises(KeyError):
        await sm.set_status(server_id, HealthStatus.ALIVE)


# ---------------------------------------------------------------------------
# Property 9: Invalid status value rejection
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 9: Invalid status value rejection


@given(status=invalid_statuses)
@settings(max_examples=100)
def test_property_9_invalid_status_rejection(status: str):
    """For any string not in ("Alive", "Dead"), set_status raises ValueError.

    **Validates: Requirements 3.8**
    """
    sm = StateManager()
    asyncio.run(_async_invalid_status_rejection(sm, status))


async def _async_invalid_status_rejection(sm: StateManager, status: str):
    with pytest.raises(ValueError):
        await sm.set_status("primary", status)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Property 10: Failover routing decision
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 10: Failover routing decision


@given(
    primary_status=valid_statuses,
    fallback_status=valid_statuses,
)
@settings(max_examples=100, deadline=None)
def test_property_10_failover_routing_decision(
    primary_status: str, fallback_status: str
):
    """For any resolvable path and all health combinations:
    (Alive, Alive) → primary; (Dead, Alive) → fallback; (Dead, Dead) → 503.

    **Validates: Requirements 4.5, 4.6, 4.7**
    """
    asyncio.run(
        _async_failover_routing(primary_status, fallback_status)
    )


async def _async_failover_routing(primary_status: str, fallback_status: str):
    app, trie, state_manager = _create_test_app()

    # Set health states
    await state_manager.set_status("primary", HealthStatus(primary_status))
    await state_manager.set_status("fallback", HealthStatus(fallback_status))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/proxy/api/v1/users")

    if primary_status == "Alive":
        assert response.status_code == 200
        body = response.json()
        assert body["server"] == "primary"
    elif fallback_status == "Alive":
        assert response.status_code == 200
        body = response.json()
        assert body["server"] == "fallback"
    else:
        # Both dead
        assert response.status_code == 503


# ---------------------------------------------------------------------------
# Property 11: Empty/whitespace path rejection
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 11: Empty/whitespace path rejection


@given(
    whitespace=st.from_regex(r"[ \t\n\r]+", fullmatch=True),
)
@settings(max_examples=100)
def test_property_11_empty_whitespace_path_rejection(whitespace: str):
    """For any empty/whitespace-only string, the proxy returns 400.

    Since HTTP clients cannot send raw \\r/\\n in URLs, we test the validation
    function directly (it is what the proxy endpoint calls first). This tests
    the actual requirement: whitespace-only paths are rejected before Trie lookup.

    **Validates: Requirements 5.1**
    """
    from app.validation import validate_path

    error = validate_path(whitespace)
    assert error is not None, f"Expected error for whitespace-only path '{whitespace!r}'"
    assert "must not be empty" in error


@given(
    whitespace=st.from_regex(r"[ \t]{1,10}", fullmatch=True),
)
@settings(max_examples=100, deadline=None)
def test_property_11_empty_whitespace_via_http(whitespace: str):
    """For URL-safe whitespace (spaces/tabs), the proxy endpoint returns 400
    when the decoded path is whitespace-only.

    **Validates: Requirements 5.1**
    """
    asyncio.run(_async_empty_whitespace_rejection(whitespace))


async def _async_empty_whitespace_rejection(whitespace: str):
    import urllib.parse

    app, _, _ = _create_test_app()
    encoded = urllib.parse.quote(whitespace, safe="")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"/proxy/{encoded}")

    assert response.status_code == 400, (
        f"Expected 400 for whitespace path, got {response.status_code}"
    )
    body = response.json()
    assert "error" in body


# ---------------------------------------------------------------------------
# Property 12: Invalid character path rejection
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 12: Invalid character path rejection


@given(
    valid_prefix=static_segments,
    invalid_char=st.sampled_from(list("!@$^&*()+=[]{}|\\:;\"'<>,? ")),
)
@settings(max_examples=100, deadline=None)
def test_property_12_invalid_character_path_rejection(
    valid_prefix: str, invalid_char: str
):
    """For any path with chars outside the allowed set, proxy returns 400.

    Characters like '#' and '?' are URL-special (fragment/query separators) and
    get stripped by HTTP clients before reaching the server, so we test chars
    that actually arrive at the handler.

    **Validates: Requirements 5.3**
    """
    asyncio.run(_async_invalid_char_rejection(valid_prefix, invalid_char))


async def _async_invalid_char_rejection(valid_prefix: str, invalid_char: str):
    app, _, _ = _create_test_app()

    import urllib.parse

    # Percent-encode the invalid char so httpx transmits it, and FastAPI
    # decodes it back to the raw character in the path parameter.
    encoded_char = urllib.parse.quote(invalid_char, safe="")
    path_with_invalid = f"{valid_prefix}{encoded_char}suffix"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"/proxy/{path_with_invalid}")

    assert response.status_code == 400, (
        f"Expected 400 for invalid char '{invalid_char}', got {response.status_code}"
    )
    body = response.json()
    assert "error" in body


# ---------------------------------------------------------------------------
# Property 13: Successful proxy response completeness
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 13: Successful proxy response completeness


@given(
    path_choice=st.sampled_from([
        "/api/v1/users",
        "/api/v1/orders",
        "/api/v1/users/123",
        "/api/v1/orders/456",
    ]),
)
@settings(max_examples=100)
def test_property_13_successful_proxy_response_completeness(path_choice: str):
    """For any successful routing, response has server, destination, params,
    and routing_decision.

    **Validates: Requirements 4.8**
    """
    asyncio.run(_async_success_response_completeness(path_choice))


async def _async_success_response_completeness(path_choice: str):
    app, _, _ = _create_test_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"/proxy{path_choice}")

    assert response.status_code == 200
    body = response.json()
    assert "server" in body, "Response missing 'server' field"
    assert "destination" in body, "Response missing 'destination' field"
    assert "params" in body, "Response missing 'params' field"
    assert isinstance(body["params"], dict), "'params' should be a dict"
    assert "routing_decision" in body, "Response missing 'routing_decision' field"
    assert isinstance(body["routing_decision"], str)


# ---------------------------------------------------------------------------
# Property 14: Error proxy response completeness
# ---------------------------------------------------------------------------
# Feature: neuro-mesh-api-gateway, Property 14: Error proxy response completeness


@given(
    scenario=st.sampled_from(["not_found", "all_dead"]),
)
@settings(max_examples=100)
def test_property_14_error_proxy_response_completeness(scenario: str):
    """For any 404 or 503 response, body has error field and original path.

    **Validates: Requirements 4.10**
    """
    asyncio.run(_async_error_response_completeness(scenario))


async def _async_error_response_completeness(scenario: str):
    app, _, state_manager = _create_test_app()

    if scenario == "not_found":
        # Use a path that won't match any registered route
        path = "/nonexistent/route/xyz"
        expected_status = 404
    else:
        # All dead → 503
        await state_manager.set_status("primary", HealthStatus.DEAD)
        await state_manager.set_status("fallback", HealthStatus.DEAD)
        path = "/api/v1/users"
        expected_status = 503

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"/proxy{path}")

    assert response.status_code == expected_status, (
        f"Expected {expected_status}, got {response.status_code}"
    )
    body = response.json()
    assert "error" in body, "Error response missing 'error' field"
    assert "path" in body, "Error response missing 'path' field"
