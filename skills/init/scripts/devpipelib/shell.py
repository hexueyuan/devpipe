"""subprocess 封装和异常层次"""

import shutil
import subprocess
from typing import Callable, Optional


# ========================
# 异常层次
# ========================

class DevpipeError(Exception):
    """devpipe 基础异常"""


class PrerequisiteError(DevpipeError):
    """前置条件不满足（缺少工具、daemon 未运行等）"""


class ConflictError(DevpipeError):
    """资源冲突（worktree/容器/分支已存在）"""


class ConfigError(DevpipeError):
    """配置文件解析错误"""


# ========================
# 核心函数
# ========================

def run_cmd(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: int = 60,
    check: bool = True,
    capture: bool = True,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    """
    执行子进程命令。

    Args:
        cmd: 命令和参数列表
        cwd: 工作目录
        timeout: 超时秒数
        check: 是否在非零退出码时抛出异常
        capture: 是否捕获 stdout/stderr
        env: 环境变量字典

    Returns:
        CompletedProcess 对象

    Raises:
        subprocess.CalledProcessError: check=True 且退出码非零
        subprocess.TimeoutExpired: 超时
    """
    kwargs = {
        "cwd": cwd,
        "timeout": timeout,
        "text": True,
    }
    if capture:
        kwargs["capture_output"] = True
    if env is not None:
        kwargs["env"] = env
    result = subprocess.run(cmd, **kwargs)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd,
            output=getattr(result, "stdout", None),
            stderr=getattr(result, "stderr", None),
        )
    return result


def cmd_exists(name: str) -> bool:
    """检查命令是否存在于 PATH 中"""
    return shutil.which(name) is not None


def log(msg: str, logger: Optional[Callable[[str], None]] = None):
    """输出日志，可注入 logger，默认 print"""
    if logger:
        logger(msg)
    else:
        print(msg)
