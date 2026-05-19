# Waiting for Conditions

Workflows can pause execution until a specific condition is met, enabling event-driven patterns like human-in-the-loop and approval flows.

The condition predicate is typically flipped by a [signal](/studio-api/workflows/interacting-with-workflows/signals) sent from outside the workflow (an API call, another service, a UI action). The workflow stays suspended at no compute cost until the predicate becomes `True` or the timeout fires.

> [!TIP]
> **Building a chat-style interaction?** Use [`wait_for_input()`](/studio-api/workflows/interacting-with-workflows/conversational_workflows) from `InteractiveWorkflow` instead. It's a built-in primitive for prompting the user and waiting for a reply — no signal definition or custom predicate needed, with built-in support for structured forms, confirmations, and timeouts.

# Common patterns

The same `wait_condition` primitive supports several recurring use cases:

- **Approval flows** — wait for a human to approve or reject (signal-driven). See the example below.
- **External callback** — wait for a third-party webhook or job to mark the workflow as ready to proceed.
- **Polling-with-backoff (rare)** — wait for an in-workflow flag flipped by another coroutine; usually better expressed as an activity that does the polling itself.

If your case is HITL-heavy, also see [Signals](/studio-api/workflows/interacting-with-workflows/signals) for how to define and send the trigger.

# Basic usage

Use `workflow.wait_condition()` to block until a predicate returns `True`:

**Python**

```python
from datetime import timedelta
from mistralai.workflows import workflow

await workflow.wait_condition(
    lambda: self.ready,
    timeout=timedelta(minutes=5)
)
```

# Example: approval flow

Combine with signals to implement a human-in-the-loop pattern:

**Python**

```python
import asyncio
import mistralai.workflows as workflows
from mistralai.workflows import workflow
from datetime import timedelta

@workflows.workflow.define(name="approval_workflow")
class ApprovalWorkflow:
    def __init__(self):
        self.approved = False

    @workflows.workflow.signal(name="approve")
    async def approve(self) -> None:
        self.approved = True

    @workflows.workflow.entrypoint
    async def run(self, request_id: str) -> str:
        try:
            # Wait up to 24 hours for the `approve` signal to flip self.approved
            await workflow.wait_condition(
                lambda: self.approved,
                timeout=timedelta(hours=24),
            )
        except asyncio.TimeoutError:
            return f"Request {request_id} timed out"

        return f"Request {request_id} approved"
```

# Timeout behavior

When a timeout is specified, `wait_condition` raises `asyncio.TimeoutError` if the condition is not met within the duration. Handle this to implement timeout logic:

**Python**

```python
import asyncio

try:
    await workflow.wait_condition(
        lambda: self.ready,
        timeout=timedelta(minutes=30)
    )
except asyncio.TimeoutError:
    # Handle timeout
    return "Operation timed out"
```
