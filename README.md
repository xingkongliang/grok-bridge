# 🌉 grok-bridge v2.0

Turn **SuperGrok** into a command-line tool. No API key needed.

## How it works

```
Your Terminal → Safari JS injection → grok.com → Response extracted via DOM
```

1. Opens a new conversation on `grok.com` via `osascript`
2. Pastes your prompt using `pbcopy` + `Cmd+V` (works with React controlled inputs)
3. Presses Return via System Events
4. Polls `document.body.innerText` until response stabilizes
5. Extracts and outputs Grok's reply

## Quick Start

```bash
# Local (on Mac)
bash scripts/grok_chat.sh "What is the mass of the sun?"

# Remote (from any machine via SSH)
MAC_SSH="ssh user@your-mac" bash scripts/grok_chat.sh "Explain quantum tunneling"

# With options
bash scripts/grok_chat.sh "Write a haiku" --timeout 90 --screenshot
```

## Requirements

- macOS with Safari
- Logged into [grok.com](https://grok.com) (free or SuperGrok)
- System Events permission (Accessibility) for keystroke simulation
- For remote use: SSH access to your Mac

## v2 vs v1

| | v1 | v2 |
|---|---|---|
| Input method | Peekaboo UI automation | pbcopy + Cmd+V (System Events) |
| Speed | ~30s per query | ~3s injection |
| Dependencies | Peekaboo (Homebrew) | None (pure macOS) |
| Reliability | Fragile (UI element detection) | Robust (DOM + clipboard) |
| React compat | ❌ JS setValue doesn't trigger React | ✅ Real paste event works |

## Architecture

```
┌──────────────┐     SSH/local      ┌──────────────┐
│  Your CLI    │ ──────────────────→ │   macOS      │
│  (anywhere)  │                     │              │
└──────────────┘                     │  osascript   │
                                     │  ↓           │
                                     │  Safari      │
                                     │  ↓           │
                                     │  grok.com    │
                                     │  ↓           │
                                     │  DOM poll    │
                                     │  ↓           │
                                     │  Response    │
                                     └──────────────┘
```

## Key Insight

React controlled `<textarea>` ignores JavaScript `value` setter + `input` event.
The only reliable way: **real clipboard paste** (`pbcopy` + `Cmd+V` via System Events).
This is what v2 does — zero extra dependencies, just macOS built-ins.

## License

MIT
