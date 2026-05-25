# `meow-base` sandbox image

The image used by every ephemeral Daytona sandbox spawned by
`run_review_in_sandbox` (spec §8.5). One image, versioned, registered
in Daytona under the snapshot name `meow-base`. S12 consumes it via
`Daytona().create(snapshot="meow-base")`.

## What's in the image

- `python:3.13-slim`
- `git` (clone the PR)
- `gh` CLI (`gh pr checkout` after clone)
- `mistral-vibe==2.10.1` (the agent harness — `vibe.core.run_programmatic`)
- Empty `/root/.vibe/` skeleton (S12 populates if needed)

## Prerequisites

- [`daytona` CLI](https://docs.daytona.io/getting-started/installation) installed
- `DAYTONA_API_KEY` exported, or `daytona login` already done
- Optional: a local Docker daemon if you want to smoke-test the image
  before pushing (the `daytona snapshot create --dockerfile` flow builds
  remotely on Daytona's infra, so Docker is not strictly required)

## Push the snapshot

```bash
bash sandbox/build-and-push.sh
daytona snapshot list   # `meow-base` should appear
```

The script forces `linux/amd64` via Daytona's remote build — host
architecture (Apple Silicon, etc.) doesn't matter.

## When to re-build

Re-run the script **manually** when any of these change:

- `mistral-vibe` version bump
- `python` base image bump
- New system tool added to the image (`apt-get install …`)

Not on every PR. Not in CI. The image is supposed to be stable for
many reviews.

## Smoke-test the image locally (optional)

```bash
docker build --platform=linux/amd64 -t meow-base sandbox/
docker run --rm meow-base python -c "import vibe; print(vibe.__version__)"
docker run --rm meow-base gh --version
docker run --rm meow-base git --version
```

The `--platform=linux/amd64` flag is required on Apple Silicon to match
Daytona's runtime architecture.

## Troubleshooting

- **`daytona: command not found`** — install the CLI (see Prerequisites).
- **Auth errors from `snapshot create`** — `daytona login` or check
  `DAYTONA_API_KEY` is exported in the current shell.
- **Remote build fails** — the CLI streams build logs; usual culprits
  are a transient PyPI/Debian mirror hiccup or a typo in the Dockerfile.
  Re-run; if persistent, smoke-build locally with the command above to
  isolate the issue.
