#!/usr/bin/env python3
"""
Grok Bridge — Safari SuperGrok 网页自动化 REST API
在 Mac 上运行，通过 CDP (Chrome DevTools Protocol) 控制 Safari 中的 grok.com

启动: python3 grok_bridge.py [--port 19998]
调用: curl -X POST http://localhost:19998/chat -d '{"prompt":"hello","mode":"auto"}'
"""

import json
import sys
import os
import time
import subprocess
import re
import argparse
import threading
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.error import URLError

# --- Safari CDP ---

def get_safari_cdp_targets():
    """获取 Safari 的 CDP targets (需要 Safari Technology Preview 或开启 Remote Automation)"""
    # Safari 不原生支持 CDP，我们用 Peekaboo + osascript 替代
    return None

def run_safari_js(js_code, timeout=30):
    """通过 osascript 在 Safari 当前标签页执行 JS"""
    # 转义单引号
    escaped = js_code.replace("\\", "\\\\").replace('"', '\\"').replace("'", "'\\''")
    cmd = f'''osascript -e 'tell application "Safari" to do JavaScript "{escaped}" in current tab of front window' '''
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return None, result.stderr.strip()
        return result.stdout.strip(), None
    except subprocess.TimeoutExpired:
        return None, "timeout"

def ensure_grok_page():
    """确保 Safari 当前页面是 grok.com"""
    url_js = "document.location.href"
    url, err = run_safari_js(url_js)
    if err:
        return False, f"无法获取 Safari URL: {err}"
    if url and "grok.com" in url:
        return True, url
    # 尝试导航到 grok.com
    nav_js = "document.location.href = 'https://grok.com'; 'navigating'"
    run_safari_js(nav_js)
    time.sleep(3)
    url, _ = run_safari_js(url_js)
    if url and "grok.com" in url:
        return True, url
    return False, f"当前页面不是 grok.com: {url}"

def new_conversation():
    """开始新对话（点击 + 按钮或导航到 grok.com）"""
    # 方法1: 直接导航
    run_safari_js("document.location.href = 'https://grok.com'; 'ok'")
    time.sleep(2)
    return True

def set_mode(mode="auto"):
    """设置 Grok 响应模式"""
    if mode == "auto":
        return True
    # 点击模式选择按钮 — 需要根据实际 DOM 调整
    # SuperGrok 的模式选择器通常在输入框附近
    mode_map = {"fast": "Fast", "expert": "Expert", "heavy": "Heavy", "auto": "Auto"}
    target = mode_map.get(mode, "Auto")
    
    # 尝试用 Peekaboo 点击
    try:
        subprocess.run(
            ["peekaboo", "see", "--app", "Safari", "--json"],
            capture_output=True, text=True, timeout=10
        )
        # 简化：直接用 JS 找模式按钮
        js = f'''
        (function() {{
            var btns = document.querySelectorAll('button, [role="option"], [role="menuitem"]');
            for (var b of btns) {{
                if (b.textContent.trim() === '{target}') {{
                    b.click();
                    return 'clicked ' + '{target}';
                }}
            }}
            return 'not found';
        }})()
        '''
        result, err = run_safari_js(js)
        return result and "clicked" in result
    except Exception:
        return False

def send_prompt(prompt, mode="auto", timeout=120):
    """发送 prompt 并等待回复"""
    
    # 1. 确保在 grok.com
    ok, info = ensure_grok_page()
    if not ok:
        return None, info
    
    # 2. 新建对话（避免上下文污染）
    new_conversation()
    time.sleep(1)
    
    # 3. 设置模式
    if mode != "auto":
        set_mode(mode)
        time.sleep(0.5)
    
    # 4. 找到输入框并填入 prompt
    # SuperGrok 用 contenteditable div 或 textarea
    escaped_prompt = prompt.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace('"', '\\"')
    
    # 尝试多种输入方式
    input_js = f'''
    (function() {{
        // 方法1: textarea
        var ta = document.querySelector('textarea');
        if (ta) {{
            var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            nativeSetter.call(ta, '{escaped_prompt}');
            ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
            return 'textarea';
        }}
        // 方法2: contenteditable
        var ce = document.querySelector('[contenteditable="true"]');
        if (ce) {{
            ce.textContent = '{escaped_prompt}';
            ce.dispatchEvent(new Event('input', {{ bubbles: true }}));
            return 'contenteditable';
        }}
        // 方法3: input
        var inp = document.querySelector('input[type="text"]');
        if (inp) {{
            var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeSetter.call(inp, '{escaped_prompt}');
            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
            return 'input';
        }}
        return 'no_input_found';
    }})()
    '''
    
    result, err = run_safari_js(input_js)
    if err or result == "no_input_found":
        # Fallback: 用 Peekaboo 输入
        return _send_via_peekaboo(prompt, timeout)
    
    time.sleep(0.3)
    
    # 5. 点击发送按钮
    send_js = '''
    (function() {
        // 找发送按钮 (通常是 SVG arrow 或 submit button)
        var btns = document.querySelectorAll('button[type="submit"], button[aria-label*="send"], button[aria-label*="Send"]');
        if (btns.length > 0) {
            btns[btns.length - 1].click();
            return 'clicked';
        }
        // 尝试 Enter 键
        var ta = document.querySelector('textarea') || document.querySelector('[contenteditable="true"]');
        if (ta) {
            ta.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', bubbles: true}));
            return 'enter';
        }
        return 'no_send_button';
    })()
    '''
    result, err = run_safari_js(send_js)
    if result == "no_send_button":
        return _send_via_peekaboo(prompt, timeout)
    
    # 6. 等待回复完成
    return _wait_for_response(timeout)

def _send_via_peekaboo(prompt, timeout):
    """Fallback: 用 Peekaboo 原生输入"""
    try:
        # 激活 Safari
        subprocess.run(["osascript", "-e", 'tell application "Safari" to activate'], timeout=5)
        time.sleep(0.5)
        
        # 用 pbcopy + Cmd+V 输入（支持中文）
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(prompt.encode("utf-8"))
        
        # 点击输入框 (用 Peekaboo 找)
        see_result = subprocess.run(
            ["peekaboo", "see", "--app", "Safari", "--json"],
            capture_output=True, text=True, timeout=10
        )
        if see_result.returncode == 0:
            elements = json.loads(see_result.stdout) if see_result.stdout else []
            # 找 textarea 或 text field
            for elem in (elements if isinstance(elements, list) else []):
                role = elem.get("role", "")
                if role in ("AXTextArea", "AXTextField", "textarea"):
                    elem_id = elem.get("id", "")
                    if elem_id:
                        subprocess.run(["peekaboo", "click", "--on", elem_id], timeout=5)
                        time.sleep(0.3)
                        break
        
        # Cmd+A 全选 + Cmd+V 粘贴
        subprocess.run(["peekaboo", "hotkey", "--keys", "cmd,a"], timeout=5)
        time.sleep(0.1)
        subprocess.run(["peekaboo", "hotkey", "--keys", "cmd,v"], timeout=5)
        time.sleep(0.3)
        
        # Enter 发送
        subprocess.run(["peekaboo", "press", "--key", "return"], timeout=5)
        
        return _wait_for_response(timeout)
    except Exception as e:
        return None, f"Peekaboo fallback 失败: {e}"

def _wait_for_response(timeout=120):
    """等待 Grok 回复完成"""
    start = time.time()
    last_text = ""
    stable_count = 0
    
    while time.time() - start < timeout:
        time.sleep(2)
        
        # 提取最后一条回复
        extract_js = '''
        (function() {
            // Grok 回复通常在 message containers 中
            var msgs = document.querySelectorAll('[class*="message"], [class*="response"], [data-testid*="message"], article, [class*="markdown"]');
            if (msgs.length === 0) {
                // 更宽泛的选择器
                msgs = document.querySelectorAll('.prose, [class*="chat"] [class*="content"]');
            }
            if (msgs.length === 0) return JSON.stringify({"status": "no_messages"});
            
            var last = msgs[msgs.length - 1];
            var text = last.innerText || last.textContent || "";
            
            // 检查是否还在生成（找 loading/thinking 指示器）
            var loading = document.querySelector('[class*="loading"], [class*="typing"], [class*="generating"], [class*="spinner"]');
            var isLoading = loading !== null;
            
            // 也检查 stop 按钮的存在（表示还在生成）
            var stopBtn = document.querySelector('button[aria-label*="stop"], button[aria-label*="Stop"]');
            if (stopBtn) isLoading = true;
            
            return JSON.stringify({
                "status": isLoading ? "generating" : "done",
                "text": text.substring(0, 50000),
                "msg_count": msgs.length
            });
        })()
        '''
        
        result, err = run_safari_js(extract_js, timeout=10)
        if err:
            continue
        
        try:
            data = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            continue
        
        if data.get("status") == "no_messages":
            continue
        
        current_text = data.get("text", "")
        
        if data.get("status") == "done" and current_text:
            return current_text, None
        
        # 文本稳定检测（连续 3 次相同 = 完成）
        if current_text and current_text == last_text:
            stable_count += 1
            if stable_count >= 3:
                return current_text, None
        else:
            stable_count = 0
            last_text = current_text
    
    # 超时但有部分文本
    if last_text:
        return last_text, "timeout (partial response)"
    return None, "timeout"

# --- HTTP Server ---

class GrokHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok", "service": "grok-bridge"})
        elif self.path == "/modes":
            self._respond(200, {"modes": ["auto", "fast", "expert", "heavy"]})
        else:
            self._respond(404, {"error": "not found"})
    
    def do_POST(self):
        if self.path == "/chat":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                prompt = body.get("prompt", "")
                mode = body.get("mode", "auto")
                timeout = body.get("timeout", 120)
                
                if not prompt:
                    self._respond(400, {"error": "prompt required"})
                    return
                
                text, err = send_prompt(prompt, mode=mode, timeout=timeout)
                if text:
                    self._respond(200, {
                        "status": "ok",
                        "response": text,
                        "warning": err  # e.g. "timeout (partial response)"
                    })
                else:
                    self._respond(500, {"status": "error", "error": err})
            except Exception as e:
                self._respond(500, {"status": "error", "error": str(e), "trace": traceback.format_exc()})
        elif self.path == "/new":
            new_conversation()
            self._respond(200, {"status": "ok"})
        else:
            self._respond(404, {"error": "not found"})
    
    def _respond(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
    
    def log_message(self, format, *args):
        sys.stderr.write(f"[grok-bridge] {args[0]}\n")

def main():
    parser = argparse.ArgumentParser(description="Grok Bridge — Safari SuperGrok REST API")
    parser.add_argument("--port", type=int, default=19998, help="HTTP 端口 (默认 19998)")
    args = parser.parse_args()
    
    print(f"[grok-bridge] 启动在 :{args.port}")
    print(f"[grok-bridge] POST /chat {{\"prompt\":\"...\",\"mode\":\"auto\"}}")
    print(f"[grok-bridge] GET  /health")
    
    server = HTTPServer(("0.0.0.0", args.port), GrokHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[grok-bridge] 停止")
        server.shutdown()

if __name__ == "__main__":
    main()
