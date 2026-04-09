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
| `doc` | 单文件 | Javadoc、注释修复 | 补充方法 Javadoc |
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

### 示例 1：import 清理

```json
{
  "version": "1.0",
  "source": "code-reviewer",
  "working_directory": "/Users/dev/my-project",
  "fixes": [
    {
      "id": "fix-001",
      "type": "import",
      "severity": "warning",
      "file": "src/main/java/com/example/logic/service/impl/ClusterServiceImpl.java",
      "line": 3,
      "end_line": 5,
      "description": "存在未使用的 import：javax.annotation.Nullable、java.util.LinkedList",
      "fix_action": "删除第 3 行的 import javax.annotation.Nullable 和第 5 行的 import java.util.LinkedList"
    }
  ]
}
```

### 示例 2：style 修复（魔法数提取）

```json
{
  "version": "1.0",
  "source": "code-reviewer",
  "working_directory": "/Users/dev/my-project",
  "fixes": [
    {
      "id": "fix-001",
      "type": "style",
      "severity": "warning",
      "file": "src/main/java/com/example/admin/master/module/cluster/ClusterChecker.java",
      "line": 88,
      "description": "魔法数 3600000 直接出现在代码中",
      "fix_action": "将 3600000 提取为类常量 private static final long CHECK_INTERVAL_MS = 3600000L，替换原处引用"
    }
  ]
}
```

### 示例 3：rename（跨文件重命名）

```json
{
  "version": "1.0",
  "source": "code-reviewer",
  "working_directory": "/Users/dev/my-project",
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
        "src/main/java/com/example/logic/converter/ClusterConverter.java",
        "src/main/java/com/example/logic/service/impl/ClusterServiceImpl.java",
        "src/main/java/com/example/logic/console/controller/view/ClusterController.java"
      ]
    }
  ]
}
```

### 示例 4：混合类型

```json
{
  "version": "1.0",
  "source": "code-reviewer",
  "working_directory": "/Users/dev/my-project",
  "fixes": [
    {
      "id": "fix-001",
      "type": "import",
      "severity": "warning",
      "file": "src/main/java/com/example/logic/service/impl/TopicServiceImpl.java",
      "line": 8,
      "description": "未使用的 import java.util.LinkedHashMap",
      "fix_action": "删除 import java.util.LinkedHashMap"
    },
    {
      "id": "fix-002",
      "type": "logic",
      "severity": "critical",
      "file": "src/main/java/com/example/logic/service/impl/TopicServiceImpl.java",
      "line": 120,
      "end_line": 125,
      "description": "缺少 null 检查，可能抛出 NPE",
      "fix_action": "在第 120 行的 topicConfig.getTopicName() 调用前添加 null 检查：if (topicConfig == null) { throw new IllegalArgumentException(\"topicConfig must not be null\"); }"
    },
    {
      "id": "fix-003",
      "type": "style",
      "severity": "warning",
      "file": "src/main/java/com/example/admin/action/UpgradeAction.java",
      "line": 55,
      "description": "使用了全限定类名 com.example.model.dto.ClusterDTO",
      "fix_action": "在文件头添加 import com.example.model.dto.ClusterDTO，将第 55 行的全限定名替换为 ClusterDTO"
    },
    {
      "id": "fix-004",
      "type": "rename",
      "severity": "suggestion",
      "file": "src/main/java/com/example/util/AclUtils.java",
      "line": 30,
      "description": "方法名 chk() 含义不明确",
      "fix_action": "将 chk() 重命名为 checkPermission()",
      "related_files": [
        "src/main/java/com/example/logic/service/impl/AclServiceImpl.java"
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
