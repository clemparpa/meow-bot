"""Sandbox coordinates for a feature-scoping ``run_feature_scope_vibe`` activity.

The scoping agent explores a clean checkout of the repo's default branch —
no PR diff to overlay — so this spec is deliberately leaner than
:class:`PrSandboxSpec`: just enough for ``with_clone`` (+ ``with_meow_secrets``).
The workflow assembles it straight from the ``issues`` webhook payload, which
already carries ``repository.default_branch``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ScopeSandboxSpec"]


class ScopeSandboxSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    installation_id: int = Field(gt=0)
    repo_full_name: str = Field(pattern=r"^[^/]+/[^/]+$")
    # Branch name (or SHA) to clone and checkout — the repo's default branch
    # in the nominal flow. with_clone handles both forms.
    ref: str = Field(min_length=1)
