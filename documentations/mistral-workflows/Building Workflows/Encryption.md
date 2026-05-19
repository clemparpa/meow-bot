# Encryption

Encrypt all payloads (workflow inputs, activity I/O, signal data) before they leave your worker. The platform stores ciphertext, and only your workers can decrypt.

| Mode | Workflow input | Activity I/O | Stored in our database |
| --- | --- | --- | --- |
| Default | cleartext | cleartext | yes (cleartext) |
| Encryption | ciphertext | ciphertext | yes (ciphertext) |

> [!NOTE]
> Encryption can be combined with [payload offloading](/studio-api/workflows/building-workflows/payload_offloading) — offloaded payloads are encrypted before they leave your worker, and the orchestrator only sees an encrypted reference.

# Prerequisites

Install the encryption extra:

```
uv add "mistralai[workflow-payload-encryption]"
```

This pulls in `cryptography`, which the SDK uses for AES-GCM encryption.

# Generate a key

Generate a 256-bit AES-GCM key:

**Python**

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

key = AESGCM.generate_key(bit_length=256)
print(key.hex())
```

Store the key in your secret manager. Anyone with this key can read your workflow data.

# Configure your workers

Two modes are available:

- `full`: encrypt every payload.
- `partial`: encrypt only fields typed as `EncryptedStrField`.

**Full encryption**

```full
TEMPORAL_PAYLOAD_ENCRYPTION__MODE=full
TEMPORAL_PAYLOAD_ENCRYPTION__MAIN_KEY=<your_hex_key>
```

Encrypted payloads appear as `<encrypted>` in execution traces and the Studio UI.

# Key rotation

To rotate without downtime, follow these steps:

- **Generate a new key** using the method shown earlier.
- **Promote the new key** and keep the old one as a secondary so workers can still decrypt in-flight executions:

  ```
  TEMPORAL_PAYLOAD_ENCRYPTION__MAIN_KEY=<new_key>
  TEMPORAL_PAYLOAD_ENCRYPTION__SECONDARY_KEY=<old_key>
  ```
- **Wait** for workflows started before the rotation to finish. The wait depends on your retention plus workflow duration (default is 30 days).
- **Remove the old key** by unsetting `SECONDARY_KEY`.
