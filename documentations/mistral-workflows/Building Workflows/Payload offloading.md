# Payload offloading

To keep the orchestration layer fast and predictable for every workflow on the platform, Mistral Workflows enforces a **2MB limit** on workflow inputs, activity inputs, and activity outputs. When you need to move data larger than that between steps, the recommended pattern is to **pass references to the data, not the data itself** — for example, an object key in a bucket, a row ID in a database, or a document ID.

To make this seamless, the SDK ships two built-in helpers that turn the reference pattern into a one-line annotation:

- **Activity field offloading** — mark a field as offloadable, and the SDK transparently stores it in *your* blob storage on the way out and rehydrates it on the way in. The orchestration layer only ever sees a small reference.
- **Payload offloading** — automatically offload any payload exceeding the 2MB limit to blob storage. Useful when the workflow itself needs to see or pass around a large value.

Both features run on the worker side and are configured per-deployment.

> [!NOTE]
> Want to encrypt payloads in addition to offloading them? See [Encryption](/studio-api/workflows/building-workflows/encryption) — both features can be combined.

# When to use what

| Your problem | Use |
| --- | --- |
| Activity I/O > 2MB, accessed only inside activities | **Activity field offloading** *(recommended)* |
| Workflow input or activity I/O > 2MB, accessed in workflow code | **Payload offloading** |

> [!TIP]
> **Quick guide**: if you can keep your large data inside activities (most common case), use **activity field offloading** — it has none of the replay-time costs of payload offloading. Only use payload offloading if the workflow itself needs to see or pass around a large value.

# Prerequisites

Install the Workflows SDK with your cloud storage provider:

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

You also need a blob storage container or bucket reachable by every worker.

> [!WARNING]
> **Set an expiry policy on your bucket**: Workflows does **not** automatically delete offloaded payloads. Configure a lifecycle / expiry policy on your bucket and align it with your workflow retention period (default: 30 days). Blobs are prefixed by namespace, so per-namespace policies work too.

# Activity field offloading (recommended)

Mark a Pydantic field as offloadable. The SDK uploads its value to your blob storage on the way out of one activity and downloads it on the way into the next.

**Key points:**

- Offloaded values are **only accessible in activities** (not in workflow context).
- Upload and download happen **within the activity context**, governed by the activity's timeout settings.
- Each `OffloadableField` is stored as a separate blob — group related fields in a single Pydantic model for better performance.

## Defining offloadable fields

**Python**

```python
from mistralai.workflows.core.encoding.fields_offloader import (
    OffloadableModel,
    OffloadableField,
)

class TranscriptionPayload(OffloadableModel):
    audio_id: str                                            # regular field
    transcript: OffloadableField[str] = OffloadableField(    # offloaded
        value=""
    )
```

## Using in activities

In your activity, access the offloaded value using the `get_value()` method. The system handles offloading and restoration automatically:

**Python**

```python
import mistralai.workflows as workflows

@workflows.activity()
async def transcribe(payload: TranscriptionPayload) -> TranscriptionPayload:
    audio = fetch_audio(payload.audio_id)
    text = await whisper(audio)

    return TranscriptionPayload(
        audio_id=payload.audio_id,
        transcript=OffloadableField(value=text),
    )
```

## Using in workflows

In the workflow body, do **not** call `.get_value()` — the value may not be local. Pass the `OffloadableField` object as-is to the next activity:

**Python**

```python
import mistralai.workflows as workflows

@workflows.workflow.define(name="transcribe-and-summarize")
class TranscribeWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, audio_id: str) -> str:
        result = await transcribe(TranscriptionPayload(audio_id=audio_id))

        # Pass the offloaded field through — DON'T unwrap in the workflow
        summary = await summarize(SummaryInput(transcript=result.transcript))
        return summary.text
```

## Performance tip

Each `OffloadableField` is a separate blob round-trip. If multiple fields are always read together, group them into a single Pydantic model:

**Python**

```python
from pydantic import BaseModel
from mistralai.workflows.core.encoding.fields_offloader import (
    OffloadableModel,
    OffloadableField,
)

class LargeContext(BaseModel):
    transcript: str
    speaker_diarization: list[dict]
    audio_features: dict[str, float]

class Payload(OffloadableModel):
    large: OffloadableField[LargeContext]   # one blob, three fields
```

## Configuration

Set these env vars on your workers. Providing the storage block is what enables the feature — there is no separate `ENABLED` flag. The default minimum size is 1MB; tune it with `MIN_SIZE_BYTES`.

**Azure**

```azure
ACTIVITY_ATTRIBUTES_OFFLOADING__MIN_SIZE_BYTES=1048576   # 1MB (default)
ACTIVITY_ATTRIBUTES_OFFLOADING__STORAGE_CONFIG__STORAGE_PROVIDER=azure
ACTIVITY_ATTRIBUTES_OFFLOADING__STORAGE_CONFIG__CONTAINER_NAME=my-workflow-payloads
ACTIVITY_ATTRIBUTES_OFFLOADING__STORAGE_CONFIG__AZURE_CONNECTION_STRING="..."
```

# Payload offloading (whole-payload escape hatch)

Use this when a workflow input or output is consistently large and you can't restructure it into activity fields.

The SDK auto-offloads any payload above 2MB to blob storage. The platform stores a reference; workers download the payload on demand.

> [!WARNING]
> **Replay cost**: when a workflow is replayed (worker restart, crash recovery), every offloaded payload is downloaded again. For workflows with many large payloads, this can cause activity timeouts and worker stalls. Prefer **activity field offloading** for hot paths.

## Configuration

Payload offloading requires configuration on **both the client and the worker** since payloads can be offloaded when starting a workflow (client-side) and when passing data between activities (worker-side).

Offloaded data is stored in **your own cloud storage**. You are responsible for:

- Creating and managing the storage bucket or container.
- Configuring appropriate access credentials.
- Ensuring **both the client and worker have access** to the same storage.
- Setting up an **expiry policy** — Workflows does not automatically delete payloads. Align the expiry with your workflow retention period (default: 30 days).

### Worker configuration

Set these env vars on your workers:

**Azure**

```azure
TEMPORAL_PAYLOAD_OFFLOADING__STORAGE_CONFIG__STORAGE_PROVIDER=azure
TEMPORAL_PAYLOAD_OFFLOADING__STORAGE_CONFIG__CONTAINER_NAME=workflow-payloads
TEMPORAL_PAYLOAD_OFFLOADING__STORAGE_CONFIG__AZURE_CONNECTION_STRING="..."
```

As with activity field offloading, presence of the storage block enables the feature — there is no `ENABLED` flag.

### Client configuration

When using the Mistral Python SDK to start workflows whose input may exceed 2MB, configure offloading on the client too:

**Azure**

```azure
from mistralai.client import Mistral
from mistralai.extra.workflows.encoding import PayloadOffloadingConfig, BlobStorageConfig

client = Mistral(
    api_key="your_api_key",
    workflow_payload_offloading=PayloadOffloadingConfig(
        storage_config=BlobStorageConfig(
            storage_provider="azure",
            container_name="workflow-payloads",
            azure_connection_string="...",
        )
    ),
)

execution = client.workflows.execute_workflow(
    workflow_identifier="my-workflow",
    input={"large_data": "..."},  # Will be offloaded if > 2MB
)
```
