"""Route handlers for the NEURO-MESH API Gateway.

This module defines the FastAPI route handler functions for:
- POST /proxy/{path:path} - Universal proxy endpoint with ML-based predictive failover
- GET /health - Server health listing
- PUT /health/{server_id} - Server health update

Implementation:
- proxy_handler: validates path, resolves via Trie, runs ML prediction,
  evaluates health, and routes with intelligent failover
- ML model predicts server failure from synthetic latency metrics
- If failure predicted, preemptively reroutes to Fallback
"""

import logging
import os
import pickle
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
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
record_network_log: Any = None  # Set by main.py lifespan

# ML Model for predictive failover
_ml_model: Any = None
_model_loaded: bool = False

router = APIRouter()


def _load_model() -> Any:
    """Load the trained ML model from model.pkl if available."""
    global _ml_model, _model_loaded
    if _model_loaded:
        return _ml_model

    model_path = Path("model.pkl")
    if model_path.exists():
        try:
            with open(model_path, "rb") as f:
                _ml_model = pickle.load(f)
            logger.info("ML model loaded from %s", model_path)
        except Exception as e:
            logger.warning("Failed to load ML model: %s", e)
            _ml_model = None
    else:
        logger.info("No model.pkl found — ML predictive failover disabled")
        _ml_model = None

    _model_loaded = True
    return _ml_model


def _predict_failure() -> tuple[bool, dict[str, float]]:
    """Generate mock latency metrics and predict server failure.

    ML prediction is only active when the ML_ENABLED environment variable
    is set to "1" or "true". This prevents non-deterministic behavior
    during testing while enabling the feature in production/demos.

    Returns:
        Tuple of (failure_predicted: bool, metrics: dict with feature values)
    """
    # Generate mock real-time metrics for this request
    metrics = {
        "rolling_latency_p95": random.uniform(50, 600),
        "error_rate_1min": random.uniform(0.0, 0.5),
        "requests_per_minute": random.uniform(100, 3000),
    }

    # Only run ML predictions when explicitly enabled (demo/production)
    ml_enabled = os.environ.get("ML_ENABLED", "0").lower() in ("1", "true")
    if not ml_enabled:
        return False, metrics

    model = _load_model()

    if model is None:
        # No model available — no prediction, rely on health status only
        return False, metrics

    # Run prediction
    features = np.array([[
        metrics["rolling_latency_p95"],
        metrics["error_rate_1min"],
        metrics["requests_per_minute"],
    ]])

    prediction = model.predict(features)[0]
    failure_predicted = bool(prediction == 1)

    if failure_predicted:
        logger.warning(
            "ML MODEL ALERT: Failure predicted! metrics=%s", metrics
        )

    return failure_predicted, metrics


@router.post("/proxy/{path:path}")
async def proxy_handler(path: str) -> JSONResponse:
    """Universal proxy endpoint with ML-based predictive failover.

    Flow:
    1. Validate incoming path
    2. Resolve route via Trie (custom DSA)
    3. Run ML model prediction on mock latency metrics
    4. If failure predicted → preemptively reroute to Fallback
    5. Otherwise use standard health-based failover logic
    6. Return routing decision with full metadata

    Args:
        path: The request sub-path captured by FastAPI's path converter.

    Returns:
        JSONResponse with appropriate status code and body.
    """
    # Step 1: Validate path
    validation_error = validate_path(path)
    if validation_error is not None:
        error_response = ProxyErrorResponse(error=validation_error, path=path)
        return JSONResponse(
            status_code=400,
            content=error_response.model_dump(),
        )

    # Step 2: Resolve route via Trie (DSA component)
    assert trie is not None, "Trie not initialized"
    result = trie.resolve(path)
    if result is None:
        error_response = ProxyErrorResponse(error="No route matched", path=path)
        return JSONResponse(
            status_code=404,
            content=error_response.model_dump(),
        )

    destination, params = result

    # Step 3: ML Prediction — predictive failover
    assert state_manager is not None, "StateManager not initialized"
    failure_predicted, metrics = _predict_failure()

    # Step 4: Routing decision with ML integration
    primary_status = await state_manager.get_status("primary")
    fallback_status = await state_manager.get_status("fallback")

    if failure_predicted and primary_status == HealthStatus.ALIVE:
        # ML model predicts failure — preemptive reroute to fallback
        if fallback_status == HealthStatus.ALIVE:
            selected_server = "fallback"
            routing_decision = (
                f"ML PREDICTIVE REROUTE: Failure predicted "
                f"(latency={metrics['rolling_latency_p95']:.0f}ms, "
                f"error_rate={metrics['error_rate_1min']:.2%}, "
                f"rps={metrics['requests_per_minute']:.0f}) — "
                f"preemptively routing to fallback"
            )
        else:
            # Fallback also dead, use primary as last resort
            selected_server = "primary"
            routing_decision = (
                f"ML predicted failure but fallback unavailable — "
                f"routing to primary (risk accepted)"
            )
    elif primary_status == HealthStatus.ALIVE:
        selected_server = "primary"
        routing_decision = (
            f"Primary server selected: server is healthy "
            f"(latency={metrics['rolling_latency_p95']:.0f}ms, "
            f"error_rate={metrics['error_rate_1min']:.2%})"
        )
    elif fallback_status == HealthStatus.ALIVE:
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

    # Step 5: Build success response
    timestamp = datetime.now(timezone.utc).isoformat()

    success_response = ProxySuccessResponse(
        server=selected_server,
        destination=destination,
        params=params,
        routing_decision=routing_decision,
        timestamp=timestamp,
    )

    # Step 6: Log the routing decision
    logger.info(
        "Routing decision: timestamp=%s path=%s destination=%s server=%s ml_failure_predicted=%s",
        timestamp,
        path,
        destination,
        selected_server,
        failure_predicted,
    )

    # Step 7: Record in network traffic log (if available)
    if record_network_log is not None:
        record_network_log(path, selected_server, destination, 200, routing_decision)

    return JSONResponse(
        status_code=200,
        content=success_response.model_dump(),
    )
