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
# internal CA, hence `curl -k`). Exits non-zero if every attempt fails.
#
# Retries: up to 4 attempts with a 5s gap between them, but only on 5xx
# responses (typically the receiver bubbling up a Mistral
# "Deployment not found" while heartbeat propagation catches up).
# 4xx responses bail out immediately — those are our bug, not a race.

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

MAX_ATTEMPTS=4
SLEEP_BETWEEN=5
RESPONSE_BODY="$(mktemp)"
trap 'rm -f "$RESPONSE_BODY"' EXIT

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  STATUS=$(curl -sSk -o "$RESPONSE_BODY" -w "%{http_code}" -X POST "$URL" \
    -H "Content-Type: application/json" \
    -H "X-Hub-Signature-256: $SIGNATURE" \
    -H "X-GitHub-Event: issue_comment" \
    -H "X-GitHub-Delivery: $DELIVERY" \
    --data-binary "@$PAYLOAD_FILE")

  if [ "$STATUS" -ge 200 ] && [ "$STATUS" -lt 400 ]; then
    cat "$RESPONSE_BODY"
    echo
    exit 0
  fi

  if [ "$STATUS" -ge 400 ] && [ "$STATUS" -lt 500 ]; then
    echo "client error: HTTP $STATUS" >&2
    cat "$RESPONSE_BODY" >&2
    echo >&2
    exit 1
  fi

  echo "attempt $attempt/$MAX_ATTEMPTS: HTTP $STATUS, retrying in ${SLEEP_BETWEEN}s" >&2
  cat "$RESPONSE_BODY" >&2
  echo >&2
  if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
    sleep "$SLEEP_BETWEEN"
  fi
done

echo "::error::receiver returned 5xx on every attempt" >&2
exit 1
