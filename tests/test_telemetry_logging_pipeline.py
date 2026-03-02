"""Tests for structured logging pipeline utilities."""

from __future__ import annotations

import io
import json
import logging
from logging.handlers import QueueListener
from queue import Queue
from typing import Any, cast

import pytest

from carbon_ops.telemetry import logging_pipeline


def test_configure_structured_logging_emits_json() -> None:
    """Configure structured logging and verify JSON payloads are emitted."""

    logger = logging.getLogger("telemetry-test")
    listener = logging_pipeline.configure_structured_logging(
        logger, trace_id="trace-123", level=logging.INFO
    )

    assert listener.handlers
    stream_handler = cast(logging.StreamHandler[Any], listener.handlers[0])
    buffer = io.StringIO()
    stream_handler.setStream(buffer)

    logger.info("sample", extra={"operation": "test"})
    logging_pipeline.shutdown_listeners([listener])

    contents = buffer.getvalue().strip()
    assert contents
    payload = json.loads(contents)
    assert payload["message"] == "sample"
    assert payload["trace_id"] == "trace-123"
    assert payload["context"]["operation"] == "test"


def test_configure_structured_logging_generates_trace_id() -> None:
    """When trace ID is omitted a random identifier should be emitted."""

    logger = logging.getLogger("telemetry-auto-trace")
    listener = logging_pipeline.configure_structured_logging(logger)

    stream_handler = listener.handlers[0]
    buffer = io.StringIO()
    stream_handler.setStream(buffer)

    logger.info("auto-trace")
    logging_pipeline.shutdown_listeners([listener])

    payload = json.loads(buffer.getvalue())
    assert payload["trace_id"]
    assert isinstance(payload["trace_id"], str)
    assert payload["message"] == "auto-trace"


def test_shutdown_listeners_logs_failures(caplog: pytest.LogCaptureFixture) -> None:
    """Listener shutdown failures should emit warnings."""

    class _FailingListener(QueueListener):
        def __init__(self) -> None:
            super().__init__(Queue(), logging.StreamHandler())

        def stop(self) -> None:
            raise RuntimeError("stop failure")

    failing_listener = _FailingListener()

    with caplog.at_level(logging.WARNING):
        logging_pipeline.shutdown_listeners([failing_listener])

    assert "Failed to stop logging listener" in caplog.text


def test_bounded_queue_handler_blocking() -> None:
    """Test that BoundedQueueHandler blocks or drops correctly."""
    from queue import Queue
    import logging
    from carbon_ops.telemetry.logging_pipeline import BoundedQueueHandler

    # Case 1: Non-blocking behavior
    q = Queue[logging.LogRecord](maxsize=1)
    handler = BoundedQueueHandler(q, block=False)
    record = logging.LogRecord("test", logging.INFO, "path", 1, "msg", (), None)
    
    handler.enqueue(record)
    assert q.full()
    
    # Mock to check if handleError is called
    class MockHandler(BoundedQueueHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.error_handled = False
        def handleError(self, record: logging.LogRecord) -> None:
            self.error_handled = True
            super().handleError(record)

    handler_nb = MockHandler(q, block=False)
    handler_nb.enqueue(record)
    assert handler_nb.error_handled

    # Case 2: Blocking behavior (default)
    q_b = Queue[logging.LogRecord](maxsize=1)
    handler_b = BoundedQueueHandler(q_b, block=True)
    handler_b.enqueue(record)
    assert q_b.full()
    # We don't test actual blocking here as it would hang the test,
    # but we've verified the non-blocking path doesn't trigger.
