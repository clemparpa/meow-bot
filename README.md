# `ci-vibe`

> A GitHub Action that wraps [Mistral Vibe](https://github.com/mistralai/mistral-vibe) in headless mode (`vibe --prompt`) to automate code review, security review, and issue triage in any GitHub repository.

[![CI](https://github.com/clemparpa/ci-vibe/actions/workflows/ci.yml/badge.svg)](https://github.com/clemparpa/ci-vibe/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

---

## Status

🚧 **Pre-release.** Current version: `v0.1.0` (MVP).

| Mode | v0.1 status |
|------|-------------|
| `review` — PR code review | ✅ available |
| `security` — SAST-like PR review | 🚧 v0.2 |
| `triage` — issue triage on open | 🚧 v0.3 |
| `custom` — arbitrary prompt | 🚧 v0.4 |

## TL;DR

```yaml
# .github/workflows/review.yml
name: Code review
on: pull_request
permissions:
  contents: read
  pull-requests: write
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: clemparpa/ci-vibe@v0
        with:
          mistral-api-key: ${{ secrets.MISTRAL_API_KEY }}
          mode: review
```

That's it. On every PR, an automated review is posted as a comment.

## Quickstart

1. Create a Mistral API key at <https://console.mistral.ai/> and add it to your repo as a secret named `MISTRAL_API_KEY`.
2. Copy the snippet above into `.github/workflows/review.yml`.
3. Open a PR. Within ~1 minute, you should see a review comment.

For more advanced configuration, see [examples/](examples/).

## Inputs

| Name | Default | Description |
|------|---------|-------------|
| `mistral-api-key` | _(required)_ | Mistral API key. |
| `mode` | `review` | One of `review`, `security`, `triage`, `custom`. Only `review` is implemented in v0.1. |
| `prompt` | `''` | Custom prompt. Required when `mode=custom`. |
| `prompt-override` | `false` | If `true`, append `prompt` to the mode's template. |
| `model` | `mistral-medium-3.5` | Mistral model identifier (e.g. `mistral-medium-3.5`, `devstral-2`). |
| `max-turns` | `10` | Maximum agent turns. |
| `max-price` | `1.00` | Maximum cost in USD. Vibe stops if exceeded. |
| `allowed-tools` | _(mode-dependent)_ | Comma-separated Vibe tools to enable. Defaults: `read_file,grep,bash` for `review`. |
| `comment-pr` | `true` | Post the result as a PR/issue comment. |
| `upload-artifact` | `true` | Upload raw output as a workflow artifact. |
| `exclude-paths` | `''` | Comma-separated globs to exclude from analysis. |
| `agents-md-path` | `AGENTS.md` | Path to `AGENTS.md` in the target repo. Copied to `.vibe/AGENTS.md` before running Vibe. Pass `''` to disable. |
| `vibe-version` | _(latest tested)_ | Pin a specific Mistral Vibe version. |
| `github-token` | `${{ github.token }}` | Token used to comment on PRs/issues. |
| `fail-on-findings` | `false` | For `mode=security` (not in v0.1): fail the job if any `High` finding is reported. |

## Outputs

| Name | Description |
|------|-------------|
| `result-path` | Path to the markdown report produced by Vibe. |
| `findings-count` | Number of findings detected (security mode) or suggestions (review mode). Extracted from a `<!-- findings:N -->` marker in the report. |
| `cost-usd` | ⚠️ Returns `0` in v0.x. `vibe --output json` does not expose `AgentStats.session_cost`. Tracked upstream. |

## Supported models

| Model | Notes |
|-------|-------|
| `mistral-medium-3.5` (default) | Balanced quality/cost. Recommended for `review`. |
| `devstral-2` | Cheaper alternative tuned for code tasks. |

## `AGENTS.md` customization

If your repo has an `AGENTS.md` at the root (per the [agents.md spec](https://agents.md/)), `ci-vibe` automatically copies it to `.vibe/AGENTS.md` before invoking Vibe, so your project's conventions and style guide flow into the review. To use a different path, set the `agents-md-path` input. To disable, pass an empty string.

## Security

- Always use a dedicated Mistral API key for CI with a usage cap set in the console.
- Enable **Require approval for all external contributors** in `Settings → Actions` to mitigate prompt-injection from fork PRs.
- Minimum workflow permissions: `contents: read`, `pull-requests: write`.
- See [`SECURITY.md`](SECURITY.md) for vulnerability reporting.

The action sanitizes PR diffs (strips HTML comments, invisible Unicode characters, hidden HTML attributes) and scrubs secrets from comments before posting.

## Cost estimate

| Mode | Per run (typical) |
|------|-------------------|
| `review` | $0.10 – $0.30 |
| `security` (v0.2+) | $0.50 – $1.50 |

`max-price` is enforced by Vibe itself — it will stop the agent if the cap is reached.

## How is this different from `anthropics/claude-code-action`?

|  | `ci-vibe` | `claude-code-action` |
|--|-----------|----------------------|
| Provider | Mistral | Anthropic |
| Model | `mistral-medium-3.5` / `devstral-2` | Claude (Sonnet/Opus/Haiku) |
| Runtime | Composite (bash + `uv`) | Composite (Bun + TS) |
| License | Apache-2.0 | MIT |
| Status | Early (v0.1 MVP) | Mature |

Use whichever model/provider you prefer or have a key for. They are not feature-equivalent — `claude-code-action` is much more mature.

## Roadmap

See [`SPEC.md`](SPEC.md) §13. Highlights:

- v0.2 — `mode: security`
- v0.3 — `mode: triage`
- v0.4 — `mode: custom`, `agents-md-path` polish
- v0.5 — `fail-on-findings`, optional SARIF upload
- v1.0 — API stable, marketplace publish

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). All contributions are subject to the [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

[Apache-2.0](LICENSE) © 2026 Clement PARPAILLON.
