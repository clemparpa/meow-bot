from githubkit.rest import WebhookIssuesLabeled, WebhookIssuesOpened

from meow.common.webhooks_inputs.issues import IssueEventInput
from meow.common.workflows import FEATURE_IMPLEMENT_WORKFLOW, FEATURE_SCOPE_WORKFLOW
from meow.receiver.utils import on, on_event

# Label that opts an issue into feature scoping. Applied at creation
# (`opened` carries it in `labels`) or added later (`labeled` reports it as
# the single added label).
SCOPE_LABEL = "meow:scope"
# Label that opts an issue into full implementation (clone, write code, open a
# PR). Routed exactly like SCOPE_LABEL but to a heavier workflow.
IMPLEMENT_LABEL = "meow:implement"


@on_event(
    "issues",
    input_factories={
        WebhookIssuesOpened: IssueEventInput.from_issue_opened,
        WebhookIssuesLabeled: IssueEventInput.from_issue_labeled,
    },
)
class IssuesController:
    # Opened already labelled `meow:scope` (label set at creation time —
    # GitHub does not fire a separate `labeled` event for those).
    scope_on_open = on(
        event_type=WebhookIssuesOpened,
        when=lambda i: SCOPE_LABEL in i.labels and i.issue_state == "open",
        triggers=FEATURE_SCOPE_WORKFLOW,
    )
    # `meow:scope` added to an existing issue. Gate on the *added* label so
    # adding some other label to an already-scoped issue doesn't re-trigger,
    # and on `open` state so labelling a closed issue doesn't scope it
    # (GitHub fires `labeled` on closed issues too).
    scope_on_label = on(
        event_type=WebhookIssuesLabeled,
        when=lambda i: i.added_label == SCOPE_LABEL and i.issue_state == "open",
        triggers=FEATURE_SCOPE_WORKFLOW,
    )

    # `meow:implement` mirrors the scope routes but triggers the implementation
    # workflow. Defined *after* the scope routes: the dispatcher fires the first
    # matching predicate and stops, so an issue carrying *both* labels resolves
    # to scoping (the cheaper intent). The two labels are meant to be used one
    # at a time.
    implement_on_open = on(
        event_type=WebhookIssuesOpened,
        when=lambda i: IMPLEMENT_LABEL in i.labels and i.issue_state == "open",
        triggers=FEATURE_IMPLEMENT_WORKFLOW,
    )
    implement_on_label = on(
        event_type=WebhookIssuesLabeled,
        when=lambda i: i.added_label == IMPLEMENT_LABEL and i.issue_state == "open",
        triggers=FEATURE_IMPLEMENT_WORKFLOW,
    )
