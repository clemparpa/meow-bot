"""Factory for the "review a pull request" vibe task.

A factory is a pure function that turns request-scoped inputs (PR
context, repo coords, user's ``.meow.yml``) into a :class:`VibeTask`.
Lives outside ``activities/`` because it's CPU-only prompt rendering —
no I/O, no need to pay the workflow round-trip.
"""

from __future__ import annotations

from meow.worker.models import MeowConfig, PrContext, VibeTask
from meow.worker.sandbox.builder import MEMORY_FILE, WORKING_DIR, pr_ref_name

__all__ = ["make_pr_review_task"]


# Vibe agent shipped in the sandbox image
# (sandbox_files/.vibe/agents/issue_commenter.toml). Read-only tool
# profile: read_file, grep, bash, todo, skill, task — no write_file.
_AGENT = "issue_commenter"

# Hardcoded until MeowConfig grows an ``agents_md_path`` field. Most
# repos use ``AGENTS.md`` at the root by convention.
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
    return VibeTask.from_meow_config(
        prompt=_build_prompt(ctx, cfg, repo_full_name=repo_full_name, pr_number=pr_number),
        agent=_AGENT,
        cfg=cfg,
    )


def _build_prompt(
    ctx: PrContext,
    cfg: MeowConfig,
    *,
    repo_full_name: str,
    pr_number: int,
) -> str:
    """Render the markdown prompt handed to ``vibe --prompt``.

    Assumes the sandbox was built with ``SandboxBuilder.with_pr_diff``
    (working tree = PR content as uncommitted on top of base) and
    ``with_memory`` (scratchpad at the repo root). The prompt points
    vibe at those two affordances rather than at a giant inlined diff.
    """
    lang_line = (
        "Write the report in the language of the diff/PR description."
        if cfg.language == "auto"
        else f"Write the report in {cfg.language}."
    )
    pr_ref = pr_ref_name(pr_number)
    return f"""You are a code reviewer for the GitHub PR \
{repo_full_name}#{pr_number}.

The repo is cloned at `{WORKING_DIR}`. The working tree holds the PR's \
content as if uncommitted on top of the base — inspect it with \
`git diff` or `git status` (no extra args needed). The PR's own commits \
stay reachable as the `{pr_ref}` ref and at SHA `{ctx.head_sha}` \
(base: `{ctx.base_sha}`), so `git log {pr_ref}` or \
`git log {ctx.head_sha}` shows the commit history if you want it.

A scratchpad lives at `{MEMORY_FILE}` in the repo root (git-ignored, \
not part of the PR). It already records the PR coordinates and SHAs, \
and you can append your own notes there to carry context across \
exploration steps.

Read surrounding code with your `read_file` / `grep` tools when context \
is missing. If `{_AGENTS_MD}` exists at the repo root, treat its \
conventions as authoritative.

Output one markdown report covering: correctness bugs, security issues, \
and clarity problems. Skip nits and style preferences. Be concise — \
focus on the highest-signal findings, not exhaustive coverage. {lang_line}
"""
