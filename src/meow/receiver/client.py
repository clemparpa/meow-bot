from typing import Any

from mistralai.client import Mistral
from pydantic import BaseModel

from meow.common.config import Settings
from meow.common.logging import get_logger
from meow.receiver.utils import WebhookContext

settings = Settings()  # ty: ignore[missing-argument]
logger = get_logger("receiver")

# Module-level client: keeps the HTTP session warm between requests and
# avoids re-validating the API key on every webhook. Errors from
# `execute_workflow` (e.g. 401) surface at first webhook, not at boot.
client: Mistral = Mistral(api_key=settings.mistral_api_key)


async def trigger_workflow(
    workflow_id: str,
    input_model: BaseModel,
    ctx: WebhookContext,
) -> dict[str, Any]:
    """Start a Mistral workflow execution and log the acceptance.

    `execution_id` includes `workflow_id` so the same delivery can fan out
    to multiple workflows without collision (idempotent per workflow).
    """
    execution = client.workflows.execute_workflow(
        workflow_identifier=workflow_id,
        execution_id=f"{ctx.event_name}-{ctx.delivery}-{workflow_id}",
        deployment_name=settings.deployment_name,
        # Wrap under `input` to match the JSON schema the worker publishes.
        # The SDK derives the schema from the entrypoint signature: for
        # `async def run(self, input: dict)` it requires a top-level `input`
        # key, and the API rejects flat dumps with a 422 "is a required
        # property". Workflows that bind the entrypoint to a BaseModel param
        # would skip this wrapping — see the matching pattern in
        # tests/e2e/test_health_ping_online.py.
        input={"input": input_model.model_dump(mode="json")},
    )
    logger.info(
        "webhook.accepted",
        extra={
            "gh_event": ctx.event_name,
            "delivery": ctx.delivery,
            "workflow": workflow_id,
            "execution_id": execution.execution_id,
        },
    )
    return {"queued": True, "execution_id": execution.execution_id}
