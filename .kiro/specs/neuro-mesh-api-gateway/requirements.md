# Requirements Document

## Introduction

NEURO-MESH Phase 1: Fault-Tolerant API Gateway. This phase establishes the foundational gateway layer using a custom Trie-based routing engine, hash-map-based state management, and a universal proxy endpoint that demonstrates intelligent failover routing between backend servers. The implementation uses Python with FastAPI in a fully asynchronous architecture.

## Glossary

- **Gateway**: The FastAPI application that intercepts incoming API requests and routes them to appropriate backend servers based on path resolution and server health status.
- **Trie**: A custom prefix tree data structure implemented from scratch (no external library) that stores route patterns and resolves dynamic path segments (e.g., `{id}`) to their configured destinations.
- **State_Manager**: A component backed by Python dictionaries (hash maps) that maintains real-time health status for registered backend servers with O(1) lookup time.
- **Server_Profile**: A data record representing a backend server, containing its identifier, address, and current health status (Alive or Dead).
- **Primary_Server**: The default backend server (Alive by default) that receives routed traffic under normal operating conditions.
- **Fallback_Server**: The secondary backend server (Alive by default) that receives routed traffic when the Primary_Server is marked as Dead.
- **Route_Pattern**: A URL path template registered in the Trie that may contain static segments and dynamic parameters enclosed in curly braces (e.g., `/api/v1/users/{id}`).
- **Proxy_Endpoint**: The universal POST endpoint at `/proxy/{path:path}` that intercepts all incoming requests and performs route resolution, health evaluation, and routing decisions.
- **Routing_Decision**: The logged outcome of a proxy request, indicating which server was selected and why.

## Requirements

### Requirement 1: Asynchronous Application Core

**User Story:** As a developer, I want the gateway built on an asynchronous FastAPI framework, so that the system can handle concurrent requests without blocking.

#### Acceptance Criteria

1. THE Gateway SHALL be implemented as a FastAPI application using Python async/await patterns.
2. THE Gateway SHALL define all route handlers as asynchronous coroutines using the `async def` syntax.
3. THE Gateway SHALL expose its API on a configurable host and port, defaulting to host `0.0.0.0` and port `8000` when no configuration is provided.
4. THE Gateway SHALL include type annotations on all public functions, method parameters, return types, and class attributes using Python 3.10+ type hint syntax.
5. WHEN the Gateway application starts, THE Gateway SHALL log a startup message indicating the configured host and port.

### Requirement 2: Custom Trie-Based Route Matching

**User Story:** As a developer, I want a custom Trie data structure for route resolution, so that path matching is efficient and supports dynamic URL segments without relying on external routing libraries.

#### Acceptance Criteria

1. THE Trie SHALL be implemented as a custom class from scratch without using any external routing or trie library.
2. THE Trie SHALL support insertion of Route_Patterns containing both static path segments and dynamic parameters enclosed in curly braces, with a maximum path depth of 20 segments.
3. WHEN a request path is provided, THE Trie SHALL resolve the path by matching static segments using case-sensitive exact comparison and dynamic segments to any non-empty path segment value, prioritizing static segment matches over dynamic segment matches at each level.
4. WHEN a request path matches a registered Route_Pattern, THE Trie SHALL return the associated destination identifier and a dictionary of extracted dynamic parameter values keyed by the parameter names defined in the Route_Pattern.
5. WHEN a request path does not match any registered Route_Pattern, THE Trie SHALL return None to indicate that no route was found.
6. THE Trie SHALL handle paths with and without trailing slashes as equivalent matches by normalizing paths before resolution.
7. THE Trie SHALL store route metadata (destination identifier) at terminal nodes.
8. IF a Route_Pattern is inserted that duplicates an already registered Route_Pattern, THEN THE Trie SHALL overwrite the existing destination identifier with the new one.
9. IF a request path contains more than 20 segments, THEN THE Trie SHALL return None to indicate that no route was found.

### Requirement 3: Hash-Map State Management

**User Story:** As a developer, I want server health tracked in a hash-map-based State Manager, so that health lookups are O(1) and the system can make instant routing decisions.

#### Acceptance Criteria

1. THE State_Manager SHALL use Python dictionaries as the underlying data structure for storing Server_Profiles.
2. THE State_Manager SHALL provide O(1) time complexity for health status lookups by server identifier.
3. THE State_Manager SHALL be initialized with two Server_Profiles: Primary_Server (status: Alive) and Fallback_Server (status: Alive).
4. THE State_Manager SHALL expose a method to retrieve the current health status of a server by its identifier.
5. THE State_Manager SHALL expose a method to update the health status of a server by its identifier, where valid status values are restricted to Alive or Dead.
6. IF a health status update is requested for a server identifier that does not exist, THEN THE State_Manager SHALL raise an error indicating that the specified server identifier is not registered.
7. IF a health status retrieval is requested for a server identifier that does not exist, THEN THE State_Manager SHALL raise an error indicating that the specified server identifier is not registered.
8. IF a health status update is requested with a status value that is not Alive or Dead, THEN THE State_Manager SHALL raise an error indicating the provided status value is invalid.
9. THE State_Manager SHALL expose a method to list all registered servers and their current health statuses as a dictionary mapping server identifiers to their status values.

### Requirement 4: Universal Proxy Endpoint

**User Story:** As a developer, I want a single POST endpoint that intercepts all incoming requests and performs intelligent routing, so that the gateway demonstrates request interception, route resolution, and failover logic in one cohesive flow.

#### Acceptance Criteria

1. THE Gateway SHALL expose a single POST endpoint at the path `/proxy/{path:path}` that accepts any sub-path.
2. WHEN the Proxy_Endpoint receives a request, THE Gateway SHALL query the Trie to resolve the destination for the provided path.
3. IF the Trie cannot resolve the provided path, THEN THE Gateway SHALL return an HTTP 404 response with an error message indicating the path could not be matched to any registered route.
4. WHEN the Trie resolves a destination, THE Gateway SHALL query the State_Manager to evaluate the health of the Primary_Server and, if necessary, the Fallback_Server.
5. IF the Primary_Server health status is Alive, THEN THE Gateway SHALL select the Primary_Server as the routing target and log the Routing_Decision.
6. IF the Primary_Server health status is Dead and the Fallback_Server health status is Alive, THEN THE Gateway SHALL select the Fallback_Server as the routing target and log the Routing_Decision.
7. IF both the Primary_Server and Fallback_Server health statuses are Dead, THEN THE Gateway SHALL return an HTTP 503 response with an error message indicating no healthy servers are available.
8. WHEN a healthy server is selected, THE Gateway SHALL return an HTTP 200 response body containing: the selected server identifier, the resolved route destination, a dictionary of extracted path parameters, and a Routing_Decision rationale stating which server was selected and the reason for selection.
9. THE Gateway SHALL log each Routing_Decision with a timestamp in ISO 8601 format, the request path, the resolved destination, and the selected server identifier.
10. IF the Proxy_Endpoint returns an error response (HTTP 404 or HTTP 503), THEN THE Gateway SHALL include in the response body an error field indicating the failure reason and the original request path.

### Requirement 5: Error Handling and Edge Cases

**User Story:** As a developer, I want the gateway to handle malformed requests and edge cases gracefully, so that the system is production-ready and resilient to unexpected input.

#### Acceptance Criteria

1. IF the Proxy_Endpoint receives a request with a path that is empty (zero-length string or contains only whitespace), THEN THE Gateway SHALL return an HTTP 400 response with an error message indicating that the request path must not be empty.
2. IF an unexpected internal error occurs during request processing, THEN THE Gateway SHALL return an HTTP 500 response with an error message that does not reveal internal implementation details, and SHALL log the exception type, exception message, and stack trace.
3. IF the Proxy_Endpoint receives a request path containing characters outside the set of unreserved characters (A-Z, a-z, 0-9, `-`, `.`, `_`, `~`), forward slashes (`/`), and percent-encoded sequences (`%XX`), THEN THE Gateway SHALL return an HTTP 400 response with an error message indicating which characters are invalid.
4. WHILE multiple requests are being processed concurrently, THE Gateway SHALL ensure that State_Manager read and write operations on server health status are serialized such that no request observes a partially-updated state.

### Requirement 6: Server Health Management Endpoint

**User Story:** As a developer, I want endpoints to view and update server health, so that I can simulate failover scenarios by toggling server status.

#### Acceptance Criteria

1. THE Gateway SHALL expose a GET endpoint at `/health` that returns the current health status of all registered servers, including each server's identifier, address, and health status (Alive or Dead).
2. THE Gateway SHALL expose a PUT endpoint at `/health/{server_id}` that accepts a JSON request body containing a health status field with a value of either "Alive" or "Dead", updates the State_Manager, and returns an HTTP 200 response containing the updated server identifier and its new health status.
3. IF the PUT endpoint receives an invalid server identifier that does not match any registered server, THEN THE Gateway SHALL return an HTTP 404 response with an error message indicating the server identifier was not found.
4. IF the PUT endpoint receives a health status value that is not "Alive" or "Dead", THEN THE Gateway SHALL return an HTTP 422 response with an error message indicating the accepted health status values.
5. IF the PUT endpoint receives a request body that is missing the health status field or is not valid JSON, THEN THE Gateway SHALL return an HTTP 422 response with an error message indicating the expected request body format.
