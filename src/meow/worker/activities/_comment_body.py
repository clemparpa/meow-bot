"""Shared rendering for vibe-result GitHub comments.

Both ``post_pr_comment`` (PR review) and ``post_issue_comment`` (feature
scoping) hit the same issues-comments endpoint and turn a
:class:`~meow.worker.models.VibeResult` into a markdown body the same way —
only the human-facing header and the terminated-early banner differ. The
body-rendering logic lives here so the two activities can't drift.
"""

from __future__ import annotations

from meow.worker.models import VibeResult

__all__ = ["build_comment_body", "scrub_secrets"]

_NO_OUTPUT_NOTE = "_No partial output was produced._"


def scrub_secrets(body: str) -> str:
    """Placeholder for v0.1.0; real sanitisation lands in v0.2+ (spec §11.2).

    Kept as a named seam so the call sites don't have to change later.
    """
    return body


def build_comment_body(result: VibeResult, *, banner: str) -> str:
    """Render the markdown body for a vibe result.

    Three cases:
    - Clean run with output: post the body as-is.
    - Terminated early with a partial body: prepend ``banner`` (+ optional
      stop_reason) above the partial output, separated by an HR.
    - Terminated early with no body: just the banner + stop_reason; no
      partial output to show.

    ``banner`` is the use-case-specific terminated-early line (e.g. "Review
    terminated early." vs. "Scoping terminated early.").
    """
    if not result.terminated_early and result.body is not None:
        return scrub_secrets(result.body)

    parts = [banner]
    if result.stop_reason:
        parts.append(f"Reason: {scrub_secrets(result.stop_reason)}")
    if result.body is not None:
        parts.append("---")
        parts.append(scrub_secrets(result.body))
    else:
        parts.append(_NO_OUTPUT_NOTE)
    return "\n\n".join(parts)
