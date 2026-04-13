# 详情页工作流时间和角色图标

## 基本信息

| 字段 | 值 |
|------|-----|
| 开发类型 | 优化重构 |
| 远程分支 | main |
| 本地分支 | refactor/workflow-time-icons |
| 开发日期 | 2026-03-17 |
| 完成日期 | 2026-03-17 |

## 原始需求

进度条仅展示阶段状态（已完成/进行中/待执行），缺少时间维度和角色信息。需要增加每个阶段的耗时显示和参与角色图标，让开发者了解时间分布和协作模式。

## 需求分析过程

context.json 的 `stage_timestamps` 字段记录了每个阶段的 started_at 和 ended_at。需要计算每个阶段的持续时间，格式化为"X秒/X分/X小时X分"。角色信息使用 emoji 标注：🤖(Agent)、👤🤖(人+Agent)。Timeline 分组也需要汇总耗时。

## 实现方案

在 worktree_service.py 中新增 `STAGE_META` 常量定义每个阶段的核心/非核心标记和角色信息。实现 `calculate_stage_duration()` 和 `format_duration()` 函数处理时间计算和格式化。`StageTimeInfo` 数据类扩展了 duration_seconds、duration_display、roles、role_desc 等字段。Timeline 分组增加总耗时汇总。

## 问题与解决方案

### 问题 1：ISO 8601 时间戳解析兼容性

`datetime.fromisoformat()` 在不同 Python 版本对时区格式支持不同。增加了 `parse_iso_timestamp()` 函数，支持多种格式的时间戳解析，包括带时区和不带时区两种格式。

## 反思与复盘

时间维度的加入使进度条从"状态可视化"升级为"过程可视化"。STAGE_META 的引入为每个阶段建立了完整的元数据体系，后续可以方便地扩展更多维度。
