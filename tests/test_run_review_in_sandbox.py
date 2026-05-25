"""Unit tests for ``run_review_in_sandbox`` (story S12).

The activity composes three side-effecting pieces — minting a GitHub
token, filtering the diff, and running vibe in a Daytona sandbox — all
of which are mocked at their import site in the activity module. We're
testing composition, not the SDKs themselves.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from meow.common.logging import _HANDLER_SENTINEL, JsonFormatter
from meow.worker.activities import run_review_in_sandbox as activity_module
from meow.worker.activities.run_review_in_sandbox import run_review_in_sandbox
from meow.worker.types import MeowConfig, PrContext, ReviewReport

_DIFF = (
    "diff --git a/src/foo.py b/src/foo.py\n"
    "index 1111..2222 100644\n"
    "--- a/src/foo.py\n"
    "+++ b/src/foo.py\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
    "diff --git a/vendor/lib.js b/vendor/lib.js\n"
    "index 3333..4444 100644\n"
    "--- a/vendor/lib.js\n"
    "+++ b/vendor/lib.js\n"
    "@@ -1 +1 @@\n"
    "-x\n"
    "+y\n"
)


def _ctx(*, repo: str = "octocat/hello", pr: int = 42, diff: str = _DIFF) -> PrContext:
    return PrContext(
        installation_id=99,
        repo_full_name=repo,
        pr_number=pr,
        base_sha="b" * 40,
        head_sha="h" * 40,
        diff=diff,
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


@pytest.fixture
def patch_seams(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub the three external seams the activity touches.

    Returns a dict of captures + the AsyncMock so tests can assert call
    args without poking at monkeypatch internals.
    """
    captured: dict[str, Any] = {}

    async def fake_mint(installation_id: int, *, permissions: Any = None) -> str:
        captured["installation_id"] = installation_id
        captured["permissions"] = permissions
        return "ghs_test_token"

    def fake_filter(diff: str, exclude_paths: list[str]) -> str:
        captured["filter_diff"] = diff
        captured["filter_excludes"] = list(exclude_paths)
        # Mimic real behaviour: drop the vendor hunk when asked to.
        if "vendor/**" in exclude_paths:
            return _DIFF.split("diff --git a/vendor")[0]
        return diff

    review_mock = AsyncMock(
        return_value=ReviewReport(body="real review", terminated_early=False),
    )

    monkeypatch.setattr(activity_module, "mint_installation_token", fake_mint)
    monkeypatch.setattr(activity_module, "filter_diff_by_exclude", fake_filter)
    monkeypatch.setattr(activity_module, "run_vibe_review", review_mock)

    captured["review_mock"] = review_mock
    return captured


async def test_returns_report_from_vibe(patch_seams: dict[str, Any]) -> None:
    report = await run_review_in_sandbox(_ctx(), MeowConfig())

    assert isinstance(report, ReviewReport)
    assert report.body == "real review"
    assert report.terminated_early is False


async def test_mints_token_with_contents_read_permission(
    patch_seams: dict[str, Any],
) -> None:
    await run_review_in_sandbox(_ctx(), MeowConfig())

    assert patch_seams["installation_id"] == 99
    assert patch_seams["permissions"] == {"contents": "read"}


async def test_passes_token_and_filtered_diff_to_vibe(
    patch_seams: dict[str, Any],
) -> None:
    cfg = MeowConfig(exclude_paths=["vendor/**"])
    await run_review_in_sandbox(_ctx(), cfg)

    review_call = patch_seams["review_mock"].await_args
    assert review_call is not None
    # Signature: run_vibe_review(ctx, cfg, token, filtered_diff)
    assert review_call.args[2] == "ghs_test_token"
    filtered = review_call.args[3]
    assert "src/foo.py" in filtered
    assert "vendor/lib.js" not in filtered


async def test_terminated_early_propagates(
    monkeypatch: pytest.MonkeyPatch,
    patch_seams: dict[str, Any],
) -> None:
    patch_seams["review_mock"].return_value = ReviewReport(
        body="partial — out of budget",
        terminated_early=True,
    )

    report = await run_review_in_sandbox(_ctx(), MeowConfig())

    assert report.terminated_early is True
    assert report.body == "partial — out of budget"


async def test_vibe_failure_is_logged_and_reraised(
    patch_seams: dict[str, Any],
    log_buffer: io.StringIO,
) -> None:
    boom = RuntimeError("sandbox boom")
    patch_seams["review_mock"].side_effect = boom

    with pytest.raises(RuntimeError, match="sandbox boom"):
        await run_review_in_sandbox(_ctx(), MeowConfig())

    events = _events(log_buffer)
    assert any(e["event"] == "activity.run_review_in_sandbox.failed" for e in events)


async def test_done_log_records_diff_sizes_and_terminated_flag(
    patch_seams: dict[str, Any],
    log_buffer: io.StringIO,
) -> None:
    cfg = MeowConfig(exclude_paths=["vendor/**"])
    await run_review_in_sandbox(_ctx(), cfg)

    events = _events(log_buffer)
    done = next(e for e in events if e["event"] == "activity.run_review_in_sandbox.done")
    assert done["repo"] == "octocat/hello"
    assert done["pr"] == 42
    assert done["diff_bytes"] == len(_DIFF)
    assert done["filtered_diff_bytes"] < done["diff_bytes"]
    assert done["terminated_early"] is False


# --- Pydantic contract guards kept from S9 -------------------------------


def test_review_report_roundtrip() -> None:
    report = ReviewReport(body="hello", terminated_early=True)
    assert ReviewReport.model_validate(report.model_dump()) == report


def test_pr_context_rejects_invalid() -> None:
    sha = "a" * 40
    with pytest.raises(ValidationError):
        PrContext(
            installation_id=1, repo_full_name="", pr_number=1,
            base_sha=sha, head_sha=sha, diff="",
        )
    with pytest.raises(ValidationError):
        PrContext(
            installation_id=1, repo_full_name="r", pr_number=0,
            base_sha=sha, head_sha=sha, diff="",
        )
    with pytest.raises(ValidationError):
        PrContext(
            installation_id=1, repo_full_name="r", pr_number=1,
            base_sha="", head_sha=sha, diff="",
        )
    with pytest.raises(ValidationError):
        PrContext(
            installation_id=1, repo_full_name="r", pr_number=1,
            base_sha=sha, head_sha="", diff="",
        )
    with pytest.raises(ValidationError):
        PrContext(
            installation_id=0, repo_full_name="r", pr_number=1,
            base_sha=sha, head_sha=sha, diff="",
        )


