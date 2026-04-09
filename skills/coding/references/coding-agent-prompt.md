# Coding Agent Prompt 模板

本文件定义了 `devpipe:coding` 阶段派遣子 Agent 执行子任务时的标准 Prompt 模板。`devpipe:design` 在生成 `.devpipe/coding-plan.md` 时引用此模板路径，`devpipe:coding` 在执行时读取此模板并替换占位符。

---

## 占位符说明

| 占位符 | 说明 | 来源 |
|--------|------|------|
| `[WORKING_DIRECTORY]` | 工作目录绝对路径 | `.devpipe/coding-plan.md` 基本信息 |
| `[TASK_DESCRIPTION]` | 子任务的完整描述 | TaskGet 获取 |
| `[MODULE_NAME]` | 子任务所属模块名称 | `.devpipe/coding-plan.md` 子任务列表 |
| `[STANDARDS_DOCS]` | 适用的模块开发规范文档路径列表，每行一个 | `.devpipe/coding-plan.md` 适用的模块开发规范 |

---

## Agent Prompt

以下是传递给子 Agent 的完整 prompt 内容（`---` 之间的部分）：

---

IMPORTANT: 在以下目录工作: [WORKING_DIRECTORY]
所有文件操作必须限定在此目录下。

## 任务

[TASK_DESCRIPTION]

## 执行步骤

按以下顺序执行：

### a. 代码开发

先阅读以下文档理解编码规范和模块开发规范：
- `.claude/docs/development-doc.md`（通用编码规范，必读）
- [STANDARDS_DOCS]

然后根据任务描述实现功能代码。遵循已有代码模式，不要过度设计。

### b. 编写单测

先阅读 `.claude/docs/coverage-driven-testing.md` 理解单测编写要求，然后为新增代码编写单元测试。

### c. 执行单测

根据项目使用的构建系统执行相关模块的单元测试：

- Maven 项目: `mvn test -pl [MODULE_NAME] -q`
- Node.js 项目: `npm test`
- Go 项目: `go test ./...`
- Cargo 项目: `cargo test`

如果测试失败，分析原因并修复，然后重新执行。最多重试 2 次。

### d. 覆盖率检查

先 `git add` 所有新增文件，确保新增代码有足够的测试覆盖。

## 返回要求

完成后汇报以下信息：
- 修改的文件列表
- 新增的类和方法
- 测试结果（通过/失败数）
- 覆盖率数值
- 遇到的问题及解决方案（如有）

---

## 使用方式

### design 阶段

在 `.devpipe/coding-plan.md` 的"子任务 Agent 执行方式"章节中，引用此模板：

```markdown
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
- `[STANDARDS_DOCS]` → 适用的模块开发规范文档路径列表（每行一个，带 - 前缀）
```

### coding 阶段

```
Agent 工具参数：
- subagent_type: "general-purpose"
- description: "开发子任务: <子任务简述>"
- prompt: （读取本模板，替换占位符后的完整文本）
```
