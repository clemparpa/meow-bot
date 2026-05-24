"""Intent detection for incoming GitHub events (spec §8.1, story S7).

The worker matches a small, hard-coded set of triggers in the body of a
comment and dispatches the workflow accordingly. v0.1.0 ships one intent
only — ``MENTION_REVIEW`` — and the regex is intentionally simple:

    @<bot-login>\\s+review\\b   (case-insensitive)

Markdown subtleties (blockquotes ``> @bot review``, HTML comments
``<!-- @bot review -->``) currently match; this is acceptable for v0.1
because the receiver's self-event filter prevents the bot from triggering
itself, and humans quoting another comment is an edge case worth handling
properly only when we add more intents in v0.2+.
"""

from __future__ import annotations

import re
from enum import StrEnum

from githubkit.utils import UNSET
from githubkit.versions.v2022_11_28.models import WebhookIssueCommentCreated


class Intent(StrEnum):
    """Discrete actions the bot can take in response to a webhook.

    Values are stable strings — they land in ``events.jsonl`` (S14) so
    renaming one is a breaking change for downstream log consumers.
    """

    MENTION_REVIEW = "mention_review"


def detect_intent(
    event: WebhookIssueCommentCreated,
    bot_login: str,
) -> Intent | None:
    """Return the intent matched by an ``issue_comment.created`` event.

    Returns ``None`` when:

    - the comment is on a plain issue (``issue.pull_request`` is ``UNSET``),
    - or the body doesn't contain ``@<bot_login> review`` (case-insensitive,
      word-bounded so ``reviewing`` doesn't match).
    """

    if event.issue.pull_request is UNSET:
        return None
    pattern = re.compile(rf"@{re.escape(bot_login)}\s+review\b", re.IGNORECASE)
    if pattern.search(event.comment.body or ""):
        return Intent.MENTION_REVIEW
    return None
