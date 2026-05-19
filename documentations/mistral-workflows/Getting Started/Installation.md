# Installation

This guide will walk you through setting up Workflows and verifying your installation.

# Prerequisites

Before installing the Workflows SDK, ensure you have:

1. [Python](https://www.python.org/downloads/) 3.12 or later installed on your machine.
2. [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager installed (`uvx` ships with `uv`).

# Install Workflows

Install the Workflows package from PyPI using uv:

```
uv add mistralai-workflows
```

This will create a virtual environment (if one doesn't exist) and install Workflows along with its core dependencies.

## Installing with Optional Dependencies

The Mistral plugin provides native integration with Mistral's AI models and services, including [durable agents](/studio-api/workflows/building-workflows/durable_agents), [tool calling](/studio-api/workflows/building-workflows/durable_agents#built-in-tools), and [multi-agent handoffs](/studio-api/workflows/building-workflows/durable_agents#multi-agent-handoffs):

```
uv add "mistralai-workflows[mistralai]"
```

For [payload offloading](/studio-api/workflows/building-workflows/payload_offloading) and direct cloud storage access from activities, install the extra for your provider:

```
# AWS S3 support
uv add "mistralai-workflows[s3]"

# Azure Blob Storage support
uv add "mistralai-workflows[azure]"

# Google Cloud Storage support
uv add "mistralai-workflows[gcs]"

# All storage providers
uv add "mistralai-workflows[storage]"
```

# Verify Installation

To verify your installation was successful, run the following command:

```
uv run python -c "import mistralai.workflows; print('Workflows is installed successfully!')"
```
