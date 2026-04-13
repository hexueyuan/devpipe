# 阶段文档查看器

## 基本信息

| 字段 | 值 |
|------|-----|
| 开发类型 | 新功能 |
| 远程分支 | main |
| 本地分支 | feature/stage-document-viewer |
| 开发日期 | 2026-03-14 |
| 完成日期 | 2026-03-14 |

## 原始需求

进度条只展示状态，开发者还需要查看每个阶段产生的文档内容（prd.md、coding-plan.md、task-progress.md 等），了解开发过程的详细记录。

## 需求分析过程

建立阶段到文档的映射关系：discuss→prd.md、design→coding-plan.md、coding→task-progress.md、review-and-fix→review-status.md、summarize→summary.md。文件读取需要支持本地和容器两种场景（worktree 在容器内时通过 docker exec 读取）。Markdown 渲染选用 Python markdown 库。

## 实现方案

定义 `STAGE_DOCUMENT_MAP` 常量管理映射关系。`_read_devflow_file()` 实现多路径文件读取：优先本地 `.devpipe/` 目录，回退容器内读取。`get_stage_documents()` 为详情页提供完整的阶段文档数据。前端通过点击进度条节点触发文档加载，无文档时显示占位文本。

## 问题与解决方案

### 问题 1：容器内文件读取回退

worktree 可能在 Docker 容器内，本地文件不存在时需要通过 `docker exec cat` 读取。实现了 `_docker_cat()` 辅助函数，并增加容器运行状态检查，避免对已停止容器的无效调用。

## 反思与复盘

文档查看器打通了"进度条 → 文件内容"的完整链路。多级文件读取回退机制增强了系统的健壮性。STAGE_DOCUMENT_MAP 的常量化管理使映射关系清晰可维护。
