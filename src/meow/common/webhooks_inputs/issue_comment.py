from typing import Literal, Self

from githubkit.rest import WebhookIssueCommentCreated
from githubkit.utils import UNSET
from pydantic import Field

from meow.common.webhooks_inputs.base_model import UnsetAwareModel
from meow.receiver.utils import WebhookContext


class IssueCommentInput(UnsetAwareModel):
    """Input du workflow pour issue_comment.created.

    Strictement ce dont le workflow a besoin pour décider et agir —
    l'enveloppe webhook complète reste au receiver.
    """

    # Auth & coordonnées GitHub
    action: Literal["created", "edited"] = Field(description="type of the issue comment event")
    installation_id: int = Field(description="GitHub App installation ID — needed to mint a token")
    repo_full_name: str = Field(description="'owner/repo' — used for every API call")
    issue_number: int = Field(description="Issue or PR number (shared namespace on GitHub)")
    is_pr: bool = Field(
        description="True if event.issue.pull_request was set — gate for PR actions"
    )
    locked: bool = Field(description="State of the issue")

    # Contenu du commentaire
    comment_body: str = Field(description="Used for intent detection (e.g. '@meow-bot review')")
    sender_login: str = Field(description="Author of the comment — for attribution and logs")

    # Traçabilité
    delivery: str | None = Field(
        default=None, description="X-GitHub-Delivery — workflow idempotency key"
    )

    @classmethod
    def from_issue_comment_created(
        cls,
        event: WebhookIssueCommentCreated,
        ctx: WebhookContext,
    ) -> Self:
        if event.installation is UNSET:
            raise ValueError("installation missing — required for GitHub App webhooks")

        return cls(
            action="created",
            installation_id=event.installation.id,  # ty: ignore[unresolved-attribute]
            repo_full_name=event.repository.full_name,  # ty: ignore[unresolved-attribute]
            issue_number=event.issue.number,  # ty: ignore[unresolved-attribute]
            is_pr=event.issue.pull_request is not UNSET,  # ty: ignore[unresolved-attribute]
            locked=event.issue.locked,  # ty: ignore[unresolved-attribute]
            comment_body=event.comment.body,  # ty: ignore[unresolved-attribute]
            sender_login=event.sender.login,  # ty: ignore[unresolved-attribute]
            delivery=ctx.delivery,
        )
