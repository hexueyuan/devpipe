import subprocess
import json
import os
import re
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

# 支持直接运行和模块运行
try:
    from .summary_service import ensure_summary
except ImportError:
    from summary_service import ensure_summary


# 开发阶段定义
STAGES = ["init", "discuss", "design", "coding", "review-and-fix", "summarize", "done"]
STAGE_LABELS = {
    "init": "初始化",
    "discuss": "需求讨论",
    "design": "方案设计",
    "coding": "代码开发",
    "review-and-fix": "评审修复",
    "summarize": "总结",
    "done": "已完成"
}

# 阶段元数据：核心/非核心 + 参与角色
STAGE_META = {
    "init":           {"is_core": False, "roles": "🤖",    "role_desc": "Agent 自动"},
    "discuss":        {"is_core": True,  "roles": "👤🤖", "role_desc": "人 + Agent"},
    "design":         {"is_core": True,  "roles": "👤🤖", "role_desc": "人 + Agent"},
    "coding":         {"is_core": True,  "roles": "🤖",    "role_desc": "Agent"},
    "review-and-fix": {"is_core": True,  "roles": "👤🤖", "role_desc": "人 + Agent"},
    "summarize":      {"is_core": False, "roles": "👤🤖", "role_desc": "人 + Agent"},
    "done":           {"is_core": False, "roles": "",      "role_desc": ""},
}

# 容器内 devflow 文件的路径（相对于 workspace_root）
_CONTAINER_DEVFLOW_DIRS = [".devpipe"]


def _get_docs_base_dir(repo_path: str) -> str:
    """
    从 devpipe.yml 读取 docs_dir 配置，返回文档存放的基础目录（绝对路径）。

    Args:
        repo_path: git 仓库路径

    Returns:
        绝对路径，默认为 {repo_path}/.devpipe/docs
    """
    default_dir = os.path.join(repo_path, ".devpipe", "docs")
    yml_path = os.path.join(repo_path, ".devpipe", "devpipe.yml")

    if not os.path.isfile(yml_path):
        return default_dir

    try:
        with open(yml_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("docs_dir:"):
                    value = line[len("docs_dir:"):].strip()
                    # 去掉行内注释
                    if "#" in value:
                        value = value[:value.index("#")].strip()
                    if value:
                        # 判断是否为绝对路径
                        if os.path.isabs(value):
                            return value
                        return os.path.join(repo_path, value)
    except IOError:
        pass

    return default_dir


def _docker_cat(container_name: str, file_path: str) -> Optional[str]:
    """通过 docker exec 读取容器内文件内容"""
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "cat", file_path],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _docker_container_running(container_name: str) -> bool:
    """检查容器是否在运行"""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (OSError, subprocess.TimeoutExpired):
        return False


def _read_devflow_file(worktree_path: str, filename: str, context: Optional[dict] = None) -> Optional[str]:
    """
    读取 devflow 文件，优先本地，回退到容器内读取。

    查找顺序：
    1. <worktree_path>/.devpipe/<filename>
    2. <docs_path>/<filename>（Docker 挂载源目录，容器内产出的文件在这里）
    3. <worktree_path>/<filename>（归档目录场景）
    4. docker exec <container_name> cat <workspace>/.devpipe/<filename>
    """
    # 1. 本地读取（尝试所有候选目录）
    for devflow_dir in _CONTAINER_DEVFLOW_DIRS:
        local_path = os.path.join(worktree_path, devflow_dir, filename)
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    return f.read()
            except IOError:
                pass

    # 2. docs_path（Docker bind mount 源目录）
    # 容器内写入 .devpipe/<filename> 实际落到 docs_path/<filename>
    if context:
        docs_path = context.get("docs_path")
        if docs_path:
            docs_file = os.path.join(docs_path, filename)
            if os.path.exists(docs_file):
                try:
                    with open(docs_file, "r", encoding="utf-8") as f:
                        return f.read()
                except IOError:
                    pass

    # 3. 直接在目录根下查找（归档目录场景）
    direct_path = os.path.join(worktree_path, filename)
    if os.path.exists(direct_path):
        try:
            with open(direct_path, "r", encoding="utf-8") as f:
                return f.read()
        except IOError:
            pass

    # 4. 从容器读取
    if context:
        container_name = context.get("container_name")
        workspace_root = context.get("workspace_root")
        if container_name and workspace_root and _docker_container_running(container_name):
            for devflow_dir in _CONTAINER_DEVFLOW_DIRS:
                container_path = os.path.join(workspace_root, devflow_dir, filename)
                result = _docker_cat(container_name, container_path)
                if result:
                    return result

    return None


@dataclass
class DevflowFile:
    """Devflow 文件展示信息"""
    filename: str        # "prd.md" | "coding-plan.md" | "task-progress.md" | "review-status.md" | "summary.md"
    content: str         # 文件内容
    is_reviewing: bool   # 是否处于评审中（生成该文件的阶段）
    stage: str           # 所属阶段标识


# 阶段 → 文档映射（点击展示）
STAGE_DOCUMENT_MAP = {
    "init": {"filename": None, "placeholder": "初始化阶段无关联文档"},
    "discuss": {"filename": "prd.md", "placeholder": "尚未生成文档"},
    "design": {"filename": "coding-plan.md", "placeholder": "尚未生成文档"},
    "coding": {"filename": "task-progress.md", "placeholder": "尚未生成文档"},
    "review-and-fix": {"filename": "review-status.md", "placeholder": "尚未生成文档"},
    "summarize": {"filename": "summary.md", "placeholder": "尚未生成文档"},
}


@dataclass
class StageTimeInfo:
    """阶段时间统计信息"""
    stage: str                        # 阶段标识
    label: str                        # 阶段显示名称
    started_at: Optional[str]         # 开始时间（ISO 8601）
    ended_at: Optional[str]           # 结束时间（ISO 8601）
    duration_seconds: Optional[int]   # 持续秒数
    duration_display: str             # 格式化的持续时间
    is_current: bool                  # 是否当前阶段
    is_completed: bool                # 是否已完成
    is_core: bool                     # 是否核心阶段
    roles: str                        # 角色标记（如 "👤🤖"）
    role_desc: str                    # 角色描述（如 "人 + Agent"）


@dataclass
class TimelineGroup:
    """Timeline 分组信息"""
    name: str                         # "环境准备" / "工作流程" / "总结复盘"
    stages: list                      # 包含的阶段名列表
    duration_seconds: Optional[int]   # 分组总耗时（秒）
    duration_display: str             # "5秒" / "5小时15分" / "进行中"
    is_completed: bool                # 分组内所有阶段是否完成
    is_current: bool                  # 分组内是否有进行中的阶段


# Timeline 分组定义
TIMELINE_GROUPS = [
    {"name": "环境准备", "stages": ["init"]},
    {"name": "工作流程", "stages": ["discuss", "design", "coding", "review-and-fix"]},
    {"name": "总结复盘", "stages": ["summarize"]},
]


# 文件与生成阶段的映射
FILE_STAGE_MAP = {
    "prd.md": "discuss",
    "coding-plan.md": "design",
    "task-progress.md": "coding",
    "review-status.md": "review-and-fix",
    "summary.md": "summarize",
}


def get_stage_documents(worktree_path: str, context: Optional[dict], applicable_stages: list[str] = None) -> dict[str, Optional[dict]]:
    """
    获取每个阶段对应的文档信息。

    返回 dict[stage_name, doc_info]，其中 doc_info 为 dict 或 None：
    - 有文档时: {"filename": "prd.md", "content": "...", "is_reviewing": True/False, "stage": "discuss"}
    - 无文档时: None（模板中根据 placeholder 映射表显示占位文案）
    """
    current_stage = context.get("stage", "init") if context else "init"
    stage_completed = context.get("stage_completed", True) if context else True
    dev_type = context.get("dev_type", "") if context else ""
    review_mode = context.get("review_mode", "") if context else ""

    # 确定适用的阶段列表
    if applicable_stages is None:
        if dev_type == "新功能":
            applicable_stages = ["init", "discuss", "design", "coding", "review-and-fix", "summarize"]
        else:
            applicable_stages = ["init", "design", "coding", "review-and-fix", "summarize"]

    result = {}
    for stage_name in applicable_stages:
        stage_def = STAGE_DOCUMENT_MAP.get(stage_name, {})
        filename = stage_def.get("filename")

        if filename is None:
            # init 阶段无文档
            result[stage_name] = None
            continue

        content = _read_devflow_file(worktree_path, filename, context)
        if content:
            is_reviewing = (current_stage == FILE_STAGE_MAP.get(filename, "") and not stage_completed)
            result[stage_name] = {
                "filename": filename,
                "content": content,
                "is_reviewing": is_reviewing,
                "stage": stage_name,
            }
        else:
            result[stage_name] = None

    return result


@dataclass
class SubtaskInfo:
    """子任务信息"""
    index: int
    name: str
    module: str
    status: str  # "已完成", "当前", "待执行"


@dataclass
class WorktreeInfo:
    """Worktree 信息数据类"""
    name: str
    path: str
    branch: str
    dev_type: str
    description: str
    summary: str
    github_issue: str
    github_issue_title: str
    github_issue_url: str
    created_at: str
    updated_at: str  # deprecated, kept for API compat
    stage: str
    stage_completed: bool
    subtasks: list[SubtaskInfo]
    acceptance_criteria: list[str]
    stage_times: list[StageTimeInfo]       # 各阶段时间统计
    total_dev_time_display: str            # 核心阶段总耗时（格式化）
    timeline_groups: list[TimelineGroup]   # Timeline 分组
    is_archived: bool = False              # 分支不存在时为 True


def get_worktree_list(repo_path: str) -> list[dict[str, str]]:
    """
    获取 git worktree 列表

    Args:
        repo_path: git 仓库路径

    Returns:
        list of dict with keys: path, branch
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
    except OSError:
        return []

    if result.returncode != 0:
        return []

    worktrees = []
    current_worktree = {}

    for line in result.stdout.strip().split("\n"):
        if line.startswith("worktree "):
            if current_worktree:
                worktrees.append(current_worktree)
            host_path = line[9:]
            current_worktree = {"path": host_path}
        elif line.startswith("HEAD "):
            current_worktree["commit"] = line[5:]
        elif line.startswith("branch "):
            branch_ref = line[7:]
            current_worktree["branch"] = branch_ref.replace("refs/heads/", "", 1) if branch_ref.startswith("refs/heads/") else branch_ref

    if current_worktree:
        worktrees.append(current_worktree)

    return worktrees


def branch_exists(repo_path: str, branch_name: str) -> bool:
    """检查本地分支是否存在"""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "show-ref", "--verify", f"refs/heads/{branch_name}"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def parse_dev_context(worktree_path: str) -> Optional[dict]:
    """
    解析 worktree 的 devflow 上下文。

    优先级：docs 目录（Docker bind mount 源）> 容器内 > worktree 本地。
    docs 目录是容器的 .devpipe 挂载源，stage-gate.sh 的更新直接写入此处，
    始终包含最新状态。worktree 本地仅作为 bootstrap 获取 docs_path 等静态字段。
    """
    # 第一步：读取 worktree 本地 context 作为 bootstrap（获取 docs_path 等）
    bootstrap_context = None
    bootstrap_candidates = [
        os.path.join(worktree_path, ".devpipe", "context.json"),
        os.path.join(worktree_path, "context.json"),
    ]
    for context_path in bootstrap_candidates:
        if not os.path.exists(context_path):
            continue
        try:
            with open(context_path, "r", encoding="utf-8") as f:
                bootstrap_context = json.load(f)
                break
        except (json.JSONDecodeError, IOError):
            continue

    # 第二步：从 docs 目录读取最新 context（Docker bind mount 源，最权威）
    # 来源 1: bootstrap_context 中的 docs_path 字段
    docs_path = bootstrap_context.get("docs_path") if bootstrap_context else None
    if docs_path:
        docs_context_file = os.path.join(docs_path, "context.json")
        if os.path.exists(docs_context_file):
            try:
                with open(docs_context_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

    # 来源 2: .devpipe/ 内 symlink 指向的 docs 目录
    devpipe_dir = os.path.join(worktree_path, ".devpipe")
    if os.path.isdir(devpipe_dir):
        for entry in os.listdir(devpipe_dir):
            entry_path = os.path.join(devpipe_dir, entry)
            if os.path.islink(entry_path) and os.path.isdir(entry_path):
                symlink_context = os.path.join(entry_path, "context.json")
                if os.path.exists(symlink_context):
                    try:
                        with open(symlink_context, "r", encoding="utf-8") as f:
                            return json.load(f)
                    except (json.JSONDecodeError, IOError):
                        pass

    # 第三步：容器回退（docs 不可用时）
    if bootstrap_context:
        container_name = bootstrap_context.get("container_name")
        if container_name and _docker_container_running(container_name):
            # 从 context 计算容器内工作目录
            repo_root = bootstrap_context.get("repo_root", "")
            repo_name = os.path.basename(repo_root) if repo_root else ""
            host_user = os.path.basename(os.path.expanduser("~"))
            workspace_root = f"/home/{host_user}/{repo_name}" if repo_name else None
            if workspace_root:
                for devflow_dir in _CONTAINER_DEVFLOW_DIRS:
                    container_content = _docker_cat(
                        container_name,
                        os.path.join(workspace_root, devflow_dir, "context.json")
                    )
                    if container_content:
                        try:
                            return json.loads(container_content)
                        except json.JSONDecodeError:
                            pass

    # 兜底：返回 bootstrap context
    return bootstrap_context


def get_branch_last_update(repo_path: str, branch: str) -> str:
    """
    获取分支最后一次提交时间

    Args:
        repo_path: git 仓库路径
        branch: 分支名

    Returns:
        格式化的时间字符串，如 "2026-03-27 11:52:04"
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci", branch],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
    except OSError:
        return "未知"

    if result.returncode != 0:
        return "未知"

    output = result.stdout.strip()
    if not output:
        return "未知"

    # 格式: "2026-03-30 16:28:40 +0800" -> "2026-03-30 16:28:44"
    # 去掉时区部分，只保留日期和时间
    parts = output.split(" ")
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return output


def _format_datetime(value: str, fallback: str = None) -> str:
    """
    将各种时间格式统一为 'YYYY-MM-DD HH:MM:SS'。
    支持 ISO 8601（带/不带时区）、纯日期等格式。
    当 value 为纯日期时，尝试从 fallback 时间戳中提取时间部分。
    """
    if not value or value == "-":
        return "-"

    # 尝试完整时间格式
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    # 纯日期格式 - 使用 fallback 的时间部分
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        if fallback:
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
                try:
                    fallback_dt = datetime.strptime(fallback, fmt)
                    return f"{value} {fallback_dt.strftime('%H:%M:%S')}"
                except ValueError:
                    continue
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    return value


def get_file_created_time(file_path: str) -> str:
    """
    获取文件的创建时间

    Args:
        file_path: 文件路径

    Returns:
        格式化的时间字符串，如 "2026-03-27 11:52:04"，失败返回 "-"
    """
    try:
        stat_info = os.stat(file_path)
        # macOS: st_birthtime 是文件创建时间
        # Linux: st_ctime 是 inode 变更时间（最接近创建时间）
        timestamp = getattr(stat_info, 'st_birthtime', stat_info.st_ctime)
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, AttributeError):
        return "-"


def get_dev_stage(worktree_path: str, context: Optional[dict] = None) -> tuple[str, str]:
    """
    判断当前开发阶段并返回阶段文件内容。
    优先从 context 的 stage 字段读取，文件优先本地、回退容器。
    """
    # 优先从 context 中获取 stage
    if context and context.get("stage"):
        stage_from_context = context["stage"]
        # 当阶段已完成时，推进到下一个阶段
        stage_completed = context.get("stage_completed", False)
        if stage_completed and stage_from_context != "done":
            dev_type = context.get("dev_type", "")
            # 新功能走完整流程，Bugfix/优化重构跳过 discuss
            if dev_type == "新功能":
                next_stage_map = {
                    "init": "discuss", "discuss": "design",
                    "design": "coding", "coding": "review-and-fix",
                    "review-and-fix": "summarize", "summarize": "done",
                }
            else:  # Bugfix / 优化重构
                next_stage_map = {
                    "init": "design",  # 跳过 discuss
                    "design": "coding", "coding": "review-and-fix",
                    "review-and-fix": "summarize", "summarize": "done",
                }
            stage_from_context = next_stage_map.get(stage_from_context, stage_from_context)
        if stage_from_context in STAGE_LABELS:
            if stage_from_context in ("coding", "review-and-fix"):
                content = _read_devflow_file(worktree_path, "task-progress.md", context)
                if content:
                    return stage_from_context, content
            elif stage_from_context in ("summarize", "done"):
                content = _read_devflow_file(worktree_path, "summary.md", context)
                if content:
                    return stage_from_context, content
            elif stage_from_context == "design":
                content = _read_devflow_file(worktree_path, "prd.md", context)
                if content:
                    return "design", content
            # init/discuss/summarize 或无对应文件时展示 context 内容
            return stage_from_context, json.dumps(context, ensure_ascii=False, indent=2)

    return "init", ""


def parse_subtasks(progress_content: str) -> list[SubtaskInfo]:
    """
    从 task-progress.md 中解析子任务表格

    Args:
        progress_content: task-progress.md 文件内容

    Returns:
        SubtaskInfo 列表
    """
    subtasks = []

    # 匹配表格行: | # | 子任务 | 模块 | 状态 |
    pattern = r'\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(已完成|当前|待执行)\s*\|'

    for match in re.finditer(pattern, progress_content):
        subtasks.append(SubtaskInfo(
            index=int(match.group(1)),
            name=match.group(2).strip(),
            module=match.group(3).strip(),
            status=match.group(4).strip()
        ))

    return subtasks


def parse_acceptance_criteria(spec_content: str) -> list[str]:
    """
    从 prd.md 或 coding-plan.md 中解析验收标准

    Args:
        spec_content: prd.md 或 coding-plan.md 文件内容

    Returns:
        验收标准列表
    """
    criteria = []

    # 找到验收标准章节
    in_criteria_section = False
    for line in spec_content.split('\n'):
        if '## 验收标准' in line:
            in_criteria_section = True
            continue
        if in_criteria_section:
            if line.startswith('## '):
                break
            # 匹配列表项: 1. xxx 或 - xxx
            match = re.match(r'^\s*(?:\d+\.\s*|-\s*)(.+)$', line)
            if match:
                criteria.append(match.group(1).strip())

    return criteria


def parse_iso_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """解析 ISO 8601 时间戳字符串为 datetime 对象"""
    if not ts:
        return None
    try:
        # 处理格式: 2026-04-07T19:20:37+08:00
        return datetime.fromisoformat(ts)
    except ValueError:
        # 尝试兼容旧格式: 2026-04-07 19:20:37
        try:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def calculate_stage_duration(started_at: Optional[str], ended_at: Optional[str]) -> Optional[int]:
    """
    计算阶段持续时间（秒）。
    如果阶段未开始或仍在进行中，返回 None。
    """
    start = parse_iso_timestamp(started_at)
    end = parse_iso_timestamp(ended_at)
    if not start:
        return None
    if not end:
        return None  # 进行中
    return int((end - start).total_seconds())


def format_duration(seconds: Optional[int]) -> str:
    """将秒数格式化为人类可读的时间"""
    if seconds is None:
        return "进行中"
    if seconds < 0:
        return "-"
    if seconds < 60:
        return f"{seconds}秒"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        if secs == 0:
            return f"{minutes}分"
        return f"{minutes}分{secs}秒"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes == 0:
            return f"{hours}小时"
        return f"{hours}小时{minutes}分"


def calculate_total_dev_time(stage_timestamps: dict, dev_type: str) -> Optional[int]:
    """
    计算核心阶段总时间（从 discuss/design 开始到 review-and-fix 结束）。

    对于新功能: discuss -> design -> coding -> review-and-fix
    对于 Bugfix/优化重构: design -> coding -> review-and-fix（跳过 discuss）
    """
    if not stage_timestamps:
        return None

    # 新功能从 discuss 开始，Bugfix/优化重构从 design 开始
    if dev_type == "新功能":
        start_stage = stage_timestamps.get("discuss", {})
    else:
        start_stage = stage_timestamps.get("design", {})
    review = stage_timestamps.get("review-and-fix", {})

    start = parse_iso_timestamp(start_stage.get("started_at"))
    end = parse_iso_timestamp(review.get("ended_at"))

    if not start:
        return None
    if not end:
        return None  # 尚未完成

    return int((end - start).total_seconds())


def get_stage_times(context: Optional[dict], current_stage: str, dev_type: str) -> list[StageTimeInfo]:
    """
    从 context 中提取阶段时间信息用于展示。

    Args:
        context: devflow 上下文字典
        current_stage: 当前阶段
        dev_type: 开发类型

    Returns:
        StageTimeInfo 列表
    """
    if not context:
        return []

    stage_timestamps = context.get("stage_timestamps", {})

    # 如果没有时间戳数据，返回空列表（向后兼容）
    if not stage_timestamps:
        return []

    # 根据 dev_type 确定适用的阶段列表（不包含 done，done 是终态标记，不在进度条中显示）
    # 新功能走完整流程，Bugfix/优化重构跳过 discuss
    if dev_type == "新功能":
        applicable_stages = ["init", "discuss", "design", "coding", "review-and-fix", "summarize"]
    else:  # Bugfix / 优化重构
        applicable_stages = ["init", "design", "coding", "review-and-fix", "summarize"]

    current_index = applicable_stages.index(current_stage) if current_stage in applicable_stages else -1

    result = []
    for i, stage in enumerate(applicable_stages):
        ts = stage_timestamps.get(stage, {})
        started = ts.get("started_at")
        ended = ts.get("ended_at")
        duration = calculate_stage_duration(started, ended)

        is_current = (stage == current_stage)
        # 如果当前阶段是 done，则所有阶段都标记为已完成
        if current_stage == "done":
            is_completed = True
            is_current = False
        else:
            is_completed = (i < current_index) or (ended is not None)

        if not started:
            duration_display = ""  # 未开始的阶段不显示时长
        else:
            duration_display = format_duration(duration)

        meta = STAGE_META.get(stage, {"is_core": False, "roles": "", "role_desc": ""})

        result.append(StageTimeInfo(
            stage=stage,
            label=STAGE_LABELS.get(stage, stage),
            started_at=started,
            ended_at=ended,
            duration_seconds=duration,
            duration_display=duration_display,
            is_current=is_current,
            is_completed=is_completed,
            is_core=meta["is_core"],
            roles=meta["roles"],
            role_desc=meta["role_desc"]
        ))

    return result


def get_timeline_groups(context: Optional[dict], current_stage: str, dev_type: str) -> list[TimelineGroup]:
    """
    计算 Timeline 分组数据。

    Args:
        context: devflow 上下文字典
        current_stage: 当前阶段
        dev_type: 开发类型

    Returns:
        TimelineGroup 列表
    """
    if not context:
        return []

    stage_timestamps = context.get("stage_timestamps", {})
    if not stage_timestamps:
        return []

    result = []

    for group_def in TIMELINE_GROUPS:
        group_name = group_def["name"]
        group_stages = group_def["stages"]

        # 对于 Bugfix/优化重构 类型，工作流程分组不包含 discuss 阶段
        if dev_type != "新功能" and group_name == "工作流程":
            group_stages = [s for s in group_stages if s != "discuss"]

        # 计算分组总耗时
        total_seconds = 0
        has_started = False
        all_completed = True
        any_current = False

        for stage in group_stages:
            ts = stage_timestamps.get(stage, {})
            started = ts.get("started_at")
            ended = ts.get("ended_at")

            if started:
                has_started = True
                if ended:
                    duration = calculate_stage_duration(started, ended)
                    if duration is not None:
                        total_seconds += duration
                else:
                    # 阶段进行中
                    all_completed = False

            # 检查是否为当前阶段
            if stage == current_stage:
                any_current = True
                all_completed = False

            # 检查阶段是否未完成
            if not ended:
                all_completed = False

        # 确定分组状态
        # 如果当前 stage 是 done，所有分组都标记为已完成
        if current_stage == "done":
            is_completed = True
            is_current = False
        else:
            is_completed = has_started and all_completed
            is_current = any_current or (has_started and not all_completed)

        # 格式化耗时显示
        if not has_started:
            duration_display = "-"
        elif is_completed:
            duration_display = format_duration(total_seconds)
        else:
            duration_display = "进行中"

        result.append(TimelineGroup(
            name=group_name,
            stages=group_stages,
            duration_seconds=total_seconds if is_completed else None,
            duration_display=duration_display,
            is_completed=is_completed,
            is_current=is_current
        ))

    return result
    """
    从 prd.md / coding-plan.md 中解析涉及模块

    Args:
        spec_content: prd.md 或 coding-plan.md 文件内容

    Returns:
        模块名列表
    """
    modules = []

    # 找到涉及模块表格
    in_modules_section = False
    for line in spec_content.split('\n'):
        if '### 涉及模块' in line or '## 涉及模块' in line:
            in_modules_section = True
            continue
        if in_modules_section:
            if line.startswith('### ') or line.startswith('## '):
                break
            # 匹配表格行: | 模块名 | ... |
            if line.startswith('|') and not line.startswith('| 模块'):
                parts = line.split('|')
                if len(parts) >= 2:
                    module = parts[1].strip()
                    if module and module != '模块':
                        modules.append(module)

    return modules


def get_archived_devspaces(repo_path: str) -> list[WorktreeInfo]:
    """
    扫描 docs 目录，获取已归档（已清理）的开发环境信息。

    Args:
        repo_path: git 仓库路径

    Returns:
        WorktreeInfo 列表（标记为归档状态）
    """
    docs_dir = _get_docs_base_dir(repo_path)
    if not os.path.isdir(docs_dir):
        return []

    result = []
    for entry in os.listdir(docs_dir):
        entry_path = os.path.join(docs_dir, entry)
        if not os.path.isdir(entry_path):
            continue

        context_path = os.path.join(entry_path, "context.json")
        if not os.path.exists(context_path):
            continue

        try:
            with open(context_path, "r", encoding="utf-8") as f:
                context = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        local_branch = context.get("local_branch", "")
        if not local_branch:
            continue

        branch = local_branch.replace("/", "-")
        worktree_path = context.get("worktree_path", entry_path)

        # 从 context 获取时间
        stage_timestamps = context.get("stage_timestamps", {})
        fallback_ts = stage_timestamps.get("discuss", stage_timestamps.get("init", {})).get("started_at")
        created_at = _format_datetime(context.get("created_at", ""), fallback=fallback_ts)

        # 获取阶段信息
        stage = context.get("stage", "done")
        stage_completed = context.get("stage_completed", True)
        dev_type = context.get("dev_type", "-")

        description = context.get("description", "-")
        summary = description

        # 计算阶段时间统计
        stage_times = get_stage_times(context, stage, dev_type)
        stage_timestamps = context.get("stage_timestamps", {})
        total_dev_time = calculate_total_dev_time(stage_timestamps, dev_type)
        total_dev_time_display = format_duration(total_dev_time)
        timeline_groups = get_timeline_groups(context, stage, dev_type)

        info = WorktreeInfo(
            name=branch,
            path=entry_path,
            branch=branch,
            dev_type=dev_type,
            description=description,
            summary=summary,
            github_issue=context.get("github_issue", ""),
            github_issue_title=context.get("github_issue_title", ""),
            github_issue_url=context.get("github_issue_url", ""),
            created_at=created_at,
            updated_at=created_at,
            stage=stage,
            stage_completed=stage_completed,
            subtasks=[],
            acceptance_criteria=[],
            stage_times=stage_times,
            total_dev_time_display=total_dev_time_display,
            timeline_groups=timeline_groups,
            is_archived=True
        )
        result.append(info)

    return result


def get_all_worktrees(repo_path: str) -> list[WorktreeInfo]:
    """
    获取所有 worktree 的完整信息

    Args:
        repo_path: git 仓库路径

    Returns:
        WorktreeInfo 列表，按更新时间倒序排列
    """
    worktrees = get_worktree_list(repo_path)
    result = []

    for wt in worktrees:
        path = wt["path"]
        branch = wt.get("branch", "unknown")

        # 只保留开发分支（feature-, fix-, refactor- 开头）
        if not (branch.startswith(("feature-", "fix-", "refactor-"))):
            continue

        # 使用分支名作为显示名称
        name = branch

        # 解析开发上下文
        context = parse_dev_context(path)

        # 获取更新时间
        updated_at = get_branch_last_update(repo_path, branch)

        # 从 context 中获取 created_at，回退到文件创建时间
        if context and context.get("created_at"):
            stage_timestamps_ctx = context.get("stage_timestamps", {})
            fallback_ts = stage_timestamps_ctx.get("discuss", stage_timestamps_ctx.get("init", {})).get("started_at")
            created_at = _format_datetime(context["created_at"], fallback=fallback_ts)
        else:
            context_file = os.path.join(path, ".devpipe", "context.json")
            created_at = get_file_created_time(context_file) if os.path.exists(context_file) else "-"

        # 获取或生成摘要
        summary = ensure_summary(path)
        description = context.get("description", "-") if context else "-"
        if not summary:
            summary = description

        # 获取阶段和子任务信息
        stage, stage_content = get_dev_stage(path, context)
        stage_completed = context.get("stage_completed", True) if context else True
        dev_type = context.get("dev_type", "-") if context else "-"
        subtasks = []
        acceptance_criteria = []

        if stage in ("coding", "review-and-fix") and stage_content:
            subtasks = parse_subtasks(stage_content)
            # 读取 prd/coding-plan 文件获取验收标准
            spec_content = _read_devflow_file(path, "prd.md", context)
            if not spec_content:
                spec_content = _read_devflow_file(path, "coding-plan.md", context)
            if spec_content:
                acceptance_criteria = parse_acceptance_criteria(spec_content)
        elif stage == "design" and stage_content:
            acceptance_criteria = parse_acceptance_criteria(stage_content)

        # 计算阶段时间统计
        stage_times = get_stage_times(context, stage, dev_type)
        stage_timestamps = context.get("stage_timestamps", {}) if context else {}
        total_dev_time = calculate_total_dev_time(stage_timestamps, dev_type)
        total_dev_time_display = format_duration(total_dev_time)

        # 计算 Timeline 分组
        timeline_groups = get_timeline_groups(context, stage, dev_type)

        # 检查分支是否仍存在（worktree 可能存在但分支已删除）
        is_archived = not branch_exists(repo_path, branch)

        info = WorktreeInfo(
            name=name,
            path=path,
            branch=branch,
            dev_type=dev_type,
            description=description,
            summary=summary,
            github_issue=context.get("github_issue", "") if context else "",
            github_issue_title=context.get("github_issue_title", "") if context else "",
            github_issue_url=context.get("github_issue_url", "") if context else "",
            created_at=created_at,
            updated_at=updated_at,
            stage=stage,
            stage_completed=stage_completed,
            subtasks=subtasks,
            acceptance_criteria=acceptance_criteria,
            stage_times=stage_times,
            total_dev_time_display=total_dev_time_display,
            timeline_groups=timeline_groups,
            is_archived=is_archived
        )
        result.append(info)

    # 合并归档环境（活跃环境优先）
    archived = get_archived_devspaces(repo_path)
    active_branches = {info.branch for info in result}
    for arch_info in archived:
        if arch_info.branch not in active_branches:
            result.append(arch_info)

    # 排序：非归档在前，组内按创建时间倒序（最新在前）
    result.sort(key=lambda x: x.created_at if x.created_at and x.created_at != "-" else "", reverse=True)
    result.sort(key=lambda x: 1 if x.is_archived else 0)

    return result
