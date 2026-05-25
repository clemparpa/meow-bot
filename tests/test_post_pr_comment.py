"""Unit tests for the S10 activity ``post_pr_comment``.

The strategy mirrors ``test_fetch_pr_context.py``: patch the only outbound
seam (``installation_client``) so it yields a ``MagicMock`` standing in
for a githubkit ``GitHub`` client. That keeps the tests focused on the
activity's composition logic and the body we send to GitHub.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from meow.common.logging import _HANDLER_SENTINEL, JsonFormatter
from meow.worker.activities import post_pr_comment as activity_module
from meow.worker.activities.post_pr_comment import (
    _HEADER,
    _scrub_secrets,
    post_pr_comment,
)
from meow.worker.types import ReviewReport

_HTML_URL = "https://github.com/octocat/hello/issues/7#issuecomment-12345"
_COMMENT_ID = 12345


def _make_gh(*, comment_id: int = _COMMENT_ID, html_url: str = _HTML_URL) -> MagicMock:
    """Build a MagicMock standing in for a githubkit ``GitHub`` client."""
    gh = MagicMock()
    comment_resp = MagicMock()
    comment_resp.parsed_data.id = comment_id
    comment_resp.parsed_data.html_url = html_url
    gh.rest.issues.async_create_comment = AsyncMock(return_value=comment_resp)
    return gh


@pytest.fixture
def captured_permissions() -> dict[str, Any]:
    """Collects the kwargs the activity passes to ``installation_client``."""
    return {}


@pytest.fixture
def patch_installation_client(
    monkeypatch: pytest.MonkeyPatch,
    captured_permissions: dict[str, Any],
) -> MagicMock:
    """Replace ``installation_client`` with a stub yielding our fake ``gh``."""
    gh = _make_gh()

    @asynccontextmanager
    async def _fake(installation_id: int, **kwargs: Any) -> AsyncIterator[MagicMock]:
        captured_permissions["installation_id"] = installation_id
        captured_permissions.update(kwargs)
        yield gh

    monkeypatch.setattr(activity_module, "installation_client", _fake)
    return gh


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


async def test_returns_html_url(patch_installation_client: MagicMock) -> None:
    url = await post_pr_comment(
        42,
        "octocat/hello",
        7,
        ReviewReport(body="looks good"),
    )
    assert url == _HTML_URL


async def test_calls_create_comment_with_correct_args(
    patch_installation_client: MagicMock,
) -> None:
    await post_pr_comment(42, "octocat/hello", 7, ReviewReport(body="hi"))

    call = patch_installation_client.rest.issues.async_create_comment.await_args
    assert call.args == ("octocat", "hello", 7)
    assert "body" in call.kwargs


async def test_body_includes_header_and_report(
    patch_installation_client: MagicMock,
) -> None:
    await post_pr_comment(
        42,
        "octocat/hello",
        7,
        ReviewReport(body="the actual review"),
    )

    call = patch_installation_client.rest.issues.async_create_comment.await_args
    body = call.kwargs["body"]
    assert body.startswith(_HEADER)
    assert "\n---\n" in body
    assert "the actual review" in body
    # Sanity: header comes before the separator, which comes before the body.
    assert body.index(_HEADER) < body.index("---") < body.index("the actual review")


async def test_requests_issues_write_permission(
    patch_installation_client: MagicMock,
    captured_permissions: dict[str, Any],
) -> None:
    await post_pr_comment(99, "octocat/hello", 1, ReviewReport(body="x"))

    assert captured_permissions["installation_id"] == 99
    assert captured_permissions["permissions"] == {"issues": "write"}


async def test_invalid_repo_full_name_raises(
    patch_installation_client: MagicMock,
) -> None:
    with pytest.raises(ValueError, match="owner/repo"):
        await post_pr_comment(42, "not-a-slash", 7, ReviewReport(body="x"))
    with pytest.raises(ValueError, match="owner/repo"):
        await post_pr_comment(42, "too/many/slashes", 7, ReviewReport(body="x"))

    patch_installation_client.rest.issues.async_create_comment.assert_not_awaited()


async def test_logs_summary(
    patch_installation_client: MagicMock,
    log_buffer: io.StringIO,
) -> None:
    await post_pr_comment(42, "octocat/hello", 7, ReviewReport(body="hello world"))

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["activity.post_pr_comment.done"]
    record = events[0]
    assert record["repo"] == "octocat/hello"
    assert record["pr"] == 7
    assert record["comment_id"] == _COMMENT_ID
    # Body is header + separator + report — bigger than just the report.
    assert record["body_bytes"] > len("hello world")


def test_scrub_secrets_is_passthrough_in_v0_1_0() -> None:
    # Invariant guard: v0.1.0 keeps scrubbing as a no-op placeholder. When
    # v0.2+ implements real sanitisation, this test should be replaced —
    # the failure here is the signal to revisit the call site.
    assert _scrub_secrets("ghp_AAA") == "ghp_AAA"
    assert _scrub_secrets("") == ""
    assert _scrub_secrets("body with\nnewlines") == "body with\nnewlines"


async def test_terminated_early_flag_ignored_for_now(
    patch_installation_client: MagicMock,
) -> None:
    # S10 does not add a budget-exhausted header — that's S12's job once the
    # real sandbox is wired. Two reports with different ``terminated_early``
    # values must produce the exact same body.
    await post_pr_comment(42, "octocat/hello", 7, ReviewReport(body="r", terminated_early=False))
    body_normal = patch_installation_client.rest.issues.async_create_comment.await_args.kwargs[
        "body"
    ]

    await post_pr_comment(42, "octocat/hello", 7, ReviewReport(body="r", terminated_early=True))
    body_terminated = patch_installation_client.rest.issues.async_create_comment.await_args.kwargs[
        "body"
    ]

    assert body_normal == body_terminated
