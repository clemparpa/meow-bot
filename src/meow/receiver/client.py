from typing import Any

from mistralai.client import Mistral
from mistralai.client.errors import SDKError

from meow.common.config import Settings
from meow.common.logging import get_logger
from meow.common.webhooks_inputs.base_model import WebhookInput
from meow.receiver.utils import WebhookContext

settings = Settings()  # ty: ignore[missing-argument]
logger = get_logger("receiver")

# Module-level client: keeps the HTTP session warm between requests and
# avoids re-validating the API key on every webhook. Errors from
# `execute_workflow` (e.g. 401) surface at first webhook, not at boot.
client: Mistral = Mistral(api_key=settings.mistral_api_key)


async def trigger_workflow(
    workflow_id: str,
    input_model: WebhookInput,
    ctx: WebhookContext,
) -> dict[str, Any]:
    """Start a Mistral workflow execution and log the acceptance.

    The `execution_id` is `{event}-{idempotency_key}-{workflow_id}`: the trailing
    `workflow_id` lets one webhook fan out to several workflows, and the model's
    `idempotency_key` (issue-scoped for `issues`, delivery-scoped otherwise) is
    what dedups runs. GitHub fires both `opened` and `labeled` when an issue is
    created already-labelled; both resolve to the same `execution_id`, so the
    second `execute_workflow` gets a 409 (`WF_1101` "already started") which we
    swallow as a no-op instead of letting it 500 the webhook delivery.
    """
    execution_id = f"{ctx.event_name}-{input_model.idempotency_key()}-{workflow_id}"
    try:
        execution = client.workflows.execute_workflow(
            workflow_identifier=workflow_id,
            execution_id=execution_id,
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
    except SDKError as exc:
        # 409 WF_1101: an execution with this id is already running — a duplicate
        # delivery for the same intent (e.g. issue opened+labeled). Treat as a
        # no-op so GitHub gets a 200 instead of retrying a deterministic 409.
        if exc.status_code != 409:
            raise
        logger.info(
            "webhook.deduplicated",
            extra={
                "gh_event": ctx.event_name,
                "delivery": ctx.delivery,
                "workflow": workflow_id,
                "execution_id": execution_id,
            },
        )
        return {"deduplicated": True, "execution_id": execution_id}

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
