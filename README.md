# `meow-bot`

> A self-hostable, OSS GitHub App that behaves like a human teammate on your repos: tag it in an issue or PR and it responds, reviews, and (later) opens PRs of its own. Powered by [Mistral Vibe](https://github.com/mistralai/mistral-vibe).

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

---

## Status

**Pre-alpha (`v0.0.x`).** Scaffold only — not ready for production use. The first runnable feature (`MENTION_REVIEW`) lands in `v0.1.0`. See [SPEC.md](SPEC.md) for the full design and roadmap.

## What it does

You install `meow-bot` on your GitHub repos. Then, on any pull request:

```text
@your-meow-bot review
```

The bot pulls the PR diff, runs Mistral Vibe in an isolated sandbox, and posts a review as a comment. Read-only by default — no commits, no pushes.

Later versions add `CODE_REQUEST` (open a PR from a natural-language request), `TRIAGE` (label and analyze new issues), and a proactive cron scanner. See the roadmap in [SPEC.md §17](SPEC.md).

## Distribution model

`meow-bot` is **self-hosted and bring-your-own-keys** by design:

- You host the worker on your own VPS via `docker compose up`.
- You create your own GitHub App from the provided manifest (1-click flow).
- You bring your own Mistral, Daytona, and GitHub App credentials.

No central service hosted by the maintainers. No quotas, no billing, no usage tracking. Just a Docker image you run.

A managed / SaaS mode may exist later as a separate sub-project — not in the core repo.

## Architecture

Three services on the host:

```text
GitHub → receiver (FastAPI, HMAC) → Mistral Workflows (managed)
                                          ↓
                                       worker → Daytona sandbox (Vibe)
                                          ↓
                                       GitHub (post comment)
```

Mistral Workflows (durability, retries, cron) and Daytona (ephemeral sandboxes) are external managed services you also sign up for. See [SPEC.md §3](SPEC.md) for the detailed diagram.

## Quickstart

> Quickstart is being written in tandem with `v0.0.x`. For now, see the placeholder at [docs/quickstart.md](docs/quickstart.md) (added in the scaffold commits).

The intended flow targets `< 15 min` for a developer who already runs Docker on a VPS:

1. Provision a VPS with a domain pointing at it.
2. Clone this repo.
3. Click the **Create my Meow App** link in the README (the GitHub App manifest flow registers the App with the right permissions in one click).
4. Drop the generated `.pem` and webhook secret into `.env`.
5. `docker compose up -d`.
6. Install your new App on a target repo, then `@<your-bot> review` on a PR.

## Configuration on the target repo

Repos using your bot can drop a `.meow.yml` at their root to tune behavior:

```yaml
# .meow.yml — optional; all fields have sane defaults
model: mistral-medium-3.5
max_turns: 15
max_price_usd: 0.50
language: auto
agents_md_path: AGENTS.md
exclude_paths:
  - "vendor/**"
  - "**/*.lock"
```

Full schema in [SPEC.md §10](SPEC.md).

## Security

- Webhook bodies are validated with HMAC-SHA256 (`X-Hub-Signature-256`).
- Installation tokens are minted just-in-time and down-scoped per intent (`contents: read` for review mode, etc.).
- Vibe runs in an ephemeral Daytona sandbox with no host secrets mounted.
- `max_turns` and `max_price` are always enforced.
- See [SECURITY.md](SECURITY.md) for vulnerability reporting, and [SPEC.md §12](SPEC.md) for the full threat model.

## Roadmap (summary)

| Version | Highlight |
|---|---|
| `v0.0.x` | Scaffold (Docker, receiver, manifest). |
| `v0.1.0` | `MENTION_REVIEW` end-to-end (read-only). |
| `v0.2.0` | Multi-intent classifier, per-thread budgets, `MENTION_QUESTION`. |
| `v0.3.0` | `CODE_REQUEST` (writes a branch, opens a PR). |
| `v0.4.0` | `TRIAGE` for new issues. |
| `v0.5.0` | Proactive cron scanner (opt-in). |
| `v1.0.0` | API stable. |

Detailed criteria in [SPEC.md §17 / §19](SPEC.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions are subject to the [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

[Apache-2.0](LICENSE) © 2026 Clement PARPAILLON.
