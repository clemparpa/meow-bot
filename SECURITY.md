# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in `meow-bot`, **do not open a public issue**.

Instead, use the **GitHub Private Vulnerability Reporting** feature:

1. Go to the [Security tab](https://github.com/clemparpa/meow-bot/security) of this repository.
2. Click **Report a vulnerability**.
3. Fill in the form with as much detail as possible (affected version, reproduction steps, impact, suggested fix if any).

## Response Targets

- **First acknowledgement** within **7 days**.
- **Fix or mitigation plan** within **30 days** for High severity issues.

## Scope

`meow-bot` is a self-hosted GitHub App. Vulnerabilities in any of the components below are in scope:

- **Webhook receiver** (`src/meow/receiver/`) — HMAC validation, request handling, dispatch logic.
- **Worker** (`src/meow/worker/`) — workflow and activity code, installation token minting and caching.
- **Sandbox orchestration** (`src/meow/worker/sandbox/`) — how Mistral Vibe is invoked, what is mounted, what tools are allowed.
- **GitHub App manifest** (`manifest/app-manifest.yml`) — requested permissions and subscribed events.
- **Prompt templates** (`prompts/`) — prompt-injection vectors inherent to the templates we ship.
- **Container images** (`Dockerfile`, `compose.yml`, `Caddyfile`) — base image choice, privilege model, mounted secrets.

Issues out of scope (please report upstream):

- [`mistralai/mistral-vibe`](https://github.com/mistralai/mistral-vibe/security) — the agent harness itself.
- [Koyeb](https://www.koyeb.com/) — sandbox provider.
- Mistral Workflows — managed control plane.

See [SPEC.md §12](SPEC.md) for the full threat model (loop prevention, HMAC validation, sandbox isolation, token down-scoping, budgeting).

## Supported Versions

While in `0.x`, only the **latest minor** receives security fixes. Once `1.0.0` ships, the latest minor and the previous minor will both be supported.

| Version | Supported |
|---------|-----------|
| `0.x` (latest minor) | yes |
| Older `0.x` | no |
