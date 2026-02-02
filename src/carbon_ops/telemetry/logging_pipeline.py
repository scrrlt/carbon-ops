"""Structured logging utilities tailored for telemetry collection."""

from __future__ import annotations

import json
import logging
import logging.handlers
from dataclasses import dataclass
from datetime import datetime, timezone
from queue import Full, Queue
from typing import Iterable, override
from uuid import uuid4

LOGGER = logging.getLogger(__name__)

_STRUCTURED_RESERVED_KEYS: tuple[str, ...] = (
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
)


@dataclass(slots=True)
class StructuredLogContext:
    """Container describing structured logging context."""

    trace_id: str | None
    extra: dict[str, object]


class JsonFormatter(logging.Formatter):
    """Render log records as JSON with contextual metadata."""

    def __init__(self, *, default_trace_id: str | None = None) -> None:
        super().__init__()
        self._default_trace_id = default_trace_id

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - inherited
        message = record.getMessage()
        trace_id = getattr(record, "trace_id", None) or self._default_trace_id

        exception_text: str | None = None
        if record.exc_info:
            exception_text = self.formatException(record.exc_info)
        elif record.exc_text:
            exception_text = record.exc_text

        context: dict[str, object] = {}
        for key, value in record.__dict__.items():
            if key in _STRUCTURED_RESERVED_KEYS:
                continue
            if key == "trace_id":
                continue
            context[key] = value

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "trace_id": trace_id,
            "context": context,
        }

        if exception_text:
            payload["exception"] = exception_text

        return json.dumps(payload, default=str)


class BoundedQueueHandler(logging.handlers.QueueHandler):
    """Queue handler that drops records when the queue is full."""

    @override
    def enqueue(self, record: logging.LogRecord) -> None:
        """Enqueue a record without blocking when the queue has capacity."""

        try:
            self.queue.put_nowait(record)
        except Full:
            self.handleError(record)

    @override
    def handleError(self, record: logging.LogRecord) -> None:
        """Drop the record silently when the queue is full."""

        return


def configure_structured_logging(
    logger: logging.Logger,
    *,
    trace_id: str | None = None,
    level: int = logging.INFO,
) -> logging.handlers.QueueListener:
    """Configure the provided logger with structured JSON output.

    Args:
        logger: Target logger to configure.
        trace_id: Optional static trace identifier applied to every log
            message unless set dynamically via ``LoggerAdapter`` or ``extra``.
        level: Logging verbosity level. Defaults to ``logging.INFO``.

    Returns:
        The queue listener responsible for draining log records.
    """
    logger.setLevel(level)

    effective_trace_id = trace_id or str(uuid4())

    record_queue: Queue[logging.LogRecord] = Queue(maxsize=1024)
    queue_handler = BoundedQueueHandler(record_queue)
    logger.addHandler(queue_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JsonFormatter(default_trace_id=effective_trace_id))

    queue_listener = logging.handlers.QueueListener(record_queue, stream_handler)
    queue_listener.start()
    return queue_listener


def shutdown_listeners(listeners: Iterable[logging.handlers.QueueListener]) -> None:
    """Stop all queue listeners while suppressing shutdown errors."""
    for listener in listeners:
        try:
            listener.stop()
        except Exception as exc:  # pragma: no cover - defensive logging cleanup
            LOGGER.warning("Failed to stop logging listener", exc_info=exc)
