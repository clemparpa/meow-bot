"""Tests for the ``GithubEventHandler`` workflow entrypoint (stories S7, S10.5).

The workflow under test is sandbox-clean by construction: it never reads
``os.environ`` and never imports ``githubkit``. ``bot_login``,
``comment_body`` and ``is_pr`` are passed directly via
``GithubEventInput``, mirroring what the receiver does in production.

S10.5 wires the ``MENTION_REVIEW`` branch to the activity chain. We test
that branch by patching the three activities at their import site in the
workflow module — the ``@workflows.activity()`` decorator preserves the
underlying coroutine, so ``AsyncMock`` substitutes cleanly.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest

from meow.common.logging import get_logger
from meow.worker.types import MeowConfig, PrContext, ReviewReport
from meow.worker.workflows import github_event_handler as workflow_module
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


def _pr_payload(
    *,
    installation_id: int = 99,
    repo: str = "octocat/hello",
    pr: int = 42,
) -> dict[str, Any]:
    """Minimal webhook payload shape the workflow extracts coords from."""
    return {
        "installation": {"id": installation_id},
        "repository": {"full_name": repo},
        "issue": {"number": pr},
    }


@pytest.fixture(autouse=True)
def _capture_worker_logs(caplog: pytest.LogCaptureFixture):
    # ``get_logger`` sets ``propagate=False``, so caplog's root handler never
    # sees these records — attach its handler directly to the meow logger.
    logger = get_logger("worker")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.INFO, logger="meow.worker")
    yield
    logger.removeHandler(caplog.handler)


async def _run(handler: GithubEventHandler, input: GithubEventInput) -> None:
    # The ``@workflows.workflow.entrypoint`` decorator preserves the
    # underlying coroutine, so we can invoke it directly without a Mistral
    # worker harness — that's a unit test of the dispatch logic, not an
    # integration test of the workflow runtime.
    await handler.run(input)


async def test_run_skips_unexpected_event(caplog: pytest.LogCaptureFixture) -> None:
    handler = GithubEventHandler()
    await _run(handler, _make_input(event="push", delivery="del-1"))

    assert [r.message for r in caplog.records] == ["workflow.github_event.unexpected_event"]
    record: Any = caplog.records[0]
    assert record.gh_event == "push"
    assert record.delivery == "del-1"


async def test_run_warns_when_no_bot_login(caplog: pytest.LogCaptureFixture) -> None:
    handler = GithubEventHandler()
    await _run(
        handler,
        _make_input(delivery="del-3", bot_login=None, comment_body="@meow-bot review"),
    )

    assert [r.message for r in caplog.records] == ["workflow.github_event.no_bot_login"]
    record: Any = caplog.records[0]
    assert record.delivery == "del-3"


async def test_run_logs_no_intent_when_body_doesnt_match(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = GithubEventHandler()
    await _run(handler, _make_input(delivery="del-4", comment_body="just a normal comment"))

    assert [r.message for r in caplog.records] == ["workflow.github_event.no_intent"]
    record: Any = caplog.records[0]
    assert record.delivery == "del-4"


async def test_run_logs_no_intent_when_comment_is_on_plain_issue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = GithubEventHandler()
    # Same matching body, but is_pr=False — detect_intent returns None.
    await _run(
        handler,
        _make_input(delivery="del-6", comment_body="@meow-bot review", is_pr=False),
    )

    assert [r.message for r in caplog.records] == ["workflow.github_event.no_intent"]


# --- S10.5: review chain wiring -------------------------------------------

_STUB_COMMENT_URL = "https://github.com/octocat/hello/issues/42#issuecomment-1"


@pytest.fixture
def patch_activities(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Replace the 3 activities at the workflow module's import site."""
    ctx = PrContext(
        installation_id=99,
        repo_full_name="octocat/hello",
        pr_number=42,
        base_sha="b" * 40,
        head_sha="h" * 40,
        diff="diff --git a/x b/x\n",
    )
    report = ReviewReport(body="stub review", terminated_early=False)

    mocks = {
        "fetch_pr_context": AsyncMock(return_value=ctx),
        "run_review_in_sandbox": AsyncMock(return_value=report),
        "post_pr_comment": AsyncMock(return_value=_STUB_COMMENT_URL),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(workflow_module, name, mock)
    return mocks


async def test_run_review_chain_calls_all_activities_in_order(
    patch_activities: dict[str, AsyncMock],
) -> None:
    handler = GithubEventHandler()
    await _run(
        handler,
        _make_input(
            delivery="del-chain-1",
            comment_body="@meow-bot review",
            payload=_pr_payload(installation_id=99, repo="octocat/hello", pr=42),
        ),
    )

    patch_activities["fetch_pr_context"].assert_awaited_once_with(99, "octocat", "hello", 42)
    # post_pr_comment takes (installation_id, repo_full_name, pr_number, report)
    post_call = patch_activities["post_pr_comment"].await_args
    assert post_call is not None
    assert post_call.args[0] == 99
    assert post_call.args[1] == "octocat/hello"
    assert post_call.args[2] == 42


async def test_run_review_chain_passes_report_to_post_comment(
    patch_activities: dict[str, AsyncMock],
) -> None:
    handler = GithubEventHandler()
    await _run(
        handler,
        _make_input(
            delivery="del-chain-2",
            comment_body="@meow-bot review",
            payload=_pr_payload(),
        ),
    )

    review_return = patch_activities["run_review_in_sandbox"].return_value
    post_call = patch_activities["post_pr_comment"].await_args
    assert post_call is not None
    # The ReviewReport returned by run_review_in_sandbox must flow through
    # to post_pr_comment as its 4th positional arg — same object identity.
    assert post_call.args[3] is review_return


async def test_run_review_chain_passes_default_config_when_no_meow_yml(
    patch_activities: dict[str, AsyncMock],
) -> None:
    # ctx.meow_yml_raw is None in the default patch_activities fixture, so
    # parse_meow_yml falls back to defaults. The workflow must pass those
    # defaults through unchanged to run_review_in_sandbox.
    handler = GithubEventHandler()
    await _run(
        handler,
        _make_input(
            delivery="del-chain-3",
            comment_body="@meow-bot review",
            payload=_pr_payload(),
        ),
    )

    review_call = patch_activities["run_review_in_sandbox"].await_args
    assert review_call is not None
    meow_config = review_call.args[1]
    assert isinstance(meow_config, MeowConfig)
    assert meow_config == MeowConfig()


async def test_run_review_chain_parses_meow_yml_from_context(
    patch_activities: dict[str, AsyncMock],
) -> None:
    # When PrContext carries a meow_yml_raw payload, parse_meow_yml is
    # called by the workflow and the resulting MeowConfig (not defaults)
    # is what run_review_in_sandbox receives.
    ctx = PrContext(
        installation_id=99,
        repo_full_name="octocat/hello",
        pr_number=42,
        base_sha="b" * 40,
        head_sha="h" * 40,
        diff="diff --git a/x b/x\n",
        meow_yml_raw="model: mistral-large-2.6\nmax_turns: 7\nexclude_paths:\n  - vendor/**\n",
    )
    patch_activities["fetch_pr_context"].return_value = ctx

    handler = GithubEventHandler()
    await _run(
        handler,
        _make_input(
            delivery="del-chain-3b",
            comment_body="@meow-bot review",
            payload=_pr_payload(),
        ),
    )

    review_call = patch_activities["run_review_in_sandbox"].await_args
    assert review_call is not None
    meow_config = review_call.args[1]
    assert isinstance(meow_config, MeowConfig)
    assert meow_config.model == "mistral-large-2.6"
    assert meow_config.max_turns == 7
    assert meow_config.exclude_paths == ["vendor/**"]
    # Unspecified fields keep their defaults.
    assert meow_config.max_price_usd == MeowConfig().max_price_usd


async def test_run_review_chain_logs_review_posted(
    patch_activities: dict[str, AsyncMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = GithubEventHandler()
    await _run(
        handler,
        _make_input(
            delivery="del-chain-4",
            comment_body="@meow-bot review",
            payload=_pr_payload(),
        ),
    )

    assert [r.message for r in caplog.records] == [
        "workflow.intent.detected",
        "workflow.review_posted",
    ]
    detected: Any = caplog.records[0]
    posted: Any = caplog.records[1]
    assert detected.intent == "mention_review"
    assert posted.delivery == "del-chain-4"
    assert posted.comment_url == _STUB_COMMENT_URL
    assert posted.terminated_early is False


async def test_run_review_chain_raises_on_malformed_payload(
    patch_activities: dict[str, AsyncMock],
) -> None:
    # Missing the "installation" key — a contract violation, not a runtime
    # hazard worth defending against. KeyError must propagate so the
    # workflow execution fails loudly rather than silently dropping work.
    handler = GithubEventHandler()
    with pytest.raises(KeyError):
        await _run(
            handler,
            _make_input(
                delivery="del-chain-5",
                comment_body="@meow-bot review",
                payload={"repository": {"full_name": "x/y"}, "issue": {"number": 1}},
            ),
        )
    patch_activities["fetch_pr_context"].assert_not_awaited()
