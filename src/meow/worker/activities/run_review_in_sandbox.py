"""Activity ``run_review_in_sandbox`` — real Daytona + vibe pipeline (S12).

Mints a down-scoped ``contents:read`` installation token, filters the PR
diff by ``exclude_paths``, then delegates the sandbox lifecycle and the
``mistral-vibe`` call to :func:`meow.worker.sandbox.vibe.run_vibe_review`.
The (ctx, MeowConfig) → ReviewReport contract frozen in S9 is preserved.
"""

from __future__ import annotations

from datetime import timedelta

import mistralai.workflows as workflows

from meow.common.github.auth import mint_installation_token
from meow.common.logging import get_logger
from meow.worker.sandbox.diff_filter import filter_diff_by_exclude
from meow.worker.sandbox.vibe import run_vibe_review
from meow.worker.types import MeowConfig, PrContext, ReviewReport

logger = get_logger("worker")


# 10 minutes is the spec-defined upper bound for a review (SPEC §8.4) — vibe
# self-limits via max_turns/max_price, but the workflow needs a hard ceiling.
@workflows.activity(start_to_close_timeout=timedelta(minutes=10))
async def run_review_in_sandbox(
    ctx: PrContext,
    meow_config: MeowConfig,
) -> ReviewReport:
    token = await mint_installation_token(
        ctx.installation_id, permissions={"contents": "read"}
    )
    filtered_diff = filter_diff_by_exclude(ctx.diff, meow_config.exclude_paths)

    try:
        report = await run_vibe_review(ctx, meow_config, token, filtered_diff)
    except Exception:
        logger.exception(
            "activity.run_review_in_sandbox.failed",
            extra={"repo": ctx.repo_full_name, "pr": ctx.pr_number},
        )
        raise

    logger.info(
        "activity.run_review_in_sandbox.done",
        extra={
            "repo": ctx.repo_full_name,
            "pr": ctx.pr_number,
            "diff_bytes": len(ctx.diff),
            "filtered_diff_bytes": len(filtered_diff),
            "terminated_early": report.terminated_early,
        },
    )
    return report
