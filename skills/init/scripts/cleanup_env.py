#!/usr/bin/env python3
"""
GitHub 项目 Docker 开发环境清理脚本

用法: cleanup_env.py <branch-name>
必须从仓库根目录运行

按顺序清理以下资源（跳过不存在的）：
1. Docker 容器（停止 + 删除）
2. Docker volume（.git 数据）
3. Tmux session
4. Git worktree
5. 本地分支
"""

import argparse
import os
import sys

# 添加当前目录到路径以便 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from devpipelib.cleanup_env import CleanupParams, CleanupRunner


def main():
    parser = argparse.ArgumentParser(
        description="GitHub 项目 Docker 开发环境清理",
        epilog=(
            "查看已有环境:\n"
            "  git worktree list\n"
            "  docker ps -a\n"
            "  tmux list-sessions"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "branch_name",
        help="要清理的分支名（如 feature/add-cluster-api）",
    )

    args = parser.parse_args()

    if not args.branch_name:
        parser.print_help()
        sys.exit(1)

    params = CleanupParams(branch_name=args.branch_name)
    runner = CleanupRunner(params)
    runner.run()


if __name__ == "__main__":
    main()
