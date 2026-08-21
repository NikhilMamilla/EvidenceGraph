"""
Structured JSON logging for EvidenceGraph backend.

Every request is assigned a correlation ID (X-Request-ID header or generated).
The correlation ID flows through all log records produced during that request.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

from pythonjsonlogger import jsonlogger  # type: ignore[import-untyped]

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Context variable — correlation ID per async request
# ---------------------------------------------------------------------------
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return _request_id_var.get() or ""


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def generate_request_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Custom JSON formatter — injects service name + request_id into every record
# ---------------------------------------------------------------------------
class EvidenceGraphJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        settings = get_settings()
        log_record["service"] = settings.app_name
        log_record["environment"] = settings.app_env.value
        rid = get_request_id()
        if rid:
            log_record["request_id"] = rid
        # Remove fields that may leak secrets
        for sensitive in ("password", "secret", "token", "key"):
            log_record.pop(sensitive, None)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
def configure_logging() -> None:
    """Call once at application startup."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.value, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = EvidenceGraphJsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Remove any pre-existing handlers to avoid duplicate log lines
    root_logger.handlers = [handler]

    # Quieten noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
