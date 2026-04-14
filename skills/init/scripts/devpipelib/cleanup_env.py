"""CleanupRunner - 开发环境清理逻辑"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from .shell import cmd_exists, log, run_cmd


@dataclass
class CleanupParams:
    """清理参数"""
    branch_name: str


class CleanupRunner:
    """开发环境清理器"""

    def __init__(
        self,
        params: CleanupParams,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.params = params
        self._logger = logger

        # 计算派生值
        self.container_name = params.branch_name.replace("/", "-")
        self.git_volume = f"git-{self.container_name}"

        # 尝试获取仓库根目录
        try:
            result = run_cmd(["git", "rev-parse", "--show-toplevel"], check=False)
            self.repo_root = result.stdout.strip() if result.returncode == 0 else os.getcwd()
        except Exception:
            self.repo_root = os.getcwd()

        self.worktree_path = os.path.join(
            self.repo_root, ".devpipe", "worktrees", self.container_name
        )

    def _log(self, msg: str):
        log(msg, self._logger)

    # ========================
    # CLI 入口
    # ========================

    def run(self) -> None:
        """CLI 模式：print + sys.exit"""
        try:
            self.run_steps()
            self._log("")
            self._log("清理完成")
        except Exception as e:
            self._log(f"ERROR: {e}")
            sys.exit(1)

    def run_steps(
        self,
        on_stage: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """
        import 模式：执行清理步骤。

        Args:
            on_stage: 回调函数 (stage_name, status)
        """
        def _stage(name: str, status: str):
            if on_stage:
                on_stage(name, status)

        self._log(f"清理开发环境: {self.params.branch_name}")
        self._log("")

        _stage("停止容器", "running")
        self._cleanup_container()
        _stage("停止容器", "done")

        _stage("删除存储卷", "running")
        self._cleanup_volume()
        _stage("删除存储卷", "done")

        _stage("关闭终端", "running")
        self._cleanup_tmux()
        _stage("关闭终端", "done")

        _stage("删除工作目录", "running")
        self._cleanup_worktree()
        _stage("删除工作目录", "done")

        # 提示持久化的阶段产出
        self._show_preserved_docs()

        _stage("删除分支", "running")
        self._cleanup_branch()
        _stage("删除分支", "done")

    # ========================
    # 私有方法
    # ========================

    def _cleanup_container(self):
        """停止并删除 Docker 容器"""
        if not cmd_exists("docker"):
            self._log("  Docker 未安装，跳过容器清理")
            return

        # 检查容器是否存在
        result = run_cmd(["docker", "ps", "-a", "--format", "{{.Names}}"], check=False)
        if result.returncode != 0:
            self._log("  无法检查 Docker 容器，跳过")
            return

        containers = result.stdout.strip().split("\n") if result.stdout.strip() else []
        if self.container_name not in containers:
            self._log("  Docker 容器不存在，跳过")
            return

        run_cmd(["docker", "rm", "-f", self.container_name], check=False)
        self._log(f"  Docker 容器已删除: {self.container_name}")

    def _cleanup_volume(self):
        """删除 Docker volume"""
        if not cmd_exists("docker"):
            self._log("  Docker 未安装，跳过存储卷清理")
            return

        result = run_cmd(["docker", "volume", "inspect", self.git_volume], check=False)
        if result.returncode != 0:
            self._log("  Docker volume 不存在，跳过")
            return

        run_cmd(["docker", "volume", "rm", self.git_volume], check=False)
        self._log(f"  Docker volume 已删除: {self.git_volume}")

    def _cleanup_tmux(self):
        """关闭 tmux session"""
        if not cmd_exists("tmux"):
            self._log("  tmux 未安装，跳过")
            return

        result = run_cmd(["tmux", "has-session", "-t", self.container_name], check=False)
        if result.returncode != 0:
            self._log("  Tmux session 不存在，跳过")
            return

        run_cmd(["tmux", "kill-session", "-t", self.container_name], check=False)
        self._log(f"  Tmux session 已关闭: {self.container_name}")

    def _cleanup_worktree(self):
        """删除 worktree"""
        if not os.path.isdir(self.worktree_path):
            # 仍然执行 prune 清理悬挂引用
            run_cmd(["git", "-C", self.repo_root, "worktree", "prune"], check=False)
            self._log("  Worktree 不存在，跳过")
            return

        result = run_cmd(
            ["git", "-C", self.repo_root, "worktree", "remove", self.worktree_path, "--force"],
            check=False,
        )
        if result.returncode != 0:
            # 回退：直接删除目录 + prune
            shutil.rmtree(self.worktree_path, ignore_errors=True)
            run_cmd(["git", "-C", self.repo_root, "worktree", "prune"], check=False)

        self._log(f"  Worktree 已删除: {self.worktree_path}")

    def _show_preserved_docs(self):
        """提示持久化的阶段产出"""
        docs_dir = os.path.join(self.repo_root, ".devpipe", "docs")
        if not os.path.isdir(docs_dir):
            return

        pattern = f"-{self.container_name}"
        for name in os.listdir(docs_dir):
            if name.endswith(pattern):
                self._log(f"  阶段产出已保留: {os.path.join(docs_dir, name)}")

    def _cleanup_branch(self):
        """删除本地分支"""
        result = run_cmd(
            ["git", "-C", self.repo_root, "show-ref", "--verify", "--quiet",
             f"refs/heads/{self.params.branch_name}"],
            check=False,
        )
        if result.returncode != 0:
            self._log("  本地分支不存在，跳过")
            return

        run_cmd(
            ["git", "-C", self.repo_root, "branch", "-D", self.params.branch_name],
            check=False,
        )
        self._log(f"  本地分支已删除: {self.params.branch_name}")
