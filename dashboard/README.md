# Workspace Dashboard

RocketMQ Workspace 开发环境管理面板，用于查看和管理 worktree 开发分支的状态与进度。

## 功能

- 展示所有 `wt-` 开头的开发分支列表
- 显示每个分支的开发阶段（新功能：init → discuss → design → coding；Bugfix/重构：init → design → coding）
- 展示子任务进度和验收标准
- 支持从容器内读取 devflow 状态文件
- 创建开发空间（iCafe 卡片查询、分支创建、容器启动）
- 一键进入 tmux session

## 目录结构

```
dashboard/
├── app.py                 # Flask 应用入口
├── config.py              # 配置文件（仓库路径、iCafe URL 模板）
├── worktree_service.py    # Worktree 状态解析服务
├── devspace_service.py    # 开发空间创建服务
├── summary_service.py     # 摘要生成服务（调用 OpenAI）
├── requirements.txt       # Python 依赖
├── static/
│   └── style.css          # 样式文件
└── templates/
    ├── index.html         # 列表页
    └── detail.html        # 详情页
```

## 部署

Dashboard 直接在宿主机运行，使用 `dashboard-ctl.sh` 脚本管理。

### 前置条件

- Python 3 已安装（`python3 --version`）
- Flask 已安装（`pip3 install flask`）
- 端口 5001 未被占用

### 启动

```bash
bash scripts/dashboard-ctl.sh start
```

### 访问

浏览器打开 http://localhost:5001

## 维护

使用 `dashboard-ctl.sh` 脚本进行管理：

```bash
# 查看状态
bash scripts/dashboard-ctl.sh status

# 查看日志（实时跟踪）
bash scripts/dashboard-ctl.sh logs

# 重启（代码更新后）
bash scripts/dashboard-ctl.sh restart

# 停止
bash scripts/dashboard-ctl.sh stop
```

### 保活机制

Dashboard 支持通过 cron 自动保活，进程异常退出后会自动重启：

```bash
# 安装保活任务（每分钟检查）
bash scripts/dashboard-ctl.sh install

# 卸载保活任务
bash scripts/dashboard-ctl.sh uninstall
```

### 文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| PID 文件 | `$WORKSPACE/.dashboard.pid` | 进程 ID |
| 日志文件 | `/tmp/dashboard.log` | 运行日志 |
| 监听端口 | `5001` | HTTP 服务 |

## 开发阶段说明

| 阶段 | 标签 | 颜色 | 对应文件 | 适用类型 |
|------|------|------|----------|----------|
| init | 初始化 | 灰色 | context.json | 所有类型 |
| discuss | 需求讨论 | 紫色 | prd.md | 仅新功能 |
| design | 方案设计 | 橙色 | coding-plan.md | 所有类型 |
| coding | 代码开发 | 青色 | task-progress.md | 所有类型 |
| review-and-fix | 评审修复 | 红色 | review-status.md | 仅完整模式 |
| summarize | 总结 | 绿色 | context.json | 所有类型 |

工作流路由：
- **新功能**：init → discuss → design → coding → review-and-fix → summarize
- **Bugfix/优化重构**：init → design → coding → review-and-fix → summarize（跳过 discuss）

## 本地开发

不使用控制脚本直接运行（用于调试）：

```bash
cd dashboard
pip install -r requirements.txt
python app.py
```

服务默认监听 `0.0.0.0:5001`。

## 配置

编辑 `config.py` 修改：

- `ROCKETMQ_PRODUCT_PATH`：rocketmq-product 仓库路径
- `ICAFE_CARD_URL_TEMPLATE`：iCafe 卡片链接模板

## API

Dashboard 提供以下 API 接口：

### 开发空间创建

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/icafe/query` | POST | 查询 iCafe 卡片信息 |
| `/api/branch/validate` | POST | 验证基础分支是否存在 |
| `/api/devspace/check-conflicts` | POST | 检查资源冲突 |
| `/api/devspace/suggest-branch` | POST | 根据描述生成建议分支名 |
| `/api/devspace/create` | POST | 启动异步创建任务 |
| `/api/devspace/status/<task_id>` | GET | 查询创建进度 |

### Worktree 查询

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/worktrees` | GET | 获取 worktree 列表（JSON） |
