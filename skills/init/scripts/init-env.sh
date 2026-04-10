#!/bin/bash
# GitHub 项目 Docker 开发环境初始化脚本
# 用法: init-env.sh <local-branch> <base-branch> <mode> [devpipe-root] [issue-num]
# 必须从仓库根目录运行
#
# 参数:
#   local-branch: 新建的本地分支名（如 feature/add-cluster-api）
#   base-branch:  基础分支名（如 main）
#   mode:         local（基于本地分支）或 remote（基于远程分支，默认）
#   devpipe-root: devpipe 仓库路径（可选，用于查找镜像构建脚本）
#                 如未指定，将使用 DEVPIPE_ROOT 或 CLAUDE_PLUGIN_ROOT 环境变量
#   issue-num:    GitHub Issue 编号（可选，用于 docs 目录命名）
#
# 架构说明:
#   宿主机: .devpipe/worktrees/<branch>/ 存放 worktree 代码
#          .devpipe/docs/<YYYYMMDD-issue-branch>/ 持久化阶段产出
#          worktree 内 .devpipe 为 symlink 指向 docs 目录
#   容器内: /home/<user>/<repo>/ 即为 worktree 代码（通过 bind mount）
#          /home/<user>/<repo>/.git/ 为独立 Docker volume（从原始 .git 复制）
#          /home/<user>/<repo>/.devpipe/ bind mount 到 docs 目录（持久化）
#          这样容器内看到的是一个「普通 git 仓库」，git 操作正常工作
#
# 执行以下操作：
# 1. 前置检查（docker、git、gh）
# 2. 脏工作区检测
# 3. 分支验证
# 4. 创建 worktree
# 5. 构建/查找 Docker 镜像
# 6. 创建 Docker 容器（worktree 挂载 + .git volume）
# 7. 初始化容器内 git 环境
# 8. 创建 tmux session（双 Panel 布局，通过 docker exec 进入容器）

set -euo pipefail

LOCAL_BRANCH="$1"
BASE_BRANCH="$2"
MODE="${3:-remote}"
# devpipe 仓库根目录（用于查找镜像构建脚本）
# 优先级: 参数 > 环境变量 DEVPIPE_ROOT > 环境变量 CLAUDE_PLUGIN_ROOT
DEVPIPE_ROOT="${4:-${DEVPIPE_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}}"
ISSUE_NUM="${5:-}"

# 仓库根目录（脚本必须从此目录运行）
REPO_ROOT="$(git rev-parse --show-toplevel)"
# Worktree 放在 .devpipe/worktrees 目录下
WORKTREE_DIR="$REPO_ROOT/.devpipe/worktrees"
# 分支名中的 / 替换为 - 用于目录名
BRANCH_DIR_NAME="${LOCAL_BRANCH//\//-}"
WORKTREE_PATH="$WORKTREE_DIR/$BRANCH_DIR_NAME"
# Docker 容器名：分支名中的 / 替换为 -
CONTAINER_NAME="${LOCAL_BRANCH//\//-}"
# Docker volume 用于存放容器内的 .git 目录（与宿主机隔离）
GIT_VOLUME="git-$CONTAINER_NAME"
# 宿主机用户信息
HOST_USER=$(whoami)
HOST_UID=$(id -u)
HOST_GID=$(id -g)
# 仓库名（从仓库根目录名称获取）
REPO_NAME=$(basename "$REPO_ROOT")
# 容器内工作目录
CONTAINER_WORKSPACE="/home/$HOST_USER/$REPO_NAME"

# 持久化 docs 目录路径（环境清理后保留）
DOCS_DATE=$(date +%Y%m%d)
if [ -n "$ISSUE_NUM" ]; then
    DOCS_DIR_NAME="${DOCS_DATE}-${ISSUE_NUM}-${BRANCH_DIR_NAME}"
else
    DOCS_DIR_NAME="${DOCS_DATE}-${BRANCH_DIR_NAME}"
fi
DOCS_DEVPIPE_PATH="$REPO_ROOT/.devpipe/docs/$DOCS_DIR_NAME"

# ========================
# 前置检查
# ========================

check_prerequisites() {
    local missing=()

    if ! command -v docker &>/dev/null; then
        missing+=("docker")
    fi
    if ! command -v git &>/dev/null; then
        missing+=("git")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        echo "ERROR: 以下工具未安装: ${missing[*]}"
        echo ""
        echo "安装方式:"
        echo "  macOS:   brew install ${missing[*]}"
        echo "  Ubuntu:  sudo apt-get install ${missing[*]}"
        echo "  CentOS:  sudo yum install ${missing[*]}"
        exit 1
    fi

    # 检查 Docker daemon 是否运行
    if ! docker info &>/dev/null; then
        echo "ERROR: Docker daemon 未运行"
        echo "请先启动 Docker Desktop 或 Docker daemon"
        exit 1
    fi

    # 检查仓库是否存在
    if [ ! -d "$REPO_ROOT/.git" ] && [ ! -f "$REPO_ROOT/.git" ]; then
        echo "ERROR: 不是一个有效的 git 仓库: $REPO_ROOT"
        echo "请确认从仓库根目录运行此脚本"
        exit 1
    fi

    # 检查 gh CLI 认证状态（可选，仅警告）
    if command -v gh &>/dev/null; then
        if ! gh auth status &>/dev/null 2>&1; then
            echo "WARNING: gh CLI 未登录，部分功能（Issue 查询、PR 创建）将不可用"
            echo "请执行 'gh auth login' 登录"
        fi
    else
        echo "WARNING: gh CLI 未安装，部分功能将不可用"
        echo "安装方式: brew install gh (macOS) / sudo apt install gh (Ubuntu)"
    fi
}

# ========================
# 冲突检测
# ========================

check_conflicts() {
    # 检查 worktree 是否已存在
    if [ -d "$WORKTREE_PATH" ]; then
        echo "ERROR: Worktree 已存在: $WORKTREE_PATH"
        echo "如需重建，先执行清理:"
        echo "  bash skills/init/scripts/cleanup-env.sh $LOCAL_BRANCH"
        exit 1
    fi

    # 检查本地分支是否已存在
    if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$LOCAL_BRANCH" 2>/dev/null; then
        echo "ERROR: 本地分支已存在: $LOCAL_BRANCH"
        echo "如需重建，先执行清理:"
        echo "  bash skills/init/scripts/cleanup-env.sh $LOCAL_BRANCH"
        exit 1
    fi

    # 检查 Docker 容器是否已存在（包括已停止的）
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "ERROR: Docker 容器已存在: $CONTAINER_NAME"
        echo "如需重建，先执行清理:"
        echo "  bash skills/init/scripts/cleanup-env.sh $LOCAL_BRANCH"
        exit 1
    fi

    # 检查 Docker volume 是否已存在
    if docker volume inspect "$GIT_VOLUME" &>/dev/null; then
        echo "ERROR: Docker volume 已存在: $GIT_VOLUME"
        echo "如需重建，先执行清理:"
        echo "  bash skills/init/scripts/cleanup-env.sh $LOCAL_BRANCH"
        exit 1
    fi

    # 检查 tmux session 是否已存在
    if command -v tmux &>/dev/null && tmux has-session -t "$CONTAINER_NAME" 2>/dev/null; then
        echo "ERROR: Tmux session 已存在: $CONTAINER_NAME"
        echo "如需重建，先执行清理:"
        echo "  bash skills/init/scripts/cleanup-env.sh $LOCAL_BRANCH"
        exit 1
    fi
}

# ========================
# 脏工作区检测
# ========================

check_clean_worktree() {
    # 空仓库（无 commit）时跳过检测，HEAD 不存在会导致 git diff 返回 128
    if ! git -C "$REPO_ROOT" rev-parse HEAD &>/dev/null; then
        return 0
    fi
    if ! git -C "$REPO_ROOT" diff --quiet HEAD 2>/dev/null || \
       ! git -C "$REPO_ROOT" diff --cached --quiet HEAD 2>/dev/null; then
        echo "ERROR: 工作区有未提交的改动"
        echo "请先提交或暂存改动后再初始化开发环境:"
        echo "  git stash     # 暂存改动"
        echo "  git commit    # 提交改动"
        exit 1
    fi
}

# ========================
# 分支验证
# ========================

sync_base_branch() {
    if [ "$MODE" = "local" ]; then
        echo "基于本地分支: $BASE_BRANCH ..."

        if ! git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$BASE_BRANCH"; then
            echo "ERROR: 本地分支不存在: $BASE_BRANCH"
            echo "请检查分支名是否正确"
            exit 1
        fi

        echo "本地分支验证完成"
    else
        echo "同步远程分支: origin/$BASE_BRANCH ..."

        git -C "$REPO_ROOT" fetch origin

        if ! git -C "$REPO_ROOT" rev-parse --verify "origin/$BASE_BRANCH" &>/dev/null; then
            echo "ERROR: 远程分支不存在: origin/$BASE_BRANCH"
            echo "请检查分支名是否正确"
            exit 1
        fi

        echo "远程代码同步完成"
    fi
}

# ========================
# 创建 Worktree
# ========================

create_worktree() {
    echo "创建 Worktree: $WORKTREE_PATH ..."

    mkdir -p "$WORKTREE_DIR"

    if [ "$MODE" = "local" ]; then
        git -C "$REPO_ROOT" worktree add "$WORKTREE_PATH" -b "$LOCAL_BRANCH" "$BASE_BRANCH"
    else
        git -C "$REPO_ROOT" worktree add "$WORKTREE_PATH" -b "$LOCAL_BRANCH" "origin/$BASE_BRANCH"
    fi

    echo "Worktree 创建完成"

    # 删除 worktree 的 .git 文件（是一个 gitdir 引用文件，不是目录）
    # 容器内通过 Docker named volume 提供独立的 .git 目录
    # 宿主机 worktree 只用于提供代码文件，不需要 git 引用
    if [ -f "$WORKTREE_PATH/.git" ]; then
        rm -f "$WORKTREE_PATH/.git"
        echo "已移除 worktree .git 引用（git 操作将在容器内进行）"
    elif [ -d "$WORKTREE_PATH/.git" ]; then
        echo "ERROR: $WORKTREE_PATH/.git 是目录而非 gitdir 引用文件，跳过删除以避免数据丢失"
        echo "请检查 worktree 创建是否正确"
        exit 1
    else
        echo "警告: $WORKTREE_PATH/.git 不存在，跳过"
    fi
}

# ========================
# 构建/查找 Docker 镜像
# ========================

build_docker_image() {
    echo "检查 Docker 镜像..."

    local sync_script=""

    # 优先使用项目本地的镜像构建脚本
    if [ -f "$REPO_ROOT/resources/sync-docker-image.sh" ]; then
        sync_script="$REPO_ROOT/resources/sync-docker-image.sh"
        echo "使用项目本地镜像构建脚本"
    # 其次使用 devpipe 仓库的镜像构建脚本
    elif [ -n "$DEVPIPE_ROOT" ] && [ -f "$DEVPIPE_ROOT/resources/sync-docker-image.sh" ]; then
        sync_script="$DEVPIPE_ROOT/resources/sync-docker-image.sh"
        echo "使用 devpipe 镜像构建脚本: $sync_script"
    else
        echo "ERROR: 找不到镜像构建脚本"
        echo "请确保以下任一条件满足:"
        echo "  1. 项目仓库中存在 resources/sync-docker-image.sh"
        echo "  2. 设置 DEVPIPE_ROOT 环境变量指向 devpipe 仓库"
        echo "  3. 设置 CLAUDE_PLUGIN_ROOT 环境变量指向 devpipe 仓库"
        echo "  4. 传递第四个参数指定 devpipe 仓库路径"
        exit 1
    fi

    DOCKER_IMAGE=$(bash "$sync_script")
    echo "使用镜像: $DOCKER_IMAGE"
}

# ========================
# 创建 Docker 容器
# ========================

create_docker_container() {
    echo "创建 Docker 容器: $CONTAINER_NAME ..."

    # 创建 Docker volume 用于存放 .git 数据
    docker volume create "$GIT_VOLUME" >/dev/null

    # 创建持久化 docs 目录并创建 symlink
    mkdir -p "$DOCS_DEVPIPE_PATH"
    ln -sfn "$DOCS_DEVPIPE_PATH" "$WORKTREE_PATH/.devpipe"

    # 构建 volume 挂载参数
    local volumes=(
        # Worktree 代码
        -v "$WORKTREE_PATH:$CONTAINER_WORKSPACE"
        # Docker volume 覆盖 .git（独立 git 数据库）
        -v "$GIT_VOLUME:$CONTAINER_WORKSPACE/.git"
        # .devpipe 工作流状态（持久化到 docs 目录）
        -v "$DOCS_DEVPIPE_PATH:$CONTAINER_WORKSPACE/.devpipe"
    )

    # 可选：挂载 SSH 密钥（容器内 git push）
    # 使用读写模式，支持 SSH ControlMaster socket 创建
    if [ -d "$HOME/.ssh" ]; then
        volumes+=(-v "$HOME/.ssh:/home/$HOST_USER/.ssh:rw")
    fi

    # 可选：挂载 .claude 配置目录（项目级）
    # 注意：不挂载为只读，因为 git checkout 可能需要修改其中的文件
    if [ -d "$REPO_ROOT/.claude" ]; then
        volumes+=(-v "$REPO_ROOT/.claude:$CONTAINER_WORKSPACE/.claude")
    fi

    # 构建环境变量参数
    local env_args=(
        -e "HOME=/home/$HOST_USER"
        -e "TERM=xterm-256color"
    )
    if [ -n "${ANTHROPIC_AUTH_TOKEN:-}" ]; then
        env_args+=(-e "ANTHROPIC_AUTH_TOKEN=$ANTHROPIC_AUTH_TOKEN")
    fi
    if [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
        env_args+=(-e "ANTHROPIC_BASE_URL=$ANTHROPIC_BASE_URL")
    fi

    # 创建容器
    docker run -d \
        --name "$CONTAINER_NAME" \
        "${volumes[@]}" \
        "${env_args[@]}" \
        -w "$CONTAINER_WORKSPACE" \
        --entrypoint "" \
        "$DOCKER_IMAGE" \
        tail -f /dev/null

    # 等待容器就绪
    local retries=0
    while [ $retries -lt 10 ]; do
        if docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -q "true"; then
            break
        fi
        sleep 0.5
        retries=$((retries + 1))
    done

    if ! docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -q "true"; then
        echo "ERROR: Docker 容器启动失败"
        docker logs "$CONTAINER_NAME" 2>&1 || true
        exit 1
    fi

    echo "Docker 容器创建完成"
}

# ========================
# 初始化容器内 Git 环境
# ========================

init_container_git() {
    echo "初始化容器内 Git 环境..."

    # 用 root 修复 Docker volume 权限
    docker exec -u root "$CONTAINER_NAME" chown -R $HOST_UID:$HOST_GID $CONTAINER_WORKSPACE/.git

    # 解析实际的 git 目录
    local ACTUAL_GIT_DIR
    ACTUAL_GIT_DIR="$(git -C "$REPO_ROOT" rev-parse --git-dir)"
    # 确保是绝对路径
    if [[ "$ACTUAL_GIT_DIR" != /* ]]; then
        ACTUAL_GIT_DIR="$REPO_ROOT/$ACTUAL_GIT_DIR"
    fi
    echo "实际 git 目录: $ACTUAL_GIT_DIR"

    # 将宿主机仓库的 .git 数据复制到 Docker volume
    docker cp "$ACTUAL_GIT_DIR/." "$CONTAINER_NAME:$CONTAINER_WORKSPACE/.git/"

    # 修复容器内 git 配置并 checkout 到开发分支
    docker exec -w "$CONTAINER_WORKSPACE" "$CONTAINER_NAME" bash -c "
        sed -i 's|worktree = .*|worktree = $CONTAINER_WORKSPACE|' .git/config 2>/dev/null || true
        rm -rf .git/worktrees
        sed -i '/worktreeConfig/d' .git/config 2>/dev/null || true
        git checkout -f $LOCAL_BRANCH
    "

    # 复制宿主机 git 全局配置（用户名、邮箱等）
    if [ -f "$HOME/.gitconfig" ]; then
        docker cp "$HOME/.gitconfig" "$CONTAINER_NAME:/home/$HOST_USER/.gitconfig"
    fi

    echo "Git 环境初始化完成 (分支: ${LOCAL_BRANCH})"
}

# ========================
# 初始化容器内 gh CLI 认证
# ========================

init_container_gh() {
    echo "初始化容器内 gh CLI 认证..."
    if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
        local gh_token
        gh_token=$(gh auth token 2>/dev/null)
        if [ -n "$gh_token" ]; then
            echo "$gh_token" | docker exec -i "$CONTAINER_NAME" gh auth login --with-token
            echo "gh CLI 认证完成"
        else
            echo "WARNING: 无法获取 gh token，跳过"
        fi
    else
        echo "WARNING: 宿主机 gh CLI 未认证，跳过"
    fi
}

# ========================
# 初始化 Claude 配置
# ========================

init_claude_config() {
    echo "初始化 Claude 配置..."

    local container_claude_dir="/home/$HOST_USER/.claude"

    # 创建容器内的 ~/.claude/ 目录
    docker exec "$CONTAINER_NAME" mkdir -p "$container_claude_dir"

    # 复制宿主机的 settings.json
    local settings_content=""

    if [ -f "$HOME/.claude/settings.json" ]; then
        settings_content=$(cat "$HOME/.claude/settings.json")
    fi

    if [ -n "$settings_content" ]; then
        # 替换 localhost 为 host.docker.internal（容器内访问宿主机）
        settings_content=$(echo "$settings_content" | sed 's|http://localhost:|http://host.docker.internal:|g')
        echo "$settings_content" | docker exec -i "$CONTAINER_NAME" tee "$container_claude_dir/settings.json" >/dev/null
        echo "Claude 配置已初始化"
    else
        echo "警告: 未找到 ~/.claude/settings.json，跳过 Claude 配置初始化"
    fi

    # 复制 statusline-command.sh 到容器内（容器内 Claude Code 状态栏显示）
    if [ -f "$HOME/.claude/statusline-command.sh" ]; then
        docker cp "$HOME/.claude/statusline-command.sh" "$CONTAINER_NAME:$container_claude_dir/statusline-command.sh"
        docker exec "$CONTAINER_NAME" chmod +x "$container_claude_dir/statusline-command.sh"
        echo "statusline-command.sh 已复制到容器"
    fi
}

# ========================
# 创建 Tmux Session
# ========================

create_tmux_session() {
    if ! command -v tmux &>/dev/null; then
        echo "tmux 未安装，跳过 tmux session 创建"
        echo "可手动进入容器: docker exec -it $CONTAINER_NAME zsh"
        return 0
    fi

    echo "创建 Tmux Session: $CONTAINER_NAME ..."

    # 配置 tmux 256 色支持
    tmux set-option -g default-terminal "screen-256color" 2>/dev/null || true
    tmux set-option -ga terminal-overrides ",xterm-256color:Tc" 2>/dev/null || true

    tmux new-session -d -s "$CONTAINER_NAME" \
        -e DEV_WORKTREE_NAME="$LOCAL_BRANCH" \
        -e DEV_CONTAINER_NAME="$CONTAINER_NAME" \
        -e DEV_REPO_ROOT="$REPO_ROOT" \
        -e TERM="xterm-256color"

    # 左 panel: 进入容器 Shell
    tmux send-keys -t "$CONTAINER_NAME":0.0 \
        "docker exec -it -w $CONTAINER_WORKSPACE $CONTAINER_NAME zsh" Enter

    sleep 1

    tmux send-keys -t "$CONTAINER_NAME":0.0 'clear' Enter

    # 垂直分割
    tmux split-window -h -t "$CONTAINER_NAME"

    # 右 panel: 进入容器并启动 Claude Code (使用 zsh 以支持主题)
    tmux send-keys -t "$CONTAINER_NAME":0.1 \
        "docker exec -it -w $CONTAINER_WORKSPACE $CONTAINER_NAME zsh" Enter

    sleep 1

    # 启动 Claude Code
    tmux send-keys -t "$CONTAINER_NAME":0.1 "unset CLAUDECODE && claude --plugin-dir ./.claude/plugins/devpipe --dangerously-skip-permissions" Enter

    echo "Tmux Session 创建完成"
}

# ========================
# 主流程
# ========================

main() {
    echo "=========================================="
    echo "  GitHub 项目 Docker 开发环境初始化"
    echo "  本地分支: $LOCAL_BRANCH"
    if [ "$MODE" = "local" ]; then
        echo "  基于分支: $BASE_BRANCH (本地)"
    else
        echo "  基于分支: origin/$BASE_BRANCH (远程)"
    fi
    echo "  容器名称: $CONTAINER_NAME"
    echo "=========================================="
    echo ""

    check_prerequisites
    check_conflicts
    check_clean_worktree
    sync_base_branch
    create_worktree
    build_docker_image
    create_docker_container
    init_container_git
    init_container_gh
    init_claude_config
    create_tmux_session

    echo ""
    echo "=========================================="
    echo "  开发环境创建完成!"
    echo "=========================================="
    echo ""
    echo "Worktree:  $WORKTREE_PATH"
    echo "Container: $CONTAINER_NAME"
    echo "Devpipe Docs: $DOCS_DEVPIPE_PATH"
    echo ""
    echo "进入开发环境:"
    echo "  tmux attach -t $CONTAINER_NAME"
    echo ""
    echo "布局:"
    echo "  左 Panel: 容器内 Shell"
    echo "  右 Panel: 容器内 Claude Code（已自动打开）"
    echo ""
    echo "手动进入容器:"
    echo "  docker exec -it $CONTAINER_NAME zsh"
}

main
