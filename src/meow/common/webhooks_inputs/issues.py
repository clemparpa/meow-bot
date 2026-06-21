from typing import Literal, Self

from githubkit.rest import WebhookIssuesLabeled, WebhookIssuesOpened
from githubkit.utils import UNSET
from pydantic import Field

from meow.common.webhooks_inputs.base_model import WebhookInput
from meow.receiver.utils import WebhookContext


def _label_names(labels: object) -> list[str]:
    """Pull label names off an issue payload's ``labels`` list.

    ``labels`` is ``UNSET`` / ``None`` / a list of label objects depending on
    the payload; normalise all three to a plain ``list[str]``.
    """
    if labels is UNSET or labels is None:
        return []
    return [label.name for label in labels]  # ty: ignore[not-iterable]


class IssueEventInput(WebhookInput):
    """Workflow input for the ``issues`` event family.

    Shared by every ``issues``-driven workflow (feature scoping *and* feature
    implementation): the receiver can only register one factory per
    ``(event, event_type)``, so both intents read the same model. It carries
    exactly what those workflows need to clone the default branch and act on
    the issue (title/body, labels, default branch) — the full webhook envelope
    stays at the receiver. The ``issues`` event never fires for PRs, so there
    is no ``is_pr`` gate here.

    Idempotency is keyed on ``(repo, issue_number)``, not the delivery: opening
    an issue already carrying the label fires both ``opened`` and ``labeled``,
    and both must collapse onto a single workflow execution.
    """

    # Auth & GitHub coordinates
    action: Literal["opened", "labeled"] = Field(description="type of the issues event")
    installation_id: int = Field(description="GitHub App installation ID — needed to mint a token")
    repo_full_name: str = Field(description="'owner/repo' — used for every API call")
    issue_number: int = Field(description="Issue number")
    issue_state: Literal["open", "closed"] = Field(
        description="Issue state — gate so a label on a closed issue doesn't scope it"
    )
    default_branch: str = Field(description="Repo default branch — the ref the agent clones")

    # Issue content (straight from the payload — no API round-trip needed)
    issue_title: str = Field(description="Issue title — fed to the scoping prompt")
    issue_body: str | None = Field(default=None, description="Issue body — fed to the prompt")

    # Label routing
    labels: list[str] = Field(
        default_factory=list, description="All label names on the issue (gate for `opened`)"
    )
    added_label: str | None = Field(
        default=None, description="The label just added (gate for `labeled`); None on `opened`"
    )

    sender_login: str = Field(description="Actor who opened/labeled the issue — for logs")

    def idempotency_key(self) -> str:
        # Collapse opened+labeled (and any redelivery) for one issue. Repo-scoped
        # because the Mistral execution_id is unique per workspace, so issue #N
        # of two repos must not dedup against each other.
        return f"{self.repo_full_name}-issue-{self.issue_number}"

    @classmethod
    def from_issue_opened(
        cls,
        event: WebhookIssuesOpened,
        ctx: WebhookContext,
    ) -> Self:
        if event.installation is UNSET:
            raise ValueError("installation missing — required for GitHub App webhooks")

        return cls(
            action="opened",
            installation_id=event.installation.id,  # ty: ignore[unresolved-attribute]
            repo_full_name=event.repository.full_name,
            issue_number=event.issue.number,
            issue_state=event.issue.state,
            default_branch=event.repository.default_branch,
            issue_title=event.issue.title,
            issue_body=event.issue.body,
            labels=_label_names(event.issue.labels),
            added_label=None,
            sender_login=event.sender.login,
            delivery=ctx.delivery,
        )

    @classmethod
    def from_issue_labeled(
        cls,
        event: WebhookIssuesLabeled,
        ctx: WebhookContext,
    ) -> Self:
        if event.installation is UNSET:
            raise ValueError("installation missing — required for GitHub App webhooks")

        added_label = event.label.name if event.label is not UNSET and event.label else None

        return cls(
            action="labeled",
            installation_id=event.installation.id,  # ty: ignore[unresolved-attribute]
            repo_full_name=event.repository.full_name,
            issue_number=event.issue.number,
            issue_state=event.issue.state,
            default_branch=event.repository.default_branch,
            issue_title=event.issue.title,
            issue_body=event.issue.body,
            labels=_label_names(event.issue.labels),
            added_label=added_label,
            sender_login=event.sender.login,
            delivery=ctx.delivery,
        )
