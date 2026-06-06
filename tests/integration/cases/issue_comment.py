"""Receiver cases for the `issue_comment` event family."""

from __future__ import annotations

from meow.common.webhooks_inputs.issue_comment import IssueCommentInput
from meow.common.workflows import PR_REVIEW_WORKFLOW
from tests.conftest import TEST_BOT_LOGIN
from tests.fixtures.webhooks import issue_comment_payload
from tests.integration.cases._models import ExpectedDispatch, WebhookCase

_REVIEW_BODY = f"@{TEST_BOT_LOGIN} review please"


def _assert_pr_review_input(input_model: IssueCommentInput) -> None:
    assert isinstance(input_model, IssueCommentInput)
    assert input_model.action == "created"
    assert input_model.repo_full_name == "octocat/hello"
    assert input_model.issue_number == 1
    assert input_model.is_pr is True
    assert input_model.sender_login == "alice"
    assert TEST_BOT_LOGIN.lower() in input_model.comment_body.lower()


ISSUE_COMMENT_CASES: list[WebhookCase] = [
    WebhookCase(
        id="issue_comment_self_delivery_skipped",
        event="issue_comment",
        payload_builder=lambda: issue_comment_payload(sender_login=TEST_BOT_LOGIN),
        expected_body={"skipped": "self"},
    ),
    WebhookCase(
        id="issue_comment_action_deleted_skipped",
        event="issue_comment",
        payload_builder=lambda: issue_comment_payload(action="deleted"),
        expected_body={"skipped": "action"},
    ),
    WebhookCase(
        id="issue_comment_not_a_pr_no_intent",
        event="issue_comment",
        payload_builder=lambda: issue_comment_payload(body=_REVIEW_BODY, is_pr=False),
        expected_body={"skipped": "no-intent"},
    ),
    WebhookCase(
        id="issue_comment_pr_without_mention_no_intent",
        event="issue_comment",
        payload_builder=lambda: issue_comment_payload(body="just a comment", is_pr=True),
        expected_body={"skipped": "no-intent"},
    ),
    WebhookCase(
        id="issue_comment_pr_review_dispatched",
        event="issue_comment",
        payload_builder=lambda: issue_comment_payload(body=_REVIEW_BODY, is_pr=True),
        expected_body={"queued": True, "execution_id": "spy-exec"},
        expected_dispatch=ExpectedDispatch(
            workflow_id=PR_REVIEW_WORKFLOW,
            assert_input=_assert_pr_review_input,
        ),
    ),
]
