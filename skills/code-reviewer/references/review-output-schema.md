# 评审输出 Schema 参考文档

本文档是 `devpipe:code-reviewer` skill 的评审输出格式完整参考，定义了评审子 Agent 的结构化输出格式，以及从评审输出到 Fix Plan JSON 的映射规则。

---

## 评审子 Agent 输出格式

评审子 Agent 的输出是一个 JSON 数组，每个元素代表一个发现的问题：

```json
[
  {
    "file_path": "relative/path/to/File.java",
    "line": 42,
    "end_line": 45,
    "category": "import",
    "severity": "must_fix",
    "source": "lint",
    "standard_reference": "JAVA009: 未使用的 import 必须删除",
    "description": "存在未使用的 import：javax.annotation.Nullable",
    "fix_suggestion": "删除第 42 行的 import javax.annotation.Nullable",
    "referenced_files": []
  }
]
```

### 完整字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_path` | string | 是 | 文件路径（相对于 working_directory） |
| `line` | integer | 是 | 问题所在行号，非负整数。0 表示文件级问题 |
| `end_line` | integer | 否 | 问题结束行号，用于范围性问题。默认等于 `line` |
| `category` | string | 是 | 问题分类枚举，见下表 |
| `severity` | string | 是 | 严重程度枚举：`must_fix` / `should_fix` / `nice_to_have` |
| `source` | string | 是 | 发现来源：`lint`（自动化工具）/ `manual`（人工静态分析） |
| `standard_reference` | string | 否 | 违反的具体规范条目（如 "JAVA009"），未引用规范时留空 |
| `description` | string | 是 | 问题描述：是什么问题 |
| `fix_suggestion` | string | 是 | 修复方案：如何修复，尽可能给出具体代码 |
| `referenced_files` | array | 否 | 关联文件列表，仅当问题涉及跨文件重命名时填写 |

---

## category 枚举详解

| category | 说明 | 典型场景 |
|----------|------|----------|
| `import` | import 语句问题 | 未使用的 import、缺少 import、import 顺序 |
| `naming` | 命名规范问题 | 方法/变量名不符合 camelCase、类名不符合 PascalCase |
| `format` | 格式问题 | 缩进不一致、空行过多/过少、空格问题 |
| `logic` | 逻辑问题 | 缺少 null 检查、条件判断错误、异常处理不当、资源泄漏 |
| `style` | 编码风格问题 | 全限定类名（FQN）、魔法数、过长方法、过多参数 |
| `doc` | 文档/注释问题 | 缺少 Javadoc、注释与代码不一致、TODO 未处理 |
| `other` | 其他问题 | 不属于以上分类的问题 |

---

## severity 校准标准

### `must_fix` — 必须修改

用于以下场景：
- Bug 或潜在 NPE
- 资源泄漏（未关闭的流、连接等）
- 安全漏洞
- 违反代码规范中标记为"强制"/"必须"的规则
- 编译错误或运行时必然异常

### `should_fix` — 建议修改

用于以下场景：
- 编码风格违规（未使用 import、FQN、魔法数等）
- 命名不规范
- 公共 API 缺少文档
- 违反代码规范中标记为"建议"/"推荐"的规则
- 可读性问题

### `nice_to_have` — 可优化

用于以下场景：
- 微小的可读性改善
- 可选的性能优化
- 代码结构建议（如提取公共方法）
- 非强制的最佳实践

---

## 从评审输出到 Fix Plan JSON 的映射规则

`devpipe:code-reviewer` 的 SKILL.md 编排层在步骤 5 中使用以下规则将评审输出转换为标准 Fix Plan JSON。

### 顶层字段

| Fix Plan 字段 | 值 | 说明 |
|---|---|---|
| `version` | `"1.0"` | 固定值 |
| `source` | `"code-reviewer"` | 固定值，标识来源为 code-reviewer skill |
| `working_directory` | 步骤 1 检测到的项目根目录绝对路径 | |
| `fixes` | 转换后的修复条目数组 | 仅包含 `critical` 和用户确认的 `warning` 条目 |

### 条目字段映射

| 评审输出字段 | Fix Plan 字段 | 映射方式 |
|---|---|---|
| `file_path` | `file` | 直接使用 |
| `line` | `line` | 直接使用 |
| `end_line` | `end_line` | 直接使用（如有） |
| `description` | `description` | 直接使用 |
| `fix_suggestion` | `fix_action` | 直接使用 |
| `standard_reference` | `context` | 作为补充上下文（如有） |
| `severity` | `severity` | 见 severity 映射表 |
| `category` | `type` | 见 category→type 映射表 |
| — | `id` | 自动递增 `fix-001`、`fix-002`... |
| `referenced_files` | `related_files` | 仅当 type 为 `rename` 时使用 |

### severity 映射

| 评审 severity | Fix Plan severity |
|---|---|
| `must_fix` | `critical` |
| `should_fix` | `warning` |
| `nice_to_have` | `suggestion` |

### category → type 映射

| 评审 category | Fix Plan type | 附加规则 |
|---|---|---|
| `import` | `import` | — |
| `naming` | `naming`（单文件）或 `rename`（跨文件） | 如果 `referenced_files` 非空，使用 `rename` 并填充 `related_files` |
| `format` | `format` | — |
| `logic` | `logic` | — |
| `style` | `style` | — |
| `doc` | `doc` | — |
| `other` | `replace` | 默认映射 |

### 纳入 Fix Plan 的条件

评审输出的所有问题并非全部纳入 Fix Plan，遵循以下规则：

1. `severity: "must_fix"` → **自动纳入**（映射为 `critical`）
2. `severity: "should_fix"` → **需要用户确认**后纳入（映射为 `warning`）
3. `severity: "nice_to_have"` → **默认不纳入**，仅在用户主动要求时纳入（映射为 `suggestion`）

---

## 完整转换示例

### 示例 1：Java — import 清理 + logic 修复 + 跨文件重命名

#### 评审子 Agent 输出

```json
[
  {
    "file_path": "src/main/java/com/example/service/impl/ClusterServiceImpl.java",
    "line": 3,
    "end_line": 5,
    "category": "import",
    "severity": "should_fix",
    "source": "lint",
    "standard_reference": "JAVA009: 未使用的 import 必须删除",
    "description": "存在未使用的 import：javax.annotation.Nullable、java.util.LinkedList",
    "fix_suggestion": "删除第 3 行的 import javax.annotation.Nullable 和第 5 行的 import java.util.LinkedList",
    "referenced_files": []
  },
  {
    "file_path": "src/main/java/com/example/service/impl/TopicServiceImpl.java",
    "line": 120,
    "end_line": 125,
    "category": "logic",
    "severity": "must_fix",
    "source": "manual",
    "standard_reference": "",
    "description": "缺少 null 检查，topicConfig 为 null 时将抛出 NPE",
    "fix_suggestion": "在第 120 行的 topicConfig.getTopicName() 调用前添加 null 检查：if (topicConfig == null) { throw new IllegalArgumentException(\"topicConfig must not be null\"); }",
    "referenced_files": []
  },
  {
    "file_path": "src/main/java/com/example/util/AclUtils.java",
    "line": 30,
    "end_line": 30,
    "category": "naming",
    "severity": "should_fix",
    "source": "manual",
    "standard_reference": "JAVA030: 方法名应使用完整的、有意义的英文单词",
    "description": "方法名 chk() 含义不明确",
    "fix_suggestion": "将 chk() 重命名为 checkPermission()",
    "referenced_files": [
      "src/main/java/com/example/service/impl/AclServiceImpl.java"
    ]
  }
]
```

#### 转换后的 Fix Plan JSON

（假设用户确认了所有 `should_fix` 项）

```json
{
  "version": "1.0",
  "source": "code-reviewer",
  "working_directory": "/Users/dev/my-java-project",
  "fixes": [
    {
      "id": "fix-001",
      "type": "import",
      "severity": "warning",
      "file": "src/main/java/com/example/service/impl/ClusterServiceImpl.java",
      "line": 3,
      "end_line": 5,
      "description": "存在未使用的 import：javax.annotation.Nullable、java.util.LinkedList",
      "fix_action": "删除第 3 行的 import javax.annotation.Nullable 和第 5 行的 import java.util.LinkedList",
      "context": "JAVA009: 未使用的 import 必须删除"
    },
    {
      "id": "fix-002",
      "type": "logic",
      "severity": "critical",
      "file": "src/main/java/com/example/service/impl/TopicServiceImpl.java",
      "line": 120,
      "end_line": 125,
      "description": "缺少 null 检查，topicConfig 为 null 时将抛出 NPE",
      "fix_action": "在第 120 行的 topicConfig.getTopicName() 调用前添加 null 检查：if (topicConfig == null) { throw new IllegalArgumentException(\"topicConfig must not be null\"); }"
    },
    {
      "id": "fix-003",
      "type": "rename",
      "severity": "warning",
      "file": "src/main/java/com/example/util/AclUtils.java",
      "line": 30,
      "description": "方法名 chk() 含义不明确",
      "fix_action": "将 chk() 重命名为 checkPermission()",
      "context": "JAVA030: 方法名应使用完整的、有意义的英文单词",
      "related_files": [
        "src/main/java/com/example/service/impl/AclServiceImpl.java"
      ]
    }
  ]
}
```

### 示例 2：Go — logic 修复（错误处理缺失）+ naming

#### 评审子 Agent 输出

```json
[
  {
    "file_path": "internal/handler/cluster.go",
    "line": 45,
    "end_line": 47,
    "category": "logic",
    "severity": "must_fix",
    "source": "manual",
    "standard_reference": "",
    "description": "os.Open 返回的 error 未检查，可能导致 nil pointer dereference",
    "fix_suggestion": "将第 45 行的 f, _ := os.Open(path) 改为 f, err := os.Open(path)，并在下一行添加 if err != nil { return fmt.Errorf(\"open config: %w\", err) }",
    "referenced_files": []
  },
  {
    "file_path": "internal/handler/cluster.go",
    "line": 12,
    "end_line": 12,
    "category": "naming",
    "severity": "should_fix",
    "source": "manual",
    "standard_reference": "Go Code Review Comments: exported names should be descriptive",
    "description": "导出函数名 Doit 不符合 Go 命名惯例，应使用描述性名称",
    "fix_suggestion": "将 func Doit() 重命名为 func ReconcileCluster()",
    "referenced_files": [
      "internal/service/cluster_service.go",
      "cmd/server/main.go"
    ]
  }
]
```

#### 转换后的 Fix Plan JSON

（假设用户确认了所有 `should_fix` 项）

```json
{
  "version": "1.0",
  "source": "code-reviewer",
  "working_directory": "/Users/dev/my-go-project",
  "fixes": [
    {
      "id": "fix-001",
      "type": "logic",
      "severity": "critical",
      "file": "internal/handler/cluster.go",
      "line": 45,
      "end_line": 47,
      "description": "os.Open 返回的 error 未检查，可能导致 nil pointer dereference",
      "fix_action": "将第 45 行的 f, _ := os.Open(path) 改为 f, err := os.Open(path)，并在下一行添加 if err != nil { return fmt.Errorf(\"open config: %w\", err) }"
    },
    {
      "id": "fix-002",
      "type": "rename",
      "severity": "warning",
      "file": "internal/handler/cluster.go",
      "line": 12,
      "description": "导出函数名 Doit 不符合 Go 命名惯例，应使用描述性名称",
      "fix_action": "将 func Doit() 重命名为 func ReconcileCluster()",
      "context": "Go Code Review Comments: exported names should be descriptive",
      "related_files": [
        "internal/service/cluster_service.go",
        "cmd/server/main.go"
      ]
    }
  ]
}
```

### 示例 3：Python — import 清理 + style（魔法数）+ logic（bare except）

#### 评审子 Agent 输出

```json
[
  {
    "file_path": "src/services/user_service.py",
    "line": 4,
    "end_line": 4,
    "category": "import",
    "severity": "should_fix",
    "source": "lint",
    "standard_reference": "F401: imported but unused",
    "description": "未使用的 import：import json",
    "fix_suggestion": "删除第 4 行的 import json",
    "referenced_files": []
  },
  {
    "file_path": "src/services/user_service.py",
    "line": 32,
    "end_line": 32,
    "category": "style",
    "severity": "should_fix",
    "source": "manual",
    "standard_reference": "",
    "description": "魔法数 86400 直接出现在代码中",
    "fix_suggestion": "在文件顶部（import 之后）添加常量 SECONDS_PER_DAY = 86400，替换第 32 行的 86400",
    "referenced_files": []
  },
  {
    "file_path": "src/services/user_service.py",
    "line": 58,
    "end_line": 60,
    "category": "logic",
    "severity": "must_fix",
    "source": "manual",
    "standard_reference": "E722: do not use bare except",
    "description": "捕获了 bare except，会吞掉 KeyboardInterrupt 等系统异常",
    "fix_suggestion": "将第 58 行的 except: 改为 except (ValueError, KeyError) as e:，并在 except 块内添加 logger.warning(f\"parse failed: {e}\")",
    "referenced_files": []
  }
]
```

#### 转换后的 Fix Plan JSON

（假设用户确认了所有 `should_fix` 项）

```json
{
  "version": "1.0",
  "source": "code-reviewer",
  "working_directory": "/Users/dev/my-python-project",
  "fixes": [
    {
      "id": "fix-001",
      "type": "import",
      "severity": "warning",
      "file": "src/services/user_service.py",
      "line": 4,
      "description": "未使用的 import：import json",
      "fix_action": "删除第 4 行的 import json",
      "context": "F401: imported but unused"
    },
    {
      "id": "fix-002",
      "type": "style",
      "severity": "warning",
      "file": "src/services/user_service.py",
      "line": 32,
      "description": "魔法数 86400 直接出现在代码中",
      "fix_action": "在文件顶部（import 之后）添加常量 SECONDS_PER_DAY = 86400，替换第 32 行的 86400"
    },
    {
      "id": "fix-003",
      "type": "logic",
      "severity": "critical",
      "file": "src/services/user_service.py",
      "line": 58,
      "end_line": 60,
      "description": "捕获了 bare except，会吞掉 KeyboardInterrupt 等系统异常",
      "fix_action": "将第 58 行的 except: 改为 except (ValueError, KeyError) as e:，并在 except 块内添加 logger.warning(f\"parse failed: {e}\")",
      "context": "E722: do not use bare except"
    }
  ]
}
```

### 示例 4：JavaScript/TypeScript — import + logic（缺少 await）+ style（== vs ===）+ delete

#### 评审子 Agent 输出

```json
[
  {
    "file_path": "src/controllers/authController.ts",
    "line": 2,
    "end_line": 2,
    "category": "import",
    "severity": "should_fix",
    "source": "lint",
    "standard_reference": "no-unused-imports",
    "description": "未使用的 import：import { Logger } from '../utils/logger'",
    "fix_suggestion": "删除第 2 行的 import { Logger } from '../utils/logger'",
    "referenced_files": []
  },
  {
    "file_path": "src/controllers/authController.ts",
    "line": 37,
    "end_line": 37,
    "category": "logic",
    "severity": "must_fix",
    "source": "manual",
    "standard_reference": "",
    "description": "await 缺失，validateToken 返回 Promise 但未 await，导致条件判断永远为 truthy",
    "fix_suggestion": "将第 37 行的 if (validateToken(token)) 改为 if (await validateToken(token))",
    "referenced_files": []
  },
  {
    "file_path": "src/services/userService.ts",
    "line": 15,
    "end_line": 15,
    "category": "style",
    "severity": "should_fix",
    "source": "lint",
    "standard_reference": "eqeqeq: use === instead of ==",
    "description": "使用 == 进行比较，应使用严格等于 ===",
    "fix_suggestion": "将第 15 行的 if (user.role == 'admin') 改为 if (user.role === 'admin')",
    "referenced_files": []
  },
  {
    "file_path": "src/services/userService.ts",
    "line": 80,
    "end_line": 95,
    "category": "other",
    "severity": "nice_to_have",
    "source": "manual",
    "standard_reference": "",
    "description": "函数 legacyAuth() 已被 @deprecated 标记且无调用方",
    "fix_suggestion": "删除第 80-95 行的 legacyAuth 函数",
    "referenced_files": []
  }
]
```

#### 转换后的 Fix Plan JSON

（假设用户确认了所有 `should_fix` 项，`nice_to_have` 默认不纳入）

```json
{
  "version": "1.0",
  "source": "code-reviewer",
  "working_directory": "/Users/dev/my-node-project",
  "fixes": [
    {
      "id": "fix-001",
      "type": "import",
      "severity": "warning",
      "file": "src/controllers/authController.ts",
      "line": 2,
      "description": "未使用的 import：import { Logger } from '../utils/logger'",
      "fix_action": "删除第 2 行的 import { Logger } from '../utils/logger'",
      "context": "no-unused-imports"
    },
    {
      "id": "fix-002",
      "type": "logic",
      "severity": "critical",
      "file": "src/controllers/authController.ts",
      "line": 37,
      "description": "await 缺失，validateToken 返回 Promise 但未 await，导致条件判断永远为 truthy",
      "fix_action": "将第 37 行的 if (validateToken(token)) 改为 if (await validateToken(token))"
    },
    {
      "id": "fix-003",
      "type": "style",
      "severity": "warning",
      "file": "src/services/userService.ts",
      "line": 15,
      "description": "使用 == 进行比较，应使用严格等于 ===",
      "fix_action": "将第 15 行的 if (user.role == 'admin') 改为 if (user.role === 'admin')",
      "context": "eqeqeq: use === instead of =="
    }
  ]
}
```

> 注意：`nice_to_have` 的 legacyAuth 删除建议未纳入 Fix Plan，仅在评审报告中展示。
