"""Intent detection for incoming GitHub events (spec §8.1, story S7).

The worker matches a small, hard-coded set of triggers in the body of a
comment and dispatches the workflow accordingly. v0.1.0 ships one intent
only — ``MENTION_REVIEW`` — and the regex is intentionally simple:

    @<bot-login>\\s+review\\b   (case-insensitive)

``detect_intent`` takes already-extracted primitives instead of the full
``WebhookIssueCommentCreated`` model so it can be called from inside a
Temporal workflow without dragging the ``githubkit`` import (which is too
invasive for the sandbox — it lazy-loads modules and calls ``os.getenv``
at runtime). The receiver does the typed parsing and hands us only the
two fields we need.

Markdown subtleties (blockquotes ``> @bot review``, HTML comments
``<!-- @bot review -->``) currently match; acceptable for v0.1 since the
receiver's self-event filter prevents the bot from triggering itself and
humans quoting another comment is an edge case worth handling properly
only when we add more intents in v0.2+.
"""

from __future__ import annotations

import re
from enum import StrEnum


class Intent(StrEnum):
    """Discrete actions the bot can take in response to a webhook.

    Values are stable strings — they land in ``events.jsonl`` (S14), so
    renaming one is a breaking change for downstream log consumers.
    """

    MENTION_REVIEW = "mention_review"


def detect_intent(
    comment_body: str | None,
    *,
    is_pr: bool,
    bot_login: str,
) -> Intent | None:
    """Return the intent matched by an ``issue_comment.created`` event.

    Returns ``None`` when the comment is on a plain issue, when the body
    is missing, or when it doesn't contain ``@<bot_login> review``
    (case-insensitive, word-bounded so ``reviewing`` doesn't match).
    """

    if not is_pr or not comment_body:
        return None
    pattern = re.compile(rf"@{re.escape(bot_login)}\s+review\b", re.IGNORECASE)
    if pattern.search(comment_body):
        return Intent.MENTION_REVIEW
    return None
