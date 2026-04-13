# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

**devpipe** 是一个 Claude Code 插件，实现了 Agentic SDLC 工作流。通过一系列 Claude Code Skills 串联，编排从需求讨论到编码、评审和总结的完整开发流程。

工作流阶段（新功能）：`init → discuss → design → coding → review-and-fix → summarize`
Bugfix/重构工作流跳过 `discuss` 阶段。

## 架构

- **插件入口：** `.claude-plugin/marketplace.json` 定义插件及 session-start hook
- **调度器：** `skills/using-devpipe/SKILL.md` — 将用户请求路由到对应的阶段 skill
- **会话钩子：** `hooks/session-start` 在每次会话启动时注入调度器 skill
- **阶段门控脚本：** `scripts/stage-gate.sh`（校验前置条件）和 `scripts/stage-complete.sh`（标记完成并记录时间戳）控制阶段流转
- **状态持久化：** `.devpipe/context.json` 记录 `stage`、`stage_completed`、`dev_type`、分支信息和时间戳。其他产物：`prd.md`、`coding-plan.md`、`task-progress.md`、`review-status.md`、`summary.md`
- **子 Agent 模式：** Skill 通过 Markdown 提示词模板编排子 Agent（如 `coding-agent-prompt.md`、`reviewer-agent-prompt.md`、`fixer-agent-prompt.md`），使用 `[PLACEHOLDER]` 语法做变量替换
- **数据交换：** `code-reviewer` 和 `code-fixer` 通过结构化的 Fix Plan JSON Schema 通信（定义在 `references/fix-plan-schema.md`）
- **Dashboard：** Flask Web 应用（`dashboard/src/app.py`），端口 5001/5051，用于监控 worktree 开发分支和工作流阶段状态，通过 `dashboard/sbin/dashboard-ctl.sh` 管理生命周期
- **Docker 开发环境：** `init` skill 创建基于 RockyLinux 9 的隔离容器，使用 git worktree 做分支隔离，tmux 双面板布局（shell + Claude Code）

## 运行 Dashboard

```bash
pip install -r dashboard/requirements.txt

dashboard/sbin/dashboard-ctl.sh start
dashboard/sbin/dashboard-ctl.sh stop
dashboard/sbin/dashboard-ctl.sh restart
dashboard/sbin/dashboard-ctl.sh logs
```

## 构建 Docker 镜像

```bash
docker build -t devpipe/devspace:latest resources/
```

## Git 规范

- **每条 git 命令必须作为独立的 Bash 调用执行**，禁止用 `&&` 链接
- **Commit message 格式：** `#<Issue编号> Short English description.`（单行、英文、句末加句号）
- **分支命名：** `feature/<name>`、`fix/<name>`、`refactor/<name>` — kebab-case，3-4 个词
- **禁止提交 `.devpipe/`** 状态文件，禁止使用 `git add .` 或 `git add -A`
- 多提交 PR 工作流：每个有意义的改动是一个独立 commit

## 关键约定

- 文档和用户可见文本使用**简体中文**；skill 名称和 commit message 使用英文
- Skill 定义在 `skills/<name>/SKILL.md`，包含 YAML frontmatter（`name`、`description`）
- 子 Agent 提示词模板使用 `---` 分隔符包裹实际提示词内容
- 本项目无构建系统、测试套件或 lint 配置 — 由 Bash 脚本、Python（dashboard）和 Markdown（skills/prompts）组成
- 自举开发（Dogfooding）：用 devpipe 开发 devpipe 自身时，仅 `dashboard/` 下的代码通过 devpipe 工作流迭代，其他部分（skills、scripts、hooks、插件配置等）手动开发，不走 devpipe 工作流
