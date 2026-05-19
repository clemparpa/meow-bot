# Publish in le Chat

To publish a conversational workflow as an assistant in le Chat (Mistral's chat interface), your workflow must return a `ChatAssistantWorkflowOutput`. The output won't be displayed in le Chat, but we enforce a common interface for inter-operability.

**Python**

```python
import mistralai.workflows as workflows
import mistralai.workflows.plugins.mistralai as workflows_mistralai

@workflows.workflow.define(
    name="expense-summary-workflow",
    workflow_display_name="Expense Summary",
    workflow_description="Generates a summary of expenses",
)
class ExpenseSummaryWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, department: str) -> workflows_mistralai.ChatAssistantWorkflowOutput:
        summary = f"Expense summary for {department}: Total $12,500"

        return workflows_mistralai.ChatAssistantWorkflowOutput(
            content=[workflows_mistralai.TextOutput(text=summary)]
        )
```

# Tagging input variants

When a workflow accepts a union of input types, clients may need a way to know which variant to use. The `@input_tag` decorator adds an `x-input-tag` field to a model's JSON schema so clients can identify and select the right one.

**Python**

```python
from pydantic import BaseModel

import mistralai.workflows as workflows
import mistralai.workflows.plugins.mistralai as workflows_mistralai
from mistralai.workflows.plugins.mistralai import input_tag

class FullParams(BaseModel):
    config: str
    options: dict[str, str]

@input_tag("simplified")
class SimpleParams(BaseModel):
    prompt: str

@workflows.workflow.define(
    name="multi-client-workflow",
    workflow_display_name="Multi-Client",
)
class MultiClientWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, params: FullParams | SimpleParams) -> workflows_mistralai.ChatAssistantWorkflowOutput:
        if isinstance(params, SimpleParams):
            resolved = params.prompt
        else:
            resolved = params.config

        return workflows_mistralai.ChatAssistantWorkflowOutput(
            content=[workflows_mistralai.TextOutput(text=f"Received: {resolved}")]
        )
```

`SimpleParams.model_json_schema()` now contains `"x-input-tag": "simplified"`. Clients inspect the union members in the workflow's `input_schema` and select the variant whose tag they recognise.

# Error handling

To signal that a workflow has failed, set `isError=True` on the output. The text content is used as the error message displayed to the user, and the workflow is marked as failed in the conversation:

**Python**

```python
import mistralai.workflows as workflows
import mistralai.workflows.plugins.mistralai as workflows_mistralai

@workflows.workflow.define(
    name="expense-validation-workflow",
    workflow_display_name="Expense Validation",
    workflow_description="Validates expense data",
)
class ExpenseValidationWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, expense_id: str) -> workflows_mistralai.ChatAssistantWorkflowOutput:
        expense = lookup_expense(expense_id)
        if expense is None:
            return workflows_mistralai.ChatAssistantWorkflowOutput(
                content=[workflows_mistralai.TextOutput(text=f"Expense {expense_id} not found.")],
                isError=True,
            )

        return workflows_mistralai.ChatAssistantWorkflowOutput(
            content=[workflows_mistralai.TextOutput(text=f"Expense {expense_id} is valid.")]
        )
```

# Structured content

`ChatAssistantWorkflowOutput` accepts an optional `structuredContent` field (`dict[str, Any]`) for attaching arbitrary structured data to the workflow output.

**Python**

```python
return workflows_mistralai.ChatAssistantWorkflowOutput(
    content=[workflows_mistralai.TextOutput(text="Done.")],
    structuredContent={"tool": "web_search", "results": [{"url": "https://example.com"}]},
)
```
