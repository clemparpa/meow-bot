# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in `ci-vibe`, **do not open a public issue**.

Instead, use the **GitHub Private Vulnerability Reporting** feature:

1. Go to the [Security tab](https://github.com/clemparpa/ci-vibe/security) of this repository.
2. Click **Report a vulnerability**.
3. Fill in the form with as much detail as possible (affected version, reproduction steps, impact).

## Response Targets

- **First acknowledgement** within **7 days**.
- **Fix or mitigation plan** within **30 days** for High severity issues.

## Scope

In scope:

- The action manifest (`action.yml`) and shell scripts under `scripts/`.
- Prompt templates under `prompts/` (prompt-injection vectors specific to the action's wrapping).

Out of scope:

- Vulnerabilities in `mistral-vibe` itself — please report those upstream at <https://github.com/mistralai/mistral-vibe/security>.
- Vulnerabilities in third-party GitHub Actions consumed by this action — report them to their respective maintainers.

## Supported Versions

While in `0.x`, only the **latest minor** is supported. Once `1.0.0` ships, the latest minor and the previous minor will both receive security fixes.

| Version | Supported |
|---------|-----------|
| `0.x` (latest minor) | ✅ |
| Older `0.x` | ❌ |
