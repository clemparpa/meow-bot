# Updates

Updates allow external systems to modify workflow state and receive a response. Unlike signals, updates are synchronous and can return values.

# Key characteristics

Updates use synchronous communication and return a response to the caller. Unlike signals, they can modify workflow state, return values, and execute activities as part of handling the request.

# Handling updates

The workflow below exposes an `update_data` handler that runs an activity, updates internal state, and returns a result to the caller — all in a single synchronous call. This makes updates the right choice when the caller needs confirmation that the operation completed.

**Python**

```python
import mistralai.workflows as workflows
import asyncio

# Activity definition
@workflows.activity()
async def process_update_data(data: str) -> str:
    # Simulate processing
    await asyncio.sleep(0.5)
    return f"Processed: {data.upper()}"

@workflows.workflow.define(name="data_processing_workflow")
class DataProcessingWorkflow:
    def __init__(self):
        self.current_value = "default"

    @workflows.workflow.update(name="update_data")
    async def update_data(self, new_value: str) -> dict:
        # Execute an activity as part of the update
        processed = await process_update_data(new_value)

        # Update workflow state
        old_value = self.current_value
        self.current_value = processed

        return {
            "success": True,
            "processed_value": processed,
            "message": f"Updated from '{old_value}' to '{processed}'"
        }

    @workflows.workflow.entrypoint
    async def run(self) -> None:
        print(f"Workflow started with value: {self.current_value}")
        # Workflow continues running...
```

# Input validation

Update handlers declare their expected parameters, and the SDK validates the payload before the handler runs. Updates validate incoming payloads against their declared parameters. Incoming data is checked against the expected types, and any extra fields not declared in the handler signature are rejected. Validation failures return HTTP 422 (Unprocessable Entity) with a descriptive error message.

For complex input structures, use Pydantic models. This is especially useful when an update carries several related fields that belong together:

**Python**

```python
import pydantic

class ConfigUpdate(pydantic.BaseModel):
    timeout: int
    retry_count: int

@workflows.workflow.update(name="update_config")
async def update_config(self, config: ConfigUpdate) -> dict:
    self.config = config
    return {"success": True}
```

# Sending an update

Once your workflow is running, you can send an update from the outside and receive the handler's return value synchronously.

**python**

```python
from mistralai.client import Mistral

client = Mistral(api_key="your_api_key")

result = client.workflows.executions.update_workflow_execution(
    execution_id="my-execution-id",
    name="update_data",
    input={"new_value": "hello"},
)
print(result.model_dump_json(indent=2))
```

# Comparison

| Feature | Communication Type | Modifies State | Returns Value | Can Execute Activities |
| --- | --- | --- | --- | --- |
| Signal | Asynchronous | Yes | No | No |
| Query | Synchronous | No | Yes | No |
| Update | Synchronous | Yes | Yes | Yes |
