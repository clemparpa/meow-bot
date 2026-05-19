# Your first workflow

This guide walks you through creating a workflow that executes a single activity.

#

To complete this quickstart, you need:

1. A [Mistral account](https://console.mistral.ai/).
2. [Python](https://www.python.org/downloads/) 3.12 or later installed on your machine.
3. [uv](https://docs.astral.sh/uv/getting-started/installation/) installed in your environment (`uvx` ships with `uv`).

#

Run the following `uvx` command in your terminal:

```
uvx mistralai-workflows-cli setup
```

This scaffolds a ready-to-run Python project with the Workflows SDK already configured, a minimal example workflow, and helper commands to run your worker and trigger executions.

The command prompts you to [generate a Mistral API key in the Mistral Console](https://console.mistral.ai/home?profile_dialog=api-keys). Follow the prompts to generate the API key, and then pass it to the command when requested. API keys are only accessible once.

Open the project directory in the IDE of your choice. The default name is `my-workflow`, but it matches whatever you entered when prompted during setup.

#

Navigate to `src/workflows/hello.py` to see an example workflow. This file contains the following code:

**Python**

```python
"""Minimal example workflow — edit this file or create new ones."""

from pydantic import BaseModel

import mistralai.workflows as workflows

class HelloInput(BaseModel):
    name: str = "World"

@workflows.activity()
async def greet(name: str) -> str:
    """A simple activity that returns a greeting."""
    return f"Hello, {name}! Welcome to Mistral Workflows."

@workflows.workflow.define(
    name="hello-world",
    workflow_display_name="Hello World",
    workflow_description="A minimal hello-world workflow.",
)
class HelloWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: HelloInput) -> str:
        return await greet(input.name)
```

This code defines a Mistral Workflow that takes a `name` as input and returns a greeting.

Open `src/discover.py`. Focus on the following snippet:

**Python**

```python
await workflows.run_worker(discovered)
```

This code automatically discovers all workflows in the `src/workflows` directory, and then watches them using the Mistral Workflows `run_worker` function.

#

From the root of your project directory, run the following command in your terminal to start the worker:

```
make start-worker
```

This command starts the worker, connects to the Mistral API, and registers your workflow so it can wait for tasks. For details on this command, see the `Makefile`. To see the workflow running, you need to trigger execution using one of the methods in the following step.

#

You can trigger your workflow using the Mistral Console, the Mistral Python SDK, or the Mistral API. The `my-workflow` project also includes a `Makefile` command to trigger workflows.

**Console**

```console
{
  "result": "Hello, <your_name>! Welcome to Mistral Workflows."
}
```

When you're done testing your workflow, press `Ctrl+C` to stop the worker.

#

You've created and executed your first workflow. To explore larger end-to-end templates, see [Cookbook examples](/studio-api/workflows/getting-started/cookbook_examples). To learn more workflow concepts, see [Core Concepts - Workflows](/studio-api/workflows/getting-started/core_concepts/workflows). For scaling patterns and running multiple workers, see [Core Concepts - Scaling with Multiple Workers](/studio-api/workflows/getting-started/core_concepts/deployments#scaling).
