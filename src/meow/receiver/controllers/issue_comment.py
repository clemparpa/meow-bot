from githubkit.rest import WebhookIssueCommentCreated

from meow.common.config import Settings
from meow.common.webhooks_inputs.issue_comment import IssueCommentInput
from meow.common.workflows import PR_REVIEW_WORKFLOW
from meow.receiver.utils import on, on_event

_settings = Settings()  # ty: ignore[missing-argument]


@on_event(
    "issue_comment",
    input_factories={
        WebhookIssueCommentCreated: IssueCommentInput.from_issue_comment_created,
    },
)
class IssueCommentController:
    pr_review = on(
        event_type=WebhookIssueCommentCreated,
        when=lambda i: (
            i.is_pr and f"@{_settings.bot_login.lower()} review" in i.comment_body.lower()
        ),
        triggers=PR_REVIEW_WORKFLOW,
    )
