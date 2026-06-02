# Implementation Plan: NEURO-MESH Phase 1 Fault-Tolerant API Gateway

## Overview

This plan implements the NEURO-MESH Phase 1 API Gateway using Python with FastAPI. The implementation follows an incremental approach: first establishing project structure and data models, then building the Trie router and State Manager as independent components, wiring them together through the proxy endpoint, adding health management endpoints, and finally integrating error handling and concurrency safety.

## Tasks

- [x] 1. Set up project structure, dependencies, and core data models
  - [x] 1.1 Create project directory structure and install dependencies
    - Create `app/` package with `__init__.py`, `main.py`, `models.py`, `trie.py`, `state_manager.py`, `routes.py`, `validation.py`
    - Create `tests/` package with `__init__.py`, `conftest.py`, `test_trie.py`, `test_state_manager.py`, `test_proxy.py`, `test_health.py`, `test_properties.py`
    - Create `requirements.txt` with: `fastapi`, `uvicorn[standard]`, `pydantic`, `httpx`, `pytest`, `pytest-asyncio`, `hypothesis`, `pytest-cov`
    - _Requirements: 1.1, 1.4_

  - [x] 1.2 Implement data models and enums
    - Create `HealthStatus` enum with values `Alive` and `Dead` in `app/models.py`
    - Create `ServerProfile` Pydantic model with fields: `server_id: str`, `address: str`, `status: HealthStatus`
    - Create request/response Pydantic models: `HealthUpdateRequest`, `ProxySuccessResponse`, `ProxyErrorResponse`, `HealthListResponse`, `HealthUpdateResponse`
    - Add full type annotations on all fields and models
    - _Requirements: 1.4, 3.1, 3.3, 4.8, 4.10, 6.1, 6.2_

- [x] 2. Implement Custom Trie-Based Route Matching
  - [x] 2.1 Implement TrieNode class and Trie class with insert and resolve methods
    - Create `TrieNode` class with: `children: dict[str, TrieNode]`, `dynamic_child: TrieNode | None`, `dynamic_param_name: str | None`, `destination: str | None`
    - Implement `Trie._normalize(path)` static method to strip leading/trailing slashes
    - Implement `Trie.insert(pattern, destination)` that splits pattern into segments, creates nodes for static/dynamic segments, stores destination at terminal node, overwrites on duplicate
    - Implement `Trie.resolve(path)` that normalizes path, enforces MAX_DEPTH=20, walks the tree prioritizing static over dynamic matches, returns `(destination, params)` or `None`
    - Handle trailing slash normalization by stripping before resolution
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

  - [x]* 2.2 Write property test for Trie insertion round-trip
    - **Property 1: Trie insertion round-trip**
    - Use Hypothesis to generate valid route patterns (1-20 segments, mix of static/dynamic) and destination strings
    - Assert that inserting a pattern and resolving a matching path returns the correct destination and extracted params
    - **Validates: Requirements 2.2, 2.4**

  - [x]* 2.3 Write property test for static over dynamic segment priority
    - **Property 2: Static over dynamic segment priority**
    - Generate a Trie with both a static and dynamic segment at the same level/prefix
    - Resolve a path matching the static segment and assert static destination is returned
    - **Validates: Requirements 2.3**

  - [x]* 2.4 Write property test for trailing slash normalization
    - **Property 3: Trailing slash normalization**
    - Generate route patterns and resolve with/without trailing slashes
    - Assert both yield identical results
    - **Validates: Requirements 2.6**

  - [x]* 2.5 Write property test for duplicate pattern overwrite
    - **Property 4: Duplicate pattern overwrite**
    - Insert same pattern with destination D1 then D2, resolve and assert D2 is returned
    - **Validates: Requirements 2.8**

  - [x]* 2.6 Write property test for depth limit enforcement
    - **Property 5: Depth limit enforcement**
    - Generate paths with >20 segments and assert Trie returns None
    - Generate valid patterns with ≤20 segments and assert insertion/resolution succeeds
    - **Validates: Requirements 2.2, 2.9**

  - [x]* 2.7 Write property test for non-matching path returns None
    - **Property 6: Non-matching path returns None**
    - Generate a Trie with registered routes and a path that does not match any, assert None
    - **Validates: Requirements 2.5**

- [x] 3. Implement Hash-Map State Management
  - [x] 3.1 Implement StateManager class with asyncio.Lock concurrency control
    - Create `StateManager` class in `app/state_manager.py`
    - Initialize `_servers: dict[str, ServerProfile]` with primary (Alive, address `http://primary:8001`) and fallback (Alive, address `http://fallback:8002`)
    - Initialize `_lock: asyncio.Lock` for concurrency safety
    - Implement `async get_status(server_id) -> HealthStatus` with lock acquisition, raise `KeyError` for unknown server
    - Implement `async set_status(server_id, status) -> ServerProfile` with lock, raise `KeyError` for unknown server, raise `ValueError` for invalid status
    - Implement `async list_all() -> dict[str, ServerProfile]` with lock, return snapshot
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 5.4_

  - [x]* 3.2 Write property test for State Manager get/set round-trip
    - **Property 7: State Manager get/set round-trip**
    - For any registered server_id and valid status, set then get and assert equality
    - **Validates: Requirements 3.4, 3.5**

  - [x]* 3.3 Write property test for unknown server identifier rejection
    - **Property 8: Unknown server identifier rejection**
    - Generate strings not in ("primary", "fallback"), assert get_status and set_status raise errors
    - **Validates: Requirements 3.6, 3.7**

  - [x]* 3.4 Write property test for invalid status value rejection
    - **Property 9: Invalid status value rejection**
    - Generate strings not in ("Alive", "Dead"), assert set_status raises ValueError
    - **Validates: Requirements 3.8**

- [x] 4. Checkpoint - Ensure core components work independently
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Input Validation and Universal Proxy Endpoint
  - [x] 5.1 Implement path validation utility
    - Create `app/validation.py` with `validate_path(path: str) -> str | None` function
    - Check for empty/whitespace-only paths, return error message
    - Check for invalid characters using regex pattern `^[A-Za-z0-9\-._~/%]+$`, return error message listing invalid characters
    - _Requirements: 5.1, 5.3_

  - [x] 5.2 Implement the universal proxy endpoint at POST /proxy/{path:path}
    - Create `proxy_handler` async function in `app/routes.py`
    - Call `validate_path` first — return 400 on empty/whitespace or invalid characters
    - Query Trie to resolve destination — return 404 with error+path if no match
    - Query State Manager for primary health, then fallback if primary is Dead
    - Return 503 with error+path if both servers are Dead
    - On successful routing, return 200 with `ProxySuccessResponse` (server, destination, params, routing_decision, timestamp in ISO 8601)
    - Log each routing decision with timestamp, request path, destination, and selected server
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 5.1, 5.3_

  - [x]* 5.3 Write property test for failover routing decision
    - **Property 10: Failover routing decision**
    - For any resolvable path, test all health state combinations: (Alive,Alive)→primary, (Dead,Alive)→fallback, (Dead,Dead)→503
    - **Validates: Requirements 4.5, 4.6, 4.7**

  - [x]* 5.4 Write property test for empty/whitespace path rejection
    - **Property 11: Empty/whitespace path rejection**
    - Generate empty and whitespace-only strings, assert proxy returns 400
    - **Validates: Requirements 5.1**

  - [x]* 5.5 Write property test for invalid character path rejection
    - **Property 12: Invalid character path rejection**
    - Generate paths with characters outside the allowed set, assert proxy returns 400 with invalid char info
    - **Validates: Requirements 5.3**

  - [x]* 5.6 Write property test for successful proxy response completeness
    - **Property 13: Successful proxy response completeness**
    - For any successful routing, assert response contains server, destination, params dict, and routing_decision rationale
    - **Validates: Requirements 4.8**

  - [x]* 5.7 Write property test for error proxy response completeness
    - **Property 14: Error proxy response completeness**
    - For any 404 or 503 response, assert response body contains error field and original path
    - **Validates: Requirements 4.10**

- [x] 6. Implement Server Health Management Endpoints
  - [x] 6.1 Implement GET /health and PUT /health/{server_id} endpoints
    - Create `health_list` async GET handler at `/health` returning all servers with id, address, status
    - Create `health_update` async PUT handler at `/health/{server_id}` accepting `HealthUpdateRequest` body
    - Validate server_id exists — return 404 if not found
    - Validate status value is "Alive" or "Dead" — return 422 if invalid
    - Validate request body is valid JSON with status field — return 422 if malformed
    - On success, update State Manager and return 200 with updated server_id and status
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x]* 6.2 Write unit tests for health endpoints
    - Test GET /health returns both servers with correct structure
    - Test PUT /health/{server_id} with valid data returns 200
    - Test PUT with invalid server_id returns 404
    - Test PUT with invalid status value returns 422
    - Test PUT with malformed/missing body returns 422
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 7. Implement Global Error Handling and Wire Application Together
  - [x] 7.1 Implement global exception handler and application wiring
    - Add FastAPI exception handler that catches unhandled exceptions, logs exception type/message/stack trace, returns 500 with generic error message (no internal details)
    - Wire Trie, State Manager, and routes into the FastAPI `app` in `app/main.py`
    - Register pre-configured routes in the Trie at startup (from design: users, users/{id}, orders, orders/{id})
    - Add startup event/lifespan that logs host and port configuration message
    - Configure default host `0.0.0.0` and port `8000`
    - Add type annotations on all public functions
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 2.7, 5.2_

  - [x]* 7.2 Write unit tests for error handling and startup
    - Test that internal exceptions return 500 without leaking details
    - Test that startup log message includes host and port
    - Test that configured routes are registered in the Trie
    - _Requirements: 1.3, 1.5, 5.2_

- [x] 8. Checkpoint - Ensure full integration works end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Integration testing and concurrency validation
  - [x]* 9.1 Write integration tests for full proxy flow and concurrency
    - Test end-to-end flow: route registration → health state → proxy request → response validation
    - Test failover scenario: primary alive → mark dead → proxy routes to fallback → mark fallback dead → 503
    - Test concurrent access: multiple coroutines reading/writing State Manager simultaneously, assert no partial updates observed
    - _Requirements: 4.1–4.10, 5.4, 6.1–6.5_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python 3.10+ with FastAPI, as specified in the design
- All async operations use `asyncio.Lock` for thread-safe concurrent access
- Hypothesis library is used for property-based testing with minimum 100 examples per property

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "3.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "3.2", "3.3", "3.4"] },
    { "id": 4, "tasks": ["5.1"] },
    { "id": 5, "tasks": ["5.2", "6.1"] },
    { "id": 6, "tasks": ["5.3", "5.4", "5.5", "5.6", "5.7", "6.2"] },
    { "id": 7, "tasks": ["7.1"] },
    { "id": 8, "tasks": ["7.2"] },
    { "id": 9, "tasks": ["9.1"] }
  ]
}
```
