# grok-bridge v3.1

Turn **SuperGrok** into a REST API + CLI tool. No API key needed.

## How it works

```
Your Terminal/Script → Safari JS injection → grok.com → Response extracted via DOM
```

## Quick Start

### 1. Start the server (on Mac)
```bash
python3 scripts/grok_bridge.py --port 19998

# With authentication (recommended for LAN)
python3 scripts/grok_bridge.py --port 19998 --host 0.0.0.0 --token mysecret
```

### 2. Send requests
```bash
# Chat
curl -X POST http://localhost:19998/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"What is the mass of the sun?","timeout":60}'

# With auth
curl -X POST http://localhost:19998/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mysecret" \
  -d '{"prompt":"Hello","timeout":60}'

# Health check
curl http://localhost:19998/health

# Read current conversation
curl http://localhost:19998/history

# New conversation
curl -X POST http://localhost:19998/new
```

### 3. CLI wrapper
```bash
bash scripts/grok_chat.sh "Explain quantum tunneling"
bash scripts/grok_chat.sh "Hello" --timeout 60 --token mysecret
```

## Server Options

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | 19998 | Listen port |
| `--host` | 127.0.0.1 | Bind address (`0.0.0.0` for LAN access) |
| `--token` | (none) | Bearer token for authentication |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Send prompt, wait for response. Body: `{"prompt":"...", "timeout":120}` |
| POST | `/new` | Start new conversation (waits until input ready) |
| GET | `/health` | Health check (Safari URL, input availability) |
| GET | `/history` | Read current page conversation |

Authentication: pass `Authorization: Bearer <token>` header or `?token=<token>` query param.

## Requirements

- macOS with Safari
- Logged into [grok.com](https://grok.com) (free or SuperGrok)
- Safari > Settings > Advanced > Show features for web developers ✓
- Safari > Develop > Allow JavaScript from Apple Events ✓

## Architecture

```
┌──────────────┐                     ┌───────────────────────┐
│  HTTP Client │  POST /chat         │      macOS            │
│  (anywhere)  │ ──────────────────→ │                       │
└──────────────┘                     │  grok_bridge.py       │
                                     │  ↓ osascript          │
                                     │  Safari do JavaScript │
                                     │  ↓ execCommand        │
                                     │  grok.com textarea    │
                                     │  ↓ button.click()     │
                                     │  Grok responds        │
                                     │  ↓ DOM poll           │
                                     │  Response extracted   │
                                     └───────────────────────┘

┌──────────────┐                     ┌───────────────────────┐
│ grok_chat.sh │  curl POST /chat    │  grok_bridge.py       │
│  (CLI)       │ ──────────────────→ │  (must be running)    │
└──────────────┘                     └───────────────────────┘
```

## v3.1 Changes

- **DOM-based response extraction**: uses message element selectors instead of full-page text splitting
- **Generation detection**: checks stop button / spinner / send button state to know when Grok is done
- **Authentication**: optional `--token` flag for bearer token auth
- **Bind control**: `--host` flag, defaults to `127.0.0.1` (was `0.0.0.0`)
- **Request validation**: checks for empty prompts, invalid JSON, timeout bounds
- **`/new` waits for readiness**: verifies input is available before returning success
- **`/health` diagnostics**: reports input availability in addition to URL
- **CLI simplified**: `grok_chat.sh` is now a thin REST client (no more Swift CGEvent helper)
- **Code quality**: readable names, explicit error handling, no bare `except`

## License

MIT
