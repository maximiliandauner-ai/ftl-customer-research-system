import json
import logging
import os
import re
from contextvars import ContextVar, Token
from datetime import UTC, datetime

SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|secret)(\s*[=:]\s*)([^\s,;]+)"
)
URL_CREDENTIAL = re.compile(r"(?P<prefix>\b[a-z][a-z0-9+.-]*://[^\s:/]+:)[^\s@]+@", re.I)
LOG_CONTEXT: ContextVar[dict[str, str | None] | None] = ContextVar("ftl_log_context", default=None)
ALLOWED_RECORD_FIELDS = (
    "event",
    "user_id",
    "pipeline_run_id",
    "outbox_id",
    "celery_task_id",
    "object_type",
    "object_id",
    "provider",
    "operation",
    "attempt",
    "duration_ms",
    "status",
    "error_code",
)


def redact(message: str) -> str:
    message = SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", message)
    return URL_CREDENTIAL.sub(r"\g<prefix>[REDACTED]@", message)


def set_log_context(*, request_id: str) -> Token[dict[str, str | None] | None]:
    return LOG_CONTEXT.set({"request_id": request_id})


def reset_log_context(token: Token[dict[str, str | None] | None]) -> None:
    LOG_CONTEXT.reset(token)


class SafeJsonFormatter(logging.Formatter):
    """Emit bounded structured logs without serializing arbitrary record attributes."""

    def format(self, record: logging.LogRecord) -> str:
        context = LOG_CONTEXT.get() or {}
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": os.environ.get("SERVICE_NAME", "application"),
            "event": getattr(record, "event", record.name),
            "request_id": context.get("request_id"),
            "user_id": None,
            "pipeline_run_id": None,
            "outbox_id": None,
            "celery_task_id": None,
            "object_type": None,
            "object_id": None,
            "provider": None,
            "operation": None,
            "attempt": 0,
            "duration_ms": 0,
            "status": "unknown",
            "error_code": None,
            "message": redact(record.getMessage()),
        }
        for field in ALLOWED_RECORD_FIELDS:
            if hasattr(record, field):
                value = getattr(record, field)
                payload[field] = redact(str(value)) if value is not None else None
        if record.exc_info:
            exception_type = record.exc_info[0]
            if exception_type is not None:
                payload["exception_type"] = exception_type.__name__
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
