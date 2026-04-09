#!/bin/bash
# GitHub 项目 Docker 开发环境清理脚本
# 用法: cleanup-env.sh <branch-name>
# 必须从仓库根目录运行
#
# 按顺序清理以下资源（跳过不存在的）：
# 1. Docker 容器（停止 + 删除）
# 2. Docker volume（.git 数据）
# 3. Tmux session
# 4. Git worktree
# 5. 本地分支

set -uo pipefail

if [ $# -lt 1 ] || [ -z "$1" ]; then
    echo "用法: cleanup-env.sh <branch-name>"
    echo "必须从仓库根目录运行"
    echo ""
    echo "查看已有环境:"
    echo "  git worktree list"
    echo "  docker ps -a"
    echo "  tmux list-sessions"
    exit 1
fi

BRANCH_NAME="$1"
# 分支名中的 / 替换为 - 用于容器名和目录名
CONTAINER_NAME="${BRANCH_NAME//\//-}"
GIT_VOLUME="git-$CONTAINER_NAME"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
WORKTREE_PATH="$REPO_ROOT/.devpipe/worktrees/$CONTAINER_NAME"

echo "清理开发环境: $BRANCH_NAME"
echo ""

# 停止并删除 Docker 容器
if command -v docker &>/dev/null; then
    if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER_NAME}$"; then
        docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1
        echo "  Docker 容器已删除: $CONTAINER_NAME"
    else
        echo "  Docker 容器不存在，跳过"
    fi

    # 删除 Docker volume
    if docker volume inspect "$GIT_VOLUME" &>/dev/null; then
        docker volume rm "$GIT_VOLUME" >/dev/null 2>&1
        echo "  Docker volume 已删除: $GIT_VOLUME"
    else
        echo "  Docker volume 不存在，跳过"
    fi
else
    echo "  Docker 未安装，跳过容器和 volume 清理"
fi

# 关闭 tmux session
if command -v tmux &>/dev/null && tmux has-session -t "$CONTAINER_NAME" 2>/dev/null; then
    tmux kill-session -t "$CONTAINER_NAME"
    echo "  Tmux session 已关闭: $CONTAINER_NAME"
else
    echo "  Tmux session 不存在，跳过"
fi

# 删除 worktree
if [ -d "$WORKTREE_PATH" ]; then
    if ! git -C "$REPO_ROOT" worktree remove "$WORKTREE_PATH" --force 2>/dev/null; then
        rm -rf "$WORKTREE_PATH"
        git -C "$REPO_ROOT" worktree prune 2>/dev/null
    fi
    echo "  Worktree 已删除: $WORKTREE_PATH"
else
    git -C "$REPO_ROOT" worktree prune 2>/dev/null
    echo "  Worktree 不存在，跳过"
fi

# 提示持久化的阶段产出
DOCS_PATTERN="$REPO_ROOT/.devpipe/docs/*-${CONTAINER_NAME}"
for docs_dir in $DOCS_PATTERN; do
    if [ -d "$docs_dir" ]; then
        echo "  阶段产出已保留: $docs_dir"
    fi
done

# 删除本地分支
if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$BRANCH_NAME" 2>/dev/null; then
    git -C "$REPO_ROOT" branch -D "$BRANCH_NAME"
    echo "  本地分支已删除: $BRANCH_NAME"
else
    echo "  本地分支不存在，跳过"
fi

echo ""
echo "清理完成"
