---
name: review-and-fix
description: 对 coding 阶段产出的代码执行自检评审、修复问题、验证单测后推送到 GitHub 并创建 Pull Request。前提：coding 阶段已完成（已有 commit 但未 push）。严格工作流顺序：只能在 coding 完成后调用，完成后由用户手动触发 summarize。当用户说"review"、"评审"、"推送代码"、"push"、"自检"也应触发。
---

# 评审修复与推送（工作流阶段）

对 coding 阶段产出的代码执行自检评审、自动修复、验证单测，然后推送到 GitHub 并创建 Pull Request。根据**源代码变更量**自动选择执行模式。

<HARD-GATE>
## 工作流顺序约束

devpipe 工作流根据 `dev_type` 走不同路径：
- **新功能**：`init → discuss → design → coding → review-and-fix → summarize`
- **Bugfix / 优化重构**：`init → design → coding → review-and-fix → summarize`

- **本阶段（review-and-fix）的前置条件**：必须已完成 `devpipe:coding`（存在本地 commit 但未 push）
- **本阶段（review-and-fix）的后继**：`devpipe:summarize`（用户手动触发）
- **执行模式（按源代码变更量自动判断）**：
  - **完整模式**（源代码变更 >= 50 行）：两阶段评审流程
    - Phase 1：code-reviewer → 自动修复 must_fix → 验证 → 推送
    - Phase 2（可选）：用户确认后修复 should_fix → 验证 → 再次推送
  - **轻量模式**（源代码变更 < 50 行）：跳过评审，仅验证后直接推送
- **禁止的行为**：
  - 禁止在 coding 阶段未完成时直接调用本 skill
  - 禁止跳过本阶段直接执行 summarize
</HARD-GATE>

**宣告：** "我正在使用 devpipe:review-and-fix 执行代码评审、修复和推送。"

---

## 步骤 1：前置校验

**执行阶段准入检查：**

```bash
bash scripts/stage-gate.sh review-and-fix
```

**额外校验：**

1. 验证存在本地 commit：
   - 执行 `git log --oneline -1` 确认有 commit
   - 执行 `git diff --name-only HEAD~1 HEAD` 确认最近 commit 有代码变更
   - 无 commit 或无变更 → **立即终止**

2. 检查是否已推送：
   - 执行 `git log --oneline origin/<local_branch>..HEAD 2>/dev/null` 检查是否有未推送的 commit
   - 如果已推送（无未推送 commit）：
     - 检查 `.devpipe/phase2-fixplan.json` 是否存在 → 存在则跳到**步骤 7（Phase 2 询问）**
     - 不存在 → 检查用户当前消息是否包含完成意图 → 有则跳到**步骤 10**，否则跳到**步骤 9**

**检测源代码变更量（排除文档和测试文件）：**

```bash
git diff --numstat HEAD~1 HEAD -- ':(exclude)*.md' ':(exclude)*Test.java' ':(exclude)*Tests.java' ':(exclude)*IT.java' ':(exclude)*_test.go' ':(exclude)test_*.py' | awk '{added+=$1; deleted+=$2} END {print added+deleted}'
```

> 统计新增行数 + 删除行数，排除 Markdown 文档、Java 单测文件（*Test.java、*Tests.java、*IT.java）、Go 测试文件（*_test.go）、Python 测试文件（test_*.py）。

**根据变更量选择执行路径：**

- **变更量 < 50 行** → 进入**轻量模式（步骤 2L）**
  > "检测到源代码变更 N 行（不含文档和测试），使用轻量模式：跳过自检评审，仅验证后推送。"
- **变更量 >= 50 行** → 进入**完整模式（步骤 2）**
  > "检测到源代码变更 N 行（不含文档和测试），使用完整模式：执行自检评审后推送。"

---

## 步骤 2L：轻量模式（源代码变更 < 50 行）

跳过代码评审，仅执行基本验证后直接推送。

### 2L.1 推送到 GitHub

按 [Git 命令参考](../../references/git_commands.md) 中的规则执行。远程分支从 `.devpipe/context.json` 获取。

```bash
git push origin HEAD:<local_branch>
```

### 2L.2 创建 Pull Request

```bash
gh pr create --base <remote_branch> --title "#<github_issue> Short English description." --body "## Summary
<变更摘要>

Closes #<github_issue>"
```

> 轻量模式**跳过 dry-run 和用户确认**。

推送成功后跳到**步骤 9（PR Review 等待）**。

---

## 步骤 2：代码评审（完整模式）

调用 `devpipe:code-reviewer` skill 执行评审，评审范围固定为最近一次 commit：

```
Skill 工具参数：
- skill: "devpipe:code-reviewer"
- args: "评审最近一次提交"
```

`code-reviewer` 完成后会输出评审报告和 Fix Plan JSON。当 code-reviewer 询问 should_fix 是否纳入时，**全部纳入** Fix Plan。同样**不确认**是否调用 code-fixer。

---

## 步骤 3：拆分 Fix Plan

`code-reviewer` 已输出评审报告（含 🔴/🟡/🟢 分级）和完整 Fix Plan JSON。从中按 `severity` 拆分为两个独立的 Fix Plan：

**拆分规则：**
- **Fix Plan A**（Phase 1）：筛选 `severity == "critical"` 的条目（原 🔴 must_fix）
- **Fix Plan B**（Phase 2）：筛选 `severity == "warning"` 的条目（原 🟡 should_fix）
- `severity == "suggestion"`（原 🟢 nice_to_have）：**丢弃，不纳入任何 Fix Plan**

两个 Fix Plan 保持相同的 JSON 结构（`version`、`source`、`working_directory`），仅 `fixes` 数组内容不同。

**创建 `.devpipe/review-status.md`（仅完整模式）：**

使用 Write 工具将评审概览和问题清单写入 `.devpipe/review-status.md`：

```markdown
# 评审修复状态

## 评审概览
- 评审模式: 完整模式
- 源代码变更量: N 行
- 评审时间: YYYY-MM-DD HH:MM:SS

## 评审问题
| # | 严重级别 | 文件 | 问题描述 | 状态 |
|---|----------|------|----------|------|
| 1 | must_fix | xxx | xxx | 待修复 |
| 2 | should_fix | xxx | xxx | 待修复 |

## 修复记录

## PR 信息
```

**持久化 Phase 2 计划：**

如果 Fix Plan B 非空，使用 Write 工具将 Fix Plan B 写入 `.devpipe/phase2-fixplan.json`，供进度恢复使用。

**展示拆分摘要（纯通知，不需用户确认）：**

```
评审结果拆分：
- Phase 1（自动修复）：X 个 must_fix 问题
- Phase 2（推送后可选）：Y 个 should_fix 问题
- 跳过：Z 个 nice_to_have 问题
```

**边界情况处理：**
- Fix Plan A 为空（无 must_fix）→ 跳过步骤 4-5，直接步骤 6 推送原始代码
- Fix Plan B 为空（无 should_fix）→ 不创建 `phase2-fixplan.json`，Phase 1 完成后跳过 Phase 2，直接步骤 9
- 两者都为空 → 直接步骤 6 推送原始代码，然后步骤 9

---

## 步骤 4：Phase 1 - 修复 must_fix

调用 `devpipe:code-fixer` skill 按 Fix Plan A 执行修复：

```
Skill 工具参数：
- skill: "devpipe:code-fixer"
- args: <Fix Plan A JSON（仅 critical 条目）>
```

等待 code-fixer 完成，检查修复报告。

如果 Fix Plan A 为空，跳过本步骤。

---

## 步骤 5：Phase 1 - 验证修复

如果步骤 4 产生了代码改动，执行验证（根据项目构建系统自动检测）。

- 测试通过 → 进入步骤 6
- 测试失败 → 修复失败的测试，重新验证（最多 3 轮）
- 3 轮后仍失败 → 与用户讨论后决定是否继续推送

如果步骤 4 无代码改动（Fix Plan A 为空或所有问题已在评审前修复），跳过验证。

**更新 `.devpipe/review-status.md`**：将 Phase 1 修复的问题状态更新为"已修复"，记录修复数和验证状态。

---

## 步骤 6：Phase 1 - Commit + Push + PR（完整模式）

按 [Git 命令参考](../../references/git_commands.md) 中的规则执行。远程分支和 Issue 编号从 `.devpipe/context.json` 获取。

### 6.1 如果有修复改动

```bash
git add <修复涉及的文件列表>
```

```bash
git commit -m "#<github_issue> Fix review issues."
```

### 6.2 推送预览与确认

在实际推送前，先执行 dry-run 确认推送内容：

```bash
git push --dry-run origin HEAD:<local_branch>
```

将 dry-run 结果展示给用户，并使用 `AskUserQuestion` 确认是否推送。

### 6.3 推送到 GitHub

```bash
git push origin HEAD:<local_branch>
```

### 6.4 创建 Pull Request

如果尚未创建 PR，使用 `gh` CLI 创建：

```bash
gh pr create --base <remote_branch> --title "#<github_issue> Short English description." --body "## Summary
<变更摘要>

Closes #<github_issue>"
```

**更新 `.devpipe/review-status.md`**：追加 PR 信息（PR URL 和远程分支）。

**注意：** 每个 git 命令独立执行，不使用 `&&` 连接。

### 6.5 检查 Phase 2

推送成功后：
- 如果 `.devpipe/phase2-fixplan.json` 存在（Fix Plan B 非空）→ 继续**步骤 7**
- 如果不存在（无 should_fix 问题）→ 跳到**步骤 9（PR Review 等待）**

---

## 步骤 7：Phase 2 - 询问用户

Phase 1 已推送成功，GitHub Actions CI 已开始运行。读取 `.devpipe/phase2-fixplan.json` 中的 should_fix 条目，展示给用户并询问：

```json
{
  "questions": [
    {
      "question": "Phase 1 已完成推送（must_fix 已修复），GitHub Actions CI 已开始运行。\n\n以下 should_fix 问题可进一步优化代码质量：\n<按文件分组列出 should_fix 条目>\n\n是否继续修复这些问题？",
      "header": "Phase 2",
      "options": [
        {"label": "继续修复", "description": "修复 should_fix 问题后再次推送"},
        {"label": "跳过", "description": "暂不修复，等待 PR Review 反馈再决定"}
      ],
      "multiSelect": false
    }
  ]
}
```

- 用户选择「继续修复」→ 进入**步骤 8**
- 用户选择「跳过」→ 删除 `.devpipe/phase2-fixplan.json`，跳到**步骤 9**

---

## 步骤 8：Phase 2 - 修复 + 验证 + 推送

### 8.1 修复 should_fix

读取 `.devpipe/phase2-fixplan.json`，调用 `devpipe:code-fixer` 执行修复：

```
Skill 工具参数：
- skill: "devpipe:code-fixer"
- args: <Fix Plan B JSON（warning 条目）>
```

### 8.2 验证修复

执行验证（根据项目构建系统）。

- 测试通过 → 进入 8.3
- 测试失败 → 修复失败的测试，重新验证（最多 3 轮）
- 3 轮后仍失败 → 与用户讨论，选择继续推送或放弃 Phase 2 改动

### 8.3 Commit + Push

```bash
git add <修复涉及的文件列表>
```

```bash
git commit -m "#<github_issue> Fix should_fix review issues."
```

```bash
git push origin HEAD:<local_branch>
```

Phase 2 已由用户在步骤 7 确认意图，**不再需要 dry-run 和推送确认**。

### 8.4 更新 review-status.md

将 Phase 2 修复的问题状态更新为"已修复"。

### 8.5 清理

推送成功后，删除 `.devpipe/phase2-fixplan.json`。

---

## 步骤 9：PR Review 等待

**不标记阶段完成**，保持 `stage_completed: false`，等待用户 PR Review 反馈或明确完成。

**轻量模式：**

```
========== 代码已推送（轻量模式） ==========
评审：已跳过（源代码变更 < 50 行）
代码推送：已推送到 <local_branch>（PR 目标: <remote_branch>）
Pull Request：已创建

当前状态：等待 PR Review
你可以：
1. 收到 Review 反馈后，告诉我具体的修改意见，我会帮你处理
2. PR 合入后，说"评审完成"进入下一阶段
=====================================================
```

**完整模式：**

```
========== 代码已推送 ==========
评审问题：X 个（🔴 A / 🟡 B / 🟢 C）

Phase 1（must_fix）：
- 修复：A 个 → 验证通过 → 已推送

Phase 2（should_fix）：
- 修复：B 个 → 验证通过 → 已推送
  （或：用户选择跳过，B 个 should_fix 问题未修复）

代码推送：已推送到 <local_branch>（PR 目标: <remote_branch>）
Pull Request：已创建

当前状态：等待 PR Review
你可以：
1. 收到 Review 反馈后，告诉我具体的修改意见，我会帮你处理
2. PR 合入后，说"评审完成"进入下一阶段
==========================================
```

---

## 步骤 10：标记阶段完成

**仅当用户明确表示完成时执行。** 触发词："评审完成"、"PR已合入"、"PR通过了"、"进入下一阶段"、"可以总结了"、"评审修复完成"。

标记阶段完成：

```bash
bash scripts/stage-complete.sh review-and-fix
```

展示完成通知：

```
========== review-and-fix 完成 ==========
代码推送：已推送到 <local_branch>（PR 目标: <remote_branch>）
Pull Request：已创建/更新
阶段状态：已完成

下一步：
执行 /devpipe:summarize 生成迭代文档
==========================================
```

---

## PR Review 反馈处理

用户收到 PR Review 反馈后，在本对话中处理：

### 获取 Review 评论

```bash
gh pr view --comments
```

或通过 API 获取详细 Review：

```bash
gh api repos/<owner>/<repo>/pulls/<pr_number>/reviews
```

### 轻量修改（命名、格式、注释等）

直接在主对话中修复：

1. 根据用户描述的 Review 反馈，修改相关文件
2. 执行验证
3. Commit 并推送：

```bash
git add <修改的文件>
```

```bash
git commit -m "#<github_issue> Address review feedback."
```

```bash
git push origin HEAD:<local_branch>
```

### 逻辑修改（需要更多上下文）

启动 general-purpose Agent 处理：

```
Agent 工具参数：
- subagent_type: "general-purpose"
- description: "处理 Review 反馈: <反馈简述>"
- prompt: （包含 Review 反馈内容、涉及文件、修改要求）
```

Agent 完成后，执行验证 → commit → push（同轻量修改流程）。

**重要：Review 反馈处理后不重新走 review-and-fix 自检流程，直接 commit + push。**

---

## 进度恢复

| 状态 | 恢复行为 |
|------|----------|
| stage 为 `review-and-fix` + 未 push + 变更量 >= 50 行 | 从步骤 2（代码评审）重新开始 |
| stage 为 `review-and-fix` + 未 push + 变更量 < 50 行 | 从步骤 2L（轻量模式）继续 |
| stage 为 `review-and-fix` + 已 push + `.devpipe/phase2-fixplan.json` 存在 | 从步骤 7（Phase 2 询问）继续 |
| stage 为 `review-and-fix` + 已 push + 无 `phase2-fixplan.json` | 跳到步骤 9（PR Review 等待） |
| stage 为 `review-and-fix` + 已 push + 无 `phase2-fixplan.json` + 用户表示完成 | 步骤 10（标记阶段完成） |

---

## 异常处理

| 情况 | 处理方式 |
|------|----------|
| 评审子 Agent 超时 | 记录失败批次，继续下一批 |
| 评审子 Agent 返回非法 JSON | 跳过该批次，记录警告 |
| code-fixer 修复失败 | 展示失败条目，与用户讨论 |
| 单测验证失败 | 修复后重试，3 轮后询问用户 |
| push 失败 | 检查远程分支和权限，报告错误原因 |
| `gh` 报 HTTP 401 | gh token 过期，在容器内或宿主机执行 `gh auth login -h github.com` 重新认证 |
| 用户中途取消 | 已完成的修复保留在本地，下次恢复 |
| Phase 1 推送成功但 Phase 2 修复失败 | 保留 Phase 1 已推送代码，与用户讨论是否重试或放弃 Phase 2 |
| 会话在 Phase 1 推送后 Phase 2 前中断 | 通过 `.devpipe/phase2-fixplan.json` 恢复到步骤 7 |

---

## 关键依赖

| 依赖 | 用途 | 使用位置 |
|------|------|----------|
| Skill (devpipe:code-reviewer) | 执行代码评审，输出 Fix Plan | 步骤 2 |
| Skill (devpipe:code-fixer) | 按 Fix Plan 修复代码 | 步骤 4（Phase 1）、步骤 8.1（Phase 2） |
| `.devpipe/context.json` | 远程分支、Issue 编号 | 步骤 1、步骤 6 |
| `.devpipe/phase2-fixplan.json` | Phase 2 Fix Plan 持久化，供进度恢复 | 步骤 3（写入）、步骤 7（读取）、步骤 8.4/9（删除） |
| [Git 命令参考](../../references/git_commands.md) | commit + push 操作 | 步骤 6、步骤 8.3 |
| `gh` CLI | 创建 PR、获取 Review | 步骤 6.4、Review 反馈处理 |

## 参考文档

- [Git 命令参考](../../references/git_commands.md) — GitHub 项目的 git 推送和提交操作
- [GitHub Issue 使用指南](../../references/github_issue_guide.md) — commit message 中的 Issue 关联规范
