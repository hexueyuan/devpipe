#!/usr/bin/env python3
"""
GitHub 项目 Docker 开发环境初始化脚本

用法: init_env.py <local-branch> <base-branch> <mode> [devpipe-root] [issue-num]
必须从仓库根目录运行

参数:
  local-branch: 新建的本地分支名（如 feature/add-cluster-api）
  base-branch:  基础分支名（如 main）
  mode:         local（基于本地分支）或 remote（基于远程分支，默认）
  devpipe-root: devpipe 仓库路径（可选，用于查找镜像构建脚本）
  issue-num:    GitHub Issue 编号（可选，用于 docs 目录命名）
"""

import argparse
import os
import sys

# 添加当前目录到路径以便 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from devpipelib.init_env import InitEnvParams, InitEnvRunner


def main():
    parser = argparse.ArgumentParser(
        description="GitHub 项目 Docker 开发环境初始化"
    )
    parser.add_argument(
        "local_branch",
        help="新建的本地分支名（如 feature/add-cluster-api）",
    )
    parser.add_argument(
        "base_branch",
        help="基础分支名（如 main）",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="remote",
        choices=["local", "remote"],
        help="local（基于本地分支）或 remote（基于远程分支，默认）",
    )
    parser.add_argument(
        "devpipe_root",
        nargs="?",
        default="",
        help="devpipe 仓库路径（可选）",
    )
    parser.add_argument(
        "issue_num",
        nargs="?",
        default="",
        help="GitHub Issue 编号（可选）",
    )

    args = parser.parse_args()

    # 环境变量回退
    devpipe_root = args.devpipe_root
    if not devpipe_root:
        devpipe_root = os.environ.get(
            "DEVPIPE_ROOT",
            os.environ.get("CLAUDE_PLUGIN_ROOT", ""),
        )

    params = InitEnvParams(
        local_branch=args.local_branch,
        base_branch=args.base_branch,
        mode=args.mode,
        devpipe_root=devpipe_root,
        issue_num=args.issue_num,
    )

    runner = InitEnvRunner(params)
    runner.run()


if __name__ == "__main__":
    main()
