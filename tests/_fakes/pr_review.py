"""Fake activities mirroring `meow.worker.activities.*` for E2E workflow tests.

Each function carries the same Temporal activity name as its production
counterpart, so `PrReviewWorkflow` dispatches transparently to whichever
implementation the worker registered. The fakes return deterministic
fixtures so the workflow's orchestration can be asserted without booting
GitHub or Koyeb.
"""

from __future__ import annotations

from datetime import timedelta

import mistralai.workflows as workflows

from meow.worker.models import MeowConfig, PrContext, PrSandboxSpec, VibeResult, VibeTask

FAKE_BASE_SHA = "b" * 40
FAKE_HEAD_SHA = "h" * 40
FAKE_COMMENT_URL = "https://github.com/owner/repo/issues/7#issuecomment-fake"


@workflows.activity(start_to_close_timeout=timedelta(seconds=5))
async def fetch_pr_context(
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
) -> PrContext:
    return PrContext(
        title="Fake PR title",
        body="Fake PR body",
        mergeable=True,
        base_sha=FAKE_BASE_SHA,
        head_sha=FAKE_HEAD_SHA,
    )


@workflows.activity(start_to_close_timeout=timedelta(seconds=5))
async def fetch_meow_config(
    installation_id: int,
    repo_full_name: str,
    base_sha: str,
) -> MeowConfig:
    return MeowConfig()


@workflows.activity(start_to_close_timeout=timedelta(seconds=5))
async def run_vibe(task: VibeTask, sandbox_spec: PrSandboxSpec) -> VibeResult:
    return VibeResult(
        body="Fake review report.",
        terminated_early=False,
        stop_reason=None,
    )


@workflows.activity(start_to_close_timeout=timedelta(seconds=5))
async def post_pr_comment(
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
    result: VibeResult,
) -> str:
    return FAKE_COMMENT_URL
