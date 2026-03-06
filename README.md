# 🌉 Grok Bridge

Turn [SuperGrok](https://grok.com) into a REST API — let your AI agents use Grok for free via Safari browser automation.

## How it Works

```
Your Agent → HTTP POST → Grok Bridge (Mac) → Safari → grok.com → Response
```

Grok Bridge runs on macOS, automating Safari's SuperGrok tab via JavaScript injection (osascript) or [Peekaboo](https://github.com/steipete/peekaboo) UI automation as fallback.

## Quick Start

### One-liner (SSH mode, no server needed)
```bash
bash grok_chat.sh "What is eBPF?" --mode expert
```

### REST API Server
```bash
# Start the bridge on your Mac
python3 grok_bridge.py --port 19998

# Call from anywhere
curl -X POST http://localhost:19998/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Explain quantum computing", "mode": "auto"}'
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/modes` | GET | List available modes |
| `/chat` | POST | Send prompt, get response |
| `/new` | POST | Start new conversation |

### POST /chat
```json
{
  "prompt": "Your question here",
  "mode": "auto",       // auto|fast|expert|heavy
  "timeout": 120        // seconds
}
```

**Response:**
```json
{
  "status": "ok",
  "response": "Grok's answer..."
}
```

## Grok Modes

| Mode | Best For | Speed |
|------|----------|-------|
| `auto` | General use | Medium |
| `fast` | Simple questions | Fast |
| `expert` | Deep analysis | Slow |
| `heavy` | Complex reasoning | Slowest |

## Requirements

- macOS 13+
- Safari with active SuperGrok login (grok.com)
- Safari → Develop menu → "Allow JavaScript from Apple Events" ✅
- Python 3.9+
- Optional: [Peekaboo](https://github.com/steipete/peekaboo) for UI automation fallback

## Installation

```bash
git clone https://github.com/ythx-101/grok-bridge.git
cd grok-bridge

# Option 1: Run the server
python3 scripts/grok_bridge.py --port 19998

# Option 2: Use the shell script directly
bash scripts/grok_chat.sh "Hello Grok"
```

## Architecture

```
┌─────────────┐     SSH/HTTP      ┌──────────────┐
│  VPS Agent  │ ──────────────── │  Mac (Bridge) │
│  (Caller)   │                   │               │
└─────────────┘                   │  ┌──────────┐ │
                                  │  │ Safari   │ │
                                  │  │ grok.com │ │
                                  │  └──────────┘ │
                                  │       ↑       │
                                  │  osascript JS │
                                  │  or Peekaboo  │
                                  └──────────────┘
```

## Integration with OpenClaw

This bridge was designed to work with [OpenClaw](https://openclaw.ai) AI agents:

```bash
# In your agent's dispatch.sh
bash dispatch.sh --agent grok --task "Analyze this code for security issues"
```

## Limitations

- Single tab, no concurrency (one request at a time)
- Depends on SuperGrok web DOM (may need updates after UI changes)
- Requires active Safari login session
- macOS only (Safari automation)

## License

MIT — see [LICENSE](LICENSE)

## Credits

Built by [小灵 🦞](https://github.com/ythx-101) as part of the OpenClaw ecosystem.
