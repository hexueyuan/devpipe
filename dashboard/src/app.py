import json
import logging
import os
from flask import Flask, render_template, jsonify, request

# 支持直接运行 python src/app.py 和模块运行 python -m src.app
try:
    from .worktree_service import get_all_worktrees, get_dev_stage, get_stage_documents, parse_dev_context, STAGES, STAGE_LABELS, STAGE_DOCUMENT_MAP
    from .config import REPO_ROOT, get_github_issue_url
    from .devspace_service import (
        query_github_issue,
        validate_branch,
        check_conflicts,
        create_devspace_async,
        get_task_status,
        generate_branch_name,
        probe_resources,
        check_uncommitted_changes,
        cleanup_devspace_async,
        attach_devspace,
    )
except ImportError:
    from worktree_service import get_all_worktrees, get_dev_stage, get_stage_documents, parse_dev_context, STAGES, STAGE_LABELS, STAGE_DOCUMENT_MAP
    from config import REPO_ROOT, get_github_issue_url
    from devspace_service import (
        query_github_issue,
        validate_branch,
        check_conflicts,
        create_devspace_async,
        get_task_status,
        generate_branch_name,
        probe_resources,
        check_uncommitted_changes,
        cleanup_devspace_async,
        attach_devspace,
    )

app = Flask(__name__)


@app.route("/")
def index():
    """主页：展示 worktree 列表"""
    worktrees = get_all_worktrees(REPO_ROOT)

    # 统计信息：按工作流阶段分组
    # 讨论中：init、discuss、design
    # 开发中：coding、review-and-fix
    # 已完成：summarize、done
    discussing_stages = {"init", "discuss", "design"}
    developing_stages = {"coding", "review-and-fix"}
    completed_stages = {"summarize", "done"}

    stats = {
        "讨论中": sum(1 for wt in worktrees if wt.stage in discussing_stages),
        "开发中": sum(1 for wt in worktrees if wt.stage in developing_stages),
        "已完成": sum(1 for wt in worktrees if wt.stage in completed_stages),
    }

    # 转换为模板友好的格式
    worktree_data = []
    for wt in worktrees:
        # 计算子任务完成进度
        completed = sum(1 for st in wt.subtasks if st.status == "已完成")
        total = len(wt.subtasks)

        worktree_data.append({
            "name": wt.name,
            "dev_type": wt.dev_type,
            "summary": wt.summary,
            "created_at": wt.created_at,
            "updated_at": wt.updated_at,
            "stage": wt.stage,
            "stage_completed": wt.stage_completed,
            "stage_label": STAGE_LABELS.get(wt.stage, wt.stage),
            "subtask_completed": completed,
            "subtask_total": total,
            "is_archived": wt.is_archived
        })

    return render_template("index.html", worktrees=worktree_data, stats=stats, stages=STAGES, stage_labels=STAGE_LABELS)


@app.route("/detail/<branch_name>")
def detail(branch_name):
    """详情页：展示单个 worktree 的详细信息"""
    worktrees = get_all_worktrees(REPO_ROOT)

    wt_info = None
    for wt in worktrees:
        if wt.name == branch_name:
            wt_info = wt
            break

    if wt_info is None:
        return "分支不存在", 404

    # 获取开发阶段和文件内容（通过 parse_dev_context 读取容器内最新状态）
    context = parse_dev_context(wt_info.path)
    stage, stage_content = get_dev_stage(wt_info.path, context)
    stage_completed = context.get("stage_completed", True) if context else True
    dev_type = context.get("dev_type", "") if context else ""
    review_mode = context.get("review_mode", "") if context else ""

    # 获取阶段文档映射
    stage_documents = get_stage_documents(wt_info.path, context)

    # 构建占位文案映射
    stage_placeholders = {}
    for stage_name, stage_def in STAGE_DOCUMENT_MAP.items():
        if stage_name == "review-and-fix" and review_mode == "lightweight":
            stage_placeholders[stage_name] = "轻量模式，跳过自检评审"
        else:
            stage_placeholders[stage_name] = stage_def.get("placeholder", "尚未生成文档")

    wt_data = {
        "name": wt_info.name,
        "path": wt_info.path,
        "dev_type": wt_info.dev_type,
        "description": wt_info.description,
        "github_issue": wt_info.github_issue,
        "github_issue_title": wt_info.github_issue_title,
        "github_issue_url": wt_info.github_issue_url,
        "created_at": wt_info.created_at,
        "updated_at": wt_info.updated_at,
        "stage": stage,
        "stage_completed": stage_completed,
        "stage_label": STAGE_LABELS.get(stage, stage),
        "stage_documents": {
            stage_name: doc for stage_name, doc in stage_documents.items()
        },
        "stage_placeholders": stage_placeholders,
        "subtasks": [{"index": st.index, "name": st.name, "module": st.module, "status": st.status} for st in wt_info.subtasks],
        "acceptance_criteria": wt_info.acceptance_criteria,
        "stage_times": [
            {
                "stage": st.stage,
                "label": st.label,
                "started_at": st.started_at,
                "ended_at": st.ended_at,
                "duration_display": st.duration_display,
                "is_current": st.is_current,
                "is_completed": st.is_completed,
                "is_core": st.is_core,
                "roles": st.roles,
                "role_desc": st.role_desc
            }
            for st in wt_info.stage_times
        ],
        "total_dev_time_display": wt_info.total_dev_time_display,
        "timeline_groups": [
            {
                "name": g.name,
                "stages": g.stages,
                "duration_seconds": g.duration_seconds,
                "duration_display": g.duration_display,
                "is_completed": g.is_completed,
                "is_current": g.is_current
            }
            for g in wt_info.timeline_groups
        ],
        "is_archived": wt_info.is_archived
    }

    return render_template("detail.html", wt=wt_data, stages=STAGES, stage_labels=STAGE_LABELS)


@app.route("/api/worktrees")
def api_worktrees():
    """API: 返回 JSON 格式的 worktree 列表"""
    worktrees = get_all_worktrees(REPO_ROOT)

    result = []
    for wt in worktrees:
        result.append({
            "name": wt.name,
            "dev_type": wt.dev_type,
            "description": wt.description,
            "github_issue": wt.github_issue,
            "github_issue_title": wt.github_issue_title,
            "github_issue_url": wt.github_issue_url,
            "created_at": wt.created_at,
            "updated_at": wt.updated_at
        })

    return jsonify({"worktrees": result})


# ========================
# 开发空间创建 API
# ========================

@app.route("/api/github/issue", methods=["POST"])
def api_github_issue():
    """
    查询 GitHub Issue 信息

    Request:
        { "issue_input": "123" }  // 或完整链接 https://github.com/owner/repo/issues/123

    Response (成功):
        {
          "success": true,
          "data": {
            "number": "123",
            "title": "Add new feature for deployment",
            "body": "...",
            "url": "https://github.com/owner/repo/issues/123",
            "dev_type": "新功能",
            "suggested_branch": "feature-add-deployment",
            "repo": "owner/repo"
          }
        }

    Response (失败):
        { "success": false, "error": "Issue 不存在或 gh 未登录" }
    """
    data = request.get_json()
    if not data or "issue_input" not in data:
        return jsonify({"success": False, "error": "缺少 issue_input 参数"})

    issue_input = data["issue_input"].strip()
    if not issue_input:
        return jsonify({"success": False, "error": "issue_input 不能为空"})

    result = query_github_issue(issue_input)
    return jsonify(result)


@app.route("/api/branch/validate", methods=["POST"])
def api_branch_validate():
    """
    验证基础分支是否存在

    Request:
        { "branch": "1.1.0-alpha", "mode": "remote" }  // mode: local/remote

    Response:
        { "success": true, "exists": true }
    """
    data = request.get_json()
    if not data or "branch" not in data:
        return jsonify({"success": False, "error": "缺少 branch 参数"})

    branch = data["branch"].strip()
    mode = data.get("mode", "remote")

    if not branch:
        return jsonify({"success": False, "error": "branch 不能为空"})

    result = validate_branch(branch, mode)
    return jsonify(result)


@app.route("/api/devspace/check-conflicts", methods=["POST"])
def api_check_conflicts():
    """
    检查资源冲突

    Request:
        { "branch_name": "wt-5x-cluster" }

    Response:
        { "success": true, "conflicts": [] }
        { "success": true, "conflicts": ["Worktree 目录已存在: ..."] }
    """
    data = request.get_json()
    if not data or "branch_name" not in data:
        return jsonify({"success": False, "error": "缺少 branch_name 参数"})

    branch_name = data["branch_name"].strip()
    if not branch_name:
        return jsonify({"success": False, "error": "branch_name 不能为空"})

    conflicts = check_conflicts(branch_name)
    return jsonify({"success": True, "conflicts": conflicts})


@app.route("/api/devspace/suggest-branch", methods=["POST"])
def api_suggest_branch():
    """
    根据描述生成建议分支名（仅描述部分，不含前缀）

    Request:
        { "description": "Add deployment feature" }

    Response:
        { "success": true, "branch_name": "add-deployment" }
    """
    data = request.get_json()
    if not data or "description" not in data:
        return jsonify({"success": False, "error": "缺少 description 参数"})

    description = data["description"].strip()
    if not description:
        return jsonify({"success": False, "error": "description 不能为空"})

    branch_name = generate_branch_name(description)
    return jsonify({"success": True, "branch_name": branch_name})


@app.route("/api/devspace/create", methods=["POST"])
def api_devspace_create():
    """
    启动异步创建任务

    Request:
        {
          "branch_name": "feature-add-deployment",
          "base_branch": "main",
          "mode": "remote",
          "github_issue": "123",
          "github_issue_title": "Add deployment feature",
          "github_issue_body": "...",
          "github_issue_url": "https://github.com/owner/repo/issues/123",
          "github_repo": "owner/repo",
          "dev_type": "新功能",
          "description": "Add deployment feature"
        }

    Response:
        { "success": true, "task_id": "uuid-xxx" }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "缺少请求体"})

    # 验证必需参数
    branch_name = data.get("branch_name", "").strip()
    base_branch = data.get("base_branch", "main").strip()
    dev_type = data.get("dev_type", "").strip()
    description = data.get("description", "").strip()

    if not branch_name:
        return jsonify({"success": False, "error": "branch_name 不能为空"})
    # 验证分支名前缀（feature-, fix-, refactor-）
    valid_prefixes = ("feature-", "fix-", "refactor-")
    if not branch_name.startswith(valid_prefixes):
        return jsonify({"success": False, "error": f"branch_name 必须以 feature-, fix- 或 refactor- 开头"})
    if not base_branch:
        return jsonify({"success": False, "error": "base_branch 不能为空"})
    if not dev_type:
        return jsonify({"success": False, "error": "dev_type 不能为空"})
    if dev_type not in ("新功能", "Bugfix", "优化重构"):
        return jsonify({"success": False, "error": f"无效的 dev_type: {dev_type}"})

    # 检查冲突
    conflicts = check_conflicts(branch_name)
    if conflicts:
        return jsonify({"success": False, "error": "资源冲突", "conflicts": conflicts})

    # 启动异步任务
    task_id = create_devspace_async({
        "branch_name": branch_name,
        "base_branch": base_branch,
        "mode": data.get("mode", "remote"),
        "github_issue": data.get("github_issue"),
        "github_issue_title": data.get("github_issue_title"),
        "github_issue_body": data.get("github_issue_body"),
        "github_issue_url": data.get("github_issue_url"),
        "github_repo": data.get("github_repo"),
        "dev_type": dev_type,
        "description": description
    })

    return jsonify({"success": True, "task_id": task_id})


@app.route("/api/devspace/status/<task_id>")
def api_devspace_status(task_id):
    """
    查询创建进度

    Response:
        {
          "status": "running",
          "progress": 60,
          "stage": "创建 Docker 容器",
          "stages": [
            {"name": "前置检查", "status": "done"},
            {"name": "分支同步", "status": "done"},
            ...
          ],
          "logs": ["..."],
          "error": null,
          "result": null
        }
    """
    status = get_task_status(task_id)
    if status is None:
        return jsonify({"success": False, "error": "任务不存在"}), 404

    return jsonify(status)


# ========================
# 开发空间清理 API
# ========================

@app.route("/api/devspace/probe-resources", methods=["POST"])
def api_probe_resources():
    """探测开发空间关联的资源"""
    data = request.get_json()
    if not data or not data.get("branch_name", "").strip():
        return jsonify({"success": False, "error": "缺少 branch_name 参数"})

    branch_name = data["branch_name"].strip()
    result = probe_resources(branch_name)
    return jsonify({"success": True, "data": result})


@app.route("/api/devspace/check-changes", methods=["POST"])
def api_check_changes():
    """检查开发空间是否有未提交变更"""
    data = request.get_json()
    if not data or not data.get("branch_name", "").strip():
        return jsonify({"success": False, "error": "缺少 branch_name 参数"})

    branch_name = data["branch_name"].strip()
    result = check_uncommitted_changes(branch_name)
    return jsonify({"success": True, "data": result})


@app.route("/api/devspace/cleanup", methods=["POST"])
def api_devspace_cleanup():
    """启动异步清理任务"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "缺少请求体"})

    branch_name = data.get("branch_name", "").strip()
    force = data.get("force", False)

    if not branch_name:
        return jsonify({"success": False, "error": "branch_name 不能为空"})

    # 非强制模式下检查未提交变更
    if not force:
        changes = check_uncommitted_changes(branch_name)
        if changes.get("has_changes"):
            return jsonify({
                "success": False,
                "error": "存在未提交的变更",
                "changes": changes["changes"]
            })

    task_id = cleanup_devspace_async(branch_name, force)
    return jsonify({"success": True, "task_id": task_id})


# ========================
# 开发空间连接 API
# ========================

@app.route("/api/devspace/attach", methods=["POST"])
def api_devspace_attach():
    """
    通过 iTerm2 连接开发空间

    Request:
        { "branch_name": "feature-xxx" }

    Response (成功):
        { "success": true, "message": "已在 iTerm2 中打开终端" }

    Response (失败):
        { "success": false, "error": "tmux session 不存在: xxx" }
    """
    data = request.get_json()
    if not data or not data.get("branch_name", "").strip():
        return jsonify({"success": False, "error": "缺少 branch_name 参数"})

    branch_name = data["branch_name"].strip()
    result = attach_devspace(branch_name)
    return jsonify(result)


if __name__ == "__main__":
    # 支持直接运行 python src/app.py
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("DASHBOARD_PORT", 5001)))
