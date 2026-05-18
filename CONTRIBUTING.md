# Contributing to `ci-vibe`

Thanks for your interest in contributing. This document covers the local setup, conventions, and PR process.

## Local setup

`ci-vibe` is a Python project (3.12) using the [Astral](https://astral.sh) tooling stack:

- [`uv`](https://docs.astral.sh/uv/) — package and project manager
- [`ruff`](https://docs.astral.sh/ruff/) — linter and formatter
- [`ty`](https://docs.astral.sh/ty/) — type checker (preview)
- [`pytest`](https://docs.pytest.org/) — test runner

Plus a couple of YAML/Markdown linters:

- [`actionlint`](https://github.com/rhysd/actionlint) — validates `action.yml` and workflows
- [`markdownlint-cli2`](https://github.com/DavidAnson/markdownlint-cli2) — markdown linter

### Install on macOS

```bash
brew install uv actionlint
npm i -g markdownlint-cli2
```

`ruff`, `ty`, and `pytest` are installed as project dev dependencies — `uv sync` takes care of them.

### Bootstrap the project

```bash
git clone https://github.com/clemparpa/ci-vibe.git
cd ci-vibe
uv sync
```

## Running checks locally

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
actionlint
markdownlint-cli2 '*.md' 'prompts/*.md'
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

Breaking changes: append `!` (e.g. `feat!: rename input X to Y`) and document migration in `CHANGELOG.md`.

## PR process

1. Open the PR against `main` with a clear description and link to a tracking issue if relevant.
2. Make sure `CHANGELOG.md` `[Unreleased]` reflects user-visible changes.
3. Make sure all CI checks pass.
4. At least one maintainer review is required before merge.

## Reporting bugs

Use the issue templates under [`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/). For **security issues**, see [`SECURITY.md`](SECURITY.md) — do not open public issues.

## Code of Conduct

This project adheres to the [Contributor Covenant 3.0](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.
