"""Stub for the review activity (story S9).

This is the signature the rest of phase C (S8, S10) targets. The real
Daytona + ``mistral-vibe`` integration lands in S11/S12 and will replace
the body of this function — the signature and return type are frozen.
"""

from __future__ import annotations

from datetime import timedelta

import mistralai.workflows as workflows

from meow.common.logging import get_logger
from meow.worker.types import MeowConfig, PrContext, ReviewReport

logger = get_logger("worker")

# The header marks the stubbed output so reviewers on test PRs can tell at
# a glance the bot hasn't actually read the diff yet. Replaced wholesale
# by S12 with the real vibe report.
_STUB_BODY = (
    "> [meow-bot stub] Review pipeline ran end-to-end, but Daytona+vibe "
    "are not yet integrated (S12)."
)


# The 10-minute budget is sized for the real sandbox (S12) so we don't
# have to re-touch the decorator when the body is filled in.
@workflows.activity(start_to_close_timeout=timedelta(minutes=10))
async def run_review_in_sandbox(
    ctx: PrContext,
    meow_config: MeowConfig,
) -> ReviewReport:
    logger.info(
        "activity.run_review_in_sandbox.stub",
        extra={
            "repo": ctx.repo_full_name,
            "pr": ctx.pr_number,
            "max_turns": meow_config.max_turns,
            "max_price_usd": meow_config.max_price_usd,
        },
    )
    return ReviewReport(body=_STUB_BODY)
