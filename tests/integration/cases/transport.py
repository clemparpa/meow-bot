"""Transport-layer cases: signature, headers, parsing — not event-specific."""

from __future__ import annotations

from tests.fixtures.webhooks import issue_comment_payload
from tests.integration.cases._models import WebhookCase

TRANSPORT_CASES: list[WebhookCase] = [
    WebhookCase(
        id="transport_bad_signature_401",
        event="issue_comment",
        payload_builder=lambda: issue_comment_payload(),
        signature_override="sha256=" + "0" * 64,
        expected_status=401,
    ),
    WebhookCase(
        id="transport_missing_event_header_skipped",
        event=None,
        payload_builder=lambda: issue_comment_payload(),
        expected_body={"skipped": "event"},
    ),
    WebhookCase(
        id="transport_unhandled_event_skipped",
        event="ping",
        payload_builder=lambda: {"zen": "Speak softly and carry a big stick."},
        expected_body={"skipped": "event"},
    ),
    WebhookCase(
        id="transport_malformed_payload_400",
        event="issue_comment",
        payload_builder=lambda: {"action": "created", "garbage": True},
        expected_status=400,
    ),
]
