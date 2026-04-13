# 阶段文档查看器 - 开发进度

## 子任务进度

| # | 子任务 | 模块 | 状态 |
|---|--------|------|------|
| 1 | STAGE_DOCUMENT_MAP 定义 | worktree_service.py | 已完成 |
| 2 | 文件读取逻辑 | worktree_service.py | 已完成 |
| 3 | Markdown 渲染为 HTML | app.py | 已完成 |
| 4 | 进度条节点点击交互 | templates/ | 已完成 |
| 5 | 无文档占位文本 | templates/ | 已完成 |

## 问题与解决方案记录

### 问题 1：容器内文件读取回退

阶段文档可能位于宿主机 worktree 目录或 Docker 容器内部。当本地文件路径不存在时，需要通过 docker exec cat 从容器内读取文件作为 fallback。解决方案是先尝试本地路径读取，捕获 FileNotFoundError 后自动切换到 docker exec 方式读取容器内对应路径的文件。
