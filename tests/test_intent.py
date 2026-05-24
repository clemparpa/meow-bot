"""Unit tests for :mod:`meow.worker.intent` (story S7)."""

from __future__ import annotations

import pytest
from githubkit.versions.v2022_11_28.models import WebhookIssueCommentCreated
from githubkit.webhooks import parse_obj

from meow.worker.intent import Intent, detect_intent
from tests.fixtures.webhooks import issue_comment_payload


def _make_event(
    body: str,
    *,
    is_pr: bool = True,
) -> WebhookIssueCommentCreated:
    payload = issue_comment_payload(body=body, is_pr=is_pr)
    # ``parse_obj`` returns a ``WebhookIssueCommentCreated`` re-exported
    # from a different submodule than the one the type alias refers to —
    # functionally identical attributes, just a separate class object —
    # so ``isinstance`` would fail. We rely on duck typing here.
    return parse_obj("issue_comment", payload)  # type: ignore[return-value]


def test_detect_intent_exact_match() -> None:
    event = _make_event("@meow-bot review")
    assert detect_intent(event, "meow-bot") == Intent.MENTION_REVIEW


@pytest.mark.parametrize(
    "body",
    [
        "@MEOW-BOT REVIEW",
        "@Meow-Bot Review",
        "@meow-bot REVIEW",
    ],
)
def test_detect_intent_case_insensitive(body: str) -> None:
    event = _make_event(body)
    assert detect_intent(event, "meow-bot") == Intent.MENTION_REVIEW


def test_detect_intent_no_mention() -> None:
    event = _make_event("hello world, nothing to see here")
    assert detect_intent(event, "meow-bot") is None


def test_detect_intent_mention_without_review() -> None:
    event = _make_event("@meow-bot please help with this PR")
    assert detect_intent(event, "meow-bot") is None


def test_detect_intent_other_login() -> None:
    event = _make_event("@octocat review")
    assert detect_intent(event, "meow-bot") is None


def test_detect_intent_review_substring_ignored() -> None:
    # ``\b`` word boundary prevents ``reviewing`` from matching ``review``.
    event = _make_event("@meow-bot reviewing this later")
    assert detect_intent(event, "meow-bot") is None


def test_detect_intent_extra_whitespace() -> None:
    event = _make_event("@meow-bot    review")
    assert detect_intent(event, "meow-bot") == Intent.MENTION_REVIEW


def test_detect_intent_inline_in_paragraph() -> None:
    event = _make_event("hey @meow-bot review please when you get a chance")
    assert detect_intent(event, "meow-bot") == Intent.MENTION_REVIEW


def test_detect_intent_on_plain_issue_returns_none() -> None:
    # Same matching body, but the comment is on a plain issue (no PR link).
    event = _make_event("@meow-bot review", is_pr=False)
    assert detect_intent(event, "meow-bot") is None


def test_detect_intent_bot_login_with_brackets() -> None:
    # GitHub Apps surface as ``<slug>[bot]`` — the brackets are regex
    # metacharacters and must be escaped. ``re.escape`` handles this.
    event = _make_event("@meow-bot[bot] review")
    assert detect_intent(event, "meow-bot[bot]") == Intent.MENTION_REVIEW


def test_detect_intent_review_followed_by_punctuation() -> None:
    event = _make_event("@meow-bot review.")
    assert detect_intent(event, "meow-bot") == Intent.MENTION_REVIEW
