# Deployments

A deployment is a named group of workers that owns a set of workflow definitions and receives all executions for those definitions. It enables worker isolation in shared workspaces and automatic execution routing.

# Setting DEPLOYMENT_NAME

`DEPLOYMENT_NAME` is **required** at worker startup. The worker fails immediately at boot if it is not set.

```
DEPLOYMENT_NAME=invoice-service MISTRAL_API_KEY=your-key uv run python worker.py
```

Valid characters: alphanumeric, hyphens, underscores (max 128 characters).

`WORKER_NAME` identifies the individual worker process and is visible in the console and API. It defaults to `socket.gethostname()`.

# Worker Isolation

In a shared workspace, multiple developers can run workers simultaneously without interfering. Each deployment only receives executions for the workflow definitions it registered.

```
# Developer A
DEPLOYMENT_NAME=alice MISTRAL_API_KEY=shared-key uv run python worker.py

# Developer B
DEPLOYMENT_NAME=bob MISTRAL_API_KEY=shared-key uv run python worker.py
```

Alice's runs land on Alice's workers. Bob's runs land on Bob's workers.

# Execution Routing

When only one active deployment owns a workflow, executions route automatically — no extra configuration needed:

```
execution = await client.execute_workflow(
    workflow_identifier="invoice_processor",
    input_data=InputData(invoice_id="INV-001"),
)
```

When two active deployments register the same workflow name, the platform cannot route automatically and returns `409 Conflict`:

```
{
  "code": "AMBIGUOUS_WORKFLOW",
  "deployments": ["alice", "bob"]
}
```

Resolve by passing `deployment_name` explicitly:

```
execution = await client.execute_workflow(
    workflow_identifier="invoice_processor",
    deployment_name="alice",
    input_data=InputData(invoice_id="INV-001"),
)
```

# Conflict Detection

When a worker registers a workflow name already owned by a different active deployment, the platform warns immediately. Registration is not blocked — the warning is returned in the registration response and appears in worker logs:

```
{
  "warnings": [
    "Workflow 'invoice_processor' is also registered by active deployment 'bob'"
  ]
}
```

The conflict resolves automatically when one of the deployments becomes inactive (its workers stop).

Multiple workers in the **same** deployment registering the same definitions is horizontal scaling — no warning is produced.

# Deployment Lifecycle

A deployment is **active** while at least one of its workers has heartbeated within the liveness window. Workers heartbeat every ~10 seconds automatically. When all workers stop, the deployment becomes **inactive** after the liveness window lapses (50 seconds in production, configurable).

Inactive deployments do not receive executions and are not counted as conflicting when checking for ambiguity.

# Horizontal Scaling

Run multiple workers under the same `DEPLOYMENT_NAME` to increase throughput. Executions are distributed across all active workers in the deployment.

For production, deploy workers as a Kubernetes `Deployment` or `StatefulSet` with replicas pointing at the same `DEPLOYMENT_NAME`. The platform load-balances tasks automatically.

# Listing Deployments

List all active deployments in your workspace:

**Python**

```python
from mistralai.client import Mistral

client = Mistral(api_key="your_api_key")

response = client.workflows.deployments.list_deployments()
for deployment in response.deployments:
    print(deployment.name, deployment.is_active)
```

Pass `workflow_name` to filter by workflow, or `active_only=false` to include inactive deployments.

Inspect a specific deployment and its individual workers:

**Python**

```python
deployment = client.workflows.deployments.get_deployment(name="invoice-service")
print(deployment.name, deployment.is_active)
for worker in deployment.workers:
    print(worker.name, worker.updated_at)
```
