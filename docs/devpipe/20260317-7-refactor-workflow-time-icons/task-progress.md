# 工作流时间和角色图标 - 开发进度

## 子任务进度

| # | 子任务 | 模块 | 状态 |
|---|--------|------|------|
| 1 | STAGE_META 元数据定义 | worktree_service.py | 已完成 |
| 2 | 阶段耗时计算 | worktree_service.py | 已完成 |
| 3 | Timeline 分组 UI 优化 | templates/ | 已完成 |
| 4 | 时间和角色 CSS 样式 | static/css/ | 已完成 |

## 问题与解决方案记录

### 问题 1：ISO 8601 时间戳解析兼容性

context.json 中的时间戳格式不完全符合标准 ISO 8601，Python 的 datetime.fromisoformat 在部分格式下会抛出 ValueError。解决方案是实现多格式解析函数，依次尝试带时区、不带时区、仅日期等多种格式，确保所有历史数据中的时间戳都能正确解析。
