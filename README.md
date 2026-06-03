<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/scikit--learn-ML-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white" alt="scikit-learn">
  <img src="https://img.shields.io/badge/Deployed-Vercel-black?style=for-the-badge&logo=vercel&logoColor=white" alt="Vercel">
  <img src="https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge" alt="License">
</p>

<h1 align="center">🧠 NEURO-MESH</h1>
<h3 align="center">Fault-Tolerant API Gateway with ML Predictive Failover</h3>

<p align="center">
  <em>An enterprise-grade intelligent reverse proxy that combines custom Data Structures,<br>
  Machine Learning, and Asynchronous Networking into a single cohesive system.</em>
</p>

<p align="center">
  <strong>Developed by <a href="#">Xiomics Systems</a></strong><br>
  Lead Engineer: Muhammad Dayan
</p>

---

## 🌐 Live Deployment

> **Production URL:** [https://neuro-mesh.vercel.app](https://neuro-mesh.vercel.app)

---

## 🏗️ Architecture Overview

NEURO-MESH is a three-pillar system integrating **Data Science**, **Data Structures & Algorithms**, and **Computer Networking** into a unified API gateway:

```
┌─────────────────────────────────────────────────────────────────┐
│                      NEURO-MESH GATEWAY                         │
├───────────────┬──────────────────────┬──────────────────────────┤
│   🧠 DS/ML    │      📊 DSA          │      🌐 Networking       │
│               │                      │                          │
│ RandomForest  │  Custom Trie Router  │  FastAPI Async Proxy     │
│ Classifier    │  (Prefix Tree)       │  (Reverse Proxy)         │
│               │                      │                          │
│ Predictive    │  HashMap O(1) State  │  HTTP Health Mgmt        │
│ Failover      │  Manager             │  Endpoints               │
│               │                      │                          │
│ 5000-sample   │  Static > Dynamic    │  Deterministic           │
│ Training Set  │  Priority            │  Failover Logic          │
│               │                      │                          │
│ model.pkl     │  Max Depth: 20       │  asyncio.Lock            │
│ (serialized)  │  Path Normalization  │  Concurrency Control     │
└───────────────┴──────────────────────┴──────────────────────────┘
```

---

## 🔬 Core Components

### 1. Data Science — ML Predictive Failover

| Aspect | Detail |
|--------|--------|
| **Model** | RandomForestClassifier (100 trees, max_depth=10) |
| **Training Data** | 5,000 synthetic API log entries |
| **Features** | `rolling_latency_p95`, `error_rate_1min`, `requests_per_minute` |
| **Target** | Binary classification: Server Failure (1) vs Healthy (0) |
| **Integration** | Real-time inference on every proxy request |
| **Endpoint** | `POST /predict-health` — interactive model chat |

The model preemptively reroutes traffic to the fallback server *before* the primary actually crashes, reducing downtime to near-zero.

### 2. Data Structures & Algorithms — Custom Routing Engine

| Component | Complexity | Description |
|-----------|-----------|-------------|
| **Trie (Prefix Tree)** | O(log n) resolve | Custom-built from scratch; supports static & dynamic `{param}` segments |
| **HashMap (dict)** | O(1) lookup | Server health state stored in Python dict with instant access |
| **Static Priority** | O(1) per level | Static segments always prioritized over dynamic at each trie level |
| **Path Normalization** | O(n) | Trailing slash equivalence, depth limit enforcement (max 20) |

No external routing libraries used — the entire Trie is implemented from first principles.

### 3. Computer Networking — Asynchronous Reverse Proxy

| Feature | Implementation |
|---------|---------------|
| **Framework** | FastAPI with full async/await architecture |
| **Concurrency** | `asyncio.Lock` serializes state access — no race conditions |
| **Proxy Endpoint** | `POST /proxy/{path:path}` — universal request interception |
| **Health Management** | `GET /health`, `PUT /health/{server_id}` |
| **Failover Logic** | Primary → Fallback → 503 (deterministic cascade) |
| **Error Handling** | Global exception handler, input validation, RFC 3986 path compliance |

---

## 📂 Project Structure

```
neuro-mesh/
├── app/
│   ├── main.py              # FastAPI entry point + dashboard + ML/DSA endpoints
│   ├── models.py            # Pydantic schemas & HealthStatus enum
│   ├── trie.py              # Custom Trie (prefix tree) implementation
│   ├── state_manager.py     # HashMap state manager with asyncio.Lock
│   ├── routes.py            # Proxy endpoint with ML integration
│   ├── health_routes.py     # Health management endpoints
│   └── validation.py        # RFC 3986 path validation
├── tests/
│   ├── test_trie.py         # 33 unit tests
│   ├── test_state_manager.py# 22 unit tests
│   ├── test_proxy.py        # 12 endpoint tests
│   ├── test_health.py       # 10 endpoint tests
│   ├── test_main.py         # 12 wiring tests
│   ├── test_properties.py   # 16 Hypothesis property-based tests (1600+ examples)
│   └── test_integration.py  # 9 end-to-end integration tests
├── train_mock_model.py      # ML model training script
├── simulate_traffic.py      # Live traffic simulator with terminal dashboard
├── index.html               # Client frontend (standalone)
├── model.pkl                # Trained RandomForest model (generated)
├── requirements.txt         # Python dependencies
├── vercel.json              # Vercel deployment configuration
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
git clone https://github.com/your-repo/neuro-mesh.git
cd neuro-mesh
pip install -r requirements.txt
```

### Train the ML Model

```bash
python train_mock_model.py
```

This generates `model.pkl` with a trained RandomForestClassifier.

### Run the Server

```bash
uvicorn app.main:app --reload
```

Gateway available at **http://localhost:8000**

### Access the Dashboard

- **Server Dashboard:** http://localhost:8000/
- **Client Frontend:** Open `index.html` in your browser
- **API Docs:** http://localhost:8000/docs

### Run Tests

```bash
pytest                          # All 114 tests
pytest --cov=app               # With coverage
pytest tests/test_properties.py # Property-based tests only
```

---

## 🔌 API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Live monitoring dashboard |
| `/proxy/{path}` | POST | Universal proxy with ML failover |
| `/health` | GET | All server statuses |
| `/health/{server_id}` | PUT | Toggle server health |
| `/predict-health` | POST | ML model prediction chat |
| `/dsa-state` | GET | Live Trie & HashMap visualization |
| `/docs` | GET | Interactive Swagger UI |

---

## 🧪 Testing

| Suite | Tests | Type |
|-------|-------|------|
| Trie | 33 | Unit |
| State Manager | 22 | Unit + Concurrency |
| Proxy Endpoint | 12 | HTTP Integration |
| Health Endpoints | 10 | HTTP Integration |
| App Wiring | 12 | Startup/Config |
| Properties | 16 (×100 examples) | Hypothesis PBT |
| Integration | 9 | End-to-End |
| **Total** | **114** | |

---

## ☁️ Vercel Deployment

The project deploys to Vercel via `vercel.json`:

```json
{
  "builds": [{"src": "app/main.py", "use": "@vercel/python"}],
  "routes": [{"src": "/(.*)", "dest": "app/main.py"}]
}
```

Push to GitHub and import into Vercel — auto-deploys on every commit.

---

## 📊 Performance Characteristics

| Metric | Value |
|--------|-------|
| Route Resolution | O(d) where d = path depth (max 20) |
| Health Lookup | O(1) amortized |
| ML Inference | ~2ms per prediction |
| Concurrent Safety | asyncio.Lock (zero race conditions) |
| Test Coverage | 114 tests, 1600+ property examples |

---

<p align="center">
  <strong>Built with precision by Xiomics Systems</strong><br>
  <em>Where intelligence meets infrastructure.</em>
</p>
