"""
Structured logging setup.

Pure stdlib (logging + contextvars + json) — no external dependencies, so
this is fully testable the same way as matching_engine.py and policy_gate.py.

Every log line is a single JSON object with a `request_id` field, populated
via a contextvar that request_id_middleware (in app/main.py) sets per
request. This means every log line emitted anywhere during a request's
processing — including deep inside a service function — can be correlated
back to that specific request, without threading a request_id parameter
through every function signature.
"""

import contextvars
import json
import logging
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class JSONLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    """Call once at app startup. Replaces any existing handlers on the root
    logger so this is safe to call even if something else (a library) has
    already configured logging.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONLogFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
