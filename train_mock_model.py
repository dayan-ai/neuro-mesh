"""NEURO-MESH Data Science Simulation: Train a failure-prediction model.

Generates a synthetic dataset of 5,000 API log entries and trains a
RandomForestClassifier to predict server failure based on latency,
error rate, and request volume metrics. Saves the trained model as model.pkl.

Usage:
    python train_mock_model.py
"""

import pickle

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

# ---------------------------------------------------------------------------
# 1. Generate synthetic dataset (5,000 samples)
# ---------------------------------------------------------------------------

np.random.seed(42)
n_samples: int = 5000

# Features:
#   rolling_latency_p95  — 95th percentile latency in ms (normal: 50-200, degraded: 200-800)
#   error_rate_1min      — error rate over last 1 minute (0.0 to 1.0)
#   requests_per_minute  — request throughput (normal: 100-1000, spike: 1000-5000)

rolling_latency_p95: np.ndarray = np.concatenate([
    np.random.uniform(50, 200, n_samples // 2),    # healthy
    np.random.uniform(200, 800, n_samples // 2),   # degraded
])

error_rate_1min: np.ndarray = np.concatenate([
    np.random.uniform(0.0, 0.05, n_samples // 2),  # healthy
    np.random.uniform(0.1, 0.8, n_samples // 2),   # degraded
])

requests_per_minute: np.ndarray = np.concatenate([
    np.random.uniform(100, 1000, n_samples // 2),   # normal load
    np.random.uniform(1000, 5000, n_samples // 2),  # high load
])

# Combine into feature matrix
X: np.ndarray = np.column_stack([
    rolling_latency_p95,
    error_rate_1min,
    requests_per_minute,
])

# Label: 1 = failure predicted, 0 = healthy
# Rule: failure if latency > 300ms AND error_rate > 0.15 AND requests > 800
y: np.ndarray = (
    (rolling_latency_p95 > 300) &
    (error_rate_1min > 0.15) &
    (requests_per_minute > 800)
).astype(int)

print(f"Dataset: {n_samples} samples")
print(f"  Healthy: {np.sum(y == 0)}")
print(f"  Failure: {np.sum(y == 1)}")
print()

# ---------------------------------------------------------------------------
# 2. Train/Test Split
# ---------------------------------------------------------------------------

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# ---------------------------------------------------------------------------
# 3. Train RandomForestClassifier
# ---------------------------------------------------------------------------

model = RandomForestClassifier(
    n_estimators=100,
    max_depth=10,
    random_state=42,
    n_jobs=-1,
)

print("Training RandomForestClassifier...")
model.fit(X_train, y_train)

# ---------------------------------------------------------------------------
# 4. Evaluate
# ---------------------------------------------------------------------------

y_pred = model.predict(X_test)
print("\nClassification Report:")
print(classification_report(y_test, y_pred, target_names=["Healthy", "Failure"]))

# Feature importance
feature_names = ["rolling_latency_p95", "error_rate_1min", "requests_per_minute"]
importances = model.feature_importances_
print("Feature Importances:")
for name, importance in zip(feature_names, importances):
    print(f"  {name}: {importance:.4f}")

# ---------------------------------------------------------------------------
# 5. Save model
# ---------------------------------------------------------------------------

model_path = "model.pkl"
with open(model_path, "wb") as f:
    pickle.dump(model, f)

print(f"\nModel saved to: {model_path}")
print("Done! The gateway can now load this model for predictive failover.")
