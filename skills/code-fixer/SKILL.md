---
name: code-fixer
description: 按标准化 Fix Plan 修复代码问题。当用户说"修复这些问题"、"按计划修复"、"fix these issues"、"处理评审反馈"、"code-fixer"时触发。接受来自 code-reviewer、checkstyle 或手动构造的 Fix Plan JSON，逐文件精确修复。辅助型 skill，不在 init-discuss-design-coding 主工作流中，可独立调用。
---

# 代码修复 Skill

按照标准化 Fix Plan 精确修复代码问题。本 skill 是**编排层**——解析、校验、分组 Fix Plan，然后派遣子 Agent 执行实际修复。

**宣告：** "我正在使用 devpipe:code-fixer 按 Fix Plan 修复代码。"

---

## Fix Plan 输入格式

Fix Plan 是标准化的 JSON 格式，定义了需要修复的代码问题列表：

```json
{
  "version": "1.0",
  "source": "<来源标识，如 code-reviewer / manual / checkstyle>",
  "working_directory": "<工作目录绝对路径>",
  "fixes": [
    {
      "id": "fix-001",
      "type": "format | import | naming | logic | style | doc | delete | replace | insert | rename",
      "severity": "critical | warning | suggestion",
      "file": "<文件相对路径>",
      "line": 42,
      "end_line": 45,
      "description": "<问题描述>",
      "fix_action": "<修改方案>",
      "context": "<可选：补充上下文>",
      "related_files": ["<仅 rename 类型使用>"]
    }
  ]
}
```

完整字段说明和示例参见 [Fix Plan Schema](references/fix-plan-schema.md)。

---

## 校验规则

解析 Fix Plan JSON 后，必须逐条校验以下规则，**任一违规则拒绝整个 Plan 并报错**：

1. `version` 必须为 `"1.0"`
2. `fixes` 必须是非空数组
3. 每个 fix 必须包含 `id`、`type`、`file`、`description`、`fix_action`
4. `type` 必须是以下枚举之一：`format`、`import`、`naming`、`logic`、`style`、`doc`、`delete`、`replace`、`insert`、`rename`
5. 非 `rename` 类型**禁止**包含 `related_files` 字段
6. `rename` 类型**必须**包含非空 `related_files` 数组
7. `line`（如提供）必须为非负整数（0 表示文件级操作）

校验失败时，输出所有违规条目的 id 和错误原因，格式：

```
Fix Plan 校验失败：
- fix-001: 缺少必填字段 fix_action
- fix-003: 非 rename 类型不允许包含 related_files
```

---

## 编排工作流

### 步骤 1：获取 Fix Plan

接受以下两种输入方式：

**方式 A：标准 JSON**

用户直接提供 Fix Plan JSON（内联或文件路径）。如果是文件路径，使用 Read 工具读取。

**方式 B：自然语言转换**

当用户输入不是标准 JSON 时（如"把第 42 行的 import 删掉"、"修复评审提到的命名问题"），将其转换为 Fix Plan JSON：

1. 从用户描述中提取：文件路径、行号、问题类型、修复方案
2. 如果信息不完整，使用 AskUserQuestion 工具补充：
   - 缺少文件路径 → "请提供需要修复的文件路径"
   - 缺少行号 → 设为 0（文件级操作）
   - 缺少修复方案 → "请描述期望的修改方式"
3. 生成 Fix Plan JSON，`source` 设为 `"manual"`
4. 将生成的 Fix Plan 展示给用户确认后再执行

### 步骤 2：校验 Fix Plan

按上述校验规则逐条检查。校验通过后输出摘要：

```
Fix Plan 校验通过：
- 来源：code-reviewer
- 修复项：8 个（critical: 3, warning: 4, suggestion: 1）
- 涉及文件：4 个
- 包含 rename 类型：1 个（影响 3 个关联文件）
```

### 步骤 3：分组与排序

1. 按 `file` 字段分组
2. 每组内按 `line` 降序排列（从文件底部开始修复，避免行号偏移影响后续修复）
3. 如果存在 `rename` 类型，将其定义文件排在最前，`related_files` 排在其后

### 步骤 4：派遣子 Agent 执行修复

读取 [fixer-agent-prompt.md](fixer-agent-prompt.md) 模板，为每批修复任务构造 Agent prompt。

**分批策略**：
- 每个 Agent 处理一批文件的修复（通常按文件分组，一个 Agent 处理 1-3 个文件）
- `rename` 类型的定义文件和所有 `related_files` 必须在同一个 Agent 中处理
- **串行执行**——同一时间只运行一个 Agent，避免文件冲突

**Agent 调用方式**：

```
Agent 工具参数：
- subagent_type: "general-purpose"
- description: "修复代码: <涉及文件简述>"
- prompt: （按 fixer-agent-prompt.md 模板构造，注入 Fix Plan 子集和 working_directory）
```

等待每个 Agent 完成后，检查返回结果再派遣下一个。

### 步骤 5：汇总修复报告

收集所有子 Agent 的返回结果，输出最终修复报告：

```
========== 修复报告 ==========
来源：code-reviewer
修复项总计：8 个

[ 已修复 ] 5 个
  - fix-001: ClusterServiceImpl.java:42 - 删除未使用的 import
  - fix-002: ClusterServiceImpl.java:88 - 方法命名改为 camelCase
  - fix-003: TopicServiceImpl.java:15 - 格式化缩进
  - fix-005: AclUtils.java:30 - 替换魔法数为常量
  - fix-007: ClusterDTO.java:10 → 重命名 getClsName → getClusterName（影响 3 个文件）

[ 已跳过 ] 2 个
  - fix-004: ConsumerServiceImpl.java:60 - fix_action 描述不明确，无法定位修改目标
  - fix-006: MonitorServiceImpl.java:120 - 目标行内容与描述不匹配

[ 失败 ] 1 个
  - fix-008: BillingServiceImpl.java:200 - Edit 工具执行失败（old_string 未匹配）
==============================
```

---

## 异常处理

| 情况 | 处理方式 |
|------|----------|
| Fix Plan JSON 解析失败 | 报错并提示用户检查 JSON 格式 |
| 校验不通过 | 列出所有违规项，拒绝执行 |
| 子 Agent 超时 | 记录该批次为失败，继续下一批次 |
| 子 Agent 报告部分跳过 | 在最终报告中标记跳过项及原因 |
| 用户中途取消 | 输出已完成的修复报告 |

---

## 注意事项

- 本 skill 是**辅助型 skill**，不在 `init → discuss → design → coding` 主工作流中
- 可被 `review-and-fix` agent 调用，也可由用户独立调用
- 不执行 git 操作、不运行构建或测试——仅修改代码文件
- 不创建或删除文件——仅编辑现有文件内容
