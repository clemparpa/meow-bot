"""Webhook case registry — one module per GitHub event family.

Adding a new event family = drop a `tests/integration/cases/<event>.py`
exporting a list of WebhookCase, then import + extend ALL_CASES below.
No fixture or test-runner change required.
"""

from __future__ import annotations

from tests.integration.cases._models import ExpectedDispatch, WebhookCase
from tests.integration.cases.issue_comment import ISSUE_COMMENT_CASES
from tests.integration.cases.transport import TRANSPORT_CASES

ALL_CASES: list[WebhookCase] = [*TRANSPORT_CASES, *ISSUE_COMMENT_CASES]

__all__ = ["ALL_CASES", "ExpectedDispatch", "WebhookCase"]
