# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - TBD

### Added

- Initial MVP scaffolding of the `ci-vibe` GitHub Action.
- Support for `mode: review` — code review of pull requests via Mistral Vibe in headless mode.
- Composite action with minimal YAML orchestration; main logic in a Python module `ci_vibe` invoked via `uv run --no-project --with mistral-vibe==<pin>`.
- Python module layout: `src/ci_vibe/{__main__,config,context,runner,parser,commenter,templates}.py`.
- Direct integration with Vibe's public Python API (`from vibe.core import run_programmatic`) instead of the CLI.
- Inputs: `mistral-api-key`, `mode`, `prompt`, `prompt-override`, `model`, `max-turns`, `max-price`, `allowed-tools`, `comment-pr`, `upload-artifact`, `exclude-paths`, `agents-md-path`, `vibe-version`, `github-token`, `fail-on-findings`, `enable-uv-cache`.
- Outputs: `result-path`, `findings-count`, `cost-usd` (returns `0` — see Known Limitations).
- Prompt template for review mode (`prompts/review.md`).
- Sanitization of PR diff (HTML comments + invisible Unicode characters via `re.sub`) to mitigate prompt injection.
- Scrubbing of secrets from comment output before posting via `gh`.
- `AGENTS.md` convention: file copied from `agents-md-path` to `${GITHUB_WORKSPACE}/.vibe/AGENTS.md` before Vibe invocation.
- **Preflight permission check** before invoking the LLM, to fail fast on misconfigured `github-token`.
- **`enable-uv-cache: false` by default** to mitigate cache-poisoning risk (pattern from `OpenHands/extensions/plugins/pr-review`).
- Example workflow under `examples/pr-review.yml`.
- CI workflow with `ruff` (lint + format), `ty` (type-check), `pytest`, `actionlint`, `markdownlint-cli2`.
- Apache-2.0 license.

### Known Limitations

- `cost-usd` output always returns `0` in v0.x: Mistral Vibe's `run_programmatic` returns `str | None` (the serialized `LLMMessage[]`), not the `AgentStats` object where `session_cost` lives. Tracked upstream.
- Modes `security`, `triage`, `custom` are declared in the manifest but **not implemented** in v0.1 — invoking them errors out cleanly. See roadmap in `SPEC.md` §13.
- No `dogfood`, `release`, `major-tag`, or `update-vibe-version` workflows yet — deferred to v0.2+.
- `ty` (Astral's type-checker) is in preview at the time of this release; falling back to `--exit-zero` if too unstable is documented in `CONTRIBUTING.md`.
