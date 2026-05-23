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

# Payload lives in a fixture file so the body satisfies githubkit's strict
# WebhookIssueCommentCreated schema (required nested issue/comment/repository
# fields). HMAC is computed over the exact file bytes; --data-binary @file
# sends those same bytes, so the signature matches without intermediate
# whitespace munging.
PAYLOAD_FILE="$(dirname "$0")/fixtures/issue_comment.json"

SIGNATURE="sha256=$(
  openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" -hex "$PAYLOAD_FILE" \
    | awk '{print $NF}'
)"

DELIVERY="smoke-$(date +%s)-$$"

curl -fsSk -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $SIGNATURE" \
  -H "X-GitHub-Event: issue_comment" \
  -H "X-GitHub-Delivery: $DELIVERY" \
  --data-binary "@$PAYLOAD_FILE"
echo
