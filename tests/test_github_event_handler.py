"""Tests for the ``GithubEventHandler`` workflow entrypoint (story S7)."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest

from meow.common.logging import _HANDLER_SENTINEL, JsonFormatter
from meow.worker.workflows.github_event_handler import (
    GithubEventHandler,
    GithubEventInput,
)
from tests.fixtures.webhooks import issue_comment_payload


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEOW_DOMAIN", "meow.test")
    monkeypatch.setenv("GITHUB_APP_ID", "1")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("MISTRAL_API_KEY", "mk-test")
    monkeypatch.setenv("DAYTONA_API_KEY", "dk-test")
    monkeypatch.setenv("DEPLOYMENT_NAME", "meow-bot-test")
    # Tests opt in to setting MEOW_BOT_LOGIN themselves so we can exercise
    # the "no_bot_login" branch.
    monkeypatch.delenv("MEOW_BOT_LOGIN", raising=False)


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


async def test_run_skips_unexpected_event(
    monkeypatch: pytest.MonkeyPatch, log_buffer: io.StringIO
) -> None:
    monkeypatch.setenv("MEOW_BOT_LOGIN", "meow-bot")
    handler = GithubEventHandler()
    await _run(
        handler,
        GithubEventInput(event="push", delivery="del-1", payload={"zen": "ok"}),
    )

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["workflow.github_event.unexpected_event"]
    assert events[0]["gh_event"] == "push"
    assert events[0]["delivery"] == "del-1"


async def test_run_handles_malformed_payload(
    monkeypatch: pytest.MonkeyPatch, log_buffer: io.StringIO
) -> None:
    monkeypatch.setenv("MEOW_BOT_LOGIN", "meow-bot")
    handler = GithubEventHandler()
    await _run(
        handler,
        GithubEventInput(event="issue_comment", delivery="del-2", payload={"bogus": True}),
    )

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["workflow.github_event.malformed_payload"]
    assert events[0]["delivery"] == "del-2"


async def test_run_warns_when_no_bot_login(log_buffer: io.StringIO) -> None:
    # MEOW_BOT_LOGIN intentionally unset (see ``_settings_env``).
    handler = GithubEventHandler()
    payload = issue_comment_payload(body="@meow-bot review", is_pr=True)
    await _run(
        handler,
        GithubEventInput(event="issue_comment", delivery="del-3", payload=payload),
    )

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["workflow.github_event.no_bot_login"]
    assert events[0]["delivery"] == "del-3"


async def test_run_logs_no_intent_when_body_doesnt_match(
    monkeypatch: pytest.MonkeyPatch, log_buffer: io.StringIO
) -> None:
    monkeypatch.setenv("MEOW_BOT_LOGIN", "meow-bot")
    handler = GithubEventHandler()
    payload = issue_comment_payload(body="just a normal comment", is_pr=True)
    await _run(
        handler,
        GithubEventInput(event="issue_comment", delivery="del-4", payload=payload),
    )

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["workflow.github_event.no_intent"]
    assert events[0]["delivery"] == "del-4"


async def test_run_logs_intent_detected(
    monkeypatch: pytest.MonkeyPatch, log_buffer: io.StringIO
) -> None:
    monkeypatch.setenv("MEOW_BOT_LOGIN", "meow-bot")
    handler = GithubEventHandler()
    payload = issue_comment_payload(body="@meow-bot review please", is_pr=True)
    await _run(
        handler,
        GithubEventInput(event="issue_comment", delivery="del-5", payload=payload),
    )

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["workflow.intent.detected"]
    assert events[0]["intent"] == "mention_review"
    assert events[0]["delivery"] == "del-5"


async def test_run_logs_no_intent_when_comment_is_on_plain_issue(
    monkeypatch: pytest.MonkeyPatch, log_buffer: io.StringIO
) -> None:
    monkeypatch.setenv("MEOW_BOT_LOGIN", "meow-bot")
    handler = GithubEventHandler()
    # Same matching body, but ``is_pr=False`` → no ``pull_request`` link →
    # detect_intent returns None.
    payload = issue_comment_payload(body="@meow-bot review", is_pr=False)
    await _run(
        handler,
        GithubEventInput(event="issue_comment", delivery="del-6", payload=payload),
    )

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["workflow.github_event.no_intent"]
