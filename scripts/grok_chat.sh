#!/bin/bash
# grok_chat.sh — 从 VPS 远程调用 Mac Safari 上的 SuperGrok
# 用法: bash grok_chat.sh "你的问题" [--mode auto|fast|expert|heavy]
#
# 两种模式：
#   1. Bridge 服务在线 → 直接 HTTP 调用（快）
#   2. Bridge 不在线 → SSH 直接执行（慢但无需预启动）

set -euo pipefail

PROMPT="${1:?用法: grok_chat.sh '你的问题' [--mode auto|fast|expert|heavy]}"
MODE="auto"
shift || true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode) MODE="$2"; shift 2 ;;
        --beta) BETA=1; shift ;;
        *) shift ;;
    esac
done

# --- Config ---
conf="${REMOTE_MAC_CONF:-$HOME/.remote-mac.conf}"
[ -f "$conf" ] && source "$conf"
MAC_SSH_HOST="${MAC_SSH_HOST:-mac.local}"
MAC_SSH_USER="${MAC_SSH_USER:-root}"
MAC_SSH_PORT="${MAC_SSH_PORT:-22}"
MAC_IP="${MAC_SSH_HOST}"
BRIDGE_PORT=19998

SSH_CMD="ssh -p ${MAC_SSH_PORT} -o ConnectTimeout=5 -o BatchMode=yes ${MAC_SSH_USER}@${MAC_SSH_HOST}"

# --- 检测 Bridge 是否在线 ---
check_bridge() {
    curl -s -m 3 "http://${MAC_IP}:${BRIDGE_PORT}/health" 2>/dev/null | grep -q '"ok"'
}

# --- 方式1: 通过 Bridge HTTP API ---
call_bridge() {
    local payload
    payload=$(python3 -c "import json; print(json.dumps({'prompt': '''${PROMPT}''', 'mode': '${MODE}', 'timeout': 120}))")
    
    response=$(curl -s -m 180 -X POST "http://${MAC_IP}:${BRIDGE_PORT}/chat" \
        -H 'Content-Type: application/json' \
        -d "$payload" 2>&1)
    
    # 提取 response 文本
    echo "$response" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if d.get('status') == 'ok':
        print(d.get('response', ''))
        if d.get('warning'):
            print(f'\\n[warning: {d[\"warning\"]}]', file=sys.stderr)
    else:
        print(f'Error: {d.get(\"error\", \"unknown\")}', file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f'Parse error: {e}', file=sys.stderr)
    print(sys.stdin.read(), file=sys.stderr)
    sys.exit(1)
"
}

# --- 方式2: SSH 直接执行 ---
call_ssh() {
    # 转义 prompt 用于 Python
    local escaped_prompt
    escaped_prompt=$(python3 -c "import json; print(json.dumps('${PROMPT}'))")
    
    ${SSH_CMD} "python3 - <<'PYEOF'
import subprocess, json, time, sys

prompt = ${escaped_prompt}
mode = '${MODE}'

def run_js(js):
    escaped = js.replace('\\\\', '\\\\\\\\').replace('\"', '\\\\\"')
    cmd = f'osascript -e \\'tell application \"Safari\" to do JavaScript \"{escaped}\" in current tab of front window\\''
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else None

# 确保在 grok.com
url = run_js('document.location.href')
if not url or 'grok.com' not in url:
    run_js(\"document.location.href = 'https://grok.com'\")
    time.sleep(3)

# 新建对话
run_js(\"document.location.href = 'https://grok.com'\")
time.sleep(2)

# 用 pbcopy + Cmd+V 输入
import subprocess as sp
proc = sp.Popen(['pbcopy'], stdin=sp.PIPE)
proc.communicate(prompt.encode('utf-8'))

sp.run(['osascript', '-e', 'tell application \"Safari\" to activate'], timeout=5)
time.sleep(0.3)

# Peekaboo: 点击输入框 + 粘贴 + 发送
sp.run(['peekaboo', 'hotkey', '--keys', 'cmd,a'], timeout=5)
time.sleep(0.1)
sp.run(['peekaboo', 'hotkey', '--keys', 'cmd,v'], timeout=5)
time.sleep(0.3)
sp.run(['peekaboo', 'press', '--key', 'return'], timeout=5)

# 等待回复
start = time.time()
last_text = ''
stable = 0

while time.time() - start < 120:
    time.sleep(2)
    r = run_js('''
    (function(){
        var m=document.querySelectorAll('[class*=\"message\"],article,[class*=\"markdown\"],.prose');
        if(!m.length)return JSON.stringify({s:\"wait\"});
        var t=m[m.length-1].innerText||'';
        var l=document.querySelector('[class*=\"loading\"],[class*=\"spinner\"]');
        var st=document.querySelector('button[aria-label*=\"stop\"],button[aria-label*=\"Stop\"]');
        return JSON.stringify({s:l||st?\"gen\":\"done\",t:t.substring(0,50000)});
    })()
    ''')
    if not r: continue
    try:
        d = json.loads(r)
    except: continue
    
    if d.get('s') == 'done' and d.get('t'):
        print(d['t'])
        sys.exit(0)
    
    txt = d.get('t', '')
    if txt and txt == last_text:
        stable += 1
        if stable >= 3:
            print(txt)
            sys.exit(0)
    else:
        stable = 0
        last_text = txt

if last_text:
    print(last_text)
else:
    print('Error: timeout', file=sys.stderr)
    sys.exit(1)
PYEOF"
}

# --- Main ---
echo "[grok] 模式: ${MODE}" >&2

if check_bridge; then
    echo "[grok] Bridge 在线，使用 HTTP API" >&2
    call_bridge
else
    echo "[grok] Bridge 离线，使用 SSH 直连" >&2
    call_ssh
fi
