---
name: discuss
description: 探索新功能需求并形成需求文档（PRD）。仅适用于「新功能」类型开发。当用户说"讨论一下需求"、"聊聊需求"、"我想做一个新功能..."、"帮我分析需求"、"梳理需求"、"需求讨论"、"产品需求"时触发。Bugfix 和优化重构不走此阶段，直接进入 design。前提：需要先执行 devpipe:init 创建开发环境。
---

# 需求讨论（仅新功能）

通过协作对话将用户的新功能想法转化为清晰的需求文档（PRD）。聚焦于「做什么」和「为什么」，不涉及「怎么实现」。

<HARD-GATE>
## 适用范围

**本阶段仅适用于「新功能」类型**。如果 `dev_type` 为 Bugfix 或优化重构，**必须拒绝进入本阶段**并提示：
> "discuss 阶段仅适用于新功能开发。当前任务类型为 [dev_type]，应直接使用 `/devpipe:design` 进行方案设计。"

不要在需求文档获得用户确认前进行任何方案设计或任务拆分。设计相关内容（怎么实现、涉及哪些模块、技术方案）应在 design 阶段完成。
</HARD-GATE>

<HARD-GATE>
## 工作流顺序约束

devpipe 工作流根据 `dev_type` 走不同路径：
- **新功能**：`init → discuss → design → coding → review-and-fix → summarize`
- **Bugfix / 优化重构**：`init → design → coding → review-and-fix → summarize`（跳过 discuss）

- **本阶段（discuss）的前置条件**：
  - 必须已执行 `devpipe:init`（`.devpipe/state/context.json` 存在且完整）
  - `dev_type` 必须为「新功能」
- **本阶段（discuss）的唯一后继**：`devpipe:design`
- **禁止的行为**：
  - 禁止 Bugfix 或优化重构类型进入本阶段
  - 禁止在 discuss 完成后调用除 `devpipe:design` 之外的任何 devpipe skill
  - 禁止在 discuss 中讨论技术实现细节（应留给 design 阶段）
</HARD-GATE>

## 流程

你必须按顺序完成以下步骤：

### 步骤 1：前置校验 + 环境感知

**执行阶段准入检查：**

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/stage-gate.sh discuss
```

脚本自动完成 context.json 校验（dev_type、description、remote_branch、local_branch 非空）和阶段标记。**脚本会检查 dev_type 是否为「新功能」，非新功能类型会被拒绝。**

**检查后续阶段状态（使用 Glob 工具，仅检查文件是否存在）：**

- 如果 `.devpipe/state/prd.md` 已存在：询问用户是继续修改已有需求还是重新开始
- 如果 `.devpipe/state/coding-plan.md` 已存在：说明已进入设计阶段，提示用户使用 `/devpipe:design` 继续

**环境感知通过后，向用户确认：**
> "检测到开发上下文：[功能描述]（新功能），GitHub Issue: #[编号]，远程分支: [分支名]。开始讨论需求。"

### 步骤 2：探索项目上下文

- 检查相关代码文件、文档、最近的 commits
- 了解项目当前状态和已有功能
- 如果请求描述了多个独立子系统，先帮用户分解为子项目，然后针对第一个子项目进入正常需求讨论流程

### 步骤 3：需求探索

以 `.devpipe/state/context.json` 中的功能描述为起点展开讨论，不要求用户重复描述需求。

**卡片详情参考：**
如果 `github_issue_body` 非空，在讨论过程中主动参考其中的补充说明和要求。

**讨论要点（聚焦需求，不涉及实现）：**
- 功能背景：为什么需要这个功能？解决什么问题？
- 用户视角：用户如何使用这个功能？
- 功能边界：本次做什么？不做什么？
- 验收标准：如何判断功能做完了？

**讨论原则：**
- **一次只问一个问题** — 不要在同一条消息中提出多个问题
- **优先使用选择题** — 使用 `AskUserQuestion` 工具提供交互式选项
- **不要讨论技术实现** — "怎么实现"是 design 阶段的事

### 步骤 4：写需求文档

需求讨论清楚后，将需求保存到 `.devpipe/state/prd.md`，格式如下：

```markdown
# 需求文档 (PRD)

## 基本信息

- 开发类型: 新功能
- 功能描述: <功能描述>
- GitHub Issue: #<编号>
- 远程分支: <远程分支名>
- 本地分支: <本地分支名>
- 创建时间: <YYYY-MM-DD>

## 需求背景

[为什么需要这个功能？解决什么问题？]

## 功能描述

[从用户视角描述功能，用户如何使用？]

## 功能边界

### 本次包含
- [功能点 1]
- [功能点 2]

### 本次不包含
- [明确排除的功能点]

## 验收标准

1. [明确、可验证的标准 1]
2. [明确、可验证的标准 2]
```

> **注意**：PRD 不包含实现方案、涉及模块、架构设计、测试场景等技术内容，这些在 design 阶段补充。

### 步骤 5：需求文档审查

`.devpipe/state/prd.md` 写入后，派遣 spec-reviewer 子 agent 审查：

1. 使用 Agent 工具（subagent_type: "general-purpose"），按 [spec-reviewer-prompt.md](spec-reviewer-prompt.md) 中的模板构造 prompt，传入 `.devpipe/state/prd.md` 的文件路径
2. 如果审查发现问题：使用 Edit 工具修改 `.devpipe/state/prd.md`，然后重新派遣审查
3. 如果审查通过：进入用户确认

**审查次数限制**：最多 2 轮审查。超过限制则将问题提交给用户决定。

### 步骤 6：用户确认需求文档（硬性门禁）

<HARD-GATE>
需求文档写入后，**必须明确询问用户是否对需求文档没有问题**，**必须等到用户明确表示确认后才能进入下一阶段**。

> "需求文档已保存到 `.devpipe/state/prd.md`。请查看确认，如有修改意见可以继续讨论。确认无误后我将进入方案设计阶段。"

禁止的行为：
- 不要自行判断"需求已经足够清晰"然后直接进入下一阶段
- 不要把"用户没有提出反对意见"等同于"用户已确认"

必须的行为：
- 等待用户回复
- 只有用户明确给出肯定回复后，才进入步骤 7
- 如果用户提出修改意见，使用 Edit 工具修改 `.devpipe/state/prd.md`，然后再次请求确认
</HARD-GATE>

### 步骤 7：调用 design 阶段

用户确认后：

1. 标记阶段完成：

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/stage-complete.sh discuss
```

2. 宣告并调用 devpipe:design：
> "需求讨论完成，接下来使用 devpipe:design 制定实施方案。"

使用 `Skill` 工具调用 `devpipe:design`：
```
Skill 工具参数：
- skill: "devpipe:design"
```

**这是唯一合法的终止状态。**

## 关键原则

- **需求优先** — 只讨论「做什么」，不讨论「怎么做」
- **一次一个问题** — 不要用多个问题压倒用户
- **选择题优先** — 使用 `AskUserQuestion` 工具
- **YAGNI** — 从需求中移除不必要的功能
- **增量验证** — 呈现需求，获得确认后再继续
