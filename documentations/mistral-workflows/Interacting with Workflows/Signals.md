# Signals

Signals allow external systems to send messages to running workflows asynchronously.

# Key characteristics

Signals use asynchronous communication and can be sent at any time during workflow execution. Workflows must explicitly handle signals, and signals can carry payload data.

# Listening for signals

The workflow below listens for `add_notification` signals indefinitely. Each time a signal arrives, it appends the message to an internal list and processes it. The `wait_condition` call suspends execution until new notifications are available, avoiding busy-waiting.

**Python**

```python
import mistralai.workflows as workflows

@workflows.workflow.define(name="notification_workflow")
class NotificationWorkflow:
    def __init__(self):
        self.notifications = []

    @workflows.workflow.signal(name="add_notification")
    async def add_notification(self, message: str, priority: int = 1) -> None:
        self.notifications.append(message)
        print(f"Received notification: {message} (Priority: {priority})")

    @workflows.workflow.entrypoint
    async def run(self) -> None:
        print("Workflow started, waiting for notifications...")
        while True:
            await workflows.workflow.wait_condition(lambda: len(self.notifications) > 0)
            print(f"Processing {len(self.notifications)} notifications")
            self.notifications.clear()
```

# Input validation

Signal handlers declare their expected parameters explicitly, and the SDK enforces this contract on every incoming payload. Signals validate incoming payloads against their declared parameters. Incoming data is checked against the expected types, and any extra fields not declared in the handler signature are rejected. Validation failures return HTTP 422 (Unprocessable Entity) with a descriptive error message.

**Python**

```python
@workflows.workflow.signal(name="add_notification")
async def add_notification(self, message: str, priority: int = 1) -> None:
    # Only 'message' and 'priority' fields are accepted
    # Extra fields like {"message": "hi", "extra": "bad"} will be rejected
    ...
```

For complex input structures, use Pydantic models. The SDK will automatically deserialize the incoming payload into the model and validate each field:

**Python**

```python
import pydantic

class UserProfile(pydantic.BaseModel):
    name: str
    address: str

@workflows.workflow.signal(name="update_profile")
async def update_profile(self, profile: UserProfile) -> None:
    self._profile = profile
```

# Sending a signal

Once your workflow is running and listening for signals, you can send one from the outside using the SDK or the API.

**python**

```python
from mistralai.client import Mistral

client = Mistral(api_key="your_api_key")

client.workflows.executions.signal_workflow_execution(
    execution_id="my-execution-id",
    name="add_notification",
    input={"message": "Deployment complete", "priority": 2},
)
```

# Comparison

| Feature | Communication Type | Modifies State | Returns Value | Can Execute Activities |
| --- | --- | --- | --- | --- |
| Signal | Asynchronous | Yes | No | No |
| Query | Synchronous | No | Yes | No |
| Update | Synchronous | Yes | Yes | Yes |
