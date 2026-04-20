import subprocess
import os

# Dashboard 根目录（devpipe 插件目录）
DEVPIPE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 动态获取仓库根目录
def get_repo_root():
    """从 DEVPIPE_ROOT 的父目录向上查找项目 git 根目录"""
    # DEVPIPE_ROOT 自身是一个独立 git 仓库，从它的父目录开始向上找项目根
    current = os.path.dirname(DEVPIPE_ROOT)
    while current != os.path.dirname(current):  # 未到文件系统根
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        current = os.path.dirname(current)
    # fallback 到当前目录
    return os.getcwd()

REPO_ROOT = get_repo_root()
WORKTREE_DIR = os.path.join(REPO_ROOT, ".devpipe", "worktrees")

DEFAULT_DASHBOARD_PORT = 5051


def get_dashboard_port() -> int:
    """从 {REPO_ROOT}/.devpipe/devpipe.yml 解析 dashboard_port，默认 5051"""
    yml_path = os.path.join(REPO_ROOT, ".devpipe", "devpipe.yml")
    if not os.path.isfile(yml_path):
        return DEFAULT_DASHBOARD_PORT
    try:
        with open(yml_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("dashboard_port:"):
                    value = line[len("dashboard_port:"):].strip()
                    if "#" in value:
                        value = value[:value.index("#")].strip()
                    if value:
                        return int(value)
    except (IOError, ValueError):
        pass
    return DEFAULT_DASHBOARD_PORT

# 分支前缀
BRANCH_PREFIXES = {
    "新功能": "feature-",
    "Bugfix": "fix-",
    "优化重构": "refactor-"
}

# GitHub Issue URL 模板（运行时生成）
def get_github_issue_url(issue_number: str, repo: str = None) -> str:
    """生成 GitHub Issue 链接"""
    if not issue_number:
        return ""
    if repo:
        return f"https://github.com/{repo}/issues/{issue_number}"
    # 尝试从 git remote 获取 repo
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
            cwd=REPO_ROOT
        )
        if result.returncode == 0:
            remote_url = result.stdout.strip()
            # 解析 git@github.com:owner/repo.git 或 https://github.com/owner/repo.git
            if remote_url.startswith("git@github.com:"):
                repo = remote_url[15:].rstrip(".git")
            elif remote_url.startswith("https://github.com/"):
                repo = remote_url[19:].rstrip(".git")
            if repo:
                return f"https://github.com/{repo}/issues/{issue_number}"
    except:
        pass
    return f"https://github.com/issues/{issue_number}"