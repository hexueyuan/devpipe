# Dashboard 列表页开发方案

## 子任务分解

| # | 子任务 | 模块 | 状态 |
|---|--------|------|------|
| 1 | Flask 项目骨架搭建 | app.py | 已完成 |
| 2 | worktree_service.py 数据层实现 | worktree_service.py | 已完成 |
| 3 | 列表页 Jinja2 模板 | templates/ | 已完成 |
| 4 | 阶段标签颜色样式 | static/css/ | 已完成 |

## 技术方案

基于 Flask 框架搭建 Dashboard Web 应用骨架，包含基本的项目结构、路由配置和静态资源组织。应用入口为 `app.py`，通过 Blueprint 或直接路由注册的方式暴露列表页端点。

数据层通过 `worktree_service.py` 实现，负责扫描本地 git worktree 目录，读取每个 worktree 下的 `.devpipe/context.json` 文件，提取分支名称、当前阶段等关键信息，组装为结构化数据返回给视图层。

前端使用 Jinja2 模板引擎渲染列表页，每个 worktree 以卡片形式展示。阶段标签通过 CSS 类名映射不同颜色，直观区分 init、discuss、design、coding、review-and-fix、summarize 等阶段状态。

## 验收标准

1. Flask 应用可正常启动并监听指定端口
2. 列表页正确显示所有 worktree 开发分支信息
3. 各阶段标签颜色正确区分，视觉清晰
