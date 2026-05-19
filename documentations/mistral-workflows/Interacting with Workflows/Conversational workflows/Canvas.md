# Canvas

Canvas is the rich-content surface in the chat interface: markdown documents, code, diagrams, slides, and interactive components. A workflow can return a canvas as output, or send one mid-run and let the user edit it before continuing.

# Rich outputs

Return rich content like markdown, code, or diagrams using `ResourceOutput`:

**Python**

```python
import mistralai.workflows as workflows
import mistralai.workflows.plugins.mistralai as workflows_mistralai

@workflows.workflow.define(
    name="expense-report-workflow",
    workflow_display_name="Expense Report",
    workflow_description="Generate expense report with charts",
)
class ExpenseReportWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, department: str) -> workflows_mistralai.ChatAssistantWorkflowOutput:
        # Generate a mermaid chart
        chart_content = """
pie title Expenses by Category
    "Travel" : 45
    "Equipment" : 25
    "Software" : 20
    "Other" : 10
"""

        canvas = workflows_mistralai.CanvasPayload(
            type="mermaid",
            title="Expense Breakdown",
            content=chart_content,
        )

        resource = workflows_mistralai.CanvasResource(
            canvas=canvas,
        )

        return workflows_mistralai.ChatAssistantWorkflowOutput(
            content=[
                workflows_mistralai.TextOutput(text=f"Expense report for {department}:"),
                workflows_mistralai.ResourceOutput(resource=resource),
            ]
        )
```

## Canvas types

| Type | Description |
| --- | --- |
| `text/markdown` | Markdown content |
| `text/html` | HTML content |
| `image/svg+xml` | SVG images |
| `slides` | Presentation slides |
| `react` | React components |
| `code` | Code with syntax highlighting |
| `mermaid` | Mermaid diagrams |

# Canvas editing (human-in-the-loop)

You can send a canvas mid-workflow using `send_assistant_message()` and then let the user edit it. The `canvas_uri` passed to `CanvasInput` must match the `uri` of a `CanvasResource` output from a previous step.

**Python**

```python
import mistralai.workflows as workflows
import mistralai.workflows.plugins.mistralai as workflows_mistralai
from mistralai.workflows.conversational import CanvasInput

@workflows.workflow.define(
    name="report-review-workflow",
    workflow_display_name="Report Review",
    workflow_description="Generate a report and let the user edit it",
)
class ReportReviewWorkflow(workflows.InteractiveWorkflow):
    @workflows.workflow.entrypoint
    async def run(self) -> workflows_mistralai.ChatAssistantWorkflowOutput:
        # Send a canvas to the user as an assistant message
        canvas_resource = workflows_mistralai.CanvasResource(
            canvas=workflows_mistralai.CanvasPayload(
                type="text/markdown",
                title="Weekly Report",
                content="# Weekly Report\n\n## Summary\n\nTODO: fill in",
            ),
        )
        await workflows_mistralai.send_assistant_message(
            "Here is your report draft. You can review and edit it below.",
            canvas=canvas_resource,
        )

        # Wait for the user to edit the canvas
        edited = await self.wait_for_input(
            CanvasInput(canvas_uri=canvas_resource.uri, prompt="Any feedback?"),
            label="Review & Edit Report",
        )

        # Use the edited content
        return workflows_mistralai.ChatAssistantWorkflowOutput(
            content=[
                workflows_mistralai.TextOutput(text="Report finalized!"),
                workflows_mistralai.ResourceOutput(
                    resource=workflows_mistralai.CanvasResource(
                        canvas=workflows_mistralai.CanvasPayload(
                            type="text/markdown",
                            title=edited.canvas.title,
                            content=edited.canvas.content,
                        ),
                    )
                ),
            ]
        )
```

`CanvasInput` returns a model with:

- `canvas.title` — the title of the edited canvas
- `canvas.content` — the edited content
- `chatInput` — optional chat message (only present when `prompt` is provided and the user sends a message)
