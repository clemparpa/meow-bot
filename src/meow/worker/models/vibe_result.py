"""Result captured from one ``run_vibe`` activity.

Produced by the runner, consumed by per-use-case action activities
(``post_pr_comment``, etc.). All presentation (headers, truncation
banners) lives action-side; this model stays format-agnostic.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["VibeResult"]


class VibeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Vibe's stdout, trimmed. ``None`` whenever the run did not exit
    # cleanly — the partial output is rarely meaningful and the action
    # layer should react to ``terminated_early`` instead of parsing
    # whatever fragment landed.
    body: str | None
    # Set on any non-zero exit (planned budget cap, hard crash, etc.).
    # Action activities use this to decide whether to post or short-circuit.
    terminated_early: bool
    # Vibe's stderr, trimmed. ``None`` when empty. Carries the
    # ``<vibe_stop_event>`` payload on budget caps and the exception
    # trace on crashes — the runner does not split the two.
    stop_reason: str | None
