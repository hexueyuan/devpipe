"""InitEnvRunner - 开发环境初始化主逻辑"""

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from .config import DevpipeConfig
from .shell import (
    ConflictError,
    PrerequisiteError,
    cmd_exists,
    log,
    run_cmd,
)


@dataclass
class InitEnvParams:
    """初始化参数"""
    local_branch: str
    base_branch: str
    mode: str = "remote"  # "remote" or "local"
    devpipe_root: str = ""
    issue_num: str = ""
    repo_root: str = ""  # 宿主仓库根目录，为空时自动探测


@dataclass
class InitEnvResult:
    """初始化结果"""
    worktree_path: str
    container_name: str
    docs_path: str


class InitEnvRunner:
    """开发环境初始化器"""

    def __init__(
        self,
        params: InitEnvParams,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.params = params
        self._logger = logger

        # 计算派生值：优先使用传入的 repo_root，否则自动探测
        self.repo_root = params.repo_root if params.repo_root else self._get_repo_root()
        self.worktree_dir = os.path.join(self.repo_root, ".devpipe", "worktrees")
        self.branch_dir_name = params.local_branch.replace("/", "-")
        self.worktree_path = os.path.join(self.worktree_dir, self.branch_dir_name)
        self.container_name = self.branch_dir_name
        self.git_volume = f"git-{self.container_name}"

        self.host_user = os.environ.get("USER", os.environ.get("USERNAME", "user"))
        self.host_uid = os.getuid()
        self.host_gid = os.getgid()
        self.repo_name = os.path.basename(self.repo_root)
        self.container_workspace = f"/home/{self.host_user}/{self.repo_name}"

        # 加载项目配置
        self.config = DevpipeConfig.load(self.repo_root)

        # docs 路径
        docs_date = datetime.now().strftime("%Y%m%d")
        if params.issue_num:
            docs_dir_name = f"{docs_date}-{params.issue_num}-{self.branch_dir_name}"
        else:
            docs_dir_name = f"{docs_date}-{self.branch_dir_name}"
        docs_base = self.config.get_docs_base_dir(self.repo_root)
        self.docs_path = os.path.join(docs_base, docs_dir_name)

        # Docker 镜像（运行时设置）
        self.docker_image: str = ""

    def _log(self, msg: str):
        log(msg, self._logger)

    def _get_repo_root(self) -> str:
        result = run_cmd(["git", "rev-parse", "--show-toplevel"])
        return result.stdout.strip()

    # ========================
    # CLI 入口
    # ========================

    def run(self) -> None:
        """CLI 模式：print + sys.exit"""
        try:
            result = self.run_steps()
            self._log("")
            self._log("==========================================")
            self._log("  开发环境创建完成!")
            self._log("==========================================")
            self._log("")
            self._log(f"Worktree:  {result.worktree_path}")
            self._log(f"Container: {result.container_name}")
            self._log(f"Devpipe Docs: {result.docs_path}")
            self._log("")
            self._log("进入开发环境:")
            self._log(f"  tmux attach -t {self.container_name}")
            self._log("")
            self._log("布局:")
            self._log("  左 Panel: 容器内 Shell")
            self._log("  右 Panel: 容器内 Claude Code（已自动打开）")
            self._log("")
            self._log("手动进入容器:")
            self._log(f"  docker exec -it {self.container_name} zsh")
        except (PrerequisiteError, ConflictError) as e:
            self._log(f"ERROR: {e}")
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            self._log(f"ERROR: 命令执行失败: {e.cmd}")
            if e.stderr:
                self._log(e.stderr)
            sys.exit(1)
        except Exception as e:
            self._log(f"ERROR: {e}")
            sys.exit(1)

    def run_steps(
        self,
        on_stage: Optional[Callable[[str, str], None]] = None,
    ) -> InitEnvResult:
        """
        import 模式：返回结果对象。

        Args:
            on_stage: 回调函数 (stage_name, status)，status 为 "running" 或 "done"
        """
        def _stage(name: str, status: str):
            if on_stage:
                on_stage(name, status)
            if status == "running":
                self._log(f"{name}...")

        self._log("==========================================")
        self._log("  GitHub 项目 Docker 开发环境初始化")
        self._log(f"  本地分支: {self.params.local_branch}")
        if self.params.mode == "local":
            self._log(f"  基于分支: {self.params.base_branch} (本地)")
        else:
            self._log(f"  基于分支: origin/{self.params.base_branch} (远程)")
        self._log(f"  容器名称: {self.container_name}")
        self._log("==========================================")
        self._log("")

        _stage("前置检查", "running")
        self._check_prerequisites()
        _stage("前置检查", "done")

        _stage("冲突检测", "running")
        self._check_conflicts()
        _stage("冲突检测", "done")

        _stage("分支同步", "running")
        self._sync_base_branch()
        _stage("分支同步", "done")

        _stage("创建 Worktree", "running")
        self._create_worktree()
        _stage("创建 Worktree", "done")

        _stage("构建镜像", "running")
        self._build_docker_image()
        _stage("构建镜像", "done")

        _stage("创建容器", "running")
        self._create_docker_container()
        _stage("创建容器", "done")

        _stage("初始化 Git", "running")
        self._init_container_git()
        _stage("初始化 Git", "done")

        _stage("初始化 gh", "running")
        self._init_container_gh()
        _stage("初始化 gh", "done")

        _stage("初始化配置", "running")
        self._init_claude_config()
        _stage("初始化配置", "done")

        _stage("创建 Tmux", "running")
        self._create_tmux_session()
        _stage("创建 Tmux", "done")

        return InitEnvResult(
            worktree_path=self.worktree_path,
            container_name=self.container_name,
            docs_path=self.docs_path,
        )

    # ========================
    # 私有方法
    # ========================

    def _check_prerequisites(self):
        """前置检查：工具和 daemon"""
        missing = []
        if not cmd_exists("docker"):
            missing.append("docker")
        if not cmd_exists("git"):
            missing.append("git")

        if missing:
            raise PrerequisiteError(
                f"以下工具未安装: {', '.join(missing)}\n"
                f"安装方式:\n"
                f"  macOS:   brew install {' '.join(missing)}\n"
                f"  Ubuntu:  sudo apt-get install {' '.join(missing)}\n"
                f"  CentOS:  sudo yum install {' '.join(missing)}"
            )

        # Docker daemon
        result = run_cmd(["docker", "info"], check=False)
        if result.returncode != 0:
            raise PrerequisiteError(
                "Docker daemon 未运行\n请先启动 Docker Desktop 或 Docker daemon"
            )

        # git 仓库
        git_dir = os.path.join(self.repo_root, ".git")
        if not os.path.exists(git_dir):
            raise PrerequisiteError(
                f"不是一个有效的 git 仓库: {self.repo_root}\n"
                "请确认从仓库根目录运行此脚本"
            )

        # gh CLI 认证（可选，仅警告）
        if cmd_exists("gh"):
            result = run_cmd(["gh", "auth", "status"], check=False)
            if result.returncode != 0:
                self._log("WARNING: gh CLI 未登录，部分功能（Issue 查询、PR 创建）将不可用")
                self._log("请执行 'gh auth login' 登录")
        else:
            self._log("WARNING: gh CLI 未安装，部分功能将不可用")
            self._log("安装方式: brew install gh (macOS) / sudo apt install gh (Ubuntu)")

    def _check_conflicts(self):
        """冲突检测"""
        errors = []
        cleanup_cmd = f"python3 cleanup_env.py {self.params.local_branch}"

        # worktree
        if os.path.exists(self.worktree_path):
            errors.append(f"Worktree 已存在: {self.worktree_path}")

        # 本地分支
        result = run_cmd(
            ["git", "-C", self.repo_root, "show-ref", "--verify", "--quiet",
             f"refs/heads/{self.params.local_branch}"],
            check=False,
        )
        if result.returncode == 0:
            errors.append(f"本地分支已存在: {self.params.local_branch}")

        # Docker 容器
        result = run_cmd(["docker", "ps", "-a", "--format", "{{.Names}}"], check=False)
        if result.returncode == 0:
            containers = result.stdout.strip().split("\n")
            if self.container_name in containers:
                errors.append(f"Docker 容器已存在: {self.container_name}")

        # Docker volume
        result = run_cmd(["docker", "volume", "inspect", self.git_volume], check=False)
        if result.returncode == 0:
            errors.append(f"Docker volume 已存在: {self.git_volume}")

        # tmux session
        if cmd_exists("tmux"):
            result = run_cmd(["tmux", "has-session", "-t", self.container_name], check=False)
            if result.returncode == 0:
                errors.append(f"Tmux session 已存在: {self.container_name}")

        if errors:
            raise ConflictError(
                "\n".join(errors) + f"\n\n如需重建，先执行清理:\n  {cleanup_cmd}"
            )

    def _sync_base_branch(self):
        """分支验证"""
        if self.params.mode == "local":
            self._log(f"基于本地分支: {self.params.base_branch} ...")
            result = run_cmd(
                ["git", "-C", self.repo_root, "show-ref", "--verify",
                 f"refs/heads/{self.params.base_branch}"],
                check=False,
            )
            if result.returncode != 0:
                raise PrerequisiteError(
                    f"本地分支不存在: {self.params.base_branch}\n请检查分支名是否正确"
                )
            self._log("本地分支验证完成")
        else:
            self._log(f"同步远程分支: origin/{self.params.base_branch} ...")
            run_cmd(["git", "-C", self.repo_root, "fetch", "origin"], timeout=120)
            result = run_cmd(
                ["git", "-C", self.repo_root, "rev-parse", "--verify",
                 f"origin/{self.params.base_branch}"],
                check=False,
            )
            if result.returncode != 0:
                raise PrerequisiteError(
                    f"远程分支不存在: origin/{self.params.base_branch}\n请检查分支名是否正确"
                )
            self._log("远程代码同步完成")

    def _create_worktree(self):
        """创建 Worktree"""
        self._log(f"创建 Worktree: {self.worktree_path} ...")
        os.makedirs(self.worktree_dir, exist_ok=True)

        if self.params.mode == "local":
            run_cmd([
                "git", "-C", self.repo_root, "worktree", "add",
                self.worktree_path, "-b", self.params.local_branch,
                self.params.base_branch,
            ])
        else:
            run_cmd([
                "git", "-C", self.repo_root, "worktree", "add",
                self.worktree_path, "-b", self.params.local_branch,
                f"origin/{self.params.base_branch}",
            ])

        self._log("Worktree 创建完成")

        # 删除 worktree 的 .git 文件
        git_file = os.path.join(self.worktree_path, ".git")
        if os.path.isfile(git_file):
            os.remove(git_file)
            self._log("已移除 worktree .git 引用（git 操作将在容器内进行）")
        elif os.path.isdir(git_file):
            raise ConflictError(
                f"{git_file} 是目录而非 gitdir 引用文件，跳过删除以避免数据丢失\n"
                "请检查 worktree 创建是否正确"
            )
        else:
            self._log(f"警告: {git_file} 不存在，跳过")

    def _build_docker_image(self):
        """构建/查找 Docker 镜像"""
        self._log("检查 Docker 镜像...")

        sync_script = None

        # 优先使用项目本地的镜像构建脚本
        local_script = os.path.join(self.repo_root, "resources", "sync-docker-image.sh")
        if os.path.isfile(local_script):
            sync_script = local_script
            self._log("使用项目本地镜像构建脚本")
        elif self.params.devpipe_root:
            devpipe_script = os.path.join(
                self.params.devpipe_root, "resources", "sync-docker-image.sh"
            )
            if os.path.isfile(devpipe_script):
                sync_script = devpipe_script
                self._log(f"使用 devpipe 镜像构建脚本: {sync_script}")

        if not sync_script:
            raise PrerequisiteError(
                "找不到镜像构建脚本\n"
                "请确保以下任一条件满足:\n"
                "  1. 项目仓库中存在 resources/sync-docker-image.sh\n"
                "  2. 设置 DEVPIPE_ROOT 环境变量指向 devpipe 仓库\n"
                "  3. 设置 CLAUDE_PLUGIN_ROOT 环境变量指向 devpipe 仓库\n"
                "  4. 传递 devpipe_root 参数指定 devpipe 仓库路径"
            )

        result = run_cmd(["bash", sync_script], timeout=300)
        self.docker_image = result.stdout.strip()
        self._log(f"使用镜像: {self.docker_image}")

    def _create_docker_container(self):
        """创建 Docker 容器"""
        self._log(f"创建 Docker 容器: {self.container_name} ...")

        # 创建 Docker volume
        run_cmd(["docker", "volume", "create", self.git_volume])

        # 创建持久化 docs 目录并创建 symlink
        os.makedirs(self.docs_path, exist_ok=True)
        devpipe_link = os.path.join(self.worktree_path, ".devpipe", "state")
        if os.path.islink(devpipe_link):
            os.remove(devpipe_link)
        elif os.path.isdir(devpipe_link):
            import shutil
            shutil.rmtree(devpipe_link)
        os.makedirs(os.path.dirname(devpipe_link), exist_ok=True)
        os.symlink(self.docs_path, devpipe_link)

        # 构建 volume 挂载参数
        volumes = [
            "-v", f"{self.worktree_path}:{self.container_workspace}",
            "-v", f"{self.git_volume}:{self.container_workspace}/.git",
            "-v", f"{self.docs_path}:{self.container_workspace}/.devpipe/state",
        ]

        # 可选：挂载 SSH 密钥
        ssh_dir = os.path.expanduser("~/.ssh")
        if os.path.isdir(ssh_dir):
            volumes.extend(["-v", f"{ssh_dir}:/home/{self.host_user}/.ssh:rw"])

        # 可选：挂载 .claude 配置目录
        claude_dir = os.path.join(self.repo_root, ".claude")
        if os.path.isdir(claude_dir):
            volumes.extend(["-v", f"{claude_dir}:{self.container_workspace}/.claude"])

        # 项目配置的额外挂载
        volumes.extend(
            self.config.docker_mount_args(self.worktree_path, self.container_workspace)
        )

        # 环境变量
        env_args = [
            "-e", f"HOME=/home/{self.host_user}",
            "-e", "TERM=xterm-256color",
        ]
        anthropic_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if anthropic_token:
            env_args.extend(["-e", f"ANTHROPIC_AUTH_TOKEN={anthropic_token}"])
        anthropic_url = os.environ.get("ANTHROPIC_BASE_URL")
        if anthropic_url:
            env_args.extend(["-e", f"ANTHROPIC_BASE_URL={anthropic_url}"])

        # 端口映射参数（来自 devpipe.yml）
        port_args = self.config.docker_port_args()

        # 创建容器
        cmd = [
            "docker", "run", "-d",
            "--name", self.container_name,
            *volumes,
            *env_args,
            *port_args,
            "-w", self.container_workspace,
            "--entrypoint", "",
            self.docker_image,
            "tail", "-f", "/dev/null",
        ]
        run_cmd(cmd)

        # 等待容器就绪
        for _ in range(10):
            result = run_cmd(
                ["docker", "inspect", "-f", "{{.State.Running}}", self.container_name],
                check=False,
            )
            if result.returncode == 0 and "true" in result.stdout.lower():
                break
            time.sleep(0.5)
        else:
            logs = run_cmd(["docker", "logs", self.container_name], check=False)
            raise PrerequisiteError(
                f"Docker 容器启动失败\n{logs.stdout or ''}\n{logs.stderr or ''}"
            )

        self._log("Docker 容器创建完成")

    def _init_container_git(self):
        """初始化容器内 Git 环境"""
        self._log("初始化容器内 Git 环境...")

        # 修复 Docker volume 权限
        run_cmd([
            "docker", "exec", "-u", "root", self.container_name,
            "chown", "-R", f"{self.host_uid}:{self.host_gid}",
            f"{self.container_workspace}/.git",
        ])

        # 解析实际的 git 目录
        result = run_cmd(["git", "-C", self.repo_root, "rev-parse", "--git-dir"])
        actual_git_dir = result.stdout.strip()
        if not os.path.isabs(actual_git_dir):
            actual_git_dir = os.path.join(self.repo_root, actual_git_dir)
        self._log(f"实际 git 目录: {actual_git_dir}")

        # 复制 .git 数据到 Docker volume
        run_cmd([
            "docker", "cp", f"{actual_git_dir}/.",
            f"{self.container_name}:{self.container_workspace}/.git/",
        ])

        # 修复容器内 git 配置并 checkout
        bash_script = f"""
            sed -i 's|worktree = .*|worktree = {self.container_workspace}|' .git/config 2>/dev/null || true
            rm -rf .git/worktrees
            sed -i '/worktreeConfig/d' .git/config 2>/dev/null || true
            git checkout -f {self.params.local_branch}
        """
        run_cmd([
            "docker", "exec", "-w", self.container_workspace,
            self.container_name, "bash", "-c", bash_script,
        ])

        # 复制宿主机 git 全局配置
        gitconfig = os.path.expanduser("~/.gitconfig")
        if os.path.isfile(gitconfig):
            run_cmd([
                "docker", "cp", gitconfig,
                f"{self.container_name}:/home/{self.host_user}/.gitconfig",
            ])

        self._log(f"Git 环境初始化完成 (分支: {self.params.local_branch})")

    def _init_container_gh(self):
        """初始化容器内 gh CLI 认证"""
        self._log("初始化容器内 gh CLI 认证...")

        if not cmd_exists("gh"):
            self._log("WARNING: 宿主机 gh CLI 未安装，跳过")
            return

        result = run_cmd(["gh", "auth", "status"], check=False)
        if result.returncode != 0:
            self._log("WARNING: 宿主机 gh CLI 未认证，跳过")
            return

        result = run_cmd(["gh", "auth", "token"], check=False)
        if result.returncode != 0 or not result.stdout.strip():
            self._log("WARNING: 无法获取 gh token，跳过")
            return

        gh_token = result.stdout.strip()

        # 使用 subprocess.Popen 传递 token
        proc = subprocess.Popen(
            ["docker", "exec", "-i", self.container_name, "gh", "auth", "login", "--with-token"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc.communicate(input=gh_token, timeout=30)

        self._log("gh CLI 认证完成")

    def _init_claude_config(self):
        """初始化 Claude 配置"""
        self._log("初始化 Claude 配置...")

        container_claude_dir = f"/home/{self.host_user}/.claude"

        # 创建容器内的 ~/.claude/ 目录
        run_cmd(["docker", "exec", self.container_name, "mkdir", "-p", container_claude_dir])

        # 复制宿主机的 settings.json
        settings_path = os.path.expanduser("~/.claude/settings.json")
        if os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings_content = f.read()

            # 替换 localhost 为 host.docker.internal
            settings_content = settings_content.replace(
                "http://localhost:", "http://host.docker.internal:"
            )

            # 写入容器
            proc = subprocess.Popen(
                ["docker", "exec", "-i", self.container_name,
                 "tee", f"{container_claude_dir}/settings.json"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                text=True,
            )
            proc.communicate(input=settings_content, timeout=30)
            self._log("Claude 配置已初始化")
        else:
            self._log("警告: 未找到 ~/.claude/settings.json，跳过 Claude 配置初始化")

        # 复制 statusline-command.sh
        statusline_path = os.path.expanduser("~/.claude/statusline-command.sh")
        if os.path.isfile(statusline_path):
            run_cmd([
                "docker", "cp", statusline_path,
                f"{self.container_name}:{container_claude_dir}/statusline-command.sh",
            ])
            run_cmd([
                "docker", "exec", self.container_name,
                "chmod", "+x", f"{container_claude_dir}/statusline-command.sh",
            ])
            self._log("statusline-command.sh 已复制到容器")

    def _create_tmux_session(self):
        """创建 Tmux Session"""
        if not cmd_exists("tmux"):
            self._log("tmux 未安装，跳过 tmux session 创建")
            self._log(f"可手动进入容器: docker exec -it {self.container_name} zsh")
            return

        self._log(f"创建 Tmux Session: {self.container_name} ...")

        # 配置 tmux 256 色支持
        run_cmd(["tmux", "set-option", "-g", "default-terminal", "screen-256color"], check=False)
        run_cmd(
            ["tmux", "set-option", "-ga", "terminal-overrides", ",xterm-256color:Tc"],
            check=False,
        )

        # 创建 session
        run_cmd([
            "tmux", "new-session", "-d", "-s", self.container_name,
            "-e", f"DEV_WORKTREE_NAME={self.params.local_branch}",
            "-e", f"DEV_CONTAINER_NAME={self.container_name}",
            "-e", f"DEV_REPO_ROOT={self.repo_root}",
            "-e", "TERM=xterm-256color",
        ])

        # 左 panel: 进入容器 Shell
        run_cmd([
            "tmux", "send-keys", "-t", f"{self.container_name}:0.0",
            f"docker exec -it -w {self.container_workspace} {self.container_name} zsh",
            "Enter",
        ])

        time.sleep(1)

        run_cmd([
            "tmux", "send-keys", "-t", f"{self.container_name}:0.0",
            "clear", "Enter",
        ])

        # 垂直分割
        run_cmd(["tmux", "split-window", "-h", "-t", self.container_name])

        # 右 panel: 进入容器并启动 Claude Code
        run_cmd([
            "tmux", "send-keys", "-t", f"{self.container_name}:0.1",
            f"docker exec -it -w {self.container_workspace} {self.container_name} zsh",
            "Enter",
        ])

        time.sleep(1)

        # 启动 Claude Code
        run_cmd([
            "tmux", "send-keys", "-t", f"{self.container_name}:0.1",
            "unset CLAUDECODE && claude --plugin-dir ./.claude/plugins/devpipe --dangerously-skip-permissions",
            "Enter",
        ])

        self._log("Tmux Session 创建完成")
