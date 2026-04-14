# Fix Plan Schema 参考文档

本文档是 `devpipe:code-fixer` skill 的 Fix Plan 格式完整参考，供调用者（如 `review-and-fix` agent、checkstyle 工具、用户手动构造）查阅。

---

## 完整字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `version` | string | 是 | 固定值 `"1.0"` |
| `source` | string | 否 | 来源标识，如 `"code-reviewer"`、`"manual"`、`"checkstyle"` |
| `working_directory` | string | 否 | 工作目录绝对路径，默认为当前目录 |
| `fixes` | array | 是 | 非空修复条目数组 |

### fix 条目字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 唯一标识，建议 `fix-001` 递增 |
| `type` | string | 是 | 修复类型枚举，见下表 |
| `severity` | string | 否 | 严重程度：`critical` / `warning` / `suggestion`，默认 `warning` |
| `file` | string | 是 | 文件路径（相对于 working_directory） |
| `line` | integer | 否 | 目标行号，非负整数。0 表示文件级操作，默认 0 |
| `end_line` | integer | 否 | 结束行号，用于范围操作。默认等于 `line` |
| `description` | string | 是 | 问题描述 |
| `fix_action` | string | 是 | 修改方案，描述具体怎么改 |
| `context` | string | 否 | 补充上下文信息 |
| `related_files` | array | 条件必填 | 仅 `rename` 类型必填且非空，其他类型禁止使用 |

---

## type 枚举详解

| type | 作用范围 | 说明 | 典型场景 |
|------|----------|------|----------|
| `format` | 单文件 | 缩进、空格、空行格式调整 | 缩进从 tab 改为 4 空格 |
| `import` | 单文件 | import 语句的增加、删除、排序 | 删除未使用的 import |
| `naming` | 单文件 | 文件内变量、方法、参数重命名 | 方法名改为 camelCase |
| `logic` | 单文件 | 条件判断、异常处理等逻辑修复 | 添加 null 检查 |
| `style` | 单文件 | 编码规范修复（FQN、魔法数等） | 魔法数提取为常量 |
| `doc` | 单文件 | Javadoc、docstring、JSDoc 等注释修复 | 补充函数文档注释 |
| `optimization` | 单文件 | 代码复用、效率优化、简化表达式 | 提取重复逻辑为公共方法 |
| `delete` | 单文件 | 删除冗余代码 | 删除废弃方法 |
| `replace` | 单文件 | 通用代码替换 | 将旧 API 调用替换为新 API |
| `insert` | 单文件 | 通用代码插入 | 在方法开头插入参数校验 |
| `rename` | **多文件** | 唯一允许跨文件的类型 | 重命名公共方法，更新所有调用方 |

### 作用范围约束

- 除 `rename` 外，所有类型严格限制在**单文件**内操作
- `rename` 类型必须在 `related_files` 中列出所有需要同步修改的文件
- 子 Agent 会强制校验：非 rename 类型禁止操作 `file` 以外的文件

---

## 完整 JSON 示例

### 示例 1：Java — import 清理

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
      "fix_action": "删除第 3 行的 import javax.annotation.Nullable 和第 5 行的 import java.util.LinkedList"
    }
  ]
}
```

### 示例 2：Go — logic 修复（错误处理缺失）

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
      "type": "naming",
      "severity": "warning",
      "file": "internal/handler/cluster.go",
      "line": 12,
      "description": "导出函数名 Doit 不符合 Go 命名惯例，应使用描述性名称",
      "fix_action": "将 func Doit() 重命名为 func ReconcileCluster()"
    }
  ]
}
```

### 示例 3：Python — import 清理 + style 修复

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
      "fix_action": "删除第 4 行的 import json"
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
      "fix_action": "将第 58 行的 except: 改为 except (ValueError, KeyError) as e:，并在 except 块内添加 logger.warning(f\"parse failed: {e}\")"
    }
  ]
}
```

### 示例 4：JavaScript/TypeScript — 混合类型

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
      "fix_action": "删除第 2 行的 import { Logger } from '../utils/logger'"
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
      "fix_action": "将第 15 行的 if (user.role == 'admin') 改为 if (user.role === 'admin')"
    },
    {
      "id": "fix-004",
      "type": "delete",
      "severity": "suggestion",
      "file": "src/services/userService.ts",
      "line": 80,
      "end_line": 95,
      "description": "函数 legacyAuth() 已被 @deprecated 标记且无调用方",
      "fix_action": "删除第 80-95 行的 legacyAuth 函数"
    }
  ]
}
```

### 示例 5：rename（跨文件重命名，Go 项目）

```json
{
  "version": "1.0",
  "source": "code-reviewer",
  "working_directory": "/Users/dev/my-go-project",
  "fixes": [
    {
      "id": "fix-001",
      "type": "rename",
      "severity": "suggestion",
      "file": "internal/model/cluster.go",
      "line": 18,
      "description": "导出类型名 CInfo 过于简略，不符合 Go 命名惯例",
      "fix_action": "将 type CInfo struct 重命名为 type ClusterInfo struct，同步更新所有引用",
      "related_files": [
        "internal/handler/cluster.go",
        "internal/service/cluster_service.go",
        "internal/api/cluster_controller.go"
      ]
    }
  ]
}
```

### 示例 6：混合语言 — Java 跨文件重命名

```json
{
  "version": "1.0",
  "source": "code-reviewer",
  "working_directory": "/Users/dev/my-java-project",
  "fixes": [
    {
      "id": "fix-001",
      "type": "rename",
      "severity": "suggestion",
      "file": "src/main/java/com/example/model/dto/ClusterDTO.java",
      "line": 42,
      "description": "方法名 getClsName() 不符合命名规范，应使用完整单词",
      "fix_action": "将 getClsName() 重命名为 getClusterName()，同步修改 setter setClsName() 为 setClusterName()",
      "related_files": [
        "src/main/java/com/example/converter/ClusterConverter.java",
        "src/main/java/com/example/service/impl/ClusterServiceImpl.java",
        "src/main/java/com/example/controller/ClusterController.java"
      ]
    }
  ]
}
```

---

## 从 code-reviewer 输出到 Fix Plan 的映射规则

`review-and-fix` agent 中的 code-reviewer 输出格式：

```
🔴 必须修改：
- 文件路径:行号 - 问题描述 → 修改方案

🟡 建议修改：
- 文件路径:行号 - 问题描述 → 修改方案
```

映射规则：

| code-reviewer 字段 | Fix Plan 字段 | 映射方式 |
|---|---|---|
| 文件路径 | `file` | 直接使用 |
| 行号 | `line` | 直接使用 |
| 问题描述 | `description` | 直接使用 |
| 修改方案（→ 后面的内容） | `fix_action` | 直接使用 |
| 红点 🔴 | `severity: "critical"` | |
| 黄点 🟡 | `severity: "warning"` | |
| 绿点 🟢 | `severity: "suggestion"` | |
| — | `type` | 根据问题描述推断：包含 "import" → `import`，包含 "命名/rename" → `naming` 或 `rename`，包含 "格式/缩进" → `format`，其他 → `replace` |
| — | `id` | 自动生成 `fix-001` 递增 |
| — | `source` | 固定为 `"code-reviewer"` |
| — | `related_files` | 仅当推断为 `rename` 类型时，需从 code-reviewer 的上下文中提取引用文件列表 |
