#!/bin/bash
# grok_chat.sh — Lightweight CLI wrapper for grok_bridge.py REST API
#
# Usage:
#   bash grok_chat.sh "your question" [--timeout 60] [--port 19998] [--host localhost] [--token xxx]
#
# Prerequisites: grok_bridge.py must be running
#   python3 scripts/grok_bridge.py --port 19998

set -euo pipefail

PROMPT="${1:?Usage: grok_chat.sh 'question' [--timeout 60] [--port 19998] [--host localhost] [--token xxx]}"
TIMEOUT=120
PORT=19998
HOST="localhost"
TOKEN=""
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    *) shift ;;
  esac
done

BASE_URL="http://${HOST}:${PORT}"
AUTH_HEADER=""
if [[ -n "$TOKEN" ]]; then
  AUTH_HEADER="Authorization: Bearer ${TOKEN}"
fi

# Health check
echo "[grok] Checking server at ${BASE_URL}..." >&2
HEALTH=$(curl -sf ${AUTH_HEADER:+-H "$AUTH_HEADER"} "${BASE_URL}/health" 2>/dev/null || echo "")
if [[ -z "$HEALTH" ]]; then
  echo "[grok] Error: server not reachable at ${BASE_URL}" >&2
  echo "[grok] Start it with: python3 scripts/grok_bridge.py --port ${PORT}" >&2
  exit 1
fi

# Send prompt
echo "[grok] Sending (${#PROMPT} chars, timeout=${TIMEOUT}s)..." >&2
PAYLOAD=$(jq -cn --arg p "$PROMPT" --argjson t "$TIMEOUT" '{prompt:$p,timeout:$t}')

RESPONSE=$(curl -sf \
  -X POST "${BASE_URL}/chat" \
  -H "Content-Type: application/json" \
  ${AUTH_HEADER:+-H "$AUTH_HEADER"} \
  -d "$PAYLOAD" \
  --max-time $((TIMEOUT + 10)) \
  2>/dev/null || echo "")

if [[ -z "$RESPONSE" ]]; then
  echo "[grok] Error: no response from server (timeout or connection error)" >&2
  exit 1
fi

STATUS=$(echo "$RESPONSE" | jq -r '.status // "unknown"')
if [[ "$STATUS" == "error" ]]; then
  ERROR=$(echo "$RESPONSE" | jq -r '.error // "unknown error"')
  echo "[grok] Error: ${ERROR}" >&2
  exit 1
fi

if [[ "$STATUS" == "timeout" ]]; then
  echo "[grok] Warning: response may be incomplete (timeout)" >&2
fi

ELAPSED=$(echo "$RESPONSE" | jq -r '.elapsed // ""')
[[ -n "$ELAPSED" ]] && echo "[grok] Done (${ELAPSED}s)" >&2

# Output the response
echo "$RESPONSE" | jq -r '.response // ""'
