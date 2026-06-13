"""Result captured from one ``run_vibe`` activity.

Produced by the runner, consumed by per-use-case action activities
(``post_pr_comment``, etc.). All presentation (headers, truncation
banners) lives action-side; this model stays format-agnostic.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict

__all__ = ["VibeResult"]


class VibeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    # The agent's output report (contents of the task's report file), trimmed.
    # ``None`` when the agent never wrote the file — the action layer reacts
    # to ``terminated_early`` rather than inventing a body.
    body: str | None
    # Set whenever the run did not produce a clean, complete report: any
    # non-zero exit (planned budget cap, hard crash, …) OR a clean exit that
    # left no report file. Action activities use this to decide whether to
    # post as-is or prepend a warning banner.
    terminated_early: bool
    # Vibe's stderr, trimmed. ``None`` when empty. Carries the
    # ``<vibe_stop_event>`` payload on budget caps and the exception
    # trace on crashes — the runner does not split the two.
    stop_reason: str | None

    @classmethod
    def from_exec(cls, *, exit_code: int, report: str, stderr: str) -> Self:
        """Build a result from one vibe run.

        ``report`` is the contents of the agent's report file (read back by the
        runner from the task's ``report_path``), not vibe's stdout — the stdout
        transcript is diagnostic only. Four cases collapse onto three render
        paths in :func:`post_pr_comment._build_body`:

        - clean exit + report present ⇒ the report, posted as-is.
        - clean exit + no report ⇒ ``terminated_early`` with an explanatory
          ``stop_reason`` (the agent finished but produced nothing to post).
        - non-zero exit + report present ⇒ the partial report is still posted,
          flagged ``terminated_early`` with ``stderr`` as the reason (the agent
          wrote its report, then a cap/crash cut it short).
        - non-zero exit + no report ⇒ banner + ``stderr`` only.
        """
        body = report.strip() or None
        if exit_code == 0 and body is not None:
            return cls(body=body, terminated_early=False, stop_reason=None)
        if exit_code != 0:
            stop_reason = stderr.strip() or None
        else:
            stop_reason = "vibe exited 0 but wrote no report file"
        return cls(body=body, terminated_early=True, stop_reason=stop_reason)
