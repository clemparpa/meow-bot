"""Unit tests for the S8 activity ``fetch_pr_context``.

The strategy is to patch ``installation_client`` (the only outbound
seam) so it yields a ``MagicMock`` standing in for a githubkit ``GitHub``
client. That keeps the tests focused on the activity's composition logic
without spinning up httpx mocks or a real installation token.
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
from githubkit.exception import RequestFailed

from meow.common.logging import _HANDLER_SENTINEL, JsonFormatter
from meow.worker.activities import fetch_pr_context as activity_module
from meow.worker.activities.fetch_pr_context import fetch_pr_context
from meow.worker.types import PrContext

_BASE_SHA = "b" * 40
_HEAD_SHA = "h" * 40
_DIFF = "diff --git a/x b/x\n@@ -1 +1 @@\n-old\n+new\n"
_MEOW_YML = "model: mistral-medium-3.5\nmax_turns: 20\n"


def _make_gh(
    *,
    base_sha: str = _BASE_SHA,
    head_sha: str = _HEAD_SHA,
    diff_text: str = _DIFF,
    meow_yml_text: str | None = _MEOW_YML,
    meow_yml_status: int = 200,
) -> MagicMock:
    """Build a MagicMock standing in for a githubkit ``GitHub`` client."""
    gh = MagicMock()

    pr_resp = MagicMock()
    pr_resp.parsed_data.base.sha = base_sha
    pr_resp.parsed_data.head.sha = head_sha
    gh.rest.pulls.async_get = AsyncMock(return_value=pr_resp)

    async def _arequest(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> MagicMock:
        if "/contents/" in url:
            if meow_yml_status != 200:
                fake_resp = MagicMock()
                fake_resp.status_code = meow_yml_status
                raise RequestFailed(fake_resp)
            assert meow_yml_text is not None
            resp = MagicMock()
            resp.text = meow_yml_text
            return resp
        # The unified-diff endpoint on /pulls/{n}
        resp = MagicMock()
        resp.text = diff_text
        return resp

    gh.arequest = AsyncMock(side_effect=_arequest)
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


async def test_returns_full_pr_context(patch_installation_client: MagicMock) -> None:
    ctx = await fetch_pr_context(42, "octocat", "hello", 7)

    assert isinstance(ctx, PrContext)
    assert ctx.repo_full_name == "octocat/hello"
    assert ctx.pr_number == 7
    assert ctx.base_sha == _BASE_SHA
    assert ctx.head_sha == _HEAD_SHA
    assert ctx.diff == _DIFF
    assert ctx.meow_yml_raw == _MEOW_YML


async def test_meow_yml_missing_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = _make_gh(meow_yml_text=None, meow_yml_status=404)

    @asynccontextmanager
    async def _fake(installation_id: int, **kwargs: Any) -> AsyncIterator[MagicMock]:
        yield gh

    monkeypatch.setattr(activity_module, "installation_client", _fake)

    ctx = await fetch_pr_context(42, "octocat", "hello", 7)
    assert ctx.meow_yml_raw is None
    assert ctx.diff == _DIFF


async def test_meow_yml_other_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = _make_gh(meow_yml_status=500)

    @asynccontextmanager
    async def _fake(installation_id: int, **kwargs: Any) -> AsyncIterator[MagicMock]:
        yield gh

    monkeypatch.setattr(activity_module, "installation_client", _fake)

    with pytest.raises(RequestFailed):
        await fetch_pr_context(42, "octocat", "hello", 7)


async def test_requests_contents_read_permission(
    patch_installation_client: MagicMock,
    captured_permissions: dict[str, Any],
) -> None:
    await fetch_pr_context(99, "octocat", "hello", 1)

    assert captured_permissions["installation_id"] == 99
    assert captured_permissions["permissions"] == {"contents": "read"}


async def test_logs_summary(
    patch_installation_client: MagicMock,
    log_buffer: io.StringIO,
) -> None:
    await fetch_pr_context(42, "octocat", "hello", 7)

    events = _events(log_buffer)
    assert [e["event"] for e in events] == ["activity.fetch_pr_context.done"]
    record = events[0]
    assert record["repo"] == "octocat/hello"
    assert record["pr"] == 7
    assert record["diff_bytes"] == len(_DIFF)
    assert record["has_meow_yml"] is True


async def test_empty_diff_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    gh = _make_gh(diff_text="")

    @asynccontextmanager
    async def _fake(installation_id: int, **kwargs: Any) -> AsyncIterator[MagicMock]:
        yield gh

    monkeypatch.setattr(activity_module, "installation_client", _fake)

    ctx = await fetch_pr_context(42, "octocat", "hello", 7)
    assert ctx.diff == ""
