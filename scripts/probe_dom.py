#!/usr/bin/env python3
"""
probe_dom.py — Diagnostic for grok.com DOM selectors.

Run this when the bridge stops working after a Grok UI update: it reports
which of the bridge's DOM anchors still match, so you can re-derive selectors
without reverse-engineering from scratch. Reads the same pinned tab the
bridge uses (first Safari tab on grok.com).

Usage: python3 probe_dom.py
"""
import json
import subprocess
import sys

DOMAIN = "grok.com"

FIND_TAB_SCRIPT = f'''
tell application "Safari"
    repeat with w in windows
        try
            repeat with i from 1 to (count of tabs of w)
                try
                    set u to URL of tab i of w
                    if u contains "{DOMAIN}" then return (id of w as text) & "|" & (i as text)
                end try
            end repeat
        end try
    end repeat
    return ""
end tell
'''

PROBE = r"""
(()=>{
    const q = (s) => document.querySelector(s);
    const qa = (s) => document.querySelectorAll(s);
    return JSON.stringify({
        url: location.href,
        input_contenteditable: qa('div[contenteditable="true"]').length,
        input_textarea: qa('textarea').length,
        submit_button: !!q('button[aria-label="Submit"], button[aria-label="Send"]'),
        stop_button: !!q('button[aria-label="Stop"], button[aria-label="Cancel"], button[data-testid="stop-button"]'),
        regenerate_button: !!q('button[aria-label="Regenerate"]'),
        response_markdown: qa('[class*="response-content-markdown"]').length,
        message_bubbles: qa('[class*="message-bubble"]').length,
        code_wrappers: qa('[class*="response-content-markdown"] pre').length,
        last_response_head: (() => {
            const r = qa('[class*="response-content-markdown"]');
            if (!r.length) return '';
            return r[r.length - 1].innerText.slice(0, 120);
        })(),
    }, null, 2);
})()
"""


def main():
    ref = subprocess.run(["osascript", "-e", FIND_TAB_SCRIPT],
                         capture_output=True, text=True).stdout.strip()
    if "|" not in ref:
        print(f"No Safari tab on {DOMAIN} found. Open one and retry.", file=sys.stderr)
        sys.exit(1)
    wid, idx = ref.split("|", 1)
    escaped = PROBE.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    result = subprocess.run(
        ["osascript", "-e",
         f'tell application "Safari" to do JavaScript "{escaped}" '
         f"in tab {idx} of window id {wid}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("osascript error (is 'Allow JavaScript from Apple Events' enabled?):",
              result.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(json.loads(result.stdout), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
