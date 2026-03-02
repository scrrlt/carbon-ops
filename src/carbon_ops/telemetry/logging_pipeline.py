"""Structured logging utilities tailored for telemetry collection."""

from __future__ import annotations

import json
import logging
import logging.handlers
from dataclasses import dataclass
from datetime import datetime, timezone
from queue import Full, Queue
from typing import Iterable, cast, override
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
    """Queue handler that prevents silent record loss.

    If 'block' is True, enqueuing will block until space is available.
    If 'block' is False, it will attempt a non-blocking put and call
    handleError if the queue is full.
    """

    def __init__(self, queue: Queue[logging.LogRecord], *, block: bool = True) -> None:
        super().__init__(queue)
        self._block = block

    @override
    def enqueue(self, record: logging.LogRecord) -> None:
        """Enqueue a record, optionally blocking if the queue is full."""
        # self.queue is typed as _QueueLike in the base class, which lacks put/put_nowait.
        # We cast to Queue to satisfy the type checker.
        queue = cast(Queue[logging.LogRecord], self.queue)
        if self._block:
            # For compliance and audit trails, we MUST NOT drop records.
            # Blocking ensures every record is eventually enqueued.
            queue.put(record)
        else:
            try:
                queue.put_nowait(record)
            except Full:
                self.handleError(record)

    @override
    def handleError(self, record: logging.LogRecord) -> None:
        """Handle errors during record enqueuing without silent drops."""
        # Call the base implementation which (if raiseExceptions is set)
        # prints the error to sys.stderr, providing visibility into drops.
        super().handleError(record)


def configure_structured_logging(
    logger: logging.Logger,
    *,
    trace_id: str | None = None,
    level: int = logging.INFO,
    block: bool = True,
) -> logging.handlers.QueueListener:
    """Configure the provided logger with structured JSON output.

    Args:
        logger: Target logger to configure.
        trace_id: Optional static trace identifier applied to every log
            message unless set dynamically via ``LoggerAdapter`` or ``extra``.
        level: Logging verbosity level. Defaults to ``logging.INFO``.
        block: Whether to block when the logging queue is full.
            Defaults to True to prevent audit trail loss.

    Returns:
        The queue listener responsible for draining log records.
    """
    logger.setLevel(level)

    effective_trace_id = trace_id or str(uuid4())

    record_queue: Queue[logging.LogRecord] = Queue(maxsize=1024)
    queue_handler = BoundedQueueHandler(record_queue, block=block)
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
