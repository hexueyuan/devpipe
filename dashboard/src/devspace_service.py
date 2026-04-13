"""
开发空间创建服务

提供开发空间创建功能的核心逻辑，完整替代 devflow:init skill。

包含功能：
- iCafe 卡片查询和开发类型映射
- 分支验证和命名
- 环境创建（worktree + container + tmux）
- 编译验证
- context.json 写入
"""

import json
import os
import re
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from openai import OpenAI

# 支持直接运行和模块运行
try:
    from .config import DEVPIPE_ROOT, REPO_ROOT, WORKTREE_DIR, BRANCH_PREFIXES
except ImportError:
    from config import DEVPIPE_ROOT, REPO_ROOT, WORKTREE_DIR, BRANCH_PREFIXES


# LLM 客户端（延迟初始化）
_llm_client = None


def _get_llm_client() -> OpenAI:
    """获取 LLM 客户端（单例模式）"""
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(
            base_url=os.environ.get("LLM_BASE_URL", "http://localhost:8086/v1"),
            api_key=os.environ.get("LLM_API_KEY", "sk-octopus-72DjJixqBZuBT7woR3Nza4LR50eYMdYfMkRBrDEtMukFltzk")
        )
    return _llm_client


def _get_github_repo() -> Optional[str]:
    """
    获取当前仓库的 GitHub repo (owner/repo 格式)。

    Returns:
        如 "hexueyuan/test-devpipe" 或 None
    """
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
                return remote_url[15:].rstrip(".git")
            elif remote_url.startswith("https://github.com/"):
                return remote_url[19:].rstrip(".git")
    except:
        pass
    return None


# 内存任务存储（CreateTask 和 CleanupTask 共用）
_tasks: Dict[str, object] = {}
_tasks_lock = threading.Lock()

# 任务过期时间（秒）
TASK_EXPIRE_SECONDS = 3600

# 脚本路径
INIT_ENV_SCRIPT = os.path.join(
    DEVPIPE_ROOT,
    "skills/init/scripts/init-env.sh"
)
CLEANUP_ENV_SCRIPT = os.path.join(
    DEVPIPE_ROOT,
    "skills/init/scripts/cleanup-env.sh"
)


# 卡片类型 → 开发类型映射
CARD_TYPE_MAP = {
    "Bug": "Bugfix",
    "bug": "Bugfix",
    "Bug(线上)": "Bugfix",  # 线上 Bug
    "缺陷": "Bugfix",
    "需求": "新功能",
    "用户故事": "新功能",
    "Story": "新功能",
    "story": "新功能",
    "功能": "新功能",
    "任务": None,  # 需要根据标题判断
    "Task": None,
    "task": None,
    "Tech Task": None,  # 技术任务，根据标题判断
    "子任务": None,
}

# 标题关键词 → 开发类型映射（用于任务类型）
TITLE_KEYWORDS_MAP = {
    "重构": "优化重构",
    "优化": "优化重构",
    "清理": "优化重构",
    "refactor": "优化重构",
    "cleanup": "优化重构",
}

# GitHub Issue label → 分支前缀映射
LABEL_BRANCH_PREFIX = {
    "feature": "feature-",
    "bug": "fix-",
    "refactor": "refactor-",
}

# GitHub Issue label → 开发类型映射
LABEL_DEV_TYPE = {
    "feature": "新功能",
    "bug": "Bugfix",
    "refactor": "优化重构",
}


@dataclass
class StageInfo:
    """阶段信息"""
    name: str
    status: str  # pending, running, done, failed


@dataclass
class CreateTask:
    """创建任务"""
    task_id: str
    status: str = "pending"  # pending, running, success, failed
    progress: int = 0
    stage: str = ""
    stages: List[StageInfo] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    error_detail: Optional[str] = None
    cleaned_up: bool = False
    result: Optional[Dict] = None
    created_at: datetime = field(default_factory=datetime.now)

    # 创建参数
    branch_name: str = ""
    base_branch: str = ""
    mode: str = "remote"
    github_issue: Optional[str] = None
    github_issue_title: Optional[str] = None
    github_issue_body: Optional[str] = None
    github_issue_url: Optional[str] = None
    github_repo: Optional[str] = None
    dev_type: str = ""
    description: str = ""
    docs_path: str = ""


def _init_stages() -> List[StageInfo]:
    """初始化阶段列表"""
    return [
        StageInfo(name="前置检查", status="pending"),
        StageInfo(name="分支同步", status="pending"),
        StageInfo(name="创建 Worktree", status="pending"),
        StageInfo(name="构建镜像", status="pending"),
        StageInfo(name="创建容器", status="pending"),
        StageInfo(name="初始化 Git", status="pending"),
        StageInfo(name="初始化配置", status="pending"),
        StageInfo(name="创建 Tmux", status="pending"),
    ]


def _update_stage(task: CreateTask, stage_name: str, status: str):
    """更新阶段状态"""
    for stage in task.stages:
        if stage.name == stage_name:
            stage.status = status
            if status == "running":
                task.stage = stage_name
            break


def _get_progress_by_stage(stage_name: str) -> int:
    """根据阶段名获取进度百分比"""
    progress_map = {
        "前置检查": 5,
        "分支同步": 15,
        "创建 Worktree": 30,
        "构建镜像": 40,
        "创建容器": 55,
        "初始化 Git": 70,
        "初始化配置": 80,
        "创建 Tmux": 95,
    }
    return progress_map.get(stage_name, 0)


def query_github_issue(issue_input: str) -> Dict:
    """
    查询 GitHub Issue 信息

    Args:
        issue_input: Issue 编号或链接，支持格式：
            - 123
            - https://github.com/owner/repo/issues/123

    Returns:
        dict with keys: success, data/error
        data keys: number, title, body, url, dev_type, suggested_branch, repo
    """
    # 解析输入
    issue_number, repo = _parse_issue_input(issue_input)
    if not issue_number:
        return {"success": False, "error": f"无法解析 Issue 编号: {issue_input}"}

    # 如果没有从输入中获取到 repo，尝试从 git remote 获取
    if not repo:
        repo = _get_github_repo()
    if not repo:
        return {"success": False, "error": "无法确定 GitHub 仓库，请确保在 git 仓库中运行或提供完整 Issue URL"}

    try:
        # 使用 gh issue view 命令查询
        result = subprocess.run(
            ["gh", "issue", "view", issue_number, "--repo", repo, "--json", "number,title,body,labels,url"],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Issue 不存在或 gh 未登录"
            return {"success": False, "error": error_msg}

        issue_data = json.loads(result.stdout)

        # 根据 label 映射开发类型
        labels = [label.get("name", "") for label in issue_data.get("labels", [])]
        dev_type = map_dev_type_from_labels(labels, issue_data.get("title", ""))

        # 生成建议分支名（只含描述部分，不含前缀）
        title = issue_data.get("title", "")
        suggested_branch = generate_branch_name(title)

        return {
            "success": True,
            "data": {
                "number": str(issue_data.get("number", issue_number)),
                "title": title,
                "body": issue_data.get("body", ""),
                "url": issue_data.get("url", f"https://github.com/{repo}/issues/{issue_number}"),
                "dev_type": dev_type,
                "labels": labels,
                "suggested_branch": suggested_branch,
                "repo": repo
            }
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "查询超时"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"解析响应失败: {e}"}
    except FileNotFoundError:
        return {"success": False, "error": "gh CLI 未安装，请先安装 GitHub CLI"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _parse_issue_input(issue_input: str) -> tuple[Optional[str], Optional[str]]:
    """
    解析 Issue 输入，支持多种格式

    Args:
        issue_input: Issue 编号或链接

    Returns:
        (issue_number, repo) 或 (None, None)
    """
    issue_input = issue_input.strip()

    # 纯数字
    if issue_input.isdigit():
        return issue_input, None

    # URL 格式: https://github.com/owner/repo/issues/123
    url_match = re.search(r'github\.com/([^/]+/[^/]+)/issues/(\d+)', issue_input)
    if url_match:
        repo = url_match.group(1)
        issue_number = url_match.group(2)
        return issue_number, repo

    return None, None


def map_dev_type_from_labels(labels: List[str], title: str) -> str:
    """
    根据 Issue labels 和标题映射开发类型

    Args:
        labels: Issue 标签列表
        title: Issue 标题

    Returns:
        开发类型：新功能、Bugfix、优化重构
    """
    # Label 到开发类型的映射
    label_map = {
        "bug": "Bugfix",
        "Bug": "Bugfix",
        "enhancement": "优化重构",
        "refactor": "优化重构",
        "feature": "新功能",
        "Feature": "新功能",
    }

    # 检查 labels
    for label in labels:
        label_lower = label.lower()
        for key, dev_type in label_map.items():
            if key.lower() in label_lower:
                return dev_type

    # 根据 title 判断
    title_lower = title.lower()
    if any(kw in title_lower for kw in ["fix", "bug", "修复", "问题"]):
        return "Bugfix"
    if any(kw in title_lower for kw in ["refactor", "optimize", "优化", "重构"]):
        return "优化重构"

    # 默认为新功能
    return "新功能"


# 兼容旧 API
def query_icafe_card(card_input: str) -> Dict:
    """
    兼容旧 API，转发到 query_github_issue
    """
    return query_github_issue(card_input)


def generate_branch_name(description: str) -> str:
    """
    根据描述生成分支名的描述部分（不含前缀）。

    先尝试用 LLM 生成语义化的名称，失败时 fallback 到关键词提取逻辑。

    Args:
        description: 功能描述或 Issue 标题

    Returns:
        分支名描述部分，如 add-login, memory-leak-fix, cleanup-code（不含前缀）
    """
    # 先尝试 LLM 生成
    try:
        llm_name = _generate_branch_name_by_llm(description)
        if llm_name:
            return llm_name
    except Exception:
        pass

    # fallback 到原有逻辑
    return _generate_short_name(description)


def _generate_branch_name_by_llm(description: str) -> Optional[str]:
    """
    使用 LLM 生成语义化的分支名描述部分（不含前缀）

    Args:
        description: 功能描述或 Issue 标题

    Returns:
        分支名描述部分（如 add-login），或 None 表示失败
    """
    if not description or not description.strip():
        return None

    client = _get_llm_client()

    prompt = f"""根据以下功能描述，生成一个简短的 kebab-case 描述短语，用于开发分支名的一部分。

要求：
1. 格式：纯 kebab-case（小写字母和连字符），不要包含任何前缀（如 feature-、fix-、refactor-）
2. 长度：不超过 20 个字符
3. 内容：用 2-4 个英文单词概括核心功能，要有语义
4. 只输出描述短语本身，不要任何解释

示例：
- "Add 5.x cluster deployment support" → 5x-cluster-deploy
- "Fix rollback issue during scaling" → rollback-scaling
- "Optimize message consumption performance" → consume-perf
- "Add metrics export feature" → metrics-export

功能描述：{description}"""

    response = client.chat.completions.create(
        model="cheap-text",
        max_tokens=50,
        messages=[{"role": "user", "content": prompt}]
    )

    raw_name = response.choices[0].message.content.strip()

    # 清洗输出
    return _clean_branch_name(raw_name)


def _clean_branch_name(raw_name: str) -> Optional[str]:
    """
    清洗 LLM 输出的分支名描述部分（不含前缀）

    Args:
        raw_name: LLM 原始输出

    Returns:
        清洗后的描述部分，或 None 表示无效
    """
    if not raw_name:
        return None

    # 移除可能的引号和空白
    name = raw_name.strip().strip('"\'`')

    # 剥离 LLM 可能生成的任何已知前缀
    known_prefixes = ["feature-", "fix-", "refactor-", "bugfix-"]
    for p in known_prefixes:
        if name.startswith(p):
            name = name[len(p):]
            break
    # 也处理旧格式 wt- 前缀
    if name.startswith('wt-'):
        name = name[3:]

    # 转换为 kebab-case：替换空格和下划线为连字符，移除非法字符
    name = re.sub(r'[\s_]+', '-', name)
    name = re.sub(r'[^a-zA-Z0-9\-]', '', name)
    name = name.lower()

    # 移除连续的连字符
    name = re.sub(r'-+', '-', name)

    # 移除首尾的连字符
    name = name.strip('-')

    # 长度限制
    if len(name) > 20:
        name = name[:20].rstrip('-')

    # 验证结果
    if len(name) < 2:  # 太短，无效
        return None

    return name


def _generate_short_name(description: str) -> str:
    """
    关键词提取方式生成简短名称（fallback 逻辑）

    Args:
        description: 功能描述或 Issue 标题

    Returns:
        简短名称，如 add-cluster-support
    """
    # 移除特殊字符，只保留字母、数字、中文和空格
    cleaned = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', description)

    # 分词
    words = cleaned.split()

    # 过滤停用词和短词
    stop_words = {'的', '了', '和', '与', '或', '是', '在', '有', '为', '将', '可以',
                  'the', 'a', 'an', 'is', 'are', 'to', 'for', 'of', 'and', 'or'}
    words = [w for w in words if w.lower() not in stop_words and len(w) > 1]

    # 取前 3-4 个关键词
    keywords = []
    for word in words[:5]:
        # 英文词转小写
        if re.match(r'^[a-zA-Z0-9]+$', word):
            keywords.append(word.lower())
        elif re.match(r'^[\u4e00-\u9fff]+$', word):
            # 中文词：跳过或用拼音（这里简化处理）
            continue
        if len(keywords) >= 4:
            break

    # 如果没有足够的关键词，生成一个简短的名称
    if len(keywords) < 2:
        # 使用时间戳的后几位
        ts = datetime.now().strftime("%m%d%H%M")
        keywords = ["dev", ts]

    # 组合成名称
    return "-".join(keywords)


def validate_branch(branch: str, mode: str = "remote") -> Dict:
    """
    验证基础分支是否存在

    Args:
        branch: 分支名
        mode: local 或 remote

    Returns:
        dict with keys: success, exists
    """
    try:
        if mode == "local":
            result = subprocess.run(
                ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
                cwd=REPO_ROOT,
                capture_output=True,
                timeout=10
            )
            exists = result.returncode == 0
        else:
            # 先 fetch
            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=REPO_ROOT,
                capture_output=True,
                timeout=60
            )
            # 检查远程分支
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                cwd=REPO_ROOT,
                capture_output=True,
                timeout=10
            )
            exists = result.returncode == 0

        return {"success": True, "exists": exists}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "验证超时"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_conflicts(branch_name: str) -> List[str]:
    """
    检查资源冲突

    Args:
        branch_name: 本地分支名

    Returns:
        冲突列表，空表示无冲突
    """
    conflicts = []

    # 检查 worktree 目录（目录名用 - 替换 /）
    worktree_path = os.path.join(WORKTREE_DIR, branch_name.replace("/", "-"))
    if os.path.exists(worktree_path):
        conflicts.append(f"Worktree 目录已存在: {worktree_path}")

    # 检查本地分支
    result = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch_name}"],
        cwd=REPO_ROOT,
        capture_output=True
    )
    if result.returncode == 0:
        conflicts.append(f"本地分支已存在: {branch_name}")

    # 容器名：将 / 替换为 -
    container_name = branch_name.replace("/", "-")

    # 检查 Docker 容器
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        containers = result.stdout.strip().split("\n")
        if container_name in containers:
            conflicts.append(f"Docker 容器已存在: {container_name}")

    # 检查 Docker volume
    volume_name = f"git-{container_name}"
    result = subprocess.run(
        ["docker", "volume", "inspect", volume_name],
        capture_output=True
    )
    if result.returncode == 0:
        conflicts.append(f"Docker volume 已存在: {volume_name}")

    # 检查 tmux session
    result = subprocess.run(
        ["tmux", "has-session", "-t", container_name],
        capture_output=True
    )
    if result.returncode == 0:
        conflicts.append(f"Tmux session 已存在: {container_name}")

    return conflicts


def create_devspace_async(params: Dict) -> str:
    """
    异步创建开发空间

    Args:
        params: 创建参数
            - branch_name: 本地分支名
            - base_branch: 基础分支
            - mode: local/remote
            - github_issue: GitHub Issue 编号（可选）
            - github_issue_title: Issue 标题（可选）
            - github_issue_body: Issue 内容（可选）
            - github_issue_url: Issue URL（可选）
            - github_repo: GitHub 仓库（可选）
            - dev_type: 开发类型
            - description: 功能描述

    Returns:
        任务 ID
    """
    task_id = str(uuid.uuid4())

    task = CreateTask(
        task_id=task_id,
        status="pending",
        stages=_init_stages(),
        branch_name=params.get("branch_name", ""),
        base_branch=params.get("base_branch", "main"),
        mode=params.get("mode", "remote"),
        github_issue=params.get("github_issue"),
        github_issue_title=params.get("github_issue_title"),
        github_issue_body=params.get("github_issue_body"),
        github_issue_url=params.get("github_issue_url"),
        github_repo=params.get("github_repo"),
        dev_type=params.get("dev_type", "新功能"),
        description=params.get("description", "")
    )

    with _tasks_lock:
        _tasks[task_id] = task

    # 启动后台线程执行创建
    thread = threading.Thread(target=_run_create_task, args=(task,))
    thread.daemon = True
    thread.start()

    return task_id


def get_task_status(task_id: str) -> Optional[Dict]:
    """
    获取任务状态

    Args:
        task_id: 任务 ID

    Returns:
        任务状态字典，或 None
    """
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return None

        return {
            "status": task.status,
            "progress": task.progress,
            "stage": task.stage,
            "stages": [{"name": s.name, "status": s.status} for s in task.stages],
            "logs": task.logs[-50:],  # 只返回最近 50 条日志
            "error": task.error,
            "error_detail": task.error_detail,
            "cleaned_up": task.cleaned_up,
            "result": task.result
        }


def _run_create_task(task: CreateTask):
    """
    执行创建任务（在后台线程中运行）
    """
    task.status = "running"

    try:
        # 执行 init-env.sh
        _run_init_script(task)

        # 写入 context.json
        _write_context_json(task)

        # 成功
        task.status = "success"
        task.progress = 100
        task.result = {
            "worktree_path": os.path.join(WORKTREE_DIR, task.branch_name.replace("/", "-")),
            "container_name": task.branch_name,
            "tmux_session": task.branch_name
        }
        task.logs.append("开发环境创建完成！")

    except CreateError as e:
        task.status = "failed"
        task.error = str(e)
        task.error_detail = e.detail
        task.logs.append(f"错误: {e}")

        # 自动回滚
        _run_cleanup(task)
        task.cleaned_up = True
        task.logs.append(f"已自动清理资源: {task.branch_name}")

    except Exception as e:
        task.status = "failed"
        task.error = f"未预期的错误: {str(e)}"
        task.logs.append(f"错误: {e}")

        # 自动回滚
        _run_cleanup(task)
        task.cleaned_up = True


class CreateError(Exception):
    """创建错误"""
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


def _run_init_script(task: CreateTask):
    """
    执行 init-env.sh 脚本

    通过解析脚本输出来更新进度
    """
    if not os.path.exists(INIT_ENV_SCRIPT):
        raise CreateError("init-env.sh 脚本不存在", INIT_ENV_SCRIPT)

    # 构建命令
    cmd = ["bash", INIT_ENV_SCRIPT, task.branch_name, task.base_branch, task.mode, DEVPIPE_ROOT, task.github_issue or ""]

    task.logs.append(f"执行: {' '.join(cmd)}")

    # 脚本开始即认为前置检查开始
    _update_stage(task, "前置检查", "running")
    task.progress = _get_progress_by_stage("前置检查")

    # 用于捕获脚本输出的 docs 路径
    docs_path = ""

    # 进度关键词映射
    progress_keywords = {
        "同步远程分支": "分支同步",
        "基于本地分支": "分支同步",
        "远程代码同步完成": "分支同步",
        "本地分支验证完成": "分支同步",
        "创建 Worktree": "创建 Worktree",
        "Worktree 创建完成": "创建 Worktree",
        "检查基础镜像": "构建镜像",
        "使用镜像": "构建镜像",
        "创建 Docker 容器": "创建容器",
        "Docker 容器创建完成": "创建容器",
        "初始化容器内 Git": "初始化 Git",
        "Git 环境初始化完成": "初始化 Git",
        "初始化 Claude 配置": "初始化配置",
        "Claude 配置已初始化": "初始化配置",
        "创建 Tmux Session": "创建 Tmux",
        "Tmux Session 创建完成": "创建 Tmux",
        "开发环境创建完成": "创建 Tmux",
    }

    # 确保环境变量正确传递
    env = os.environ.copy()
    if "HOME" not in env:
        env["HOME"] = os.path.expanduser("~")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPO_ROOT,
        bufsize=1,
        env=env
    )

    current_stage = "前置检查"  # 脚本开始即进入前置检查阶段

    for line in iter(process.stdout.readline, ''):
        line = line.rstrip()
        if not line:
            continue

        task.logs.append(line)

        # 捕获 docs 路径
        if line.startswith("Devpipe Docs:"):
            docs_path = line.split(":", 1)[1].strip()

        # 检查是否是错误
        if line.startswith("ERROR:"):
            process.terminate()
            raise CreateError(line, "\n".join(task.logs[-20:]))

        # 更新进度
        for keyword, stage_name in progress_keywords.items():
            if keyword in line:
                if current_stage and current_stage != stage_name:
                    _update_stage(task, current_stage, "done")
                _update_stage(task, stage_name, "running")
                task.progress = _get_progress_by_stage(stage_name)
                current_stage = stage_name
                break

    process.wait()

    if process.returncode != 0:
        raise CreateError(
            f"init-env.sh 执行失败 (exit code: {process.returncode})",
            "\n".join(task.logs[-20:])
        )

    # 标记最后一个阶段完成
    if current_stage:
        _update_stage(task, current_stage, "done")

    # 保存 docs 路径到 task
    task.docs_path = docs_path


def _write_context_json(task: CreateTask):
    """
    写入 context.json 文件

    写入到 docs_path（持久化目录），而非 worktree/.devpipe/。
    Docker 容器将 docs_path bind mount 到 .devpipe，所以必须写入 docs_path
    才能让容器内的 stage-gate.sh 找到 context.json。
    """
    # 优先使用 docs_path（Docker 挂载源），回退到 worktree/.devpipe/
    if task.docs_path and os.path.isdir(task.docs_path):
        devflow_dir = task.docs_path
    else:
        worktree_path = os.path.join(WORKTREE_DIR, task.branch_name.replace("/", "-"))
        devflow_dir = os.path.join(worktree_path, ".devpipe")

    if not os.path.exists(devflow_dir):
        os.makedirs(devflow_dir, exist_ok=True)

    # 当前时间（ISO 8601 格式）
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")

    context = {
        "stage": "init",
        "stage_completed": True,
        "dev_type": task.dev_type,
        "description": task.description,
        "github_issue": task.github_issue or "",
        "github_issue_title": task.github_issue_title or "",
        "github_issue_body": task.github_issue_body or "",
        "github_issue_url": task.github_issue_url or "",
        "github_repo": task.github_repo or "",
        "remote_branch": task.base_branch,
        "local_branch": task.branch_name,
        "container_name": task.branch_name.replace("/", "-"),
        "repo_root": REPO_ROOT,
        "worktree_path": worktree_path,
        "docs_path": task.docs_path,
        "created_at": now_iso,
        "stage_timestamps": {
            "init": {
                "started_at": now_iso,
                "ended_at": now_iso
            }
        }
    }

    context_path = os.path.join(devflow_dir, "context.json")
    with open(context_path, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

    task.logs.append(f"context.json 已写入: {context_path}")


def _run_cleanup(task: CreateTask):
    """
    执行清理脚本回滚资源
    """
    if not task.branch_name:
        return

    if not os.path.exists(CLEANUP_ENV_SCRIPT):
        task.logs.append(f"警告: 清理脚本不存在: {CLEANUP_ENV_SCRIPT}")
        return

    try:
        result = subprocess.run(
            ["bash", CLEANUP_ENV_SCRIPT, task.branch_name],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                task.logs.append(f"[cleanup] {line}")
        if result.stderr:
            for line in result.stderr.strip().split("\n"):
                task.logs.append(f"[cleanup error] {line}")
    except Exception as e:
        task.logs.append(f"[cleanup error] {e}")


import shutil


@dataclass
class CleanupTask:
    """清理任务"""
    task_id: str
    status: str = "pending"  # pending, running, success, failed
    progress: int = 0
    stage: str = ""
    stages: List[StageInfo] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    error_detail: Optional[str] = None
    cleaned_up: bool = False
    result: Optional[Dict] = None
    created_at: datetime = field(default_factory=datetime.now)
    branch_name: str = ""
    force: bool = False


def probe_resources(branch_name: str) -> Dict:
    """
    探测开发空间关联的 5 种资源是否存在。

    Returns:
        {
            "container": {"exists": bool, "name": str},
            "volume": {"exists": bool, "name": str},
            "tmux": {"exists": bool, "name": str},
            "worktree": {"exists": bool, "path": str},
            "branch": {"exists": bool, "name": str},
            "total_count": int
        }
    """
    result = {}
    total = 0

    # 容器名：将 / 替换为 -
    container_name = branch_name.replace("/", "-")
    try:
        proc = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5
        )
        containers = proc.stdout.strip().split("\n") if proc.stdout.strip() else []
        exists = container_name in containers
    except Exception:
        exists = False
    result["container"] = {"exists": exists, "name": container_name}
    if exists:
        total += 1

    # Volume
    volume_name = f"git-{branch_name.replace('/', '-')}"
    try:
        proc = subprocess.run(
            ["docker", "volume", "inspect", volume_name],
            capture_output=True, timeout=5
        )
        exists = proc.returncode == 0
    except Exception:
        exists = False
    result["volume"] = {"exists": exists, "name": volume_name}
    if exists:
        total += 1

    # Tmux (tmux session 名不支持 /，需要替换)
    tmux_name = branch_name.replace("/", "-")
    try:
        proc = subprocess.run(
            ["tmux", "has-session", "-t", tmux_name],
            capture_output=True, timeout=5
        )
        exists = proc.returncode == 0
    except Exception:
        exists = False
    result["tmux"] = {"exists": exists, "name": tmux_name}
    if exists:
        total += 1

    # Worktree（目录名用 - 替换 /）
    worktree_path = os.path.join(WORKTREE_DIR, branch_name.replace("/", "-"))
    exists = os.path.isdir(worktree_path)
    result["worktree"] = {"exists": exists, "path": worktree_path}
    if exists:
        total += 1

    # Branch
    try:
        proc = subprocess.run(
            ["git", "-C", REPO_ROOT, "show-ref", "--verify", f"refs/heads/{branch_name}"],
            capture_output=True, timeout=5
        )
        exists = proc.returncode == 0
    except Exception:
        exists = False
    result["branch"] = {"exists": exists, "name": branch_name}
    if exists:
        total += 1

    result["total_count"] = total
    return result


def check_uncommitted_changes(branch_name: str) -> Dict:
    """
    检查开发空间是否有未提交的变更。

    Returns:
        {"has_changes": bool, "changes": str}
    """
    worktree_path = os.path.join(WORKTREE_DIR, branch_name.replace("/", "-"))
    if not os.path.isdir(worktree_path):
        return {"has_changes": False, "changes": ""}

    # 容器名：将 / 替换为 -
    container_name = branch_name.replace("/", "-")
    # 检查容器是否存在
    try:
        proc = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5
        )
        containers = proc.stdout.strip().split("\n") if proc.stdout.strip() else []
        container_exists = container_name in containers
    except Exception:
        container_exists = False

    if not container_exists:
        return {"has_changes": False, "changes": ""}

    # 动态计算容器内路径
    repo_name = os.path.basename(REPO_ROOT)
    container_repo_path = f"/home/$USER/{repo_name}"

    # 通过容器内 git status 检查
    try:
        proc = subprocess.run(
            ["docker", "exec", container_name, "git", "-C",
             container_repo_path, "status", "--short"],
            capture_output=True, text=True, timeout=10
        )
        changes = proc.stdout.strip()
        return {"has_changes": bool(changes), "changes": changes}
    except Exception:
        return {"has_changes": False, "changes": ""}


def _init_cleanup_stages() -> List[StageInfo]:
    """初始化清理阶段列表"""
    return [
        StageInfo(name="停止容器", status="pending"),
        StageInfo(name="删除存储卷", status="pending"),
        StageInfo(name="关闭终端", status="pending"),
        StageInfo(name="删除工作目录", status="pending"),
        StageInfo(name="删除分支", status="pending"),
    ]


def cleanup_devspace_async(branch_name: str, force: bool = False) -> str:
    """
    异步清理开发空间。

    Args:
        branch_name: 分支名
        force: 是否强制清理（跳过未提交变更检查）

    Returns:
        任务 ID
    """
    # 防重复：检查是否已有同分支的 running CleanupTask
    with _tasks_lock:
        for t in _tasks.values():
            if (isinstance(t, CleanupTask)
                    and t.branch_name == branch_name
                    and t.status == "running"):
                return t.task_id

    task_id = str(uuid.uuid4())
    task = CleanupTask(
        task_id=task_id,
        status="pending",
        stages=_init_cleanup_stages(),
        branch_name=branch_name,
        force=force,
    )

    with _tasks_lock:
        _tasks[task_id] = task

    thread = threading.Thread(target=_run_cleanup_task, args=(task,))
    thread.daemon = True
    thread.start()

    return task_id


def _run_cleanup_task(task: CleanupTask):
    """在后台线程中执行清理任务"""
    task.status = "running"
    branch = task.branch_name
    # 容器名：将 / 替换为 -
    container_name = branch.replace("/", "-")
    volume_name = f"git-{branch.replace('/', '-')}"
    worktree_path = os.path.join(WORKTREE_DIR, branch.replace("/", "-"))
    tmux_name = branch.replace("/", "-")

    steps = [
        ("停止容器", 20, _cleanup_container, (container_name,)),
        ("删除存储卷", 40, _cleanup_volume, (volume_name,)),
        ("关闭终端", 60, _cleanup_tmux, (tmux_name,)),
        ("删除工作目录", 80, _cleanup_worktree, (worktree_path, branch)),
        ("删除分支", 100, _cleanup_branch, (branch,)),
    ]

    for stage_name, progress, fn, args in steps:
        _update_stage(task, stage_name, "running")
        task.progress = progress
        try:
            skipped, msg = fn(*args)
            if skipped:
                task.logs.append(f"[{stage_name}] 跳过: {msg}")
                _update_stage(task, stage_name, "done")
            else:
                task.logs.append(f"[{stage_name}] {msg}")
                _update_stage(task, stage_name, "done")
        except Exception as e:
            task.logs.append(f"[{stage_name}] 失败: {e}")
            _update_stage(task, stage_name, "failed")
            # 继续执行下一步

    task.status = "success"
    task.stage = "完成"
    task.logs.append("清理完成")


def _cleanup_container(name: str):
    """清理 Docker 容器。返回 (skipped, message)"""
    try:
        proc = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5
        )
        containers = proc.stdout.strip().split("\n") if proc.stdout.strip() else []
        if name not in containers:
            return True, "容器不存在"
    except Exception:
        return True, "无法探测容器"

    proc = subprocess.run(
        ["docker", "rm", "-f", name],
        capture_output=True, text=True, timeout=30
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "docker rm 失败")
    return False, f"已删除容器 {name}"


def _cleanup_volume(name: str):
    """清理 Docker volume"""
    try:
        proc = subprocess.run(
            ["docker", "volume", "inspect", name],
            capture_output=True, timeout=5
        )
        if proc.returncode != 0:
            return True, "存储卷不存在"
    except Exception:
        return True, "无法探测存储卷"

    proc = subprocess.run(
        ["docker", "volume", "rm", name],
        capture_output=True, text=True, timeout=30
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "docker volume rm 失败")
    return False, f"已删除存储卷 {name}"


def _cleanup_tmux(session: str):
    """清理 tmux session"""
    try:
        proc = subprocess.run(
            ["tmux", "has-session", "-t", session],
            capture_output=True, timeout=5
        )
        if proc.returncode != 0:
            return True, "终端会话不存在"
    except Exception:
        return True, "无法探测终端会话"

    proc = subprocess.run(
        ["tmux", "kill-session", "-t", session],
        capture_output=True, text=True, timeout=30
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "tmux kill-session 失败")
    return False, f"已关闭终端 {session}"


def _cleanup_worktree(path: str, branch: str):
    """清理 worktree 目录"""
    if not os.path.isdir(path):
        return True, "工作目录不存在"

    proc = subprocess.run(
        ["git", "-C", REPO_ROOT, "worktree", "remove", path, "--force"],
        capture_output=True, text=True, timeout=30
    )
    if proc.returncode != 0:
        # 回退：直接删除目录 + prune
        shutil.rmtree(path, ignore_errors=True)
        subprocess.run(
            ["git", "-C", REPO_ROOT, "worktree", "prune"],
            capture_output=True, timeout=30
        )
    return False, f"已删除工作目录 {path}"


def _cleanup_branch(branch: str):
    """清理本地分支"""
    try:
        proc = subprocess.run(
            ["git", "-C", REPO_ROOT, "show-ref", "--verify", f"refs/heads/{branch}"],
            capture_output=True, timeout=5
        )
        if proc.returncode != 0:
            return True, "分支不存在"
    except Exception:
        return True, "无法探测分支"

    proc = subprocess.run(
        ["git", "-C", REPO_ROOT, "branch", "-D", branch],
        capture_output=True, text=True, timeout=30
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git branch -D 失败")
    return False, f"已删除分支 {branch}"


def attach_devspace(branch_name: str) -> Dict:
    """
    通过 osascript 调用 iTerm2 打开新窗口并执行 tmux attach。

    Args:
        branch_name: 分支名

    Returns:
        {"success": True/False, "message"/"error": ...}
    """
    session_name = branch_name.replace("/", "-")

    # 1. 校验 tmux session 是否存在
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True, timeout=5
        )
        if result.returncode != 0:
            return {"success": False, "error": f"tmux session 不存在: {session_name}"}
    except FileNotFoundError:
        return {"success": False, "error": "tmux 未安装"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "检查 tmux session 超时"}

    # 2. 检查 iTerm2 是否安装
    if not os.path.exists("/Applications/iTerm.app"):
        return {"success": False, "error": "iTerm2 未安装，请先安装 iTerm2"}

    # 3. 通过 osascript 调用 iTerm2
    applescript = f'''
tell application "iTerm2"
    activate
    set newWindow to (create window with default profile)
    tell current session of newWindow
        write text "tmux attach -t {session_name}"
    end tell
end tell
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "osascript 执行失败"
            return {"success": False, "error": f"无法打开 iTerm2: {error_msg}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "打开 iTerm2 超时"}
    except FileNotFoundError:
        return {"success": False, "error": "osascript 不可用"}

    return {"success": True, "message": "已在 iTerm2 中打开终端"}


def cleanup_expired_tasks():
    """
    清理过期任务（可由定时任务调用）
    """
    now = datetime.now()
    with _tasks_lock:
        expired = []
        for task_id, task in _tasks.items():
            age = (now - task.created_at).total_seconds()
            if age > TASK_EXPIRE_SECONDS:
                expired.append(task_id)
        for task_id in expired:
            del _tasks[task_id]
