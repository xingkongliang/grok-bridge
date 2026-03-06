#!/bin/bash
# grok_chat.sh v2 — Turn SuperGrok into a CLI tool
# Sends a prompt to grok.com via Safari automation, waits for response
#
# Usage: bash grok_chat.sh "your question" [--timeout 60] [--screenshot]
#
# How it works:
#   1. Navigate Safari to grok.com (new conversation)
#   2. Focus textarea, paste prompt via pbcopy + Cmd+V
#   3. Press Return to submit
#   4. Poll DOM until response stabilizes
#   5. Extract and output Grok's reply
#
# Requirements:
#   - macOS with Safari logged into grok.com
#   - System Events permission (Accessibility)
#   - If running remotely: MAC_SSH="ssh user@host" bash grok_chat.sh "question"
#
# v1 used Peekaboo UI automation — slow, fragile, extra dependency
# v2 uses Safari JS injection + System Events — 10x faster, zero extra deps

set -euo pipefail

PROMPT="${1:?Usage: grok_chat.sh 'question' [--timeout 60] [--screenshot]}"
TIMEOUT=60
SCREENSHOT=false
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --screenshot) SCREENSHOT=true; shift ;;
    *) shift ;;
  esac
done

# Remote mode: set MAC_SSH="ssh -o ConnectTimeout=5 user@host"
MAC_SSH="${MAC_SSH:-}"

run_cmd() {
  if [[ -n "$MAC_SSH" ]]; then
    $MAC_SSH "$*"
  else
    eval "$*"
  fi
}

run_js() {
  local js="$1"
  run_cmd "osascript -e 'tell application \"Safari\" to do JavaScript \"${js}\" in current tab of window 1'" 2>/dev/null
}

# --- Step 1: New conversation ---
echo "[grok] New conversation..." >&2
run_cmd "osascript -e 'tell application \"Safari\" to set URL of current tab of window 1 to \"https://grok.com/\"'" 2>/dev/null
sleep 4

# --- Step 2: Activate Safari + focus textarea ---
echo "[grok] Sending (${#PROMPT} chars)..." >&2
run_cmd "osascript -e 'tell application \"Safari\" to activate'" 2>/dev/null
sleep 1
run_js "var ta=document.querySelector('textarea');if(ta)ta.focus();"
sleep 0.5

# --- Step 3: Paste + Return via System Events ---
printf '%s' "$PROMPT" | run_cmd pbcopy
sleep 0.3

run_cmd "osascript -e '
tell application \"System Events\"
  tell process \"Safari\"
    keystroke \"v\" using command down
    delay 0.5
    keystroke return
  end tell
end tell
'" 2>/dev/null

# --- Step 4: Poll for response ---
echo "[grok] Waiting (max ${TIMEOUT}s)..." >&2
PREV=""
STABLE=0
sleep 10

for ((i=1; i<=TIMEOUT; i++)); do
  sleep 2
  CURRENT=$(run_js "document.body.innerText.substring(0,4000)" 2>/dev/null || echo "")

  if [[ -n "$CURRENT" && ${#CURRENT} -gt 200 && "$CURRENT" == "$PREV" ]]; then
    STABLE=$((STABLE + 1))
    [[ $STABLE -ge 3 ]] && { echo "[grok] Done (${i}x2s)" >&2; break; }
  else
    STABLE=0
  fi
  PREV="$CURRENT"
  ((i % 5 == 0)) && echo "[grok] Polling... ${i}x2s" >&2
done

[[ $STABLE -lt 3 ]] && echo "[grok] Warning: timeout, response may be incomplete" >&2

# --- Step 5: Extract reply ---
FULL=$(run_js "document.body.innerText" 2>/dev/null || echo "")

PROMPT_PREFIX=$(echo "$PROMPT" | head -c 40)
echo "$FULL" | awk -v prefix="$PROMPT_PREFIX" '
  BEGIN { found=0 }
  !found && index($0, prefix) > 0 { found=1; next }
  found { print }
' | grep -vE "^(Think Harder|Auto|Upgrade to|Toggle|Share|Like|Dislike|Are you satisfied|Get notified|Expert|Fast|Enable|Quick Answer|Explain|Compare|Make it|Executing code)$" \
  | grep -vE "^[0-9]+(\.[0-9]+)?s$" \
  | grep -vE "^[0-9]+ sources$" \
  | sed '/^$/d' \
  | head -80

# --- Step 6: Optional screenshot ---
if $SCREENSHOT; then
  TS=$(date +%s)
  SHOT="/tmp/grok_${TS}.jpg"
  if [[ -n "$MAC_SSH" ]]; then
    $MAC_SSH "/usr/sbin/screencapture -x -t jpg /tmp/grok_shot.jpg && cat /tmp/grok_shot.jpg" > "$SHOT" 2>/dev/null
  else
    /usr/sbin/screencapture -x -t jpg "$SHOT" 2>/dev/null
  fi
  echo "[grok] Screenshot: $SHOT" >&2
fi
