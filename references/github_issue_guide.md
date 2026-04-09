# GitHub Issue 使用指南

## 核心概念

GitHub Issues 是项目任务追踪工具。每个开发任务都应关联一个 GitHub Issue，确保代码变更可追溯。

## Commit Message 格式

```
#<Issue编号> Short English description.
```

**规范要求：**
- 描述必须是英文，不能包含中文
- 描述以英文句号 `.` 结尾
- 如果 Issue 标题是中文，翻译为简短的英文描述
- 使用 `#数字` 格式关联 Issue

示例：
```
#42 Refactor cluster deploy operation.
#108 Fix order amount calculation error.
```

多 Issue 关联：
```
#42 #56 Fix two related issues.
```

## 获取 Issue 编号

优先级：
1. 用户在提需求时直接提供（"Issue 42"、"#42"、Issue 链接）
2. 如果用户没提供，使用 `AskUserQuestion` 主动询问
3. 如果用户说没有 Issue，建议创建一个，但不强制

## 查询 Issue 信息

使用 `gh` CLI 查询 Issue 详情：

```bash
# 查看 Issue 详情
gh issue view <number> --json title,body,labels,state,url

# 列出 Issue
gh issue list --state open --limit 10
```

## 注意事项

- Issue 编号使用 `#数字` 格式（如 `#42`）
- commit message 中的描述必须是英文，将中文 Issue 标题翻译为简短英文
- 不要猜测 Issue 编号，宁可询问用户
- 确保 `gh auth status` 已登录
