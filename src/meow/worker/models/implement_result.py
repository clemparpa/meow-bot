"""Result captured from one ``run_feature_implement_vibe`` activity.

Richer than :class:`VibeResult` because the implementation flow forks on it:
the workflow commits + opens a PR when the agent produced changes, and falls
back to an explanatory issue comment when it didn't. Wraps the vibe run's
:class:`VibeResult` (the PR description + terminated-early signal) alongside the
:class:`Changeset` the agent left in the (read-only) sandbox — committed
worker-side, so no git state crosses the sandbox boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from meow.worker.models.changeset import Changeset
from meow.worker.models.vibe_result import VibeResult

__all__ = ["ImplementResult"]


class ImplementResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    # The vibe run: ``body`` is the agent's PR description (read from the report
    # file), plus the terminated-early / stop-reason signal.
    vibe: VibeResult
    # The file changes the agent made (empty when it changed nothing, or when
    # the run terminated early / the diff was too large to ship). The workflow
    # opens a PR iff this is non-empty; otherwise it posts a comment.
    changeset: Changeset
