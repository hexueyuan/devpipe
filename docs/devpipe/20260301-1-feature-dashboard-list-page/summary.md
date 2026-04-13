# Dashboard 列表页

## 基本信息

| 字段 | 值 |
|------|-----|
| 开发类型 | 新功能 |
| 远程分支 | main |
| 本地分支 | feature/dashboard-list-page |
| 开发日期 | 2026-03-01 |
| 完成日期 | 2026-03-01 |

## 原始需求

devpipe 工作流管理了每个开发分支的阶段状态（通过 `.devpipe/context.json`），但缺少可视化界面。开发者需要一个 Web Dashboard 来快速总览所有开发分支的进度和状态，取代手动查看每个 worktree 下的 context.json 文件。

## 需求分析过程

核心目标是提供"一览全局"的能力。分析后确定：使用 Flask 框架（轻量、Python 生态契合），通过 `git worktree list --porcelain` 获取分支列表，再解析各 worktree 下的 `.devpipe/context.json` 获取状态信息。数据层封装为 `worktree_service.py`，与 Flask 路由解耦。阶段标签使用不同颜色区分，提升扫描效率。

## 实现方案

建立了 Flask 应用框架：`app.py` 作为路由入口，`worktree_service.py` 封装 git worktree 解析和 context.json 读取逻辑。列表页使用 Jinja2 模板渲染，每个分支以卡片形式展示，包含分支名、开发阶段标签。阶段标签通过 CSS 类名映射不同颜色，与 STAGES 常量定义保持一致。Dashboard 启动脚本 `dashboard-ctl.sh` 管理应用生命周期。

## 问题与解决方案

### 问题 1：git worktree list 输出解析

`git worktree list --porcelain` 的输出格式为多行键值对，需逐行解析 worktree/HEAD/branch 三个字段。branch 字段包含 `refs/heads/` 前缀需要去除。最终实现了通用的解析函数，正确处理各种边界情况。

## 反思与复盘

本次迭代建立了 Dashboard 的基础框架，数据层和展示层的分离为后续功能扩展打下了良好基础。worktree_service.py 的抽象粒度合适，后续迭代可以方便地新增数据维度。
