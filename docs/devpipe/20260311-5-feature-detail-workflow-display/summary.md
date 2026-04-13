# 详情页工作流进度条

## 基本信息

| 字段 | 值 |
|------|-----|
| 开发类型 | 新功能 |
| 远程分支 | main |
| 本地分支 | feature/detail-workflow-display |
| 开发日期 | 2026-03-11 |
| 完成日期 | 2026-03-11 |

## 原始需求

详情页缺少对工作流阶段进度的可视化展示，开发者无法直观看到当前分支在工作流中的位置。需要添加阶段进度条，用颜色区分不同状态。

## 需求分析过程

devpipe 工作流有两种路径：新功能（含 discuss）和 Bugfix/优化重构（跳过 discuss）。进度条需要根据 dev_type 动态适配阶段列表。状态判断逻辑：根据 stage 在阶段列表中的位置，索引之前为已完成、当前索引为进行中、之后为待执行。特殊处理 done 状态（所有阶段标记为已完成）。

## 实现方案

在 worktree_service.py 中实现 `get_stage_times()` 和 `get_timeline_groups()` 函数。`get_stage_times()` 根据 dev_type 确定适用阶段列表，计算每个阶段的状态。`get_timeline_groups()` 将阶段分为三组：环境准备(init)、工作流程(discuss/design/coding/review-and-fix)、总结复盘(summarize)。模板使用水平进度条展示，CSS 实现已完成(绿)、进行中(蓝色脉冲)、待执行(灰)三种状态样式。

## 问题与解决方案

### 问题 1：Bugfix 和优化重构跳过 discuss 阶段

当 dev_type 不是"新功能"时，阶段列表需要从 `applicable_stages` 中移除 discuss。同时 Timeline 的"工作流程"分组也需要同步过滤，避免出现空阶段节点。

## 反思与复盘

进度条可视化大幅提升了详情页的直观性。阶段状态机的逻辑抽象到数据层，使模板保持简洁。Timeline 分组的设计为后续增加时间信息做好了准备。
