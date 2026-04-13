# 详情页工作流进度条 - 开发进度

## 子任务进度

| # | 子任务 | 模块 | 状态 |
|---|--------|------|------|
| 1 | 阶段状态计算逻辑 | worktree_service.py | 已完成 |
| 2 | 进度条 HTML 和 CSS | templates/ | 已完成 |
| 3 | dev_type 阶段适配 | worktree_service.py | 已完成 |
| 4 | Timeline 分组展示 | templates/ | 已完成 |

## 问题与解决方案记录

### 问题 1：优化重构和 Bugfix 跳过 discuss 阶段的处理

不同 dev_type 的工作流阶段列表不同：新功能包含完整的 init-discuss-design-coding-review-summarize 六个阶段，而优化重构和 Bugfix 跳过 discuss 阶段。解决方案是根据 dev_type 动态过滤阶段列表，在进度条渲染时只展示当前 dev_type 对应的阶段节点。
