# 列表页标签展示优化方案

## 子任务分解

| # | 子任务 | 模块 | 状态 |
|---|--------|------|------|
| 1 | 解析 dev_type 和 github_issue 字段 | worktree_service.py | 已完成 |
| 2 | 标签 HTML 和 CSS 实现 | templates/ + static/css/ | 已完成 |
| 3 | Issue 链接跳转 | templates/ | 已完成 |

## 技术方案

在 `worktree_service.py` 数据层中增加对 `context.json` 内 `dev_type` 和 `github_issue` 字段的解析逻辑。`dev_type` 用于区分 feature、fix、refactor 等开发类型，`github_issue` 存储关联的 GitHub Issue 编号和 URL。

前端标签组件采用 badge 样式设计，`dev_type` 以不同颜色的标签展示（如 feature 绿色、fix 红色、refactor 蓝色）。HTML 结构使用 `<span>` 标签配合 CSS 类名实现样式切换，保持语义清晰。

GitHub Issue 编号以可点击链接形式呈现，点击后在新标签页跳转到对应的 GitHub Issue 页面。链接 URL 根据仓库信息和 Issue 编号动态拼接。

## 验收标准

1. dev_type 标签正确显示并以不同颜色区分类型
2. GitHub Issue 编号以链接形式展示，点击可跳转到对应 Issue 页面
