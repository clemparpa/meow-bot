# Contributing to `meow-bot`

Thanks for your interest in contributing. This document covers the local setup, conventions, and PR process.

## Project shape

`meow-bot` is a self-hosted GitHub App made of three services running together via `docker compose`:

- `receiver` — FastAPI app that validates GitHub webhooks (HMAC) and dispatches work.
- `worker` — long-running Python process that drives Mistral Workflows, spawns Koyeb sandboxes, and runs [Mistral Vibe](https://github.com/mistralai/mistral-vibe) on the target repo (vibe is pre-installed in `koyeb/sandbox`).
- `caddy` — reverse proxy + automatic TLS.

All Python code lives under `src/meow/` with a `src/` layout. See [SPEC.md](SPEC.md) for the architecture and roadmap.

## Local setup

Python 3.13 + the [Astral](https://astral.sh) tooling stack:

- [`uv`](https://docs.astral.sh/uv/) — package and project manager
- [`ruff`](https://docs.astral.sh/ruff/) — linter and formatter
- [`ty`](https://docs.astral.sh/ty/) — type checker (preview)
- [`pytest`](https://docs.pytest.org/) — test runner

Plus:

- [Docker](https://docs.docker.com/) + Docker Compose for the runtime services.
- [`markdownlint-cli2`](https://github.com/DavidAnson/markdownlint-cli2) for Markdown linting.

### Install on macOS

```bash
brew install uv
npm i -g markdownlint-cli2
```

`ruff`, `ty`, and `pytest` are project dev dependencies — `uv sync` takes care of them.

### Bootstrap

```bash
git clone https://github.com/clemparpa/meow-bot.git
cd meow-bot
uv sync
cp .env.example .env   # fill in once you have a GitHub App + Mistral + Koyeb key
```

To run the services locally:

```bash
docker compose up --build
```

The receiver listens on `:8000` inside its container; Caddy fronts it on `:443`. For dev without TLS you can hit `http://localhost:8000/healthz` directly via `docker compose up receiver`.

### Git hooks (lefthook)

Run once after `uv sync`:

```bash
uv run lefthook install
```

This wires `pre-commit` (ruff + format check + ty) and `pre-push` (full lint + tests) into `.git/hooks/`.

## Running checks locally

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
markdownlint-cli2 '*.md' 'docs/*.md'
```

These are the same checks `.github/workflows/ci.yml` runs.

### Note on `ty`

`ty` is in preview as of early 2026. If you hit a false positive that blocks your PR, leave a comment in the PR — we may run `ty` with `--exit-zero` temporarily while waiting for upstream fixes.

## Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation only
- `chore:` tooling / housekeeping
- `refactor:` no behavior change
- `test:` add/modify tests
- `ci:` CI configuration

Breaking changes: append `!` (e.g. `feat!: rename config key X to Y`) and document migration in `CHANGELOG.md`.

## PR process

1. Open the PR against `main` with a clear description and link to a tracking issue if relevant.
2. Make sure `CHANGELOG.md` `[Unreleased]` reflects user-visible changes.
3. Make sure all CI checks pass.
4. At least one maintainer review is required before merge.

## Reporting bugs

Use the issue templates under `.github/ISSUE_TEMPLATE/` (added in a later commit). For **security issues**, see [SECURITY.md](SECURITY.md) — do not open public issues.

## Code of Conduct

This project adheres to the [Contributor Covenant 3.0](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.
