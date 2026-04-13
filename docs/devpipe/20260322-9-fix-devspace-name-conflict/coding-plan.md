# 开发空间名字冲突修复方案

## 子任务分解

| # | 子任务 | 模块 | 状态 |
|---|--------|------|------|
| 1 | 排查 devspace_service.py 冲突检测逻辑 | devspace_service.py | 已完成 |
| 2 | 增加 worktree/container/volume/branch 预检 | devspace_service.py | 已完成 |
| 3 | 冲突自动清理机制 | devspace_service.py | 已完成 |

## 技术方案

排查现有 `devspace_service.py` 中的冲突检测逻辑，发现创建流程仅检查了 git worktree 是否存在，遗漏了 Docker container、volume 和 branch 等资源的冲突检测。当前一次创建失败后残留资源未清理，导致后续同名创建卡住。

在创建流程的预检阶段增加完整的资源冲突检测，依次检查 git branch 是否已存在、git worktree 目录是否残留、Docker container 是否同名运行、Docker volume 是否已创建。每项检测返回明确的冲突类型和资源标识。

实现冲突自动清理机制，当检测到残留资源时，按安全顺序（停止容器 -> 移除容器 -> 移除 volume -> 清理 worktree -> 删除分支）执行清理操作。清理过程记录详细日志，确保可追溯。清理完成后自动重新进入创建流程。

## 验收标准

1. 冲突检测覆盖 worktree、container、volume、branch 四类资源
2. 同名创建不再卡住，冲突资源自动清理后重新创建
3. 自动清理过程有详细日志记录
