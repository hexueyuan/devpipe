# 详情页工作流进度条方案

## 子任务分解

| # | 子任务 | 模块 | 状态 |
|---|--------|------|------|
| 1 | 阶段状态计算逻辑 | worktree_service.py | 已完成 |
| 2 | 进度条 HTML 和 CSS | templates/ + static/css/ | 已完成 |
| 3 | dev_type 阶段适配 | worktree_service.py | 已完成 |
| 4 | Timeline 分组展示 | worktree_service.py + templates/ | 已完成 |

## 技术方案

在 `worktree_service.py` 中实现阶段状态计算逻辑，根据 `context.json` 中的 `stage` 和 `stage_completed` 字段，判断各阶段的状态（已完成、进行中、未开始）。状态计算需考虑阶段的线性顺序依赖关系。

进度条采用横向步骤条设计，每个节点代表一个工作流阶段，通过 CSS 类名区分已完成（绿色）、进行中（蓝色）和未开始（灰色）三种状态。节点之间用连接线串联，形成完整的流水线视觉效果。

针对不同 `dev_type` 适配不同的阶段序列：新功能（feature）包含 discuss 阶段，完整流程为 init -> discuss -> design -> coding -> review-and-fix -> summarize；bugfix 和 refactor 跳过 discuss 阶段。Timeline 分组将阶段按逻辑归类展示，提供更清晰的进度概览。

## 验收标准

1. 进度条正确反映当前工作流阶段状态
2. 新功能类型包含 discuss 阶段，bugfix/refactor 类型跳过 discuss
3. Timeline 分组展示逻辑正确，阶段归类清晰
