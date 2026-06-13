"""Receiver cases for the `issues` event family (feature scoping)."""

from __future__ import annotations

from meow.common.webhooks_inputs.issues import IssueScopeInput
from meow.common.workflows import FEATURE_SCOPE_WORKFLOW
from meow.receiver.controllers.issues import SCOPE_LABEL
from tests.conftest import TEST_BOT_LOGIN
from tests.fixtures.webhooks import issues_payload
from tests.integration.cases._models import ExpectedDispatch, WebhookCase


def _assert_scope_input(input_model: IssueScopeInput) -> None:
    assert isinstance(input_model, IssueScopeInput)
    assert input_model.repo_full_name == "octocat/hello"
    assert input_model.issue_number == 7
    assert input_model.default_branch == "main"
    assert SCOPE_LABEL in input_model.labels


ISSUES_CASES: list[WebhookCase] = [
    WebhookCase(
        id="issues_self_delivery_skipped",
        event="issues",
        payload_builder=lambda: issues_payload(
            action="opened", labels=[SCOPE_LABEL], sender_login=TEST_BOT_LOGIN
        ),
        expected_body={"skipped": "self"},
    ),
    WebhookCase(
        id="issues_opened_without_scope_label_no_intent",
        event="issues",
        payload_builder=lambda: issues_payload(action="opened", labels=["bug"]),
        expected_body={"skipped": "no-intent"},
    ),
    WebhookCase(
        id="issues_opened_with_scope_label_dispatched",
        event="issues",
        payload_builder=lambda: issues_payload(action="opened", labels=[SCOPE_LABEL, "bug"]),
        expected_body={"queued": True, "execution_id": "spy-exec"},
        expected_dispatch=ExpectedDispatch(
            workflow_id=FEATURE_SCOPE_WORKFLOW,
            assert_input=_assert_scope_input,
        ),
    ),
    WebhookCase(
        id="issues_labeled_scope_dispatched",
        event="issues",
        payload_builder=lambda: issues_payload(
            action="labeled", labels=[SCOPE_LABEL], added_label=SCOPE_LABEL
        ),
        expected_body={"queued": True, "execution_id": "spy-exec"},
        expected_dispatch=ExpectedDispatch(
            workflow_id=FEATURE_SCOPE_WORKFLOW,
            assert_input=_assert_scope_input,
        ),
    ),
    WebhookCase(
        id="issues_labeled_other_label_no_intent",
        event="issues",
        # `meow:scope` already present, but the *added* label is something else
        # → must not re-trigger.
        payload_builder=lambda: issues_payload(
            action="labeled", labels=[SCOPE_LABEL, "bug"], added_label="bug"
        ),
        expected_body={"skipped": "no-intent"},
    ),
    WebhookCase(
        id="issues_action_closed_skipped",
        event="issues",
        payload_builder=lambda: issues_payload(action="closed", labels=[SCOPE_LABEL]),
        expected_body={"skipped": "action"},
    ),
]
