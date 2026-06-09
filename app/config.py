"""Enterprise configuration management for NEURO-MESH gateway.

Centralizes environment-based configuration with sensible defaults,
environment variable overrides, and validation.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EnterpriseConfig:
    """Enterprise configuration with environment overrides."""

    # Server
    host: str
    port: int
    debug: bool
    environment: str  # "development", "staging", "production"

    # Logging
    log_level: str  # "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
    structured_logging: bool  # Enable JSON structured logs

    # Observability
    enable_tracing: bool  # Enable request tracing
    enable_metrics: bool  # Enable Prometheus-style metrics
    request_timeout_seconds: float
    shutdown_grace_period_seconds: float

    # Feature flags
    enable_ml_predictions: bool
    enable_health_checks: bool

    @classmethod
    def from_env(cls) -> "EnterpriseConfig":
        """Build config from environment variables with defaults."""
        return cls(
            host=os.getenv("NEURO_MESH_HOST", "0.0.0.0"),
            port=int(os.getenv("NEURO_MESH_PORT", "8000")),
            debug=os.getenv("NEURO_MESH_DEBUG", "false").lower() == "true",
            environment=os.getenv("NEURO_MESH_ENV", "development"),
            log_level=os.getenv("NEURO_MESH_LOG_LEVEL", "INFO").upper(),
            structured_logging=os.getenv("NEURO_MESH_STRUCTURED_LOGS", "true").lower() == "true",
            enable_tracing=os.getenv("NEURO_MESH_TRACING", "true").lower() == "true",
            enable_metrics=os.getenv("NEURO_MESH_METRICS", "true").lower() == "true",
            request_timeout_seconds=float(os.getenv("NEURO_MESH_REQUEST_TIMEOUT", "30")),
            shutdown_grace_period_seconds=float(os.getenv("NEURO_MESH_SHUTDOWN_GRACE", "10")),
            enable_ml_predictions=os.getenv("NEURO_MESH_ML_ENABLED", "true").lower() == "true",
            enable_health_checks=os.getenv("NEURO_MESH_HEALTH_ENABLED", "true").lower() == "true",
        )
