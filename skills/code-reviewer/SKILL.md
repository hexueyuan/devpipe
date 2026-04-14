---
name: code-reviewer
description: 对代码变更进行评审并输出标准化 Fix Plan JSON。当用户说"评审代码"、"review 代码"、"检查代码"、"code-reviewer"、"评审本次改动"、"review 最近提交"、"帮我看看代码"时触发。支持三种评审范围：未提交的变更、指定 commit、最近一次 commit。辅助型 skill，可独立调用，也被 devpipe:review-and-fix 工作流阶段内联使用。输出可直接传递给 devpipe:code-fixer 执行修复。
---

# 代码评审 Skill

对代码变更进行静态评审，输出标准化 Fix Plan JSON。本 skill 是**编排层**——确定评审范围、发现代码规范、派遣子 Agent 执行评审、将评审结果转换为 Fix Plan JSON。

**宣告：** "我正在使用 devpipe:code-reviewer 评审代码变更。"

---

## 评审范围

支持三种评审模式，由用户输入自动检测：

| 模式 | 触发条件 | 获取文件列表 | 获取 Diff |
|------|----------|-------------|----------|
| 未提交变更（默认） | 用户说"评审改动"或未指定；`git diff --name-only` 有结果 | `git diff --name-only` | `git diff` |
| 指定 commit | 用户提供 commit SHA 或引用（如"评审 abc1234"） | `git diff --name-only <COMMIT>~1 <COMMIT>` | `git diff <COMMIT>~1 <COMMIT>` |
| 最近一次提交 | 用户说"评审最近一次提交"；或无未提交变更时兜底 | `git diff --name-only HEAD~1 HEAD` | `git diff HEAD~1 HEAD` |

---

## 编排工作流

### 步骤 1：确定评审范围

**自动检测逻辑**（按优先级）：

1. 如果用户明确提供了 commit SHA 或引用 → 使用"指定 commit"模式
2. 如果用户说"最近一次提交"/"last commit" → 使用"最近一次提交"模式
3. 否则，执行 `git diff --name-only` 检查是否有未提交变更：
   - 有结果 → 使用"未提交变更"模式
   - 无结果 → 兜底使用"最近一次提交"模式
4. 如果所有模式都无变更文件 → 报告："没有找到可评审的代码变更。" 并终止

**文件过滤**：

- 只保留源代码文件（按语言过滤，如 `.java`、`.py`、`.go`、`.ts`、`.js`）
- 排除测试资源文件、生成代码、配置文件
- 如果用户指定了特定文件或目录，与 diff 文件列表取交集

**工作目录检测**：

通过查找 `pom.xml`、`package.json`、`pyproject.toml`、`go.mod`、`.git` 等标记确定项目根目录。如果用户指定的文件路径包含子项目前缀，则将工作目录设为该子项目根目录。

输出范围摘要：

```
评审范围：
- 模式：未提交的变更
- 变更文件：4 个
- 语言：Java
- 工作目录：/path/to/project
```

### 步骤 2：发现代码规范

**动态发现协议**（不硬编码项目特定路径）：

1. **检测项目语言**：根据步骤 1 中文件扩展名统计，确定主要语言
2. **搜索代码规范文档**（按优先级）：
   - 使用 Glob 搜索 `.claude/docs/*code-style*`、`.claude/docs/*coding-standard*`、`.claude/docs/*style-guide*`（不区分大小写）
   - 检查 `.claude/docs/development-doc.md` 是否存在
   - 检查项目根目录下的工具配置文件（`checkstyle.xml`、`.editorconfig`、`.eslintrc.*`、`pylintrc` 等）
3. **检测 Lint 工具**：
   - Java：检查 `pom.xml` 是否配置了 `maven-checkstyle-plugin` → 构造 Checkstyle 命令
   - Python：检查 `pyproject.toml` / `setup.cfg` 中的 lint 配置
   - 其他语言：类似模式
4. **构造 Lint 命令**（Java/Checkstyle 示例）：
   - 从变更文件路径中截取 `src/main/java/` 之后的部分作为 `checkstyle.includes` 参数
   - 多个文件用逗号拼接
   - 命令格式：`mvn checkstyle:check -Dcheckstyle.includes="<includes>" --fail-at-end -Dcheckstyle.consoleOutput=true 2>&1`

输出发现摘要：

```
发现的代码规范：
- .claude/docs/code-style.md（项目编码规范）
- .claude/docs/development-doc.md（开发指南）
- pom.xml 中配置了 Checkstyle 插件
```

如果未找到任何规范文档，输出提示：

```
未发现项目代码规范文档，将使用语言通用最佳实践进行评审。
```

### 步骤 3：派遣评审子 Agent

读取 [reviewer-agent-prompt.md](reviewer-agent-prompt.md) 模板，为每批评审任务构造 Agent prompt。

**分批策略**：
- 每个 Agent 评审一批文件（按模块/目录分组，每批 5-8 个文件）
- 如果文件总数 ≤ 8，使用单个 Agent
- 如果文件总数 > 8，按模块/目录分组为多批，每批约 5 个文件

**并行 vs 串行策略**：
- **不同模块的批次可并行执行**——不同模块的文件没有交叉引用，评审标准独立，并行不会影响一致性
- **同一模块内的批次串行执行**——确保同模块文件的评审标准一致性
- 如果所有文件属于同一模块，全部串行执行

> **分组示例**：假设有 12 个变更文件，分布在 `service`（6 个）和 `controller`（6 个）两个模块。拆为 4 批：service 批次 1（3 个）和 service 批次 2（3 个）串行，controller 批次 1（3 个）和 controller 批次 2（3 个）串行，但两组之间并行执行。

**Agent 调用方式**：

```
Agent 工具参数：
- subagent_type: "general-purpose"
- description: "代码评审: <涉及文件简述>"
- prompt: （按 reviewer-agent-prompt.md 模板构造，注入文件列表、diff 内容、规范文档路径、语言、lint 命令）
```

等待每个 Agent 完成后，解析返回的 JSON 问题数组。同模块内等前一批完成再派遣下一批；不同模块的首批可同时派遣。

### 步骤 4：汇总评审结果

收集所有子 Agent 返回的 JSON issue 数组：

1. 合并所有 issue 到一个列表
2. 去重：同一文件 + 同一行号 + 相同描述的 issue 只保留一条
3. 按文件分组，每个文件内按行号升序排列

### 步骤 5：转换为 Fix Plan JSON

按 [评审输出 Schema](../../references/review-output-schema.md) 中的映射规则，将评审结果转换为标准 Fix Plan JSON。

**转换流程**：

1. 为每条 issue 生成 `id`（`fix-001` 递增）
2. 将 `category` 映射为 `type`（import→import, naming→naming/rename, format→format, logic→logic, style→style, doc→doc, optimization→optimization, other→replace）
3. 将 `severity` 映射为 Fix Plan 的 `severity`（must_fix→critical, should_fix→warning, nice_to_have→suggestion）
4. 对 `naming` 类型：如果 `referenced_files` 非空，使用 `rename` 类型并填充 `related_files`
5. 将 `standard_reference` 映射到 `context` 字段
6. 设置顶层字段：`version: "1.0"`、`source: "code-reviewer"`、`working_directory: <步骤 1 检测的路径>`

**纳入条件**：

- `severity: "critical"`（原 `must_fix`）：**自动纳入** Fix Plan
- `severity: "warning"`（原 `should_fix`）：展示给用户，使用 AskUserQuestion 询问是否纳入
- `severity: "suggestion"`（原 `nice_to_have`）：**默认不纳入**，仅在评审报告中展示

### 步骤 6：输出评审报告

展示评审报告和生成的 Fix Plan：

```
========== 评审报告 ==========
模式：未提交的变更
变更文件数：4
发现问题数：8（🔴 3 / 🟡 4 / 🟢 1）
使用的规范：code-style.md, development-doc.md

🔴 必须修改 (3):
- ClusterServiceImpl.java:42 - 未使用的 import javax.annotation.Nullable
- TopicServiceImpl.java:120 - 缺少 null 检查，可能抛出 NPE
- AclUtils.java:30 - 方法名 chk() 含义不明确

🟡 建议修改 (4):
- ClusterServiceImpl.java:88 - 魔法数 3600000 应提取为常量
- TopicServiceImpl.java:15 - 缩进不一致
- ConsumerServiceImpl.java:60 - 公共方法缺少 Javadoc
- MonitorServiceImpl.java:200 - 全限定类名应使用 import

🟢 可优化 (1):
- BillingServiceImpl.java:150 - 可考虑提取公共校验方法

Fix Plan 已生成（含 🔴 3 条 + 用户确认的 🟡 条目）。
==============================
```

询问用户是否调用 `devpipe:code-fixer` 执行修复：

```
是否需要调用 devpipe:code-fixer 执行修复？
```

如果用户确认，使用 Skill 工具调用 code-fixer：

```
Skill 工具参数：
- skill: "devpipe:code-fixer"
- args: （生成的 Fix Plan JSON）
```

---

## 异常处理

| 情况 | 处理方式 |
|------|----------|
| 没有变更文件 | 报告"没有找到可评审的代码变更"并终止 |
| 未找到代码规范文档 | 提示用户，使用语言通用最佳实践继续评审 |
| Lint 工具执行失败 | 记录警告，跳过自动化检查，仅使用人工静态分析 |
| 子 Agent 超时 | 记录该批次为失败，继续下一批次 |
| 子 Agent 返回非法 JSON | 记录警告，跳过该批次结果 |
| 用户中途取消 | 输出已收集的部分评审结果 |
| Git 命令执行失败 | 报告错误原因（如非 git 仓库、commit 不存在等）并终止 |

---

## 注意事项

- 本 skill 是**辅助型 skill**，可独立调用，也被 `devpipe:review-and-fix` 工作流阶段内联使用
- 输出是标准 Fix Plan JSON，可直接作为 `devpipe:code-fixer` 的输入
- 只执行**只读** git 操作（diff、log、show），不执行 add/commit/push
- 不修改任何文件——纯分析评审
- 可以独立调用，也可以链式调用：`code-reviewer` → 用户确认 → `code-fixer`

---

## 关键依赖

| 依赖 | 用途 | 使用位置 |
|------|------|----------|
| Agent 工具 (general-purpose) | 执行评审的独立上下文 | 步骤 3 派遣评审子 Agent |
| Skill (devpipe:code-fixer) | 执行修复（可选链式调用） | 步骤 6 用户确认后 |
| [reviewer-agent-prompt.md](reviewer-agent-prompt.md) | 子 Agent Prompt 模板 | 步骤 3 构造 prompt |
| [评审输出 Schema](../../references/review-output-schema.md) | 输出格式和映射规则参考 | 步骤 5 格式转换 |

## 参考文档

- [评审输出 Schema](../../references/review-output-schema.md) — 评审子 Agent 输出格式和 Fix Plan 映射规则
- [Fix Plan Schema](../../references/fix-plan-schema.md) — Fix Plan JSON 完整格式参考（code-fixer skill 维护）
