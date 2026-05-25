"""Pydantic types shared by worker activities (S9 stubs).

These three models are introduced together so that S9, S10 and the future
S8/S13 stories can be implemented against a stable contract. The fields
are intentionally minimal — S8 will expand ``PrContext`` with the real PR
diff plumbing and S13 will expand ``MeowConfig`` with the full ``.meow.yml``
schema. ``ReviewReport`` is the final S9 contract and consumed as-is by
S10's ``post_pr_comment``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PrContext(BaseModel):
    """Minimal stub — extended in S8.

    S8 adds: ``base_sha``, ``head_sha``, ``diff: str``,
    ``meow_yml_raw: str | None``.
    """

    repo_full_name: str = Field(min_length=1)
    pr_number: int = Field(ge=1)


class MeowConfig(BaseModel):
    """Minimal stub — extended in S13.

    S13 adds ``model``, ``language``, ``agents_md_path``, ``exclude_paths``
    and the parser that loads them from ``.meow.yml``.
    """

    max_turns: int = Field(default=15, ge=1)
    max_price_usd: float = Field(default=0.50, gt=0)


class ReviewReport(BaseModel):
    """Output of ``run_review_in_sandbox`` (frozen in S9, consumed by S10).

    ``terminated_early`` anticipates S12: when the sandbox hits ``max_turns``
    or ``max_price_usd`` (spec §14), the activity flips the flag so
    ``post_pr_comment`` can prepend an explicit header to the report.
    """

    body: str = Field(min_length=1)
    terminated_early: bool = False
