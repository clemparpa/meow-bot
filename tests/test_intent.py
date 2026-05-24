"""Unit tests for :mod:`meow.worker.intent` (story S7)."""

from __future__ import annotations

import pytest

from meow.worker.intent import Intent, detect_intent


def test_detect_intent_exact_match() -> None:
    assert (
        detect_intent("@meow-bot review", is_pr=True, bot_login="meow-bot") == Intent.MENTION_REVIEW
    )


@pytest.mark.parametrize(
    "body",
    [
        "@MEOW-BOT REVIEW",
        "@Meow-Bot Review",
        "@meow-bot REVIEW",
    ],
)
def test_detect_intent_case_insensitive(body: str) -> None:
    assert detect_intent(body, is_pr=True, bot_login="meow-bot") == Intent.MENTION_REVIEW


def test_detect_intent_no_mention() -> None:
    assert (
        detect_intent("hello world, nothing to see here", is_pr=True, bot_login="meow-bot") is None
    )


def test_detect_intent_mention_without_review() -> None:
    assert (
        detect_intent("@meow-bot please help with this PR", is_pr=True, bot_login="meow-bot")
        is None
    )


def test_detect_intent_other_login() -> None:
    assert detect_intent("@octocat review", is_pr=True, bot_login="meow-bot") is None


def test_detect_intent_review_substring_ignored() -> None:
    # ``\b`` word boundary prevents ``reviewing`` from matching ``review``.
    assert detect_intent("@meow-bot reviewing this later", is_pr=True, bot_login="meow-bot") is None


def test_detect_intent_extra_whitespace() -> None:
    assert (
        detect_intent("@meow-bot    review", is_pr=True, bot_login="meow-bot")
        == Intent.MENTION_REVIEW
    )


def test_detect_intent_inline_in_paragraph() -> None:
    body = "hey @meow-bot review please when you get a chance"
    assert detect_intent(body, is_pr=True, bot_login="meow-bot") == Intent.MENTION_REVIEW


def test_detect_intent_on_plain_issue_returns_none() -> None:
    # Same matching body, but is_pr=False — detect_intent must gate on it.
    assert detect_intent("@meow-bot review", is_pr=False, bot_login="meow-bot") is None


def test_detect_intent_bot_login_with_brackets() -> None:
    # GitHub Apps surface as ``<slug>[bot]`` — the brackets are regex
    # metacharacters and must be escaped. ``re.escape`` handles this.
    assert (
        detect_intent("@meow-bot[bot] review", is_pr=True, bot_login="meow-bot[bot]")
        == Intent.MENTION_REVIEW
    )


def test_detect_intent_review_followed_by_punctuation() -> None:
    assert (
        detect_intent("@meow-bot review.", is_pr=True, bot_login="meow-bot")
        == Intent.MENTION_REVIEW
    )


def test_detect_intent_empty_body_returns_none() -> None:
    assert detect_intent(None, is_pr=True, bot_login="meow-bot") is None
    assert detect_intent("", is_pr=True, bot_login="meow-bot") is None
