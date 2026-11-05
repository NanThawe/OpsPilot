import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

request_id_context: ContextVar[str] = ContextVar(
    "request_id",
    default="-",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }

        event = getattr(record, "event", None)
        if event is not None:
            payload["event"] = event

        event_data = getattr(record, "event_data", None)
        if isinstance(event_data, dict):
            payload.update(event_data)

        if record.exc_info:
            payload["exception"] = self.formatException(
                record.exc_info
            )

        return json.dumps(
            payload,
            default=str,
            ensure_ascii=False,
        )


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def make_request_id(value: str | None) -> str:
    if value:
        cleaned = value.strip()

        if (
            cleaned
            and len(cleaned) <= 100
            and all(
                character.isalnum()
                or character in "-_"
                for character in cleaned
            )
        ):
            return cleaned

    return str(uuid4())


def log_event(
    logger: logging.Logger,
    event: str,
    **fields: Any,
) -> None:
    logger.info(
        event,
        extra={
            "event": event,
            "event_data": fields,
        },
    )


class TraceTimer:
    def __init__(
        self,
        logger: logging.Logger,
        event: str,
        **fields: Any,
    ):
        self.logger = logger
        self.event = event
        self.fields = fields
        self.started = 0.0

    def __enter__(self):
        self.started = perf_counter()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        duration_ms = round(
            (perf_counter() - self.started) * 1000,
            2,
        )

        fields = {
            **self.fields,
            "duration_ms": duration_ms,
            "success": exc_type is None,
        }

        if exc_type is not None:
            fields["error_type"] = exc_type.__name__

        log_event(
            self.logger,
            self.event,
            **fields,
        )

        return False