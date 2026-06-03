"""NEURO-MESH Phase 1: Fault-Tolerant API Gateway application entry point.

This module wires together the Trie router, State Manager, and route handlers
into a single FastAPI application instance. It configures startup events,
global exception handling, route registration, DSA visualization, and ML prediction.

Deployment: Vercel-ready with dynamic path resolution for model.pkl.
"""

import logging
import os
import pickle
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.health_routes import health_router
from app.routes import router as proxy_router
from app.state_manager import StateManager
from app.trie import Trie, TrieNode
import app.health_routes as health_routes_module
import app.routes as routes_module

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path resolution (Vercel-compatible)
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(os.path.dirname(os.path.abspath(__file__))).parent
MODEL_PATH: Path = BASE_DIR / "model.pkl"

# Configuration defaults
DEFAULT_HOST: str = "0.0.0.0"
DEFAULT_PORT: int = 8000

# Pre-configured routes registered at startup (pattern, destination)
STARTUP_ROUTES: list[tuple[str, str]] = [
    ("/api/v1/users", "user-service"),
    ("/api/v1/users/{id}", "user-service"),
    ("/api/v1/orders", "order-service"),
    ("/api/v1/orders/{id}", "order-service"),
]

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
            logger.info("ML model loaded from %s", MODEL_PATH)
        except Exception as e:
            logger.warning("Failed to load ML model: %s", e)
    else:
        logger.info("model.pkl not found at %s — prediction disabled", MODEL_PATH)
    return _ml_model


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: create Trie + StateManager, register routes, load model."""
    trie = Trie()
    state_manager = StateManager()

    for pattern, destination in STARTUP_ROUTES:
        trie.insert(pattern, destination)

    routes_module.trie = trie
    routes_module.state_manager = state_manager
    health_routes_module.state_manager = state_manager

    app.state.trie = trie
    app.state.state_manager = state_manager

    # Pre-load ML model
    _load_ml_model()

    logger.info("Gateway started on %s:%d", DEFAULT_HOST, DEFAULT_PORT)
    yield
    logger.info("Gateway shutting down")


app = FastAPI(title="NEURO-MESH API Gateway", lifespan=lifespan)

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
    """Return the live Trie structure and HashMap (State Manager) contents.

    Shows the internal data structures powering the gateway.
    """
    trie: Trie = request.app.state.trie
    state_manager: StateManager = request.app.state.state_manager

    # Serialize Trie
    trie_structure = _serialize_trie_node(trie._root)

    # Serialize HashMap (State Manager)
    servers = await state_manager.list_all()
    hashmap_state = {
        sid: {"server_id": p.server_id, "address": p.address, "status": p.status.value}
        for sid, p in servers.items()
    }

    return JSONResponse(content={
        "trie": {
            "description": "Custom prefix-tree (Trie) for O(log n) route resolution",
            "max_depth": Trie.MAX_DEPTH,
            "registered_routes": [f"{p} -> {d}" for p, d in STARTUP_ROUTES],
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
# ML Predict Endpoint: POST /predict-health
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    """Request body for the ML prediction endpoint."""
    rolling_latency_p95: float
    error_rate_1min: float
    requests_per_minute: float


@app.post("/predict-health")
async def predict_health(body: PredictRequest) -> JSONResponse:
    """Run the trained Random Forest model on user-provided metrics.

    Returns whether the model predicts server failure or survival.
    """
    model = _load_ml_model()

    if model is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": "ML model not available. Run train_mock_model.py first.",
                "prediction": None,
            },
        )

    features = np.array([[
        body.rolling_latency_p95,
        body.error_rate_1min,
        body.requests_per_minute,
    ]])

    prediction = int(model.predict(features)[0])
    probability = model.predict_proba(features)[0].tolist()

    return JSONResponse(content={
        "input": {
            "rolling_latency_p95": body.rolling_latency_p95,
            "error_rate_1min": body.error_rate_1min,
            "requests_per_minute": body.requests_per_minute,
        },
        "prediction": "WILL FAIL" if prediction == 1 else "WILL SURVIVE",
        "failure_predicted": prediction == 1,
        "confidence": {
            "survive_probability": round(probability[0], 4),
            "fail_probability": round(probability[1], 4),
        },
        "model": "RandomForestClassifier (100 trees, max_depth=10)",
    })


# ---------------------------------------------------------------------------
# Web Dashboard (GET /) — Enhanced with Model Chat & DSA Viewer
# ---------------------------------------------------------------------------

DASHBOARD_HTML: str = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NEURO-MESH Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: #0f0f1a;
    color: #e0e0e0;
    min-height: 100vh;
    padding: 2rem;
  }
  .header { text-align: center; margin-bottom: 2.5rem; }
  .header h1 {
    font-size: 2.2rem;
    background: linear-gradient(135deg, #00d4ff, #7b2ff7);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.3rem;
  }
  .header p { color: #888; font-size: 0.95rem; }
  .grid {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 1.5rem; max-width: 900px; margin: 0 auto 2rem;
  }
  .card {
    background: #1a1a2e; border: 1px solid #2a2a4a;
    border-radius: 12px; padding: 2rem; text-align: center;
    transition: all 0.3s ease;
  }
  .card:hover { border-color: #444; transform: translateY(-2px); }
  .card h2 {
    font-size: 1rem; color: #aaa; margin-bottom: 1rem;
    text-transform: uppercase; letter-spacing: 1px; font-weight: 500;
  }
  .status-indicator {
    width: 70px; height: 70px; border-radius: 50%;
    margin: 0 auto 1rem; display: flex; align-items: center;
    justify-content: center; font-size: 1.5rem; transition: all 0.4s ease;
  }
  .status-alive {
    background: radial-gradient(circle, #00ff88 0%, #00cc6a 70%);
    box-shadow: 0 0 30px rgba(0, 255, 136, 0.3);
  }
  .status-dead {
    background: radial-gradient(circle, #ff4444 0%, #cc0000 70%);
    box-shadow: 0 0 30px rgba(255, 68, 68, 0.3);
    animation: pulse-red 1.5s infinite;
  }
  @keyframes pulse-red {
    0%,100% { box-shadow: 0 0 30px rgba(255,68,68,0.3); }
    50% { box-shadow: 0 0 50px rgba(255,68,68,0.6); }
  }
  .status-text { font-size: 1.2rem; font-weight: 600; margin-top: 0.5rem; }
  .status-text.alive { color: #00ff88; }
  .status-text.dead { color: #ff4444; }
  .address { color: #666; font-size: 0.8rem; margin-top: 0.4rem; font-family: monospace; }

  .section {
    max-width: 900px; margin: 2rem auto;
    background: #1a1a2e; border: 1px solid #2a2a4a;
    border-radius: 12px; padding: 1.8rem;
  }
  .section h3 {
    color: #00d4ff; font-size: 1rem; margin-bottom: 1rem;
    text-transform: uppercase; letter-spacing: 1px;
  }
  .input-row { display: flex; gap: 0.8rem; margin-bottom: 1rem; flex-wrap: wrap; }
  .input-row label { display: flex; flex-direction: column; gap: 0.3rem; flex: 1; min-width: 150px; }
  .input-row label span { font-size: 0.75rem; color: #888; text-transform: uppercase; }
  .input-row input {
    background: #0f0f1a; border: 1px solid #333; border-radius: 6px;
    padding: 0.6rem; color: #e0e0e0; font-size: 0.9rem;
  }
  .input-row input:focus { outline: none; border-color: #7b2ff7; }
  .btn {
    background: linear-gradient(135deg, #7b2ff7, #00d4ff);
    border: none; color: #fff; font-size: 0.85rem; font-weight: 600;
    padding: 0.7rem 1.5rem; border-radius: 6px; cursor: pointer;
    transition: transform 0.15s;
  }
  .btn:hover { transform: translateY(-1px); }
  .result-box {
    margin-top: 1rem; background: #0f0f1a; border: 1px solid #2a2a4a;
    border-radius: 8px; padding: 1rem; font-family: monospace;
    font-size: 0.8rem; color: #8892b0; white-space: pre-wrap;
    max-height: 300px; overflow-y: auto;
  }
  .prediction-survive { color: #00ff88; font-weight: bold; }
  .prediction-fail { color: #ff4444; font-weight: bold; }

  .info-bar {
    max-width: 900px; margin: 0 auto 2rem;
    background: #1a1a2e; border: 1px solid #2a2a4a;
    border-radius: 12px; padding: 1.2rem 2rem;
    display: flex; justify-content: space-between; align-items: center;
  }
  .info-item { text-align: center; }
  .info-item .label { color: #888; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px; }
  .info-item .value { font-size: 1rem; color: #00d4ff; font-weight: 600; margin-top: 0.2rem; }
  .refresh-dot {
    width: 8px; height: 8px; background: #00ff88; border-radius: 50%;
    display: inline-block; margin-right: 6px; animation: blink 2s infinite;
  }
  @keyframes blink { 0%,100%{opacity:1;} 50%{opacity:0.3;} }

  .footer {
    text-align: center; margin-top: 2.5rem; color: #555; font-size: 0.8rem;
  }
  .footer .brand { color: #7b2ff7; font-weight: 600; }
</style>
</head>
<body>

<div class="header">
  <h1>NEURO-MESH API Gateway</h1>
  <p>Fault-Tolerant Routing &middot; Custom DSA &middot; ML Predictive Failover</p>
</div>

<div class="grid">
  <div class="card">
    <h2>Primary Server</h2>
    <div class="status-indicator" id="primary-indicator">&#x25CF;</div>
    <div class="status-text" id="primary-status">Loading...</div>
    <div class="address" id="primary-address">&mdash;</div>
  </div>
  <div class="card">
    <h2>Fallback Server</h2>
    <div class="status-indicator" id="fallback-indicator">&#x25CF;</div>
    <div class="status-text" id="fallback-status">Loading...</div>
    <div class="address" id="fallback-address">&mdash;</div>
  </div>
</div>

<div class="info-bar">
  <div class="info-item"><div class="label">Routing</div><div class="value">Custom Trie</div></div>
  <div class="info-item"><div class="label">State</div><div class="value">HashMap O(1)</div></div>
  <div class="info-item"><div class="label">ML Model</div><div class="value">RandomForest</div></div>
  <div class="info-item"><div class="label">Status</div><div class="value"><span class="refresh-dot"></span>Live</div></div>
</div>

<!-- ML Model Chat Section -->
<div class="section">
  <h3>&#x1F9E0; ML Model Chat &mdash; Predict Server Health</h3>
  <p style="color:#777;font-size:0.82rem;margin-bottom:1rem;">
    Enter metrics below to ask the Random Forest model whether the server will survive or fail.
  </p>
  <div class="input-row">
    <label><span>Latency P95 (ms)</span><input type="number" id="inp-latency" value="350" step="10"></label>
    <label><span>Error Rate (0-1)</span><input type="number" id="inp-error" value="0.25" step="0.01" min="0" max="1"></label>
    <label><span>Requests/min</span><input type="number" id="inp-rps" value="1500" step="50"></label>
  </div>
  <button class="btn" onclick="predictHealth()">Ask Model</button>
  <div class="result-box" id="predictResult" style="display:none;"></div>
</div>

<!-- DSA Structure Viewer -->
<div class="section">
  <h3>&#x1F333; Live DSA State &mdash; Trie &amp; HashMap</h3>
  <p style="color:#777;font-size:0.82rem;margin-bottom:1rem;">
    View the internal data structures powering the gateway in real-time.
  </p>
  <button class="btn" onclick="loadDSA()">Load DSA State</button>
  <div class="result-box" id="dsaResult" style="display:none;"></div>
</div>

<div class="footer">
  <p>Auto-refreshing every 2s &middot; NEURO-MESH Phase 1 &middot; Muhammad Dayan</p>
  <p style="margin-top:0.4rem;">Powered by <span class="brand">Xiomics Systems</span></p>
</div>

<script>
async function fetchHealth() {
  try {
    const resp = await fetch('/health');
    const data = await resp.json();
    updateServer('primary', data.servers.primary);
    updateServer('fallback', data.servers.fallback);
  } catch(e) { console.error(e); }
}

function updateServer(id, info) {
  const ind = document.getElementById(id+'-indicator');
  const st = document.getElementById(id+'-status');
  const ad = document.getElementById(id+'-address');
  const alive = info.status === 'Alive';
  ind.className = 'status-indicator '+(alive?'status-alive':'status-dead');
  st.textContent = info.status;
  st.className = 'status-text '+(alive?'alive':'dead');
  ad.textContent = info.address;
}

async function predictHealth() {
  const box = document.getElementById('predictResult');
  const latency = parseFloat(document.getElementById('inp-latency').value);
  const errorRate = parseFloat(document.getElementById('inp-error').value);
  const rps = parseFloat(document.getElementById('inp-rps').value);

  box.style.display = 'block';
  box.textContent = 'Thinking...';

  try {
    const resp = await fetch('/predict-health', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({rolling_latency_p95:latency, error_rate_1min:errorRate, requests_per_minute:rps})
    });
    const data = await resp.json();

    if (data.prediction) {
      const cls = data.failure_predicted ? 'prediction-fail' : 'prediction-survive';
      box.innerHTML = `<span class="${cls}">Prediction: ${data.prediction}</span>\\n\\n`
        + `Confidence:\\n  Survive: ${(data.confidence.survive_probability*100).toFixed(1)}%\\n`
        + `  Fail:    ${(data.confidence.fail_probability*100).toFixed(1)}%\\n\\n`
        + `Model: ${data.model}\\n`
        + `Input: latency=${latency}ms, error_rate=${errorRate}, rps=${rps}`;
    } else {
      box.textContent = 'Model not available: ' + (data.error || 'Unknown error');
    }
  } catch(e) {
    box.textContent = 'Error: ' + e.message;
  }
}

async function loadDSA() {
  const box = document.getElementById('dsaResult');
  box.style.display = 'block';
  box.textContent = 'Loading...';

  try {
    const resp = await fetch('/dsa-state');
    const data = await resp.json();
    box.textContent = JSON.stringify(data, null, 2);
  } catch(e) {
    box.textContent = 'Error: ' + e.message;
  }
}

fetchHealth();
setInterval(fetchHealth, 2000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Serve the live web dashboard for the NEURO-MESH gateway."""
    return HTMLResponse(content=DASHBOARD_HTML)


# ---------------------------------------------------------------------------
# Global Exception Handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch all unhandled exceptions. Log details, return generic 500."""
    logger.error(
        "Unhandled exception: type=%s message=%s\n%s",
        type(exc).__name__,
        str(exc),
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT)
