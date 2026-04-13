# 阶段文档查看器方案

## 子任务分解

| # | 子任务 | 模块 | 状态 |
|---|--------|------|------|
| 1 | STAGE_DOCUMENT_MAP 定义 | worktree_service.py | 已完成 |
| 2 | 文件读取逻辑 | worktree_service.py | 已完成 |
| 3 | Markdown 渲染为 HTML | app.py + templates/ | 已完成 |
| 4 | 进度条节点点击交互 | templates/ + static/js/ | 已完成 |
| 5 | 无文档占位文本 | templates/ | 已完成 |

## 技术方案

在 `worktree_service.py` 中定义 `STAGE_DOCUMENT_MAP` 常量，建立工作流阶段到对应产物文件的映射关系（如 discuss -> prd.md、design -> coding-plan.md、coding -> task-progress.md 等）。文件读取逻辑根据映射关系定位 `.devpipe/` 目录下的对应文件并返回原始 Markdown 内容。

在 `app.py` 中集成 Markdown 渲染库（如 markdown 或 mistune），将读取到的 Markdown 文本转换为 HTML 片段，传递给模板渲染。模板中使用 `|safe` 过滤器输出渲染后的 HTML 内容，确保格式正确。

前端通过 JavaScript 为进度条节点绑定点击事件，点击某个阶段节点时，通过 AJAX 请求加载对应阶段的文档内容并动态更新页面展示区域。当阶段尚无产出文档时，显示占位提示文本（如"该阶段暂无文档"），避免页面空白。

## 验收标准

1. 点击进度条阶段节点可查看对应阶段的产物文档
2. Markdown 文档正确渲染为格式化 HTML
3. 无文档的阶段显示友好的占位提示文本
