"""Unit tests for :meth:`VibeResult.from_exec`.

``from_exec`` turns one vibe run — its exit code, the ``meow-review.md``
report the agent wrote, and stderr — into the result the action layer posts.
The body now comes from the *report file*, never from vibe's stdout
transcript, so these cover the four (exit_code × report-present) cases.
"""

from __future__ import annotations

from meow.worker.models import VibeResult


def test_clean_exit_with_report_posts_it_as_is() -> None:
    result = VibeResult.from_exec(
        exit_code=0,
        report="  ## Review\n\nLGTM.\n  ",
        stderr="",
    )

    assert result.body == "## Review\n\nLGTM."
    assert result.terminated_early is False
    assert result.stop_reason is None


def test_clean_exit_without_report_is_terminated_early() -> None:
    # Agent exited 0 but never wrote the file (e.g. forgot the write_file
    # call): nothing to post, surface a banner instead of inventing a body.
    result = VibeResult.from_exec(exit_code=0, report="   \n  ", stderr="")

    assert result.body is None
    assert result.terminated_early is True
    assert result.stop_reason == "vibe exited 0 but wrote no meow-review.md"


def test_nonzero_exit_with_report_keeps_partial_and_flags_early() -> None:
    # The agent wrote its report, then a cap/crash cut the run short: we still
    # post the partial review, flagged terminated_early with stderr's reason.
    result = VibeResult.from_exec(
        exit_code=1,
        report="## Review\n\nPartial findings.",
        stderr="<vibe_stop_event>max_price</vibe_stop_event>",
    )

    assert result.body == "## Review\n\nPartial findings."
    assert result.terminated_early is True
    assert result.stop_reason == "<vibe_stop_event>max_price</vibe_stop_event>"


def test_nonzero_exit_without_report_is_banner_only() -> None:
    result = VibeResult.from_exec(exit_code=137, report="", stderr="killed")

    assert result.body is None
    assert result.terminated_early is True
    assert result.stop_reason == "killed"


def test_nonzero_exit_without_report_or_stderr_has_no_reason() -> None:
    result = VibeResult.from_exec(exit_code=2, report="", stderr="   ")

    assert result.body is None
    assert result.terminated_early is True
    assert result.stop_reason is None
