---
name: design
description: 制定技术方案和实施计划。支持两种入口：新功能从 discuss 进入（读取 prd.md），Bugfix/优化重构从 init 直接进入（以卡片详情为输入）。当用户说"制定计划"、"拆分任务"、"写个计划"、"怎么实现"、"设计方案"也应触发。严格工作流顺序：devpipe:design 完成后只能调用 devpipe:coding。
---

# 方案设计

制定详细的技术方案和实施计划。本阶段是所有开发类型（新功能、Bugfix、优化重构）的必经阶段，聚焦于「怎么实现」。

<HARD-GATE>
## 工作流顺序约束

devpipe 工作流根据 `dev_type` 走不同路径：
- **新功能**：`init → discuss → design → coding → review-and-fix → summarize`
- **Bugfix / 优化重构**：`init → design → coding → review-and-fix → summarize`（跳过 discuss）

- **本阶段（design）的入口**：
  - 新功能：从 `devpipe:discuss` 进入，读取 `.devpipe/prd.md` 作为需求输入
  - Bugfix/优化重构：从 `devpipe:init` 直接进入，以 `context.json` 的 github_issue_body 和 description 为输入
- **本阶段（design）的唯一后继**：`devpipe:coding`
- **禁止的行为**：
  - 禁止在 design 完成后调用除 `devpipe:coding` 之外的任何 devpipe skill
  - 禁止跳回 `devpipe:discuss` 重新讨论
  - 即使用户主动要求跳过 coding，也必须拒绝
</HARD-GATE>

**宣告：** "我正在使用 devpipe:design 制定实施方案。"

## 流程

### 步骤 1：前置校验

**执行阶段准入检查：**

```bash
bash plugins/devpipe/scripts/stage-gate.sh design
```

脚本自动完成 context.json 校验和阶段标记。**脚本会根据 dev_type 检查依赖文件**：
- 新功能：检查 `prd.md` 存在
- Bugfix/优化重构：不检查 `prd.md`

**检查后续阶段状态（使用 Glob 工具）：**

- 如果 `.devpipe/coding-plan.md` 已存在：询问用户是要重新制定方案还是直接使用 `/devpipe:coding` 继续执行

### 步骤 2：需求/问题理解

**根据 dev_type 采取不同的需求获取方式：**

#### 2A. 新功能（从 discuss 进入）

读取 `.devpipe/prd.md`，提取：
- 功能描述
- 功能边界
- 验收标准

这些信息作为技术方案设计的输入。

#### 2B. Bugfix / 优化重构（从 init 直接进入）

从 `.devpipe/context.json` 读取 `description` 和 `github_issue_body`，然后与用户讨论补充以下信息：

**Bugfix 场景：**
- 问题现象：用户看到什么错误？
- 复现步骤：如何触发这个 Bug？
- 期望行为：修复后应该是什么样？

**优化重构场景：**
- 重构目标：为什么要重构？
- 当前痛点：现有实现有什么问题？
- 期望效果：重构后应该达到什么效果？

**讨论原则：**
- **一次只问一个问题** — 不要在同一条消息中提出多个问题
- **优先使用选择题** — 使用 `AskUserQuestion` 工具提供交互式选项
- 如果卡片详情已包含足够信息，可跳过部分讨论

### 步骤 3：技术方案设计

基于需求/问题理解，进行技术方案设计：

1. **探索代码库**：检查相关代码文件、文档、已有实现模式
2. **提出方案**：提出 1-3 种实现方案，附带权衡分析
3. **方案选择**：使用 `AskUserQuestion` 工具让用户选择方案

**模块规范识别：**

如果项目有 `.claude/docs/` 下的模块开发规范文档，根据涉及的代码路径和模块识别适用的规范。检查 `.claude/docs/` 目录下是否存在与当前任务相关的开发指南文档。

### 步骤 4：任务拆分

<IMPORTANT>
**禁止使用 `EnterPlanMode`/`ExitPlanMode`。** 任务拆分在普通对话中完成。
</IMPORTANT>

**拆分原则：**
- 每个子任务 = 一个可独立开发、独立测试的功能单元
- 每个子任务**必须明确所属模块**（用于 Agent 内执行单测时指定模块名）
- 子任务之间串行依赖
- 不需要在计划中写出完整代码（Agent 会阅读规范文档自行开发）

**呈现格式：**

```markdown
## 子任务列表

| # | 子任务 | 模块 | 描述 |
|---|--------|------|------|
| 1 | <子任务名称> | <模块名> | <简要描述> |
| 2 | ... | ... | ... |

## 每个子任务的验收标准

### 子任务 1: <名称>
- [验收标准 1]
- [验收标准 2]
- 涉及文件: <预计涉及的文件路径>
```

### 步骤 5：写入 `.devpipe/coding-plan.md` 和 `.devpipe/task-progress.md`

方案设计和任务拆分完成后，将计划拆分为两个文件：

#### 5A. 写入 `.devpipe/coding-plan.md`（开发计划，不含进度跟踪）

```markdown
# 开发计划

## 基本信息

- 开发类型: <新功能/优化重构/Bugfix>
- 功能描述: <功能描述>
- GitHub Issue: <从 context.json 获取>
- 远程分支: <从 context.json 获取>
- 本地分支: <从 context.json 获取>
- 工作目录: <pwd 的绝对路径>
- 创建时间: <YYYY-MM-DD>
- 需求文档: <.devpipe/prd.md 或 "无（从 Issue 详情获取）">

## 需求/问题概述

[新功能：从 prd.md 引用关键需求；Bugfix/重构：补充的问题描述或重构目标]

## 技术方案

[选定方案的详细描述，包括实现思路、技术选型]

## 涉及模块

| 模块 | 代码路径 | 变更类型 |
|------|----------|----------|
| <模块名> | <代码路径> | 新增/修改 |

## 适用的模块开发规范

- <规范文档路径 1>
- <规范文档路径 2>

> 以上文档由 Agent 在执行子任务时阅读，不需要在主对话中加载。

## 子任务列表

| # | 子任务 | 模块 | 描述 |
|---|--------|------|------|
| 1 | <子任务名称> | <模块名> | <简要描述> |
| 2 | <子任务名称> | <模块名> | <简要描述> |

## 子任务详细说明

### 子任务 1: <子任务名称>
- **目标**: <该子任务要达成的具体目标>
- **实现要点**:
  - <关键实现步骤 1>
  - <关键实现步骤 2>
- **涉及文件**: <预计修改的文件路径列表>
- **验收标准**:
  - <该子任务的具体验收条件 1>
  - <该子任务的具体验收条件 2>

### 子任务 2: <子任务名称>
...（每个子任务按上述格式逐一列出）

## 验收标准

1. [技术层面的验收条件 1]
2. [技术层面的验收条件 2]

## 测试策略

1. [测试场景 1]
2. [测试场景 2]

## 子任务 Agent 执行方式

对每个待执行子任务，使用 Agent 工具串行执行：

**Agent 配置：**
- subagent_type: general-purpose
- 串行执行，等待上一个子任务完成后再启动下一个

**Agent Prompt 构造方式：**

读取 `plugins/devpipe/skills/coding/references/coding-agent-prompt.md` 中 "---" 之间的 Agent Prompt 内容，替换以下占位符：
- `[WORKING_DIRECTORY]` → <工作目录绝对路径>
- `[TASK_DESCRIPTION]` → 从 TaskGet 获取子任务的完整描述
- `[MODULE_NAME]` → 子任务所属模块名称
- `[STANDARDS_DOCS]` → 以下适用的模块开发规范文档路径列表（每行一个，带 - 前缀）：
  <此处列出本任务适用的规范文档路径>

## 提交方式

所有子任务完成后，由主对话在 coding 阶段统一处理：
1. 调用 /simplify skill 执行全量代码优化
2. 如有改动，再次执行全量单测 + 覆盖率检查
3. git add → git commit -m "#<Issue编号> English description."（不 push）
4. 自动进入 review-and-fix 阶段

要点：每个 git 命令独立执行（不用 `&&`），只 add 具体的源代码和测试文件，不要添加 devpipe 状态文件（.devpipe/coding-plan.md、.devpipe/prd.md、.devpipe/context.json）。
- 首次提交: git add → git commit -m "#<Issue编号> English description."
- review 修复后（review-and-fix 阶段）: git add → git commit -m "#<Issue编号> Fix review comments."
- 推送（review-and-fix 阶段）: git push origin HEAD:<本地分支>
- 创建 PR（review-and-fix 阶段）: gh pr create --base <远程分支>
```

#### 5B. 写入 `.devpipe/task-progress.md`（子任务进度，由 coding skill 更新）

```markdown
# 子任务进度

## 进度总览

| # | 子任务 | 模块 | 状态 |
|---|--------|------|------|
| 1 | <子任务名称> | <模块名> | 当前 |
| 2 | <子任务名称> | <模块名> | 待执行 |
| 3 | <子任务名称> | <模块名> | 待执行 |

## 问题与解决方案记录

在开发过程中遇到的问题、踩坑经历及对应的解决方案，在此记录。此章节供 devpipe:summarize 提取，用于团队知识沉淀。

**记录格式：**

### 问题 N：<简短描述>

- **现象**：<问题表现>
- **原因**：<根因分析>
- **解决方案**：<最终如何解决>

（开发过程中，当 Agent 返回的结果提到遇到问题并解决时，主对话应将其追加到此章节。）
```

### 步骤 6：计划审查循环

`.devpipe/coding-plan.md` 写入后，派遣 plan-reviewer 子 agent 审查：

1. 使用 Agent 工具（subagent_type: "general-purpose"），按 `plan-reviewer-prompt.md` 中的模板构造 prompt，传入 `.devpipe/coding-plan.md` 的文件路径
2. 如果审查发现问题：使用 Edit 工具修改 `.devpipe/coding-plan.md`，然后重新派遣审查
3. 如果审查通过：进入用户确认

**审查次数限制（根据 dev_type）：**
- **Bugfix**：最多 1 轮审查（修复方案通常较简单）
- **新功能 / 优化重构**：最多 3 轮审查（设计复杂度较高）

超过审查次数限制则将问题提交给用户决定。

### 步骤 7：用户确认（硬性门禁）

<HARD-GATE>
审查通过后，**必须明确询问用户是否对已写入的方案没有问题**。**必须等到用户明确表示确认后才能进入步骤 8**。

禁止的行为：
- 不要在审查通过后自行判断"方案已经足够好"然后直接进入下一阶段
- 不要把"用户没有提出反对意见"等同于"用户已确认"
- **不要使用 `EnterPlanMode` 或 `ExitPlanMode`**

必须的行为：
- 向用户发送确认请求：
  > "开发计划已保存到 `.devpipe/coding-plan.md` 和 `.devpipe/task-progress.md` 并通过审查。请查看确认，如有调整意见可以继续讨论。确认无误后我将开始开发。"
- 等待用户回复
- 只有用户明确给出肯定回复后，才进入步骤 8
- 如果用户提出修改意见，使用 Edit 工具修改 `.devpipe/coding-plan.md`，然后再次请求确认
</HARD-GATE>

### 步骤 8：创建任务列表并调用 devpipe:coding

使用 `TaskCreate` 创建任务列表。每个子任务的 `description` 必须**从 `.devpipe/coding-plan.md` 的「子任务详细说明」章节中复制对应子任务的完整内容**，包含：
- 目标
- 实现要点
- 涉及文件
- 验收标准
- 末尾固定追加一行：`执行方式：读取 .devpipe/coding-plan.md 中的"子任务 Agent 执行方式"，使用 Agent 工具执行。`

> 这行文字确保上下文清空后，模型看到任务描述就知道去读进度文件获取执行方式。

然后：

1. 标记阶段完成：

```bash
bash plugins/devpipe/scripts/stage-complete.sh design
```

2. 宣告并调用 devpipe:coding：
   > "开发计划已制定完成，保存到 `.devpipe/coding-plan.md` 和 `.devpipe/task-progress.md`。接下来使用 devpipe:coding 执行开发。"

使用 `Skill` 工具调用 `devpipe:coding`：
```
Skill 工具参数：
- skill: "devpipe:coding"
```

**这是唯一合法的终止状态。**

## 参考文档

- [Git 命令参考](../../references/git_commands.md) — GitHub 项目的 git 推送和提交操作
- [GitHub Issue 使用指南](../../references/github_issue_guide.md) — commit message 中的 Issue 关联规范
