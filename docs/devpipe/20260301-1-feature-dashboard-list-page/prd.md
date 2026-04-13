# Dashboard 列表页

## 需求背景

devpipe 工作流通过 `.devpipe/context.json` 管理每个开发分支的阶段状态，但缺少直观的可视化界面来总览所有开发分支的进度。开发者需要一个 Web Dashboard 来快速了解各分支的开发阶段和状态。

## 需求描述

搭建一个基于 Flask 的 Web Dashboard，提供列表页展示所有 git worktree 开发分支。每个分支卡片显示分支名、当前阶段、阶段标签颜色。

### 功能要求

1. 使用 Flask 框架搭建 Web 应用，监听 5001 端口
2. 通过 `git worktree list` 获取所有活跃的 worktree 分支
3. 解析每个 worktree 下的 `.devpipe/context.json` 获取开发上下文
4. 列表页以卡片形式展示分支信息，包含分支名、开发阶段、阶段标签
5. 阶段标签使用不同颜色区分：初始化(灰)、需求讨论(蓝)、方案设计(紫)、代码开发(橙)、评审修复(红)、总结(绿)、已完成(深绿)

### 涉及模块

| 模块 | 说明 |
|------|------|
| `dashboard/src/app.py` | Flask 应用主入口和路由定义 |
| `dashboard/src/worktree_service.py` | Git worktree 数据解析层 |
| `dashboard/templates/` | Jinja2 模板文件 |

## 验收标准

1. 启动 Flask 应用后可在浏览器访问列表页
2. 列表页正确显示所有 git worktree 开发分支
3. 每个分支卡片包含分支名和当前阶段标签
4. 阶段标签颜色与阶段状态对应
