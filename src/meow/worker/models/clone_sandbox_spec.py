"""Sandbox coordinates for a read-only single-branch clone.

Shared by every workflow whose agent only needs a clean checkout of one ref —
feature scoping and feature implementation both work on a read-only clone of the
default branch and never push from the sandbox (implementation extracts the
agent's changeset and commits it worker-side). Deliberately leaner than
:class:`PrSandboxSpec`: just enough for ``with_clone`` (+ ``with_meow_secrets``).
The workflow assembles it straight from the ``issues`` webhook payload, which
already carries ``repository.default_branch``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["CloneSandboxSpec"]


class CloneSandboxSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    installation_id: int = Field(gt=0)
    repo_full_name: str = Field(pattern=r"^[^/]+/[^/]+$")
    # Branch name (or SHA) to clone and checkout — the repo's default branch
    # in the nominal flow. with_clone handles both forms.
    ref: str = Field(min_length=1)
