#!/usr/bin/env bash
# Build and push the meow-base sandbox image to Daytona as a named snapshot.
#
# Prerequisites:
#   - `daytona` CLI installed (https://docs.daytona.io/getting-started/installation)
#   - `DAYTONA_API_KEY` exported, or `daytona login` already done
#
# `daytona snapshot create --dockerfile` builds remotely on Daytona, so a
# local Docker daemon is NOT required. The image is forced linux/amd64
# regardless of the host architecture (relevant on Apple Silicon).
#
# Run manually after bumping `mistral-vibe` or system tooling — never in CI.

set -euo pipefail

SNAPSHOT_NAME="${SNAPSHOT_NAME:-meow-base}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKERFILE_PATH="${SCRIPT_DIR}/Dockerfile"

echo "Pushing snapshot '${SNAPSHOT_NAME}' from ${DOCKERFILE_PATH}…"
daytona snapshot create "${SNAPSHOT_NAME}" --dockerfile "${DOCKERFILE_PATH}"
echo "Done. Verify with: daytona snapshot list"
