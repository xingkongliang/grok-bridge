---
name: grok-bridge
description: 通过 Safari SuperGrok 网页获得免费 Grok 4 访问（CDP + Peekaboo 自动化）
---

# Grok Bridge

通过 Mac Safari 上已登录的 SuperGrok 网页，将 Grok 变成 REST API。
原理：VPS → SSH → Mac → Safari CDP/Peekaboo → SuperGrok 网页交互。

## 用法

### 一问一答（Bridge 模式）
```bash
bash skills/our/grok-bridge/scripts/grok_chat.sh "你的问题"
# 或指定模式
bash skills/our/grok-bridge/scripts/grok_chat.sh "你的问题" --mode expert
```

### HTTP API（需先启动服务）
```bash
# 在 Mac 上启动 Bridge 服务
bash skills/our/grok-bridge/scripts/start_bridge.sh

# 调用
curl -s -X POST http://100.92.28.97:19998/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"你的问题","mode":"auto"}'
```

## 参数
- `--mode auto|fast|expert|heavy`：Grok 响应模式（默认 auto）
- `--beta`：启用 Grok 4.20 Beta

## 前提
- Mac 在线，Safari 已打开 grok.com 且已登录 SuperGrok
- Safari 开发者工具已启用（Safari → 设置 → 高级 → 显示"开发"菜单）
- Safari WebDriver/CDP 或 Peekaboo 可用

## 架构
```
VPS (小灵)
  → SSH → Mac
    → Safari CDP (localhost:端口) → grok.com 页面
    → 注入 JS: 填写输入框 → 点击发送 → 等待回复 → 提取文本
    → 返回结果
```

## 模式说明
| 模式 | 用途 | 速度 |
|------|------|------|
| auto | 自动选择 | 中 |
| fast | 简单问答 | 快 |
| expert | 深度分析 | 慢 |
| heavy | 最强推理 | 最慢 |

## 限制
- 依赖 Safari 登录态（SuperGrok 订阅）
- 不支持并发（单标签页）
- 网页 DOM 可能随版本更新变化
