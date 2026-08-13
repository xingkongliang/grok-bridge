#!/bin/bash
# smoke_test.sh — 30-second end-to-end check for grok-bridge.
# Requires the server running. Usage: bash smoke_test.sh [port]
set -euo pipefail
PORT="${1:-19998}"
BASE="http://localhost:${PORT}"

echo "== /health =="
HEALTH=$(curl -sf "${BASE}/health")
echo "$HEALTH" | jq .
[[ $(echo "$HEALTH" | jq -r '.on_grok') == "true" ]] || {
  echo "FAIL: pinned tab is not on grok.com" >&2; exit 1; }
[[ $(echo "$HEALTH" | jq -r '.input_available') == "true" ]] || {
  echo "FAIL: input not available (logged out? page not loaded?)" >&2; exit 1; }

echo "== /chat =="
RESP=$(curl -sf -X POST "${BASE}/chat" -H "Content-Type: application/json" \
  -d '{"prompt":"Reply with exactly the word PONG and nothing else.","timeout":60}')
echo "$RESP" | jq .
[[ $(echo "$RESP" | jq -r '.status') == "ok" ]] || { echo "FAIL: /chat status" >&2; exit 1; }
echo "$RESP" | jq -r '.response' | grep -qi "PONG" || { echo "FAIL: unexpected /chat response" >&2; exit 1; }

echo "SMOKE TEST PASSED"
