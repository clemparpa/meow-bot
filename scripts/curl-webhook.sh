#!/usr/bin/env bash
# POST a signed `issue_comment` webhook against the meow-bot receiver.
#
# Used by:
#   - the smoke-e2e CI workflow (.github/workflows/smoke-e2e.yml)
#   - manual dogfood against a live `docker compose up` stack
#
# Usage:
#   WEBHOOK_SECRET=<secret> scripts/curl-webhook.sh [URL]
#
# URL defaults to https://localhost/gh/webhook (i.e. through Caddy with its
# internal CA, hence `curl -k`). Exits non-zero if the response is not 2xx.

set -euo pipefail

: "${WEBHOOK_SECRET:?WEBHOOK_SECRET must be set}"

URL="${1:-https://localhost/gh/webhook}"

PAYLOAD='{"action":"created","sender":{"login":"alice"},"comment":{"body":"@meow review"}}'

# Hex-only HMAC-SHA256 of the body, prefixed with `sha256=` to match the
# X-Hub-Signature-256 contract enforced by meow.common.github.webhook.
SIGNATURE="sha256=$(
  printf '%s' "$PAYLOAD" \
    | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" -hex \
    | awk '{print $NF}'
)"

DELIVERY="smoke-$(date +%s)-$$"

curl -fsSk -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $SIGNATURE" \
  -H "X-GitHub-Event: issue_comment" \
  -H "X-GitHub-Delivery: $DELIVERY" \
  -d "$PAYLOAD"
echo
