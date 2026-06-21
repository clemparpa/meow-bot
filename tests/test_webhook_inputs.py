"""Unit tests for webhook-input idempotency keys.

The key is folded into the Mistral ``execution_id`` to dedup runs. For ``issues``
it is repo+issue-scoped so a create-already-labelled (which fires both ``opened``
and ``labeled``) collapses onto one execution; for comments it stays the delivery
so every comment re-triggers.
"""

from __future__ import annotations

import re
from typing import Literal

from meow.common.webhooks_inputs.issue_comment import IssueCommentInput
from meow.common.webhooks_inputs.issues import IssueEventInput


def _issue(
    *,
    action: Literal["opened", "labeled"] = "opened",
    repo: str = "owner/repo",
    issue_number: int = 54,
    added_label: str | None = None,
    delivery: str = "d",
) -> IssueEventInput:
    return IssueEventInput(
        action=action,
        installation_id=1,
        repo_full_name=repo,
        issue_number=issue_number,
        issue_state="open",
        default_branch="main",
        issue_title="t",
        sender_login="u",
        added_label=added_label,
        delivery=delivery,
    )


def test_issue_key_collapses_opened_and_labeled() -> None:
    opened = _issue(action="opened", delivery="d1")
    labeled = _issue(action="labeled", added_label="meow:implement", delivery="d2")
    # Same issue, different deliveries → identical key: the two events collapse
    # onto one execution. The repo slash is folded to '_' (execution_id charset).
    assert opened.idempotency_key() == labeled.idempotency_key() == "owner_repo-issue-54"


def test_issue_key_is_execution_id_safe() -> None:
    # Mistral rejects an execution_id with anything outside [A-Za-z0-9_-]; the
    # repo's slash (and a '.') must be folded out.
    key = _issue(repo="my.org/weird.repo").idempotency_key()
    assert re.fullmatch(r"[A-Za-z0-9_-]+", key)


def test_issue_key_differs_by_issue_and_repo() -> None:
    assert _issue(issue_number=55).idempotency_key() != _issue(issue_number=54).idempotency_key()
    # Repo-scoped: issue #54 of two repos must not dedup against each other
    # (execution_id is unique per Mistral workspace).
    assert _issue(repo="a/x").idempotency_key() != _issue(repo="b/y").idempotency_key()


def test_comment_key_is_the_delivery() -> None:
    comment = IssueCommentInput(
        action="created",
        installation_id=1,
        repo_full_name="owner/repo",
        issue_number=7,
        is_pr=True,
        locked=False,
        comment_body="@meow-bot review",
        sender_login="u",
        delivery="deliv-xyz",
    )
    assert comment.idempotency_key() == "deliv-xyz"
