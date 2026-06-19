"""Factory for the "implement a feature" vibe task.

A factory is a pure function that turns request-scoped inputs (the issue
content + repo coords + the user's ``.meow.yml``) into a :class:`VibeTask`.
Lives outside ``activities/`` because it's CPU-only prompt rendering — no I/O.

The prompt prose lives in ``prompts/feature_implement.md`` and is rendered
through :func:`meow.worker.vibe_tasks._prompts.render_prompt`.
"""

from __future__ import annotations

from meow.common.webhooks_inputs.issues import IssueEventInput
from meow.worker.models import MeowConfig, VibeTask
from meow.worker.sandbox.builder import REPORT_PATH, WORKING_DIR
from meow.worker.vibe_tasks._prompts import render_prompt

__all__ = ["make_feature_implement_task"]


# Write-capable agent shipped in the sandbox image
# (sandbox_files/.vibe/agents/feature_implementer.toml): adds `search_replace`
# to the read-only profile so it can edit code. It writes the PR description to
# REPORT_PATH, which run_feature_implement_vibe reads back; git plumbing is done
# by the activity, not the agent.
_AGENT = "feature_implementer"
_AGENTS_MD = "AGENTS.md"


def make_feature_implement_task(webhook: IssueEventInput, cfg: MeowConfig) -> VibeTask:
    """Build the VibeTask that drives a single feature-implementation run."""
    prompt = render_prompt(
        "feature_implement.md",
        repo_full_name=webhook.repo_full_name,
        issue_number=webhook.issue_number,
        issue_title=webhook.issue_title,
        # `or ""` because issues may have no body and string.Template rejects
        # None substitutions with TypeError.
        issue_body=webhook.issue_body or "",
        working_dir=WORKING_DIR,
        default_branch=webhook.default_branch,
        report_file=REPORT_PATH,
        agents_md=_AGENTS_MD,
    )
    return VibeTask.from_meow_config(prompt=prompt, agent=_AGENT, cfg=cfg, report_path=REPORT_PATH)
