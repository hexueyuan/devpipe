# Attach 按钮点击修复方案

## 子任务分解

| # | 子任务 | 模块 | 状态 |
|---|--------|------|------|
| 1 | 排查 attach 按钮事件和 AppleScript 调用链路 | app.py + static/js/ | 已完成 |
| 2 | 修复 iTerm2 tmux attach 命令参数 | devspace_service.py | 已完成 |

## 技术方案

排查 attach 按钮的完整调用链路：前端 JavaScript 点击事件 -> Flask API 端点 -> `devspace_service.py` 中的 AppleScript 调用。定位问题根因为 AppleScript 脚本向 iTerm2 发送的 tmux attach 命令参数拼接错误，导致 tmux 会话名称与实际创建的会话名称不匹配。

修复 `devspace_service.py` 中 iTerm2 tmux attach 命令的参数生成逻辑，确保 tmux session 名称与创建时使用的命名规则一致。同时修正 AppleScript 中窗口创建和命令发送的时序问题，避免命令在终端窗口就绪前发送导致丢失。

## 验收标准

1. 点击 attach 按钮正常触发 API 调用，无前端错误
2. iTerm2 正确打开新窗口并 attach 到对应的 tmux 会话
