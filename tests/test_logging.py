"""Tests for :mod:`meow.common.logging`."""

from __future__ import annotations

import json
import logging
import re

import pytest

from meow.common.logging import get_logger

_ISO8601_UTC = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+00:00$",
)


@pytest.fixture(autouse=True)
def _reset_meow_loggers() -> None:
    """Reset loggers under the ``meow.`` namespace between tests."""
    manager = logging.Logger.manager
    for name in list(manager.loggerDict):
        if name.startswith("meow."):
            logger = logging.getLogger(name)
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
            logger.propagate = True
            logger.setLevel(logging.NOTSET)


def _parse_lines(captured: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in captured.strip().splitlines() if line.strip()]


def test_minimal_schema(capsys: pytest.CaptureFixture[str]) -> None:
    logger = get_logger("receiver")
    logger.info("webhook.received")

    lines = _parse_lines(capsys.readouterr().out)
    assert len(lines) == 1

    record = lines[0]
    assert set(record.keys()) >= {"ts", "svc", "level", "event"}
    assert record["svc"] == "receiver"
    assert record["level"] == "info"
    assert record["event"] == "webhook.received"
    assert isinstance(record["ts"], str)
    assert _ISO8601_UTC.match(record["ts"]) is not None


def test_extra_fields_at_top_level(capsys: pytest.CaptureFixture[str]) -> None:
    logger = get_logger("receiver")
    logger.info(
        "webhook.received",
        extra={"gh_event": "issue_comment", "delivery": "abcd-1234"},
    )

    lines = _parse_lines(capsys.readouterr().out)
    assert len(lines) == 1
    record = lines[0]
    assert record["gh_event"] == "issue_comment"
    assert record["delivery"] == "abcd-1234"
    # Schema keys are still present alongside the extras.
    assert record["svc"] == "receiver"
    assert record["event"] == "webhook.received"


def test_level_is_lowercased(capsys: pytest.CaptureFixture[str]) -> None:
    logger = get_logger("worker")
    logger.warning("budget.exceeded")

    lines = _parse_lines(capsys.readouterr().out)
    assert len(lines) == 1
    assert lines[0]["level"] == "warning"
    assert lines[0]["svc"] == "worker"


def test_extra_cannot_clobber_schema_keys(capsys: pytest.CaptureFixture[str]) -> None:
    logger = get_logger("receiver")
    logger.info("webhook.received", extra={"svc": "intruder", "level": "fatal"})

    lines = _parse_lines(capsys.readouterr().out)
    assert len(lines) == 1
    record = lines[0]
    # Schema keys must reflect the service / real level, not the extras.
    assert record["svc"] == "receiver"
    assert record["level"] == "info"


def test_idempotent_no_double_handler(capsys: pytest.CaptureFixture[str]) -> None:
    first = get_logger("foo")
    second = get_logger("foo")

    assert first is second
    assert len(first.handlers) == 1

    second.info("ping")
    lines = _parse_lines(capsys.readouterr().out)
    assert len(lines) == 1
    assert lines[0]["event"] == "ping"


def test_independent_services_have_distinct_loggers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    receiver = get_logger("receiver")
    worker = get_logger("worker")

    assert receiver is not worker

    receiver.info("hello")
    worker.info("hello")

    lines = _parse_lines(capsys.readouterr().out)
    assert [line["svc"] for line in lines] == ["receiver", "worker"]
