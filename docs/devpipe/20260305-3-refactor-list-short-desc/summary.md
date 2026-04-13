# 列表页显示功能简短描述

## 基本信息

| 字段 | 值 |
|------|-----|
| 开发类型 | 优化重构 |
| 远程分支 | main |
| 本地分支 | refactor/list-short-desc |
| 开发日期 | 2026-03-05 |
| 完成日期 | 2026-03-05 |

## 原始需求

列表页卡片只有分支名和标签，缺少功能描述信息。需要展示 context.json 中的 description 字段，提高信息密度，让开发者无需点进详情页就能了解每个分支在做什么。

## 需求分析过程

description 字段长度不固定，需要截断处理。评估了前端 CSS 截断和后端截断两种方案，选择 CSS `text-overflow: ellipsis` 方案，因为前端截断保留了完整数据用于 title 提示。

## 实现方案

在 worktree_service.py 中传递 description 字段到模板。列表页模板中在卡片底部区域添加描述文本，使用 CSS 单行截断。鼠标悬停时通过 title 属性显示完整描述。

## 问题与解决方案

### 问题 1：长描述文本溢出

部分描述文本过长导致卡片高度不一致，通过 CSS `white-space: nowrap; overflow: hidden; text-overflow: ellipsis` 统一处理。

## 反思与复盘

简洁的优化，有效提升了列表页的信息密度。CSS 截断方案比后端截断更灵活，也更易于未来调整展示行数。
