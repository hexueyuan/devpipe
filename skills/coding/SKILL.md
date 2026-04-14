---
name: coding
description: 按照开发计划执行编码、测试和提交。当用户想写代码、继续开发、恢复之前的开发进度时使用。即使用户说"coding 吧"、"继续开发"、"接着做"、"从上次继续"、"恢复开发"、"接着写代码"、"继续上次的任务"、"开始编码"、"执行计划"也应触发。前提：需要 .devpipe/state/coding-plan.md（由 devpipe:design 产出）。严格工作流顺序：devpipe:coding 只能在 devpipe:design 完成后调用。
---

# 执行开发计划

按 `.devpipe/state/coding-plan.md` 中的计划，逐任务执行编码和测试。所有开发类型（新功能、Bugfix、优化重构）统一走子任务模式。

<HARD-GATE>
## 工作流顺序约束

devpipe 工作流根据 `dev_type` 走不同路径：
- **新功能**：`init → discuss → design → coding → review-and-fix → summarize`
- **Bugfix / 优化重构**：`init → design → coding → review-and-fix → summarize`（跳过 discuss）

- **本阶段（coding）的前置条件**：必须已执行 `devpipe:design`（`.devpipe/state/coding-plan.md` 存在且完整）
- **本阶段（coding）的后继**：`devpipe:review-and-fix`（自动调用）
- **禁止的行为**：
  - 禁止在 `.devpipe/state/coding-plan.md` 不存在时开始编码
  - 禁止跳过 design 阶段直接调用本 skill
</HARD-GATE>

**宣告：** "我正在使用 devpipe:coding 执行开发计划。"

**核心设计**：每个子任务在独立的 Agent 上下文中执行，主对话只负责编排。

---

## 步骤 1：前置校验

### 1.1 执行阶段准入检查

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/stage-gate.sh coding
```

脚本自动完成 context.json 校验（必需字段非空）、依赖文件检查（coding-plan.md 必须存在）和阶段标记。

### 1.2 校验 coding-plan.md

读取 `.devpipe/state/coding-plan.md`，验证以下章节存在且有实质内容：
- 基本信息、需求/问题概述、技术方案、涉及模块、子任务列表、子任务 Agent 执行方式、提交方式
- 章节缺失 → **立即终止**："`.devpipe/state/coding-plan.md` 不完整，建议重新执行 `/devpipe:design`。"

### 1.3 进度恢复

读取 `.devpipe/state/task-progress.md` 中的子任务进度表：
- 使用 `TaskCreate` 重建任务列表，将已完成的子任务标记为 completed
- 找到标记为"当前"的子任务，从该任务继续执行
- 向用户确认是否继续（上下文清空后直接继续执行，无需确认）

---

## 步骤 2：子任务执行

按 TaskList 中的任务顺序，串行执行每个子任务。

### 对每个子任务：

#### 2.1 启动 Agent

从 `.devpipe/state/coding-plan.md` 获取 Agent Prompt 构造方式，读取 `plugins/devpipe/skills/coding/references/coding-agent-prompt.md` 模板，按 coding-plan.md 中的替换规则构造 prompt，启动 general-purpose Agent：

```
Agent 工具参数：
- subagent_type: "general-purpose"
- prompt: （按 .devpipe/state/coding-plan.md 中"Agent Prompt 必须包含以下要素"构造）
- description: "开发子任务: <子任务简述>"
```

等待 Agent 完成，不要在后台运行——串行执行更可控，避免并行引入的文件冲突和进度管理复杂性。

#### 2.2 检查 Agent 结果

Agent 返回后检查：
- **成功**（测试通过、覆盖率达标）：进入更新进度步骤
- **部分完成**（代码写完但测试未通过等）：在主对话中处理剩余问题，或重新启动 Agent
- **失败**：分析原因，与用户讨论后决定下一步

#### 2.3 更新进度

子任务完成后更新 `.devpipe/state/task-progress.md`：
- 将当前子任务标记为"已完成"
- 将下一个子任务标记为"当前"
- **如果 Agent 返回的结果中提到遇到问题并解决，将问题追加到"问题与解决方案记录"章节**

使用 `TaskUpdate` 将完成的子任务标记为 completed。

---

## 步骤 3：整合阶段

所有子任务完成后执行整合。

### 3.1 全量单测 + 增量覆盖率

执行全量验证（根据项目构建系统自动检测测试命令），确认各模块间没有冲突。

- 如果测试失败或覆盖率不达标，修复问题后重新验证

### 3.2 Git commit（不 push）

按 [Git 命令参考](../../references/git_commands.md) 中的规则执行提交。GitHub Issue 编号和远程分支从 `.devpipe/state/coding-plan.md` 获取。

```bash
git add <源代码和测试文件列表>
```

```bash
git commit -m "#<Issue编号> Short English description."
```

**注意：不执行 git push。** 推送在 review-and-fix 阶段完成。

### 3.3 更新 stage 并调用 review-and-fix

1. 标记阶段完成并预设下一阶段：

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/stage-complete.sh coding --next-stage review-and-fix
```

2. 宣告并调用 devpipe:review-and-fix：
   > "coding 阶段完成，代码已 commit。接下来使用 devpipe:review-and-fix 执行代码评审和推送。"

```
Skill 工具参数：
- skill: "devpipe:review-and-fix"
```

---

## 进度持久化

`.devpipe/state/task-progress.md` 是**唯一的恢复依据**——不依赖对话历史，不依赖 SKILL.md 是否在上下文中。

### 保存时机

| 节点 | 触发时机 |
|------|----------|
| 每个子任务完成后 | 更新进度表 |
| 所有子任务完成 + commit 后 | 记录整合完成状态 |

### 对话恢复

当新对话开始、上下文被清空、或对话从压缩上下文恢复时：

1. 读取当前目录下的 `.devpipe/state/coding-plan.md` 和 `.devpipe/state/task-progress.md`
2. 如果存在，从 `coding-plan.md` 读取**子任务 Agent 执行方式**，从 `task-progress.md` 读取**子任务进度**
3. 向用户确认是否继续（上下文清空后直接继续执行，无需确认）
4. 使用 `TaskCreate` 重建任务列表，将已完成的子任务标记为 completed
5. 按进度表中标记"当前"的子任务，读取 `coding-agent-prompt.md` 模板并按替换规则构造 Prompt 继续执行
6. 如果所有子任务已完成但未 commit，从整合阶段继续
7. 如果用户说不继续，删除进度文件

---

## 异常处理

| 情况 | 处理方式 |
|------|----------|
| Agent 执行成功 | 检查返回摘要，确认无异常后更新进度 |
| Agent 部分完成（如测试未通过） | 在主对话中补充处理，或重新启动 Agent |
| Agent 超时或异常退出 | 检查 git status 查看已完成的文件改动，在主对话中继续剩余步骤 |
| 全量测试失败 | 定位失败模块，修复后重新提交 |
| 用户中途取消 | 进度已保存在 `.devpipe/state/task-progress.md`，下次可恢复 |
| 上下文被清空 | 读取 `.devpipe/state/coding-plan.md` 和 `.devpipe/state/task-progress.md`，按其中的 Agent 执行方式继续 |
| 新对话继续开发 | 读取 `.devpipe/state/coding-plan.md` 和 `.devpipe/state/task-progress.md`，确认后从"当前"子任务继续 |

## 关键依赖

| 依赖 | 用途 | 使用位置 |
|------|------|----------|
| Agent 工具 (general-purpose) | 执行子任务的独立上下文 | 步骤 2 主编排 |
| `coding-agent-prompt.md` | 子任务 Agent Prompt 模板 | 步骤 2 构造 prompt |
| Skill (devpipe:review-and-fix) | 代码评审和推送（自动调用） | 整合步骤 3 |

## 参考文档

- [Coding Agent Prompt 模板](references/coding-agent-prompt.md) — 子任务 Agent 的标准 Prompt 模板和占位符说明
- [Git 命令参考](../../references/git_commands.md) — GitHub 项目的 git 推送和提交操作
- [GitHub Issue 使用指南](../../references/github_issue_guide.md) — commit message 中的 Issue 关联规范

