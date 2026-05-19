# Progress tracking

Display a checklist of steps with real-time status updates using `TodoList`. Users see which step the workflow is on and can follow long-running processes without guessing.

# Todo list

**Python**

```python
import mistralai.workflows as workflows
import mistralai.workflows.plugins.mistralai as workflows_mistralai

@workflows.workflow.define(
    name="expense-processing-workflow",
    workflow_display_name="Expense Processing",
    workflow_description="Process expense with step-by-step progress",
)
class ExpenseProcessingWorkflow(workflows.InteractiveWorkflow):
    @workflows.workflow.entrypoint
    async def run(self, expense_id: str) -> workflows_mistralai.ChatAssistantWorkflowOutput:
        # Define the steps
        validate_item = workflows_mistralai.TodoListItem(
            title="Validate expense",
            description="Check expense details and receipts"
        )
        approve_item = workflows_mistralai.TodoListItem(
            title="Get approval",
            description="Route to manager for approval"
        )
        process_item = workflows_mistralai.TodoListItem(
            title="Process payment",
            description="Submit for reimbursement"
        )

        async with workflows_mistralai.TodoList(
            items=[validate_item, approve_item, process_item]
        ) as todo_list:
            # Step 1: Validate (using context manager for automatic status)
            async with validate_item:
                pass  # ... validation logic ...

            # Step 2: Approve (using context manager for automatic status)
            async with approve_item:
                pass  # ... approval logic ...

            # Step 3: Process (using context manager for automatic status)
            async with process_item:
                pass  # ... processing logic ...

        return workflows_mistralai.ChatAssistantWorkflowOutput(
            content=[workflows_mistralai.TextOutput(text=f"Expense {expense_id} processed successfully")]
        )
```

## Updating item status

There are two ways to update the status of a `TodoListItem`:

**Context manager:**

**Python**

```python
async with item:
    # Status automatically set to "in_progress" on enter
    # ... do work ...
    # Status automatically set to "done" on successful exit
```

**Manual control (for fine-grained status updates):**

**Python**

```python
await item.set_status("in_progress")
# ... do work ...
await item.set_status("done")
```

Use manual control when you need to update status at specific points, handle conditional flows, or implement custom exception handling.

## TodoListItem properties

| Property | Type | Description |
| --- | --- | --- |
| `id` | `str` | Auto-generated UUID |
| `title` | `str` | Display title for the step |
| `description` | `str` | Detailed description |
| `status` | `"todo" | "in_progress" | "done"` | Current status (defaults to `"todo"`) |
