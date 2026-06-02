# NEURO-MESH Phase 1: Fault-Tolerant API Gateway

A custom-built, asynchronous API Gateway using FastAPI with intelligent failover routing between backend servers.

## Architecture

- **Custom Trie Router** — Prefix tree for O(log n) path resolution with static/dynamic segment support
- **Hash-Map State Manager** — O(1) server health lookups with asyncio.Lock concurrency control
- **Universal Proxy Endpoint** — Intercepts requests, resolves routes, and applies deterministic failover logic
- **Health Management** — REST endpoints for viewing and toggling server health to simulate failover scenarios

## Project Structure

```
app/
├── __init__.py
├── main.py              # FastAPI app entry point, lifespan, exception handler
├── models.py            # Pydantic models and HealthStatus enum
├── trie.py              # Custom Trie-based route matching engine
├── state_manager.py     # Hash-map state manager with asyncio.Lock
├── routes.py            # POST /proxy/{path:path} endpoint
├── health_routes.py     # GET /health, PUT /health/{server_id}
└── validation.py        # Input path validation utility

tests/
├── __init__.py
├── conftest.py          # Shared pytest fixtures
├── test_trie.py         # Trie unit tests (33 tests)
├── test_state_manager.py # StateManager unit tests (22 tests)
├── test_proxy.py        # Proxy endpoint tests (12 tests)
├── test_health.py       # Health endpoint tests (10 tests)
├── test_main.py         # App wiring and error handler tests (12 tests)
├── test_properties.py   # Hypothesis property-based tests (16 tests, 100 examples each)
└── test_integration.py  # End-to-end integration tests (9 tests)

requirements.txt         # Python dependencies
```

## Quick Start

### Prerequisites

- Python 3.10+

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Server

```bash
uvicorn app.main:app --reload
```

The gateway starts on `http://0.0.0.0:8000` by default.

### Run Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=app --cov-report=term-missing
```

## API Endpoints

### Proxy Endpoint

```
POST /proxy/{path}
```

Resolves the path against registered routes and applies failover routing logic.

**Example:**
```bash
curl -X POST http://localhost:8000/proxy/api/v1/users/42
```

**Response (200):**
```json
{
  "server": "primary",
  "destination": "user-service",
  "params": {"id": "42"},
  "routing_decision": "Primary server selected: server is healthy",
  "timestamp": "2024-01-01T00:00:00+00:00"
}
```

### Health Endpoints

```
GET  /health                  # List all servers and their health status
PUT  /health/{server_id}      # Update a server's health status
```

**Toggle server health:**
```bash
curl -X PUT http://localhost:8000/health/primary \
  -H "Content-Type: application/json" \
  -d '{"status": "Dead"}'
```

## Failover Logic

1. If **Primary** is Alive → route to Primary
2. If Primary is Dead and **Fallback** is Alive → route to Fallback
3. If **both** are Dead → return HTTP 503

## Pre-Registered Routes

| Pattern | Destination |
|---------|-------------|
| `/api/v1/users` | user-service |
| `/api/v1/users/{id}` | user-service |
| `/api/v1/orders` | order-service |
| `/api/v1/orders/{id}` | order-service |

## License

Internal project — Muhammad Dayan
