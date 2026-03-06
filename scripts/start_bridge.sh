#!/bin/bash
# start_bridge.sh — 在 Mac 上启动 Grok Bridge 服务
# 通过 Node agent run 启动（确保有 GUI session 权限）
# 或通过 SSH 直接启动

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BRIDGE_SCRIPT="${SCRIPT_DIR}/grok_bridge.py"
PORT="${1:-19998}"

conf="${REMOTE_MAC_CONF:-$HOME/.remote-mac.conf}"
[ -f "$conf" ] && source "$conf"
MAC_SSH_HOST="${MAC_SSH_HOST:-mac.local}"
MAC_SSH_USER="${MAC_SSH_USER:-root}"
MAC_SSH_PORT="${MAC_SSH_PORT:-22}"

SSH_CMD="ssh -p ${MAC_SSH_PORT} -o ConnectTimeout=5 -o BatchMode=yes ${MAC_SSH_USER}@${MAC_SSH_HOST}"

echo "[grok-bridge] 传输 bridge 脚本到 Mac..."
cat "$BRIDGE_SCRIPT" | ${SSH_CMD} "cat > /tmp/grok_bridge.py"

echo "[grok-bridge] 检查是否已在运行..."
${SSH_CMD} "pgrep -f 'grok_bridge.py' && echo 'already running' && exit 0; \
    echo '启动 Grok Bridge on :${PORT}...'; \
    nohup python3 /tmp/grok_bridge.py --port ${PORT} > /tmp/grok_bridge.log 2>&1 &
    sleep 1; \
    pgrep -f 'grok_bridge.py' && echo 'started' || echo 'failed'"

echo "[grok-bridge] 验证..."
sleep 2
curl -s -m 5 "http://${MAC_SSH_HOST}:${PORT}/health" 2>/dev/null && echo " ✅ Grok Bridge 已启动" || echo " ⚠️ 启动可能需要更多时间"
