"""Repo coordinates for the ``run_vibe`` clone phase.

Decoupled from :class:`VibeTask` so a future vibe-without-repo case
(e.g. greenfield code gen) doesn't have to invent an empty clone spec.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["CloneSpec"]


class CloneSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    installation_id: int = Field(gt=0)
    repo_full_name: str = Field(pattern=r"^[^/]+/[^/]+$")
    # Branch name or commit SHA — ``git checkout`` handles both.
    ref: str = Field(min_length=1)
