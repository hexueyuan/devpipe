# 阶段文档查看器

## 需求背景

进度条展示了阶段状态，但开发者还需要查看每个阶段产生的文档内容（如 prd.md、coding-plan.md 等），以了解开发过程的详细记录。

## 需求描述

点击进度条的阶段节点，查看对应阶段的文档内容。支持 Markdown 渲染为 HTML，无文档时显示占位提示。

### 功能要求

1. 建立阶段到文档的映射关系（STAGE_DOCUMENT_MAP）
2. 读取 worktree 中对应的文档文件内容
3. 使用 Markdown 渲染引擎将文档内容转换为 HTML 展示
4. 点击进度条节点切换显示对应文档
5. 无文档的阶段显示占位文本提示

### 涉及模块

| 模块 | 说明 |
|------|------|
| `dashboard/src/worktree_service.py` | STAGE_DOCUMENT_MAP 定义和文件读取 |
| `dashboard/templates/detail.html` | 文档展示区域和交互逻辑 |

## 验收标准

1. 点击阶段节点可查看对应文档内容
2. Markdown 内容正确渲染为 HTML
3. 无文档阶段显示友好的占位提示
4. 文档切换流畅，无页面跳转
5. init 阶段显示"初始化阶段无关联文档"
