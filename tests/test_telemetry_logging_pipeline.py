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
