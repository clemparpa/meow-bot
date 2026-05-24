"""Tests for the ``GithubEventHandler`` workflow entrypoint (story S7).

The workflow under test is sandbox-clean by construction: it never reads
``os.environ`` and never imports ``githubkit``. ``bot_login``,
``comment_body`` and ``is_pr`` are passed directly via
``GithubEventInput``, mirroring what the receiver does in production.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from meow.common.logging import _HANDLER_SENTINEL, JsonFormatter
from meow.worker.workflows.github_event_handler import (
    GithubEventHandler,
    GithubEventInput,
)


def _make_input(
    *,
    event: str = "issue_comment",
    delivery: str = "del-0",
    bot_login: str | None = "meow-bot",
    comment_body: str | None = "hello",
    is_pr: bool = True,
    payload: dict[str, Any] | None = None,
) -> GithubEventInput:
    return GithubEventInput(
        event=event,
        delivery=delivery,
        bot_login=bot_login,
        comment_body=comment_body,
        is_pr=is_pr,
        payload=payload if payload is not None else {},
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


async def _run(handler: GithubEventHandler, input: GithubEventInput) -> None:
    # The ``@workflows.workflow.entrypoint`` decorator preserves the
    # underlying coroutine, so we can invoke it directly without a Mistral
    # worker harness — that's a unit test of the dispatch logic, not an
    # integration test of the workflow runtime.
    await handler.run(input)


async def test_run_skips_unexpected_event(log_buffer: io.StringIO) -> None:
    handler = GithubEventHandler()
    await _run(handler, _make_input(event="push", delivery="del-1"))

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["workflow.github_event.unexpected_event"]
    assert events[0]["gh_event"] == "push"
    assert events[0]["delivery"] == "del-1"


async def test_run_warns_when_no_bot_login(log_buffer: io.StringIO) -> None:
    handler = GithubEventHandler()
    await _run(
        handler,
        _make_input(delivery="del-3", bot_login=None, comment_body="@meow-bot review"),
    )

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["workflow.github_event.no_bot_login"]
    assert events[0]["delivery"] == "del-3"


async def test_run_logs_no_intent_when_body_doesnt_match(log_buffer: io.StringIO) -> None:
    handler = GithubEventHandler()
    await _run(handler, _make_input(delivery="del-4", comment_body="just a normal comment"))

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["workflow.github_event.no_intent"]
    assert events[0]["delivery"] == "del-4"


async def test_run_logs_intent_detected(log_buffer: io.StringIO) -> None:
    handler = GithubEventHandler()
    await _run(
        handler,
        _make_input(delivery="del-5", comment_body="@meow-bot review please"),
    )

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["workflow.intent.detected"]
    assert events[0]["intent"] == "mention_review"
    assert events[0]["delivery"] == "del-5"


async def test_run_logs_no_intent_when_comment_is_on_plain_issue(
    log_buffer: io.StringIO,
) -> None:
    handler = GithubEventHandler()
    # Same matching body, but is_pr=False — detect_intent returns None.
    await _run(
        handler,
        _make_input(delivery="del-6", comment_body="@meow-bot review", is_pr=False),
    )

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["workflow.github_event.no_intent"]
