#!/usr/bin/env python3
"""
grok_bridge.py v3.2 — Talk to Grok via Safari JS injection (macOS)

Uses AppleScript `do JavaScript` to inject JS into Safari, driving grok.com
without any API key, browser extension, or Accessibility permission.

v3.2: pins a dedicated grok.com tab (found by URL, created if missing) and
never activates Safari — the bridge works in a background tab while you use
other apps. /new is serialized with /chat (no more mid-chat navigation).
Code blocks in responses keep their ``` fences.

Usage:
  python3 grok_bridge.py --port 19998
  python3 grok_bridge.py --port 19998 --host 127.0.0.1 --token mysecret
"""
import json
import time
import threading
import re
import argparse
import subprocess
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote
from socketserver import ThreadingMixIn

GROK_URL = "https://grok.com"
DOMAIN = "grok.com"
VERSION = "v3.2"

# Multiple selectors for resilience against UI changes.
# contenteditable first: grok.com's composer is a Tiptap/ProseMirror div;
# the page also contains a bare <textarea> that silently ignores input.
INPUT_SELECTORS = [
    'div[contenteditable="true"]',
    "textarea",
    '[data-testid="text-input"]',
    '[role="textbox"]',
]
SEND_SELECTORS = [
    'button[aria-label="Submit"]',
    'button[aria-label="Send"]',
    'button[data-testid="send-button"]',
]

# AppleScript: find the first Safari tab whose URL contains DOMAIN
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

# AppleScript: create a DOMAIN tab in the background (no focus steal)
MAKE_TAB_SCRIPT = f'''
tell application "Safari"
    if (count of windows) is 0 then
        make new document with properties {{URL:"{GROK_URL}"}}
        return (id of front window as text) & "|1"
    else
        tell window 1 to make new tab at end of tabs with properties {{URL:"{GROK_URL}"}}
        return (id of window 1 as text) & "|" & ((count of tabs of window 1) as text)
    end if
end tell
'''

# JS helper: markdown container → text with ``` fences preserved for code blocks.
# Handles both direct <pre> children and wrapper divs whose header carries the
# language name and a Copy button (grok.com's "not-prose" blocks).
_JS_MD_HELPERS = r"""
    const fencePre = (pre, fallbackLang) => {
        const codeEl = pre.querySelector('code');
        const cls = codeEl ? (codeEl.className || '') : '';
        let lang = (cls.match(/language-([\w.+#-]+)/) || [null, ''])[1];
        if (!lang && fallbackLang) lang = fallbackLang;
        const body = (codeEl || pre).innerText.replace(/\n+$/, '');
        return '```' + lang + '\n' + body + '\n```';
    };
    const mdText = (m) => [...m.children].map(ch => {
        if (ch.tagName === 'PRE') return fencePre(ch, '');
        const pres = ch.querySelectorAll ? ch.querySelectorAll('pre') : [];
        if (pres.length === 1) {
            const head = (ch.innerText.split('\n')[0] || '').trim();
            const lang = /^[A-Za-z0-9+#.-]{1,20}$/.test(head) ? head.toLowerCase() : '';
            return fencePre(pres[0], lang);
        }
        return (ch.innerText || '').trim();
    }).filter(Boolean).join('\n\n');
"""

# JS: count assistant message containers on the page
JS_COUNT_MESSAGES = r"""
(()=>{
    const msgs = document.querySelectorAll(
        '[class*="message"]'
    );
    let count = 0;
    for (const m of msgs) {
        const role = m.getAttribute('data-role') ||
                     m.getAttribute('data-message-author-role') ||
                     m.className || '';
        if (/assistant|bot|grok|response/i.test(role) ||
            m.querySelector('[class*="markdown"]')) {
            count++;
        }
    }
    return String(count);
})()
""".strip()

# JS: extract the last assistant message's text content
JS_LAST_RESPONSE = ("(()=>{" + _JS_MD_HELPERS + r"""
    // Strategy 1: grok.com uses .response-content-markdown for assistant responses
    const responses = document.querySelectorAll('[class*="response-content-markdown"]');
    if (responses.length > 0) {
        return mdText(responses[responses.length - 1]);
    }
    // Strategy 2: message bubbles - take the last one (usually assistant)
    const bubbles = document.querySelectorAll('[class*="message-bubble"]');
    if (bubbles.length > 0) {
        return bubbles[bubbles.length - 1].innerText.trim();
    }
    // Strategy 3: general markdown/prose blocks
    const prose = document.querySelectorAll('[class*="markdown"], [class*="prose"]');
    if (prose.length > 0) {
        return prose[prose.length - 1].innerText.trim();
    }
    return '';
})()""")

# JS: check if Grok is still generating
# When idle: Submit button exists (disabled when input empty, enabled when has text)
# When generating: Submit button is replaced by a Stop button
# When done: Regenerate button appears, Submit button returns
JS_IS_GENERATING = r"""
(()=>{
    // If Regenerate button exists, generation is complete
    const regen = document.querySelector('button[aria-label="Regenerate"]');
    if (regen) return 'false';
    // If Stop/Cancel button exists, still generating
    const stop = document.querySelector(
        'button[aria-label="Stop"], button[aria-label="Cancel"], ' +
        'button[data-testid="stop-button"]'
    );
    if (stop) return 'true';
    // If Submit button is missing entirely (replaced by stop), still generating
    const submit = document.querySelector(
        'button[aria-label="Submit"], button[aria-label="Send"]'
    );
    if (!submit) return 'true';
    return 'false';
})()
""".strip()


class GrokBridge:
    def __init__(self):
        self.lock = threading.Lock()
        self.win_id = None
        self.tab_idx = None

    # ---------- low-level ----------

    def _osascript(self, script, timeout=30):
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(f"osascript error: {result.stderr.strip()[:300]}")
        return result.stdout.strip()

    def _resolve_tab(self, create=True):
        """Pin the first Safari tab on DOMAIN; optionally create one (in the
        background — Safari is never activated, the user's focus is not stolen)."""
        ref = self._osascript(FIND_TAB_SCRIPT)
        if not ref and create:
            ref = self._osascript(MAKE_TAB_SCRIPT)
            time.sleep(3)
        if ref and "|" in ref:
            wid, idx = ref.split("|", 1)
            self.win_id, self.tab_idx = int(wid), int(idx)
            return True
        self.win_id = self.tab_idx = None
        return False

    def _js(self, js_code, timeout=30):
        """Execute JavaScript in the pinned tab, re-resolving it once if stale."""
        escaped = js_code.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        for attempt in (0, 1):
            if self.win_id is None and not self._resolve_tab():
                raise RuntimeError(f"no {DOMAIN} tab found and could not create one")
            try:
                return self._osascript(
                    f'tell application "Safari" to do JavaScript "{escaped}" '
                    f"in tab {self.tab_idx} of window id {self.win_id}",
                    timeout=timeout,
                )
            except RuntimeError:
                if attempt == 1:
                    raise
                self.win_id = None  # tab moved/closed — re-resolve and retry

    def _tab_url(self):
        if self.win_id is None and not self._resolve_tab(create=False):
            return ""
        try:
            return self._osascript(
                f'tell application "Safari" to get URL of tab {self.tab_idx} '
                f"of window id {self.win_id}"
            )
        except RuntimeError:
            return ""

    def _set_tab_url(self, url):
        self._osascript(
            f'tell application "Safari" to set URL of tab {self.tab_idx} '
            f'of window id {self.win_id} to "{url}"'
        )

    def _ensure_grok(self):
        if not self._resolve_tab(create=True):
            raise RuntimeError(f"could not find or create a {DOMAIN} tab")

    def _find_input(self):
        """Find the input element using multiple selectors."""
        for selector in INPUT_SELECTORS:
            result = self._js(f"!!document.querySelector('{selector}')")
            if result == "true":
                return selector
        return None

    def _wait_ready(self, timeout=20):
        """Wait until the input element is available."""
        start = time.time()
        while time.time() - start < timeout:
            selector = self._find_input()
            if selector:
                return selector
            time.sleep(0.5)
        return None

    # ---------- composer ----------

    def _type_and_send(self, text, input_selector):
        """Type text via JS insertText and click Send button."""
        safe_text = (
            text.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "")
        )
        type_js = f"""(()=>{{
            const el = document.querySelector('{input_selector}');
            if (!el) return 'NO_ELEMENT';
            el.focus();
            if (el.tagName === 'TEXTAREA') {{ el.select(); }}
            else {{
                document.execCommand('selectAll', false, null);
                document.execCommand('delete', false, null);
            }}
            document.execCommand('insertText', false, '{safe_text}');
            const got = (el.value || el.innerText || '').trim();
            return got ? 'OK' : 'EMPTY';
        }})()"""
        result = self._js(type_js)
        if result == "EMPTY":
            # Hidden tabs occasionally reject execCommand — make the tab
            # visible within Safari (still no app focus steal) and retry.
            print("[bridge] hidden-tab typing failed, switching current tab", flush=True)
            self._osascript(
                f'tell application "Safari" to tell window id {self.win_id} '
                f"to set current tab to tab {self.tab_idx}"
            )
            time.sleep(0.5)
            result = self._js(type_js)
        if str(result) != "OK":
            return False

        time.sleep(0.5)

        # Try specific send button selectors
        for btn_selector in SEND_SELECTORS:
            r = self._js(
                f"(()=>{{const b=document.querySelector('{btn_selector}');"
                f"if(b&&!b.disabled){{b.click();return'OK'}};return'NO'}})()"
            )
            if "OK" in str(r):
                return True

        # Fallback: find button with Submit/Send text or aria-label
        r = self._js(
            "(()=>{"
            "const bs=[...document.querySelectorAll('button')];"
            "const b=bs.find(x=>/submit|send|发送/i.test(x.ariaLabel||x.textContent||''));"
            "if(b&&!b.disabled){b.click();return'OK'}return'NO'"
            "})()"
        )
        if "OK" in str(r):
            return True

        # Last resort: Enter key event
        self._js(
            f"document.querySelector('{input_selector}')"
            f"?.dispatchEvent(new KeyboardEvent('keydown',"
            f"{{key:'Enter',code:'Enter',keyCode:13,bubbles:true}}))"
        )
        return True

    # ---------- state ----------

    def _get_last_response(self):
        """Extract the last assistant message using DOM structure."""
        return self._js(JS_LAST_RESPONSE, timeout=15)

    def _get_body_text(self):
        """Fallback: get full page text."""
        return self._js("document.body.innerText", timeout=15)

    def _is_generating(self):
        """Check if Grok is still generating a response."""
        try:
            return self._js(JS_IS_GENERATING, timeout=10) == "true"
        except Exception:
            return False

    def _count_messages(self):
        """Count assistant messages on the page."""
        try:
            return int(self._js(JS_COUNT_MESSAGES, timeout=10))
        except (ValueError, RuntimeError):
            return -1

    def _clean_response(self, text):
        """Remove Grok UI artifacts from response text."""
        # Remove trailing UI elements
        for marker in [
            "\nAsk anything", "\nDeepSearch", "\nThink Harder", "\nThink\n",
            "\nAttach", "\nGrok", "\nFast\n", "\nAuto\n", "\nUpgrade to",
        ]:
            idx = text.rfind(marker)
            if idx > 0:
                text = text[:idx]
        # Remove timing indicators like "1.3s"
        text = re.sub(r"\n[0-9]+(\.[0-9]+)?s\n?", "\n", text)
        text = re.sub(r"\n[0-9]+(\.[0-9]+)?s$", "", text)
        # Remove action buttons text
        text = re.sub(
            r"\n(Share|Compare|Make it|Explain|Toggle|Like|Dislike).*", "", text
        )
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _extract_fallback(self, body, prompt):
        """Fallback extraction using prompt prefix as marker."""
        marker = prompt[:60]
        parts = body.split(marker)
        after = parts[-1] if len(parts) >= 2 else body
        return self._clean_response(after)

    # ---------- chat ----------

    def chat(self, prompt, timeout=120):
        with self.lock:
            return self._chat(prompt, timeout)

    def _chat(self, prompt, timeout):
        try:
            self._ensure_grok()
            input_sel = self._wait_ready()
            if not input_sel:
                return {"status": "error", "error": "input element not found"}

            msg_count_before = self._count_messages()
            response_before = self._get_last_response()
            if not self._type_and_send(prompt, input_sel):
                return {"status": "error", "error": "failed to send prompt"}

            # Poll for response completion
            start = time.time()
            last_response = ""
            stable_count = 0
            response_detected = False

            while time.time() - start < timeout:
                time.sleep(2)

                # Primary: DOM-based extraction (reliable, scoped to message)
                response = self._get_last_response()

                if response:
                    # Check if this is a NEW response (not from a previous turn)
                    new_count = self._count_messages()
                    if not response_detected:
                        if new_count > msg_count_before or msg_count_before < 0:
                            response_detected = True
                        elif response != response_before:
                            # Content changed from before send — new response
                            response_detected = True

                    if not response_detected:
                        continue

                    # Check completion: response stable + not generating
                    generating = self._is_generating()
                    if response == last_response and not generating:
                        stable_count += 1
                        if stable_count >= 2:
                            cleaned = self._clean_response(response)
                            return {
                                "status": "ok",
                                "response": cleaned,
                                "elapsed": round(time.time() - start, 1),
                            }
                    else:
                        stable_count = 0

                    last_response = response
                else:
                    # DOM selectors didn't match yet (page transitioning)
                    # Only use body-text fallback after waiting long enough
                    if time.time() - start > 20 and not response_detected:
                        body = self._get_body_text()
                        fallback = self._extract_fallback(body, prompt)
                        if fallback and len(fallback) > 10:
                            response_detected = True
                            last_response = fallback

            # Timeout — return whatever we have
            cleaned = self._clean_response(last_response) if last_response else ""
            return {
                "status": "timeout",
                "response": cleaned,
                "elapsed": round(time.time() - start, 1),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ---------- misc ----------

    def new_conversation(self):
        """Navigate the pinned tab to grok.com for a fresh conversation."""
        with self.lock:
            try:
                self._ensure_grok()
                self._set_tab_url(GROK_URL)
                if self._wait_ready(timeout=15):
                    return {"status": "ok"}
                return {"status": "error", "error": "input not ready after navigation"}
            except Exception as e:
                return {"status": "error", "error": str(e)}

    def history(self):
        try:
            if not self._resolve_tab(create=False):
                return {"status": "error", "error": f"no {DOMAIN} tab open"}
            body = self._get_body_text()
            return {
                "status": "ok",
                "content": self._clean_response(body),
                "raw_length": len(body),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def health(self):
        try:
            found = self._resolve_tab(create=False)
            url = self._tab_url() if found else ""
            return {
                "status": "ok",
                "tab_found": found,
                "url": url,
                "on_grok": DOMAIN in url,
                "input_available": self._find_input() is not None if found else False,
                "version": VERSION,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "version": VERSION}


bridge = None
auth_token = None


class RequestHandler(BaseHTTPRequestHandler):
    def _check_auth(self):
        if not auth_token:
            return True
        provided = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not provided:
            # Also check query param ?token=xxx
            if "?" in self.path:
                params = dict(
                    p.split("=", 1)
                    for p in self.path.split("?", 1)[1].split("&")
                    if "=" in p
                )
                provided = unquote(params.get("token", ""))
        if secrets.compare_digest(provided, auth_token):
            return True
        self._json_response(401, {"status": "error", "error": "unauthorized"})
        return False

    def do_POST(self):
        if not self._check_auth():
            return

        content_length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._json_response(400, {"status": "error", "error": "invalid JSON"})
            return

        path = self.path.split("?")[0]

        if path == "/chat":
            prompt = data.get("prompt", "").strip()
            if not prompt:
                self._json_response(
                    400, {"status": "error", "error": "prompt is required"}
                )
                return
            try:
                timeout = min(max(int(data.get("timeout", 120)), 10), 600)
            except (ValueError, TypeError):
                timeout = 120
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] >> {prompt[:80]}", flush=True)
            result = bridge.chat(prompt, timeout)
            self._json_response(200, result)
            resp_preview = str(
                result.get("response", result.get("error", ""))
            )[:80]
            print(f"[{ts}] << [{result.get('status')}] {resp_preview}", flush=True)

        elif path == "/new":
            result = bridge.new_conversation()
            self._json_response(200 if result["status"] == "ok" else 500, result)

        else:
            self._json_response(404, {"status": "error", "error": "not found"})

    def do_GET(self):
        if not self._check_auth():
            return

        path = self.path.split("?")[0]

        if path == "/health":
            self._json_response(200, bridge.health())
        elif path == "/history":
            result = bridge.history()
            self._json_response(200 if result["status"] == "ok" else 500, result)
        else:
            self._json_response(404, {"status": "error", "error": "not found"})

    def _json_response(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, *args):
        pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grok Bridge REST API")
    parser.add_argument("--port", type=int, default=19998)
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address (default: 127.0.0.1, use 0.0.0.0 for LAN)")
    parser.add_argument("--token", default="",
                        help="Bearer token for authentication (optional)")
    args = parser.parse_args()

    bridge = GrokBridge()
    auth_token = args.token or ""

    print(f"Grok Bridge {VERSION} on {args.host}:{args.port}", flush=True)
    if auth_token:
        print("Auth: token required", flush=True)
    else:
        print("Auth: none (add --token for security)", flush=True)
    print(
        "Requires: Safari > Develop > Allow JavaScript from Apple Events",
        flush=True,
    )

    ThreadedHTTPServer((args.host, args.port), RequestHandler).serve_forever()
