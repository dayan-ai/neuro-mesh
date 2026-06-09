"""NEURO-MESH Phase 1: Fault-Tolerant API Gateway application entry point.

This module wires together the Trie router, State Manager, and route handlers
into a single FastAPI application instance. It configures startup events,
global exception handling, route registration, DSA visualization, ML prediction,
and network traffic logging.

Enterprise features:
- Structured logging with correlation IDs
- Request instrumentation and tracing
- Environment-based configuration
- Graceful shutdown handling

Deployment: Vercel-ready with dynamic path resolution for model.pkl.
"""

import logging
import os
import pickle
import random
import signal
import sys
import traceback
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.config import EnterpriseConfig
from app.health_routes import health_router
from app.instrumentation import InstrumentationMiddleware, StructuredLogger, get_structured_logger
from app.routes import router as proxy_router
from app.state_manager import StateManager
from app.trie import Trie, TrieNode
import app.health_routes as health_routes_module
import app.routes as routes_module

# Load enterprise configuration
config = EnterpriseConfig.from_env()

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = get_structured_logger(__name__, enable_json=config.structured_logging)

# ---------------------------------------------------------------------------
# Configuration (enterprise-grade)
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(os.path.dirname(os.path.abspath(__file__))).parent
MODEL_PATH: Path = BASE_DIR / "model.pkl"

# Use config from environment
DEFAULT_HOST: str = config.host
DEFAULT_PORT: int = config.port

# Pre-configured routes registered at startup — expanded to 10+ for DSA showcase
STARTUP_ROUTES: list[tuple[str, str]] = [
    ("/api/v1/users", "user-service"),
    ("/api/v1/users/{id}", "user-service"),
    ("/api/v1/users/{id}/profile", "user-service"),
    ("/api/v1/orders", "order-service"),
    ("/api/v1/orders/{id}", "order-service"),
    ("/api/v1/orders/{id}/items", "order-service"),
    ("/api/v1/products", "product-service"),
    ("/api/v1/products/{id}", "product-service"),
    ("/api/v1/payments", "payment-service"),
    ("/api/v1/payments/{id}", "payment-service"),
    ("/api/v1/auth/login", "auth-service"),
    ("/api/v1/auth/register", "auth-service"),
    ("/api/v1/notifications", "notification-service"),
    ("/api/v2/analytics/events", "analytics-service"),
    ("/api/v2/analytics/reports/{id}", "analytics-service"),
]

# ---------------------------------------------------------------------------
# Network Traffic Log (Circular Queue — last 50 requests)
# ---------------------------------------------------------------------------
NETWORK_LOG: deque[dict[str, Any]] = deque(maxlen=50)

MOCK_CLIENT_IPS: list[str] = [
    "192.168.1.101", "192.168.1.102", "10.0.0.45", "172.16.0.88",
    "192.168.1.200", "10.0.0.12", "172.16.5.33", "192.168.2.77",
]
MOCK_SERVER_IPS: dict[str, str] = {
    "primary": "10.10.1.1",
    "fallback": "10.10.1.2",
}


def record_network_log(
    path: str, server: str, destination: str, status_code: int, routing_decision: str
) -> None:
    """Record a proxy request into the circular network log."""
    NETWORK_LOG.append({
        "time": datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3],
        "source_ip": random.choice(MOCK_CLIENT_IPS),
        "dest_ip": MOCK_SERVER_IPS.get(server, "10.10.1.1"),
        "protocol": "HTTP/1.1" if status_code == 200 else "TCP",
        "method": "POST",
        "length": random.randint(180, 1400),
        "status": status_code,
        "info": f"POST /proxy/{path} → {destination} [{server}] {routing_decision[:60]}",
    })


# Make it accessible to routes module
routes_module_record = record_network_log

# ---------------------------------------------------------------------------
# ML Model Loading (Vercel-compatible path)
# ---------------------------------------------------------------------------
_ml_model: Any = None


def _load_ml_model() -> Any:
    """Load the trained ML model from model.pkl using absolute path."""
    global _ml_model
    if _ml_model is not None:
        return _ml_model
    if MODEL_PATH.exists():
        try:
            with open(MODEL_PATH, "rb") as f:
                _ml_model = pickle.load(f)
            logger.info("ML model loaded", model_path=str(MODEL_PATH))
        except Exception as e:
            logger.warning("Failed to load ML model", error=str(e))
    else:
        logger.info("model.pkl not found", model_path=str(MODEL_PATH), status="prediction_disabled")
    return _ml_model


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan with enterprise features.
    
    - Wire Trie router and State Manager
    - Register startup routes
    - Load ML model
    - Setup graceful shutdown handlers
    """
    logger.info(
        "Gateway started on 0.0.0.0:8000",
        environment=config.environment,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        structured_logging=config.structured_logging,
    )

    trie = Trie()
    state_manager = StateManager()

    for pattern, destination in STARTUP_ROUTES:
        trie.insert(pattern, destination)

    routes_module.trie = trie
    routes_module.state_manager = state_manager
    routes_module.record_network_log = record_network_log  # type: ignore[attr-defined]
    health_routes_module.state_manager = state_manager

    app.state.trie = trie
    app.state.state_manager = state_manager
    app.state.config = config

    # Pre-load ML model
    if config.enable_ml_predictions:
        _load_ml_model()

    logger.info("Gateway startup complete", routes_registered=len(STARTUP_ROUTES))

    # Graceful shutdown handler
    def signal_handler(signum: int, frame: Any) -> None:
        logger.info("Shutdown signal received", signal_number=signum)
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    yield

    logger.info("Gateway shutting down", grace_period_seconds=config.shutdown_grace_period_seconds)


app = FastAPI(
    title="NEURO-MESH API Gateway",
    description="Enterprise-grade fault-tolerant API gateway with ML predictive failover",
    lifespan=lifespan,
)

# Add enterprise instrumentation middleware
instrumentation_logger = get_structured_logger(__name__, enable_json=config.structured_logging)
app.add_middleware(InstrumentationMiddleware, logger=instrumentation_logger)

# Include routers
app.include_router(proxy_router)
app.include_router(health_router)


# ---------------------------------------------------------------------------
# DSA Showcase Endpoint: GET /dsa-state
# ---------------------------------------------------------------------------


def _serialize_trie_node(node: TrieNode, prefix: str = "") -> dict[str, Any]:
    """Recursively serialize a TrieNode to a JSON-friendly dict."""
    result: dict[str, Any] = {}
    if node.destination:
        result["_destination"] = node.destination

    for segment, child in node.children.items():
        child_path = f"{prefix}/{segment}" if prefix else f"/{segment}"
        result[segment] = _serialize_trie_node(child, child_path)

    if node.dynamic_child is not None:
        param_key = f"{{{node.dynamic_param_name or 'param'}}}"
        child_path = f"{prefix}/{param_key}" if prefix else f"/{param_key}"
        result[param_key] = _serialize_trie_node(node.dynamic_child, child_path)

    return result


@app.get("/dsa-state")
async def dsa_state(request: Request) -> JSONResponse:
    """Return the live Trie structure and HashMap (State Manager) contents."""
    trie: Trie = request.app.state.trie
    state_manager: StateManager = request.app.state.state_manager

    trie_structure = _serialize_trie_node(trie._root)
    servers = await state_manager.list_all()
    hashmap_state = {
        sid: {"server_id": p.server_id, "address": p.address, "status": p.status.value}
        for sid, p in servers.items()
    }

    return JSONResponse(content={
        "trie": {
            "description": "Custom prefix-tree (Trie) for O(log n) route resolution",
            "max_depth": Trie.MAX_DEPTH,
            "registered_routes": [f"{p} → {d}" for p, d in STARTUP_ROUTES],
            "structure": trie_structure,
        },
        "hashmap": {
            "description": "Python dict-backed State Manager for O(1) health lookups",
            "data_structure": "dict[str, ServerProfile]",
            "lookup_complexity": "O(1)",
            "servers": hashmap_state,
        },
    })


# ---------------------------------------------------------------------------
# Network Logs Endpoint: GET /network-logs
# ---------------------------------------------------------------------------


@app.get("/network-logs")
async def network_logs() -> JSONResponse:
    """Return the last 50 network traffic entries (Wireshark-style)."""
    return JSONResponse(content={"logs": list(NETWORK_LOG)})


# ---------------------------------------------------------------------------
# ML Predict Endpoint: POST /predict-health
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    """Request body for the ML prediction endpoint."""
    rolling_latency_p95: float
    error_rate_1min: float
    requests_per_minute: float


@app.post("/predict-health")
async def predict_health(body: PredictRequest) -> JSONResponse:
    """Run the trained Random Forest model on user-provided metrics."""
    model = _load_ml_model()

    if model is None:
        return JSONResponse(
            status_code=503,
            content={"error": "ML model not available. Run train_mock_model.py first.", "prediction": None},
        )

    features = np.array([[body.rolling_latency_p95, body.error_rate_1min, body.requests_per_minute]])
    prediction = int(model.predict(features)[0])
    probability = model.predict_proba(features)[0].tolist()

    return JSONResponse(content={
        "input": {"rolling_latency_p95": body.rolling_latency_p95, "error_rate_1min": body.error_rate_1min, "requests_per_minute": body.requests_per_minute},
        "prediction": "WILL FAIL" if prediction == 1 else "WILL SURVIVE",
        "failure_predicted": prediction == 1,
        "confidence": {"survive_probability": round(probability[0], 4), "fail_probability": round(probability[1], 4)},
        "model": "RandomForestClassifier (100 trees, max_depth=10)",
    })


# ---------------------------------------------------------------------------
# Web Dashboard (GET /) — served inline
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Serve the multi-tab dashboard."""
    html_path = BASE_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>index.html not found</h1>", status_code=404)


# ---------------------------------------------------------------------------
# Global Exception Handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch all unhandled exceptions with enterprise error handling.
    
    - Logs full stack trace with correlation context
    - Returns generic error message (no internal details)
    """
    logger.error(
        "Unhandled exception in request",
        error_type=type(exc).__name__,
        error_message=str(exc),
        stack_trace=traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        log_level=config.log_level.lower(),
    )
