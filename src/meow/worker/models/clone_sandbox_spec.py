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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meow.worker.sandbox.builder import SandboxBuilder

__all__ = ["CloneSandboxSpec"]


class CloneSandboxSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    installation_id: int = Field(gt=0)
    repo_full_name: str = Field(pattern=r"^[^/]+/[^/]+$")
    # Branch name (or SHA) to clone and checkout — the repo's default branch
    # in the nominal flow. with_clone handles both forms.
    ref: str = Field(min_length=1)

    def configure_builder(self, builder: SandboxBuilder) -> SandboxBuilder:
        """Configure a :class:`SandboxBuilder` for a read-only clone sandbox.

        Wire up ``with_meow_secrets`` and ``with_clone`` (at the specified ref),
        plus ``with_report`` (the agent's output file). This is shared by both
        feature-scope and feature-implement workflows — they differ only in
        post-processing (feature-implement extracts a changeset).
        Returns the builder for chaining or immediate use.
        """
        return (
            builder.with_meow_secrets(
                installation_id=self.installation_id,
                repo_full_name=self.repo_full_name,
            )
            .with_clone(
                repo_full_name=self.repo_full_name,
                ref=self.ref,
            )
            .with_report()
        )
