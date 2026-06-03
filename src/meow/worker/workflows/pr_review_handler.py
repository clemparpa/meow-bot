import mistralai.workflows as workflows

from meow.common.logging import get_logger
from meow.common.workflows import PR_REVIEW_WORKFLOW

logger = get_logger("worker")


@workflows.workflow.define(
    name=PR_REVIEW_WORKFLOW,
    workflow_display_name="PR Review Handler",
    workflow_description="Reviews a GitHub pull request via the vibe sandbox.",
)
class PrReviewWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: dict) -> None:
        logger.info(
            "workflow.pr_review.received",
            extra={"repo": input.get("repo_full_name"), "pr_number": input.get("issue_number")},
        )
        return None
