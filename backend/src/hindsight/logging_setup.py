"""Structured (JSON) logs. Every line carries the request ID of the request that produced it."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

# Set by the request-ID middleware, read by every log line written during that request.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_STANDARD_ATTRS = set(vars(logging.makeLogRecord({})))


class JsonFormatter(logging.Formatter):
    """Formats each log record as one JSON line, including the current request ID."""

    def format(self, record: logging.LogRecord) -> str:
        """Turn a log record into a JSON string (time, level, message, requestId, extra fields)."""
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "requestId": request_id_var.get(),
        }
        # Anything passed with logger.info("...", extra={...}) becomes a JSON field.
        entry.update({k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str) -> None:
    """Send all logs to stdout as JSON, at the given level (e.g. "INFO")."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Our middleware writes one access line per request; silence uvicorn's plain-text one.
    logging.getLogger("uvicorn.access").disabled = True
