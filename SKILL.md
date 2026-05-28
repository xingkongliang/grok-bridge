---
name: grok-bridge
description: >
  Talk to Grok (xAI) via Safari automation on macOS — start the REST API server, send prompts, manage conversations.
  Use this skill whenever the user wants to query Grok, use Grok as a tool, start/stop the grok-bridge server,
  or integrate Grok into a workflow. Also trigger when the user mentions "grok", "SuperGrok", "xAI chat",
  or wants to use a browser-based LLM through automation.
---

# grok-bridge

Turn SuperGrok into a REST API via Safari JS injection. No API key needed — just a logged-in Safari session on grok.com.

## How it works

The Python server (`scripts/grok_bridge.py`) uses AppleScript to inject JavaScript into Safari, driving grok.com's web UI programmatically. No Accessibility permission required.

```
HTTP Client → grok_bridge.py → osascript → Safari do JavaScript → grok.com → DOM poll → Response
```

## Prerequisites

Before using, ensure:
1. Safari > Settings > Advanced > "Show features for web developers" is checked
2. Safari > Develop > "Allow JavaScript from Apple Events" is checked
3. Safari is logged into [grok.com](https://grok.com) (free or SuperGrok)

If the user hasn't set these up, walk them through it before starting the server.

## Before using

Always check if the server is already running before trying to start it:
```bash
curl -s http://localhost:19998/health
```
If you get a JSON response with `"status": "ok"`, the server is up — skip to the API Endpoints section. If connection refused, start the server below.

## Starting the server

The server script is at `scripts/grok_bridge.py` relative to this SKILL.md file's directory. It uses Python stdlib only — no pip install needed. Use the directory containing this SKILL.md as the base path.

```bash
# SKILL_DIR = directory containing this SKILL.md (resolve before use)

# Local only (default)
python3 <SKILL_DIR>/scripts/grok_bridge.py --port 19998

# LAN access with auth (for remote machines via Tailscale etc.)
python3 <SKILL_DIR>/scripts/grok_bridge.py --port 19998 --host 0.0.0.0 --token <secret>
```

Server options:
- `--port` (default 19998) — listen port
- `--host` (default 127.0.0.1) — bind address, use `0.0.0.0` for LAN
- `--token` (optional) — bearer token for authentication

Run in background if the user wants it persistent:
```bash
nohup python3 <SKILL_DIR>/scripts/grok_bridge.py --port 19998 > /tmp/grok-bridge.log 2>&1 &
```

## API Endpoints

All endpoints return JSON. Authentication via `Authorization: Bearer <token>` header or `?token=<token>` query param.

### POST /chat — Send a prompt, wait for Grok's response
```bash
curl -X POST http://localhost:19998/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"your question here","timeout":120}'
```
- `prompt` (required): the question to ask Grok
- `timeout` (optional, default 120, range 10-600): max seconds to wait

Response: `{"status":"ok","response":"...","elapsed":5.2}`

### POST /new — Start a new conversation
```bash
curl -X POST http://localhost:19998/new
```
Navigates Safari to grok.com and waits until the input is ready.

### GET /health — Health check
```bash
curl http://localhost:19998/health
```
Returns Safari URL, whether it's on grok.com, input availability, and version.

### GET /history — Read current conversation
```bash
curl http://localhost:19998/history
```

## CLI wrapper

For quick one-off queries from the terminal (requires server running):
```bash
bash scripts/grok_chat.sh "your question" --timeout 60 --token mysecret
```

## Common workflows

**Use Grok to answer a question from another tool's pipeline:**
1. Ensure server is running
2. POST /chat with the prompt
3. Parse the JSON response

**Start a fresh conversation before a new topic:**
1. POST /new
2. POST /chat with the new prompt

**Check if everything is working:**
1. GET /health — verify `on_grok: true` and `input_available: true`

## Concurrency limitation

grok-bridge controls a single Safari tab. All `/chat` requests are serialized via a Python threading lock — only one runs at a time, others queue. However `/new` and `/health` are not gated by the same lock, so calling `/new` while a `/chat` is in progress will navigate Safari away and break the ongoing request.

**Rule: never send concurrent requests.** Wait for each `/chat` to complete before sending the next. If you need to call Grok from multiple agents or scripts, queue them through a single caller.

## Troubleshooting

- **"input element not found"**: Safari may not be on grok.com, or the page hasn't loaded. Run GET /health to check, then POST /new to navigate.
- **"osascript error"**: "Allow JavaScript from Apple Events" is not enabled in Safari's Develop menu.
- **Timeout with partial response**: Grok may be slow. Increase the `timeout` parameter. The response field will contain whatever was generated before timeout.
- **Auth errors**: If `--token` was set, every request needs `Authorization: Bearer <token>` header.
