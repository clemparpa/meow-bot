"""Sandbox coordinates for a PR-review ``run_vibe`` activity.

Bundles everything :class:`SandboxBuilder` needs to wire ``with_clone``,
``with_pr_diff``, and ``with_memory`` for a single PR review run. The
workflow class assembles this from the webhook payload + the result of
``fetch_pr_context``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meow.worker.sandbox.builder import SandboxBuilder

__all__ = ["PrSandboxSpec"]


class PrSandboxSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    installation_id: int = Field(gt=0)
    repo_full_name: str = Field(pattern=r"^[^/]+/[^/]+$")
    pr_number: int = Field(gt=0)
    base_sha: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)

    def configure_builder(self, builder: SandboxBuilder) -> SandboxBuilder:
        """Configure a :class:`SandboxBuilder` for a PR-review sandbox.

        Wire up ``with_meow_secrets``, ``with_clone`` (at the base SHA),
        ``with_pr_diff`` (to overlay the PR changes), ``with_memory`` (the
        PR-scoped scratchpad), and ``with_report`` (the agent's output file).
        Returns the builder for chaining or immediate use.
        """
        return (
            builder.with_meow_secrets(
                installation_id=self.installation_id,
                repo_full_name=self.repo_full_name,
            )
            .with_clone(
                repo_full_name=self.repo_full_name,
                ref=self.base_sha,
            )
            .with_pr_diff(
                pr_number=self.pr_number,
                base_sha=self.base_sha,
                head_sha=self.head_sha,
            )
            .with_memory(
                pr_number=self.pr_number,
                base_sha=self.base_sha,
                head_sha=self.head_sha,
                repo_full_name=self.repo_full_name,
            )
            .with_report()
        )
