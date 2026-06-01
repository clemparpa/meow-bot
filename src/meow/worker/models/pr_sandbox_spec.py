"""Sandbox coordinates for a PR-review ``run_vibe`` activity.

Bundles everything :class:`SandboxBuilder` needs to wire ``with_clone``,
``with_pr_diff``, and ``with_memory`` for a single PR review run. The
workflow class assembles this from the webhook payload + the result of
``fetch_pr_context``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["PrSandboxSpec"]


class PrSandboxSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    installation_id: int = Field(gt=0)
    repo_full_name: str = Field(pattern=r"^[^/]+/[^/]+$")
    pr_number: int = Field(gt=0)
    base_sha: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)
