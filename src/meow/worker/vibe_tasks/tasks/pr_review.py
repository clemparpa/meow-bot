"""Factory for the "review a pull request" vibe task.

A factory is a pure function that turns request-scoped inputs (PR
context, repo coords, user's ``.meow.yml``) into a :class:`VibeTask`.
Lives outside ``activities/`` because it's CPU-only prompt rendering —
no I/O, no need to pay the workflow round-trip.

The prompt prose lives in ``prompts/pr_review.md`` and is rendered
through :func:`meow.worker.vibe_tasks._prompts.render_prompt`.
"""

from __future__ import annotations

from meow.worker.models import MeowConfig, PrContext, VibeTask
from meow.worker.sandbox.builder import (
    MEMORY_FILE,
    REPORT_PATH,
    WORKING_DIR,
    pr_ref_name,
)
from meow.worker.vibe_tasks._prompts import render_prompt

__all__ = ["make_pr_review_task"]


# Vibe agent shipped in the sandbox image
# (sandbox_files/.vibe/agents/issue_commenter.toml). Tool profile:
# read_file, grep, bash, todo, skill, task, write_file — the last lets it
# write its review to REPORT_PATH, which run_pr_review_vibe reads back.
_AGENT = "issue_commenter"
_AGENTS_MD = "AGENTS.md"


def make_pr_review_task(
    ctx: PrContext,
    cfg: MeowConfig,
    *,
    repo_full_name: str,
    pr_number: int,
) -> VibeTask:
    """Build the VibeTask that drives a single PR review run.

    ``repo_full_name`` and ``pr_number`` arrive as explicit kwargs
    because :class:`PrContext` doesn't carry them today (tracked
    pre-existing bug). Drop these kwargs once PrContext is extended.
    """
    prompt = render_prompt(
        "pr_review.md",
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        pr_title=ctx.title,
        # `or ""` because PRs may have no description and string.Template
        # rejects None substitutions with TypeError.
        pr_description=ctx.body or "",
        working_dir=WORKING_DIR,
        pr_ref=pr_ref_name(pr_number),
        head_sha=ctx.head_sha,
        base_sha=ctx.base_sha,
        memory_file=MEMORY_FILE,
        report_file=REPORT_PATH,
        agents_md=_AGENTS_MD,
    )
    return VibeTask.from_meow_config(prompt=prompt, agent=_AGENT, cfg=cfg, report_path=REPORT_PATH)
