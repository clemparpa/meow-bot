"""Pydantic types shared by worker activities.

``ReviewReport`` is the S9 contract consumed as-is by S10's
``post_pr_comment``. ``PrContext`` is produced by ``fetch_pr_context`` and
threaded through the rest of the review chain. ``MeowConfig`` mirrors the
``.meow.yml`` schema (SPEC §10) — see ``meow.common.meow_yml.parse_meow_yml``
for the loader that produces an instance from raw YAML text.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PrContext(BaseModel):
    """Snapshot of a PR's diff + repo-level config at the time of review.

    Produced by ``fetch_pr_context`` (S8), consumed by
    ``run_review_in_sandbox`` (S9/S12) and ``post_pr_comment`` (S10).
    """

    repo_full_name: str = Field(min_length=1)
    pr_number: int = Field(ge=1)
    base_sha: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)
    # An empty diff is a valid edge case (e.g. a PR that only changes the
    # title or labels), so no min_length here.
    diff: str
    meow_yml_raw: str | None = None


class MeowConfig(BaseModel):
    """Parsed ``.meow.yml`` — repo-level configuration for the bot (SPEC §10).

    All fields have spec-defined defaults so an unconfigured repo gets a
    sensible review. ``model`` and ``language`` drive the vibe call;
    ``max_turns`` / ``max_price_usd`` are the budget guardrails enforced by
    ``run_review_in_sandbox`` (SPEC §14); ``agents_md_path`` points at the
    repo-level convention doc the bot injects into vibe's context;
    ``exclude_paths`` is a list of gitignore-style globs whose diff hunks
    are stripped before being shown to vibe (saves turns on vendored /
    generated code).
    """

    model: str = Field(default="mistral-medium-3.5", min_length=1)
    max_turns: int = Field(default=15, ge=1)
    max_price_usd: float = Field(default=0.50, gt=0)
    language: str = Field(default="auto", min_length=1)
    agents_md_path: str = Field(default="AGENTS.md", min_length=1)
    exclude_paths: list[str] = Field(default_factory=list)


class ReviewReport(BaseModel):
    """Output of ``run_review_in_sandbox`` (frozen in S9, consumed by S10).

    ``terminated_early`` anticipates S12: when the sandbox hits ``max_turns``
    or ``max_price_usd`` (spec §14), the activity flips the flag so
    ``post_pr_comment`` can prepend an explicit header to the report.
    """

    body: str = Field(min_length=1)
    terminated_early: bool = False
