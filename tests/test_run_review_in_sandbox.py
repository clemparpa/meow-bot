"""Unit tests for the S9 stub activity ``run_review_in_sandbox``."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from meow.common.logging import _HANDLER_SENTINEL, JsonFormatter
from meow.worker.activities.run_review_in_sandbox import (
    _STUB_BODY,
    run_review_in_sandbox,
)
from meow.worker.types import MeowConfig, PrContext, ReviewReport


def _ctx(*, repo: str = "octocat/hello", pr: int = 42) -> PrContext:
    return PrContext(
        repo_full_name=repo,
        pr_number=pr,
        base_sha="b" * 40,
        head_sha="h" * 40,
        diff="diff --git a/x b/x\n",
    )


@pytest.fixture
def log_buffer() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    logger = logging.getLogger("meow.worker")
    original_handlers = logger.handlers[:]
    original_propagate = logger.propagate
    logger.handlers.clear()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter("worker"))
    setattr(handler, _HANDLER_SENTINEL, True)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield buf
    finally:
        logger.handlers = original_handlers
        logger.propagate = original_propagate


def _events(buf: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line]


async def test_returns_stub_report() -> None:
    # ``@workflows.activity()`` only attaches metadata — the coroutine is
    # awaitable directly, no worker harness needed for a stub.
    report = await run_review_in_sandbox(_ctx(), MeowConfig())

    assert isinstance(report, ReviewReport)
    assert report.body == _STUB_BODY
    assert report.terminated_early is False


async def test_logs_inputs(log_buffer: io.StringIO) -> None:
    await run_review_in_sandbox(
        _ctx(pr=7),
        MeowConfig(max_turns=20, max_price_usd=1.25),
    )

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["activity.run_review_in_sandbox.stub"]
    record = events[0]
    assert record["repo"] == "octocat/hello"
    assert record["pr"] == 7
    assert record["max_turns"] == 20
    assert record["max_price_usd"] == 1.25


def test_review_report_roundtrip() -> None:
    # Mistral Workflows serialises activity I/O through the task queue, so
    # the contract must survive a model_dump → model_validate round-trip.
    report = ReviewReport(body="hello", terminated_early=True)
    assert ReviewReport.model_validate(report.model_dump()) == report


def test_pr_context_rejects_invalid() -> None:
    sha = "a" * 40
    with pytest.raises(ValidationError):
        PrContext(repo_full_name="", pr_number=1, base_sha=sha, head_sha=sha, diff="")
    with pytest.raises(ValidationError):
        PrContext(repo_full_name="r", pr_number=0, base_sha=sha, head_sha=sha, diff="")
    with pytest.raises(ValidationError):
        PrContext(repo_full_name="r", pr_number=1, base_sha="", head_sha=sha, diff="")
    with pytest.raises(ValidationError):
        PrContext(repo_full_name="r", pr_number=1, base_sha=sha, head_sha="", diff="")
