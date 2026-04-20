#!/bin/bash
# Dashboard 控制脚本
# 用法: dashboard-ctl.sh <command>
#
# 命令:
#   start     启动 Dashboard（如果未运行）
#   stop      停止 Dashboard
#   restart   重启 Dashboard
#   status    查看运行状态
#   logs      查看日志（实时跟踪）
#   install   安装保活 cron 任务
#   uninstall 卸载保活 cron 任务

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(dirname "$SCRIPT_DIR")"
DASHBOARD_DIR="$WORKSPACE/src"
PID_FILE="/tmp/devpipe-dashboard.pid"
LOG_FILE="/tmp/devpipe-dashboard.log"

# 从插件根目录向上查找宿主仓库根目录（含 .git 的目录）
find_repo_root() {
    local dir
    dir="$(dirname "$(dirname "$WORKSPACE")")"  # 插件根目录的父级
    while [ "$dir" != "/" ]; do
        if [ -d "$dir/.git" ]; then
            echo "$dir"
            return
        fi
        dir="$(dirname "$dir")"
    done
    echo "$PWD"
}

# 从 devpipe.yml 读取 dashboard_port，默认 5051
get_dashboard_port() {
    local repo_root yml_path
    repo_root="$(find_repo_root)"
    yml_path="$repo_root/.devpipe/devpipe.yml"
    if [ -f "$yml_path" ]; then
        local val
        val=$(grep '^dashboard_port:' "$yml_path" 2>/dev/null | head -1 | sed 's/^dashboard_port:[[:space:]]*//' | sed 's/[[:space:]]*#.*//')
        if [ -n "$val" ]; then
            echo "$val"
            return
        fi
    fi
    echo "5051"
}

PORT=$(get_dashboard_port)

# ========================
# 辅助函数
# ========================

is_running() {
    if [ ! -f "$PID_FILE" ]; then
        return 1
    fi

    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null)
    if [ -z "$pid" ]; then
        return 1
    fi

    # 检查进程是否存在且是 python 进程
    if kill -0 "$pid" 2>/dev/null; then
        # 验证是否是 dashboard 进程
        if ps -p "$pid" -o args= 2>/dev/null | grep -q "app.py"; then
            return 0
        fi
    fi

    return 1
}

check_port() {
    if lsof -i :$PORT -sTCP:LISTEN >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

# ========================
# 命令实现
# ========================

cmd_start() {
    if is_running; then
        echo "Dashboard 已在运行 (PID: $(cat "$PID_FILE"))"
        echo "  URL: http://localhost:$PORT"
        return 0
    fi

    # 检查端口是否被占用
    if check_port; then
        echo "ERROR: 端口 $PORT 已被占用"
        lsof -i :$PORT -sTCP:LISTEN
        return 1
    fi

    # 检查 dashboard 目录
    if [ ! -f "$DASHBOARD_DIR/app.py" ]; then
        echo "ERROR: Dashboard 目录不存在: $DASHBOARD_DIR"
        return 1
    fi

    echo "启动 Dashboard..."

    # 使用 nohup 后台启动
    cd "$DASHBOARD_DIR"
    nohup python3 app.py >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo $pid > "$PID_FILE"

    # 等待启动
    local retries=0
    while [ $retries -lt 10 ]; do
        sleep 0.5
        if check_port; then
            break
        fi
        retries=$((retries + 1))
    done

    if is_running && check_port; then
        echo "Dashboard 已启动"
        echo "  PID:  $(cat "$PID_FILE")"
        echo "  URL:  http://localhost:$PORT"
        echo "  日志: $LOG_FILE"
        return 0
    else
        echo "ERROR: 启动失败"
        echo "查看日志: tail -50 $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

cmd_stop() {
    if ! is_running; then
        echo "Dashboard 未运行"
        rm -f "$PID_FILE"
        return 0
    fi

    local pid
    pid=$(cat "$PID_FILE")
    echo "停止 Dashboard (PID: $pid)..."

    kill "$pid" 2>/dev/null

    # 等待进程退出
    local retries=0
    while [ $retries -lt 20 ]; do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "Dashboard 已停止"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 0.5
        retries=$((retries + 1))
    done

    # 强制终止
    echo "强制终止..."
    kill -9 "$pid" 2>/dev/null
    rm -f "$PID_FILE"
    echo "Dashboard 已强制停止"
    return 0
}

cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

cmd_status() {
    if is_running; then
        local pid
        pid=$(cat "$PID_FILE")
        echo "Dashboard 运行中"
        echo "  PID:  $pid"
        echo "  URL:  http://localhost:$PORT"
        echo "  日志: $LOG_FILE"

        # 显示进程信息
        echo ""
        echo "进程信息:"
        ps -p "$pid" -o pid,ppid,%cpu,%mem,etime,args 2>/dev/null || true
        return 0
    else
        echo "Dashboard 未运行"
        rm -f "$PID_FILE" 2>/dev/null
        return 1
    fi
}

cmd_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo "日志文件不存在: $LOG_FILE"
        return 1
    fi

    echo "查看日志: $LOG_FILE"
    echo "按 Ctrl+C 退出"
    echo "---"
    tail -f "$LOG_FILE"
}

cmd_install() {
    local cron_cmd="$SCRIPT_DIR/dashboard-ctl.sh start"
    local cron_entry="* * * * * $cron_cmd >/dev/null 2>&1"

    # 检查是否已安装
    if crontab -l 2>/dev/null | grep -q "dashboard-ctl.sh start"; then
        echo "保活任务已安装"
        crontab -l | grep "dashboard-ctl.sh"
        return 0
    fi

    # 添加 cron 条目
    (crontab -l 2>/dev/null; echo "$cron_entry") | crontab -

    echo "已安装保活 cron 任务（每分钟检查）"
    echo "  $cron_entry"
    echo ""
    echo "Dashboard 如果未运行，将在 1 分钟内自动启动"
}

cmd_uninstall() {
    if ! crontab -l 2>/dev/null | grep -q "dashboard-ctl.sh"; then
        echo "保活任务未安装"
        return 0
    fi

    # 移除 cron 条目
    crontab -l 2>/dev/null | grep -v "dashboard-ctl.sh" | crontab -

    echo "已卸载保活 cron 任务"
}

cmd_help() {
    echo "Dashboard 控制脚本"
    echo ""
    echo "用法: $(basename "$0") <command>"
    echo ""
    echo "命令:"
    echo "  start      启动 Dashboard（如果未运行）"
    echo "  stop       停止 Dashboard"
    echo "  restart    重启 Dashboard"
    echo "  status     查看运行状态"
    echo "  logs       查看日志（实时跟踪）"
    echo "  install    安装保活 cron 任务"
    echo "  uninstall  卸载保活 cron 任务"
    echo ""
    echo "文件位置:"
    echo "  PID 文件:  $PID_FILE"
    echo "  日志文件:  $LOG_FILE"
    echo "  监听端口:  $PORT"
}

# ========================
# 主入口
# ========================

case "${1:-}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    status)
        cmd_status
        ;;
    logs)
        cmd_logs
        ;;
    install)
        cmd_install
        ;;
    uninstall)
        cmd_uninstall
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        cmd_help
        exit 1
        ;;
esac
