#!/bin/bash
# 公共基础镜像构建脚本
# 检测 Dockerfile 变更，按需构建镜像，始终维护 latest 标签
#
# 用法:
#   bash resources/sync-docker-image.sh
#
# 返回值:
#   成功时输出镜像名 "devpipe/devspace:latest"
#   失败时 exit 1

set -euo pipefail

# 宿主机用户信息（传入 Dockerfile 的 ARG）
HOST_USER=$(whoami)
HOST_UID=$(id -u)
HOST_GID=$(id -g)

WORKSPACE="/home/${HOST_USER}"
IMAGE_NAME="devpipe/devspace"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKERFILE="$SCRIPT_DIR/Dockerfile"

if [ ! -f "$DOCKERFILE" ]; then
    echo "ERROR: Dockerfile 不存在: $DOCKERFILE" >&2
    exit 1
fi

# 基于 Dockerfile 内容生成 hash 标签
TAG=$(shasum "$DOCKERFILE" | cut -c1-8)
FULL_IMAGE="$IMAGE_NAME:$TAG"

if docker image inspect "$FULL_IMAGE" &>/dev/null; then
    echo "镜像已是最新: $FULL_IMAGE" >&2
else
    echo "检测到 Dockerfile 变更，开始构建镜像..." >&2

    # 清理旧版本（保留 latest 标签在下面重新打）
    old_images=$(docker images "$IMAGE_NAME" --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
        | grep -v "latest" | grep -v "$TAG" || true)
    if [ -n "$old_images" ]; then
        echo "清理旧版本镜像..." >&2
        echo "$old_images" | xargs -r docker rmi 2>/dev/null >&2 || true
    fi

    docker build -t "$FULL_IMAGE" \
        -f "$DOCKERFILE" \
        --build-arg USER_NAME="$HOST_USER" \
        --build-arg USER_UID="$HOST_UID" \
        --build-arg USER_GID="$HOST_GID" \
        "$SCRIPT_DIR" >&2

    echo "镜像构建完成: $FULL_IMAGE" >&2
fi

# 始终将 latest 指向当前版本
docker tag "$FULL_IMAGE" "$IMAGE_NAME:latest" 2>/dev/null >&2

# 输出镜像名供调用方使用
echo "$IMAGE_NAME:latest"
