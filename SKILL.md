---
name: grok-bridge
description: >
  Query the SuperGrok web app (grok.com) by driving a logged-in Safari session via REST — no API key, no token cost.
  Use this when the user wants the flagship grok.com chat model's take on something conversational, or specifically
  wants Grok's real-time X/Twitter knowledge: current events, trending topics, "what's the buzz on X about ...",
  sentiment on a post or account. Also use to start/stop/health-check the grok-bridge server. This is a TEXT-ONLY
  chat bridge — it cannot read your files, run code, or act on a codebase, and it serializes one Safari tab.
  For agentic Grok work — anything that touches local files, writes or refactors code, runs commands, or needs to be
  scripted/parallelized/headless through the local `grok` CLI — use the `grok-build` skill instead, not this one.
---

# grok-bridge

Turn SuperGrok into a REST API via Safari JS injection. No API key needed — just a logged-in Safari session on grok.com.

## How it works

The Python server (`scripts/grok_bridge.py`) uses AppleScript to inject JavaScript into Safari, driving grok.com's web UI programmatically. No Accessibility permission required.

```
HTTP Client → grok_bridge.py → osascript → Safari do JavaScript → grok.com → DOM poll → Response
```

The bridge pins a dedicated grok.com tab (first one found by URL; created in the background if missing) and never activates Safari — the user can keep working in other apps and tabs while requests run. Keep only one grok.com tab open so the right one gets pinned.

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

grok-bridge controls a single Safari tab. `/chat` and `/new` share a Python threading lock — only one runs at a time, others queue.

**Rule: never send concurrent requests.** Wait for each `/chat` to complete before sending the next. If you need to call Grok from multiple agents or scripts, queue them through a single caller.

## Troubleshooting

- **"input element not found"**: the pinned tab isn't logged in or hasn't loaded. Run GET /health to check, then POST /new to navigate.
- **"no grok.com tab found"**: Safari has no window; open Safari and retry (the bridge creates the tab itself).
- **"osascript error"**: "Allow JavaScript from Apple Events" is not enabled in Safari's Develop menu.
- **Timeout with partial response**: Grok may be slow. Increase the `timeout` parameter. The response field will contain whatever was generated before timeout.
- **Auth errors**: If `--token` was set, every request needs `Authorization: Bearer <token>` header.
- **Selectors broken after a Grok UI update**: run `python3 scripts/probe_dom.py` to see which DOM anchors still match, and `bash scripts/smoke_test.sh` for an end-to-end check.
