#!/usr/bin/env bash
# stage-gate.sh — devpipe stage entry gate check + stage start marker
#
# Usage: bash plugins/devpipe/scripts/stage-gate.sh <stage> [context-dir]
#   stage:       discuss | design | coding | review-and-fix | summarize
#   context-dir: path to .devpipe directory, default ".devpipe"
#
# Exit codes:
#   0 = passed, JSON summary on stdout
#   1 = context.json missing or required fields empty
#   2 = prerequisite stage not met
#   3 = dependency file missing

set -euo pipefail

STAGE="${1:?用法: stage-gate.sh <stage> [context-dir]}"
DEVPIPE_DIR="${2:-.devpipe}"
CONTEXT_FILE="${DEVPIPE_DIR}/context.json"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

die() {
    local code="$1"; shift
    echo "$*" >&2
    exit "$code"
}

iso_now() {
    # ISO 8601 with timezone offset, compatible with macOS and Linux
    local raw
    raw="$(date +"%Y-%m-%dT%H:%M:%S%z")"
    # Insert colon into timezone offset: +0800 -> +08:00
    echo "${raw:0:${#raw}-2}:${raw:${#raw}-2}"
}

require_jq() {
    command -v jq >/dev/null 2>&1 || die 1 "错误: jq 未安装，请先安装 jq。"
}

# ------------------------------------------------------------------
# Validate context.json existence and required fields
# ------------------------------------------------------------------

validate_context() {
    [[ -f "$CONTEXT_FILE" ]] || die 1 "\`.devpipe/context.json\` 不存在，请先执行 \`/devpipe:init\` 创建开发环境。"

    local missing=()
    for field in dev_type description remote_branch local_branch; do
        local val
        val="$(jq -r --arg f "$field" '.[$f] // ""' "$CONTEXT_FILE")"
        [[ -n "$val" ]] || missing+=("$field")
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        die 1 "\`.devpipe/context.json\` 字段缺失: ${missing[*]}，请先执行 \`/devpipe:init\` 创建开发环境。"
    fi
}

# ------------------------------------------------------------------
# Prerequisite stage check
# ------------------------------------------------------------------

check_prerequisite_stage() {
    local current_stage
    current_stage="$(jq -r '.stage // ""' "$CONTEXT_FILE")"
    local dev_type
    dev_type="$(jq -r '.dev_type // ""' "$CONTEXT_FILE" | tr '[:upper:]' '[:lower:]')"

    case "$STAGE" in
        discuss)
            # discuss only for 新功能, check dev_type
            if [[ "$dev_type" != "新功能" && "$dev_type" != "新功能" ]]; then
                die 2 "discuss 阶段仅适用于「新功能」类型。当前 dev_type 为「$(jq -r '.dev_type' "$CONTEXT_FILE")」，请直接使用 \`/devpipe:design\` 进行方案设计。"
            fi
            ;;
        design)
            # design follows discuss (for 新功能) or init (for Bugfix/重构)
            ;;
        coding)
            # coding follows design
            ;;
        review-and-fix)
            if [[ "$current_stage" != "coding" && "$current_stage" != "review-and-fix" ]]; then
                die 2 "当前阶段为 \`$current_stage\`，review-and-fix 阶段要求前置阶段为 coding 或 review-and-fix。请先完成 coding 阶段。"
            fi
            ;;
        summarize)
            if [[ "$current_stage" != "review-and-fix" && "$current_stage" != "summarize" ]]; then
                die 2 "当前阶段为 \`$current_stage\`，summarize 阶段要求前置阶段为 review-and-fix 或 summarize。请先完成 review-and-fix 阶段。"
            fi
            ;;
        *)
            die 1 "未知阶段: $STAGE。支持的阶段: discuss, design, coding, review-and-fix, summarize"
            ;;
    esac
}

# ------------------------------------------------------------------
# Dependency file check
# ------------------------------------------------------------------

check_dependency_files() {
    local dev_type
    dev_type="$(jq -r '.dev_type // ""' "$CONTEXT_FILE")"
    # Normalize dev_type for comparison (handle both "新功能" and variations)
    local dev_type_lower
    dev_type_lower="$(echo "$dev_type" | tr '[:upper:]' '[:lower:]')"

    case "$STAGE" in
        discuss)
            # discuss only for 新功能, no additional file deps
            ;;
        design)
            # For 新功能: require prd.md (from discuss)
            # For Bugfix/优化重构: no prd.md required (coming directly from init)
            if [[ "$dev_type" == "新功能" ]]; then
                [[ -f "${DEVPIPE_DIR}/prd.md" ]] || die 3 "\`.devpipe/prd.md\` 不存在，请先执行 \`/devpipe:discuss\` 讨论需求。"
            fi
            # For Bugfix/优化重构, no prd.md check - they come directly from init
            ;;
        coding)
            # All dev_types require coding-plan.md now
            [[ -f "${DEVPIPE_DIR}/coding-plan.md" ]] || die 3 "\`.devpipe/coding-plan.md\` 不存在，请先执行 \`/devpipe:design\` 制定方案。"
            ;;
        # review-and-fix, summarize have no file deps beyond context.json
    esac
}

# ------------------------------------------------------------------
# Update context.json: set stage, stage_completed, stage_timestamps
# ------------------------------------------------------------------

update_context() {
    local now
    now="$(iso_now)"

    local tmp="${CONTEXT_FILE}.tmp"

    jq --arg stage "$STAGE" \
       --arg now "$now" \
       '
       .stage as $prev_stage |
       (if ($prev_stage != null and $prev_stage != "" and $prev_stage != $stage)
        then .stage_timestamps[$prev_stage].ended_at //= $now
        else . end) |
       .stage = $stage |
       .stage_completed = false |
       .stage_timestamps[$stage] = {
           "started_at": $now,
           "ended_at": null
       }
       ' "$CONTEXT_FILE" > "$tmp" && mv "$tmp" "$CONTEXT_FILE"
}

# ------------------------------------------------------------------
# Output JSON summary to stdout
# ------------------------------------------------------------------

output_summary() {
    jq '{
        dev_type: .dev_type,
        description: .description,
        github_issue: (.github_issue // ""),
        remote_branch: .remote_branch,
        local_branch: .local_branch,
        stage: .stage,
        stage_completed: .stage_completed,
        github_issue_body: (if .github_issue_body then "present" else "absent" end)
    }' "$CONTEXT_FILE"
}

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

require_jq
validate_context
check_prerequisite_stage
check_dependency_files
update_context
output_summary
