# grok-bridge v3.1

Talk to Grok via Safari automation — REST API + CLI wrapper.

## Architecture
- Safari AppleScript `do JavaScript` = CDP Runtime.evaluate
- `document.execCommand('insertText')` = input (bypasses React controlled components)
- JS `button.click()` = submit (no System Events permission needed)
- DOM-based response extraction (message element selectors, not full-page text split)
- Generation detection via stop button / spinner / send button state
- **No Accessibility permission required**

## Usage

### REST API (recommended)
```bash
# Start server on Mac
python3 scripts/grok_bridge.py --port 19998
python3 scripts/grok_bridge.py --port 19998 --host 0.0.0.0 --token mysecret

# Chat
curl -X POST http://localhost:19998/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mysecret" \
  -d '{"prompt":"hello","timeout":120}'

# Endpoints
GET  /health   — health check (URL, input availability)
GET  /history  — read current page conversation
POST /new      — new conversation (waits until input ready)
POST /chat     — send question, wait for response
```

### CLI wrapper
```bash
bash scripts/grok_chat.sh "your question" --timeout 60 --token mysecret
```

Requires `grok_bridge.py` to be running. Uses `curl` + `jq`.

## Prerequisites
1. Safari > Settings > Advanced > Show features for web developers ✓
2. Safari > Develop > Allow JavaScript from Apple Events ✓
3. Safari logged into grok.com (SuperGrok recommended)

## Files
- `scripts/grok_bridge.py` — REST API server (v2, Python stdlib only)
- `scripts/grok_chat.sh` — CLI wrapper (calls REST API via curl)
