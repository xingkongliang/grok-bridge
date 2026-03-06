# grok-bridge v3.0

Talk to Grok via Safari automation — CLI tool + REST API.

## 架构
- Safari AppleScript `do JavaScript` = CDP Runtime.evaluate
- `document.execCommand('insertText')` = 输入（绕过 React 受控组件）
- JS `button.click()` = 提交（不依赖 System Events 权限）
- **不需要辅助功能权限**

## 用法

### REST API 模式（推荐）
```bash
# 在 Mac 上启动服务
python3 scripts/grok_bridge.py --port 19998

# 远程调用
curl -X POST http://100.92.28.97:19998/chat \
  -d '{"prompt":"你好","timeout":120}'

# 其他端点
GET  /health   — 健康检查
GET  /history  — 读取当前页面对话
POST /new      — 新建对话
POST /chat     — 发送问题
```

### CLI 模式（旧版 bash，备用）
```bash
MAC_SSH="ssh user@mac" bash scripts/grok_chat.sh "your question"
```

## 前置条件
1. Safari > 设置 > 高级 > 显示"网页开发者"功能 ✓
2. Safari > 开发 > 允许来自 Apple Events 的 JavaScript ✓
3. Safari 已登录 grok.com（SuperGrok 推荐）

## 文件
- `scripts/grok_bridge.py` — REST API 服务（v1, by AG Opus）
- `scripts/grok_chat.sh` — CLI 工具（v3, bash + CGEvent）

## 设计决策（AG Opus 的判断）
> Safari 不支持标准 Chrome DevTools Protocol。macOS 上控制 Safari 最可靠的方式是 AppleScript + JavaScript 注入。
