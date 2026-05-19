# Resetting Workflows

Reset a workflow execution to restart it from a specific point in its event history.

# When to reset

Resetting is useful when a workflow gets stuck — for example, because of a non-determinism error after a code change — or when it cannot complete due to a bug that has since been fixed.

> [!WARNING]
> Resetting should only be used **after fixing the underlying problem**. All progress made after the reset point will be lost.

# How it works

When you reset a workflow:

1. The current run is terminated
2. A new run is created under the same execution ID
3. All events up to the reset point are copied to the new run
4. The workflow replays from the reset point using the **latest version of your code**

This means any bug fix you deployed will take effect when the workflow resumes.

# Usage

**Python**

```python
from mistralai.client import Mistral

client = Mistral(api_key="your_api_key")

client.workflows.executions.reset_workflow(
    execution_id="your-execution-id",
    event_id=42,  # Must be a WORKFLOW_TASK_COMPLETED event
    reason="Bug fixed in activity logic",
    exclude_signals=True,  # Optional: skip replaying signals after this point
    exclude_updates=True   # Optional: skip replaying updates after this point
)
```

## Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `execution_id` | `str` | Yes | The execution to reset |
| `event_id` | `int` | Yes | Event ID to reset to (must be a `WORKFLOW_TASK_COMPLETED` event) |
| `reason` | `str` | Yes | Reason for the reset (recorded in event history) |
| `exclude_signals` | `bool` | No | Skip replaying signals received after the reset point |
| `exclude_updates` | `bool` | No | Skip replaying updates received after the reset point |

# Finding the reset point

Use the trace events API to find valid reset points:

**Python**

```python
events = client.workflows.executions.get_workflow_execution_trace_events(
    execution_id=execution_id,
    include_internal_events=True,
)

# Filter for WORKFLOW_TASK_COMPLETED events
valid_reset_points = [
    e for e in events
    if e.event_type == "WORKFLOW_TASK_COMPLETED"
]
```

If you provide an invalid event ID, the API returns a `WF_1001` error with a `valid_reset_events` field listing valid alternatives.

# Best practices

1. **Fix the root cause first** — resetting without fixing the bug will reproduce the same failure
2. **Always provide a reason** — it is recorded in the event history for auditing
3. **Use `exclude_signals` carefully** — skipping signals means any external input received after the reset point won't be replayed
4. **Test your fix** — deploy and test the fix on a development workspace before resetting production workflows
