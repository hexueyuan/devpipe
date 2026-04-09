#!/usr/bin/env bash
# stage-complete.sh — devpipe stage completion marker
#
# Usage: bash plugins/devpipe/scripts/stage-complete.sh <stage> [--next-stage <name>] [context-dir]
#   stage:        current stage being completed
#   --next-stage: optional, preset the next stage (stage=<next>, stage_completed=false)
#   context-dir:  path to .devpipe directory, default ".devpipe"
#
# Exit codes:
#   0 = success, JSON confirmation on stdout
#   1 = context.json missing or error

set -euo pipefail

# ------------------------------------------------------------------
# Parse arguments
# ------------------------------------------------------------------

STAGE=""
NEXT_STAGE=""
DEVPIPE_DIR=".devpipe"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --next-stage)
            NEXT_STAGE="${2:?--next-stage 需要一个值}"
            shift 2
            ;;
        -*)
            echo "未知选项: $1" >&2
            exit 1
            ;;
        *)
            if [[ -z "$STAGE" ]]; then
                STAGE="$1"
            else
                DEVPIPE_DIR="$1"
            fi
            shift
            ;;
    esac
done

[[ -n "$STAGE" ]] || { echo "用法: stage-complete.sh <stage> [--next-stage <name>] [context-dir]" >&2; exit 1; }

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
    local raw
    raw="$(date +"%Y-%m-%dT%H:%M:%S%z")"
    echo "${raw:0:${#raw}-2}:${raw:${#raw}-2}"
}

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

command -v jq >/dev/null 2>&1 || die 1 "错误: jq 未安装，请先安装 jq。"
[[ -f "$CONTEXT_FILE" ]] || die 1 "\`.devpipe/context.json\` 不存在。"

NOW="$(iso_now)"
TMP="${CONTEXT_FILE}.tmp"

if [[ -n "$NEXT_STAGE" ]]; then
    # Mark current stage completed with ended_at, then set next stage
    jq --arg stage "$STAGE" \
       --arg now "$NOW" \
       --arg next "$NEXT_STAGE" \
       '
       .stage_completed = true |
       .stage_timestamps[$stage].ended_at = $now |
       .stage = $next |
       .stage_completed = false
       ' "$CONTEXT_FILE" > "$TMP" && mv "$TMP" "$CONTEXT_FILE"
else
    # Just mark current stage completed with ended_at
    jq --arg stage "$STAGE" \
       --arg now "$NOW" \
       '
       .stage_completed = true |
       .stage_timestamps[$stage].ended_at = $now
       ' "$CONTEXT_FILE" > "$TMP" && mv "$TMP" "$CONTEXT_FILE"
fi

# Output confirmation
jq '{
    stage: .stage,
    stage_completed: .stage_completed,
    stage_timestamps: .stage_timestamps
}' "$CONTEXT_FILE"
