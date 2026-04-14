---
name: summarize
description: 开发完成后的总结归档。收集开发过程资料，生成完整的迭代文档（基本信息、原始需求、需求分析过程、实现方案、问题与解决方案、反思与复盘共 6 节，Markdown 格式，保存到 .devpipe/state/summary.md），清理状态文件。用户手动触发。当用户说"总结"、"归档"、"summarize"、"代码已合入"、"开发完成了"、"收尾"、"PR已合入"时触发。前提：review-and-fix 阶段已完成（代码已推送并合入）。这是工作流的终止阶段。
---

# 开发总结与归档（工作流终止阶段）

收集本次开发过程的资料，生成完整的迭代文档（6 个核心章节），清理状态文件，完成工作流闭环。

**文档定位**：面向团队知识沉淀和开发经验传承。文档不仅要记录"做了什么"，更要记录"为什么这样做"、"过程中遇到了什么"、"学到了什么"，帮助团队成员（包括未来的自己）快速理解一次开发任务的完整脉络。

<HARD-GATE>
## 工作流顺序约束

devpipe 工作流的阶段顺序取决于 `dev_type`：
- **新功能**：`init → discuss → design → coding → review-and-fix → summarize`
- **Bugfix / 优化重构**：`init → design → coding → review-and-fix → summarize`（跳过 discuss）

- **本阶段（summarize）的前置条件**：必须已完成 `devpipe:review-and-fix`（代码已推送到 GitHub）
- **本阶段是工作流的终止阶段**，完成后 stage 更新为 `"done"`
- **禁止的行为**：
  - 禁止在 review-and-fix 阶段未完成时直接调用本 skill
  - 禁止在 stage 不是 `"review-and-fix"` 或 `"summarize"` 时执行
  - 即使用户主动要求"跳过总结"，也应提醒："建议执行总结归档以保留开发记录，确认要跳过吗？"如果用户坚持跳过，仅执行清理步骤（步骤 4）。
</HARD-GATE>

**宣告：** "我正在使用 devpipe:summarize 进行开发总结与归档。"

---

## 步骤 1：前置校验

**执行阶段准入检查：**

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/stage-gate.sh summarize
```

脚本自动完成 context.json 校验（必需字段非空）、前置阶段检查（stage 必须为 "review-and-fix" 或 "summarize"）和阶段标记（stage="summarize"、stage_completed=false、stage_timestamps.summarize.started_at）。失败时立即终止并展示错误信息。成功时输出 JSON 摘要。

**额外检查：**

检查 `.devpipe/state/prd.md` 和 `.devpipe/state/coding-plan.md` 是否存在（用于生成文档）：
- 缺少任一文件 → 警告但不终止，文档中对应章节标注"（资料缺失）"

---

## 步骤 2：收集资料

从以下来源收集开发过程信息（按优先级排列）：

| 来源 | 提取内容 | 必需 |
|------|----------|------|
| `.devpipe/state/context.json` | 开发类型、描述、卡片号、远程分支、本地分支、开发开始日期 | 是 |
| `.devpipe/state/prd.md` | 原始需求内容、需求分析、实现方案 | 是 |
| `git diff --stat HEAD~1 HEAD`（或对应 commit 范围） | 代码变更统计（辅助理解改动范围） | 否 |
| `git log --oneline -20` | 提交历史（辅助理解变更范围） | 否 |
| `.devpipe/state/coding-plan.md` | 技术方案、模块设计 | 是 |
| `.devpipe/state/task-progress.md` | 开发过程中的问题记录、解决方案（见"问题与解决方案记录"章节） | 是 |
| `.devpipe/state/review-status.md` | 评审问题和修复情况（可选，仅完整模式生成） | 否 |

重点是从 prd.md、coding-plan.md 和 task-progress.md 中**深度提炼**需求分析思路、方案设计逻辑、过程中的问题和解决方案，而非全文复制。对于每个章节，都要回答"为什么"而不仅仅是"是什么"。

---

## 步骤 3：生成迭代文档

将收集的资料精炼为迭代文档，写入 `.devpipe/state/summary.md`（固定路径）。文档面向团队成员阅读，用于知识沉淀和开发经验传承，所以内容要**完整、有深度**，清晰呈现一次开发任务从需求到落地的全过程，以及过程中的思考和收获。

### 文档模板

文档仅包含以下 6 个核心章节，不要添加额外章节：

```markdown
# <功能描述>

## 基本信息

| 字段 | 值 |
|------|-----|
| 开发类型 | <dev_type> |
| GitHub Issue | #<github_issue>（如有） |
| 远程分支 | <remote_branch> |
| 本地分支 | <local_branch> |
| 开发日期 | <created_at> |
| 完成日期 | <当前日期> |

## 原始需求

清晰记录本次开发任务的原始需求来源和内容：
- 需求来自哪里（GitHub Issue 描述、产品经理口述、线上问题等）
- 需求的原始表述是什么
- 需求的业务背景和价值（为什么要做这件事）

从 prd.md 的需求背景部分和 context.json 的描述中提炼。如有 GitHub Issue，引用 Issue 中的关键信息。

## 需求分析过程

记录从"原始需求"到"明确的技术任务"之间的分析和思考过程：
- 需求的边界和范围是如何确定的（做什么、不做什么）
- 涉及哪些模块和组件，影响面分析
- 与现有功能的关系（复用、扩展还是新建）
- 关键的技术约束和前提条件
- 如有多个可选方案，列出备选方案及最终选择的理由

这个章节的核心价值是让读者理解"为什么最终的方案是这样的"，而不仅仅是"方案是什么"。

## 实现方案

详细描述最终采用的技术实现方案：
- 整体架构设计和模块划分
- 核心类/接口的设计及其职责
- 关键的设计决策及理由（如设计模式选择、分层策略、数据流向等）
- 与现有代码的集成方式
- 接口契约（如有新增 API，说明请求/响应格式）

重点描述方案的设计思路和关键决策，而非逐行解释代码实现。

## 问题与解决方案

记录开发过程中遇到的问题、踩坑经历及对应的解决方案：
- 每个问题用 `### 问题 N：<简短描述>` 作为子标题
- 描述问题的现象、原因分析和最终解决方案
- 如无明显问题，可记录开发过程中的技术发现或值得注意的细节

这个章节是团队知识沉淀的核心部分，帮助后续开发者避免重复踩坑。

从 task-progress.md 中的问题记录、git commit message 中的 fix 相关提交、以及 prd.md 中的注意事项提炼。

## 反思与复盘

对本次开发过程的回顾和总结：
- 做得好的地方（可复用的经验和模式）
- 可以改进的地方（流程、设计、编码等方面）
- 对后续工作的建议或待办事项
- 学到的新知识或新技能

保持坦诚和建设性，这个章节的目的是持续改进。
```

### 写作要求

- **原始需求**：如实记录需求来源，保留关键原文或链接，不要过度解读
- **需求分析过程**：重点是分析的逻辑链条，让读者理解决策的依据
- **实现方案**：描述设计思路和关键决策，不是代码的逐行解释
- **问题与解决方案**：具体描述现象、原因、方案，可配图或代码片段辅助说明
- **反思与复盘**：坦诚且建设性，既肯定成果也指出改进空间
- 整篇文档控制在 150-300 行以内，每个章节内容充实但不冗余
- 使用技术术语要准确，避免模糊表述

### 文档保存

文档写入 `.devpipe/state/summary.md`（固定路径），供 Dashboard 在"总结"和"已完成"阶段展示。

`.devpipe/state/` 已通过 bind mount 持久化到 `.devpipe/docs/<name>/` 目录，环境清理后文件自动保留，无需额外归档。

**保存步骤：**

1. 使用 Write 工具将文档写入 `.devpipe/state/summary.md`

---

## 步骤 4：清理状态

1. **标记阶段完成并更新为终止状态：**

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/stage-complete.sh summarize --next-stage done
```

2. **保留** `.devpipe/state/summary.md`（不删除，供 Dashboard 在"总结"和"已完成"阶段持续展示）

> **设计理由**：所有产出文件（`context.json`、`prd.md`、`coding-plan.md`、`task-progress.md`、`review-status.md`、`summary.md`）均保留用于归档。`.devpipe/state/` 已通过 bind mount 持久化到 `.devpipe/docs/` 目录，环境清理不影响这些文件。

---

## 步骤 5：完成通知

```
========== devpipe:summarize 完成 ==========
迭代文档：
  - .devpipe/state/summary.md（Dashboard 展示用，已持久化到 .devpipe/docs/ 目录）
内容：基本信息 / 原始需求 / 需求分析过程 / 实现方案 / 问题与解决方案 / 反思与复盘
状态：所有产出文件已保留（.devpipe/state/ 下的 context.json / prd.md / coding-plan.md / task-progress.md / review-status.md / summary.md）
工作流状态：done

本次开发工作流已全部完成。
如需开始新的开发任务，请执行 /devpipe:init。
=============================================
```

---

## 进度恢复

| 状态 | 恢复行为 |
|------|----------|
| stage 为 `summarize` + `.devpipe/state/summary.md` 已存在 | 提示文档已生成，询问是否重新生成或直接清理 |
| stage 为 `summarize` + `.devpipe/state/summary.md` 不存在 | 从步骤 2 继续 |
| stage 为 `done` | 提示工作流已结束 |

---

## 异常处理

| 情况 | 处理方式 |
|------|----------|
| prd.md 不存在 | 警告，文档中"原始需求"和"需求分析过程"章节标注"（资料缺失）" |
| coding-plan.md 不存在 | 警告，文档中"实现方案"章节标注"（资料缺失）" |
| task-progress.md 不存在 | 警告，文档中"问题与解决方案"章节标注"（资料缺失）" |
| git log/diff 命令失败 | 警告，辅助信息省略 |
| .devpipe/state/summary.md 写入失败 | 报告错误，终止 |
| 用户中途取消 | 已生成的文档保留，下次恢复 |

---

## 关键依赖

| 依赖 | 用途 | 使用位置 |
|------|------|----------|
| `.devpipe/state/context.json` | 元数据（分支、卡片号等） | 步骤 2 收集资料 |
| `.devpipe/state/prd.md` | 需求和设计信息 | 步骤 2 收集资料 |
| `.devpipe/state/coding-plan.md` | 技术方案、模块设计 | 步骤 2 收集资料 |
| `.devpipe/state/task-progress.md` | 问题与解决方案记录 | 步骤 2 收集资料 |
| `.devpipe/state/review-status.md` | 评审问题和修复情况（可选） | 步骤 2 收集资料 |
| Git CLI | 提交历史和变更统计 | 步骤 2 收集资料 |
