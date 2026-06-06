"""Trivial workflow used as a connectivity smoke test against Mistral Workflows.

Not shipped with the worker — lives under `tests/e2e/` and is only
registered when the online e2e test runs. Validates the full chain:
SDK ↔ control plane ↔ worker ↔ activity, without exercising the
review pipeline.
"""

from __future__ import annotations

from datetime import timedelta

import mistralai.workflows as workflows

HEALTH_PING_WORKFLOW = "HealthPing"


@workflows.activity(start_to_close_timeout=timedelta(seconds=10))
async def health_ping_echo(message: str) -> str:
    return f"echo: {message}"


@workflows.workflow.define(
    name=HEALTH_PING_WORKFLOW,
    workflow_display_name="Health Ping",
    workflow_description="Connectivity smoke test for the Mistral Workflows pipe.",
)
class HealthPingWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: dict) -> str:
        message = input.get("message", "pong")
        return await health_ping_echo(message)
