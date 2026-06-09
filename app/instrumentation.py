"""Enterprise instrumentation and observability utilities.

Provides request correlation, structured logging context, and
distributed tracing capabilities.
"""

import contextvars
import json
import logging
import time
import uuid
from typing import Any, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Context variables for request correlation
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


class StructuredLogger:
    """JSON-structured logging with context propagation."""

    def __init__(self, logger: logging.Logger, enable_json: bool = True):
        self.logger = logger
        self.enable_json = enable_json

    def _build_context(self) -> dict[str, Any]:
        """Build structured context from context vars."""
        return {
            "request_id": request_id_var.get(),
            "correlation_id": correlation_id_var.get(),
            "user_id": user_id_var.get(),
            "timestamp": time.time(),
        }

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        """Log with structured context using stdlib logger."""
        context = self._build_context()
        context.update(kwargs)
        if self.enable_json:
            log_message = json.dumps({"message": message, **context})
        else:
            log_message = f"{message} | {context}"
        self.logger.log(level, log_message)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info with structured context."""
        self._log(logging.INFO, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error with structured context."""
        self._log(logging.ERROR, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning with structured context."""
        self._log(logging.WARNING, message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug with structured context."""
        self._log(logging.DEBUG, message, **kwargs)


class InstrumentationMiddleware(BaseHTTPMiddleware):
    """HTTP middleware for request instrumentation.

    - Assigns unique request IDs
    - Tracks request duration
    - Logs structured request/response data
    - Propagates correlation IDs
    """

    def __init__(self, app: Any, logger: Optional[StructuredLogger] = None):
        super().__init__(app)
        self.logger = logger

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """Process request with instrumentation."""
        # Generate or extract request ID
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        cid = request.headers.get("X-Correlation-ID", rid)
        uid = request.headers.get("X-User-ID", "anonymous")

        # Set context for this request
        request_id_var.set(rid)
        correlation_id_var.set(cid)
        user_id_var.set(uid)

        # Record timing
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)

            # Add correlation headers to response
            response.headers["X-Request-ID"] = rid
            response.headers["X-Correlation-ID"] = cid

            # Log request metrics
            duration_ms = (time.time() - start_time) * 1000
            if self.logger:
                self.logger.info(
                    "HTTP request completed",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )

            return response

        except Exception as e:
            if self.logger:
                duration_ms = (time.time() - start_time) * 1000
                self.logger.error(
                    "HTTP request failed",
                    method=request.method,
                    path=request.url.path,
                    error=str(e),
                    duration_ms=duration_ms,
                )
            raise


def get_structured_logger(name: str, enable_json: bool = True) -> StructuredLogger:
    """Get a structured logger instance."""
    logger = logging.getLogger(name)
    return StructuredLogger(logger, enable_json=enable_json)
