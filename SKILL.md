# grok-bridge v2.0

Turn SuperGrok into a CLI tool via Safari JS injection + System Events.

## Usage

```bash
# Local (on Mac)
bash scripts/grok_chat.sh "your question"

# Remote (via SSH)
MAC_SSH="ssh user@mac" bash scripts/grok_chat.sh "your question"

# Options
bash scripts/grok_chat.sh "question" --timeout 90 --screenshot
```

## How it works

1. `osascript` navigates Safari to `grok.com`
2. `pbcopy` + `Cmd+V` (System Events) pastes prompt into textarea
3. System Events presses Return to submit
4. Polls `document.body.innerText` until stable (3 consecutive matches)
5. Extracts reply via awk, filters UI noise

## Requirements

- macOS + Safari logged into grok.com
- Accessibility permission for System Events
- SSH access (for remote use)

## Key design decision

React controlled textarea ignores JS `value` setter. Real clipboard paste (`pbcopy` + `Cmd+V`) is the only reliable input method.
