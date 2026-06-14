from githubkit.rest import WebhookIssuesLabeled, WebhookIssuesOpened

from meow.common.webhooks_inputs.issues import IssueScopeInput
from meow.common.workflows import FEATURE_SCOPE_WORKFLOW
from meow.receiver.utils import on, on_event

# Label that opts an issue into feature scoping. Applied at creation
# (`opened` carries it in `labels`) or added later (`labeled` reports it as
# the single added label).
SCOPE_LABEL = "meow:scope"


@on_event(
    "issues",
    input_factories={
        WebhookIssuesOpened: IssueScopeInput.from_issue_opened,
        WebhookIssuesLabeled: IssueScopeInput.from_issue_labeled,
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
