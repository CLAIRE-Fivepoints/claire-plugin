#!/usr/bin/env bash
# Azure DevOps Email Bridge — watch Gmail for PBI assignment emails → GitHub issues
# Part of the fivepoints plugin.
#
# Usage:
#   claire fivepoints azure-issue-bridge run [--dry-run] [--max-results N]
#   claire fivepoints azure-issue-bridge start [--interval N] [--dry-run]
#   claire fivepoints azure-issue-bridge stop
#   claire fivepoints azure-issue-bridge status
#
# Pipeline:
#   Gmail inbox → parse PBI ID → fetch ADO work item → gh issue create
#
# Required:
#   AZURE_DEVOPS_PAT   — Azure DevOps PAT (env or ~/.config/claire/.env)
#   Gmail OAuth2       — run: claire email auth

set -euo pipefail

source "$LIB_DIR/logging.sh"
source "$LIB_DIR/daemon_env.sh"

# Daemon management — global PID and log files (singleton per machine, issue #2548)
AZURE_BRIDGE_PIDFILE="$HOME/.claire/runtime/azure-issue-bridge.pid"
AZURE_BRIDGE_LOGFILE="$HOME/.claire/runtime/logs/azure-issue-bridge.log"

# Check if background daemon is running
cmd_azure_bridge_is_running() {
    # Check PID file first (primary check)
    if [[ -f "$AZURE_BRIDGE_PIDFILE" ]]; then
        local pid
        pid=$(cat "$AZURE_BRIDGE_PIDFILE")

        if ps -p "$pid" > /dev/null 2>&1; then
            if ps -p "$pid" -o command= 2>/dev/null | grep -q "azure_issue_bridge"; then
                return 0
            else
                rm -f "$AZURE_BRIDGE_PIDFILE"
            fi
        else
            rm -f "$AZURE_BRIDGE_PIDFILE"
        fi
    fi

    # Fallback: check if any azure_issue_bridge process exists (issue #2548)
    if pgrep -f "azure_issue_bridge" >/dev/null 2>&1; then
        return 0
    fi

    return 1
}

# Start background daemon
cmd_azure_bridge_start() {
    # Acquire startup lock to prevent concurrent starts (issue #2500)
    if ! acquire_daemon_lock "$AZURE_BRIDGE_PIDFILE"; then
        log_info "Azure issue bridge start already in progress — skipping"
        return 0
    fi

    if cmd_azure_bridge_is_running; then
        local pid
        pid=$(cat "$AZURE_BRIDGE_PIDFILE")
        log_info "Azure issue bridge already running (PID: $pid)"
        release_daemon_lock "$AZURE_BRIDGE_PIDFILE"
        return 0
    fi

    # Load credentials from config env file if available
    local claire_env_file="$HOME/.config/claire/.env"
    if [[ -f "$claire_env_file" ]]; then
        # shellcheck disable=SC1090
        source "$claire_env_file" 2>/dev/null || true
    fi

    # Skip start if credentials are not available
    if [[ -z "${AZURE_DEVOPS_PAT:-}" ]]; then
        log_info "Azure issue bridge: AZURE_DEVOPS_PAT not set — skipping auto-start"
        release_daemon_lock "$AZURE_BRIDGE_PIDFILE"
        return 0
    fi

    log_info "Starting Azure issue bridge..."

    mkdir -p "$(dirname "$AZURE_BRIDGE_LOGFILE")"
    export CLAIRE_HOME

    # Pass any extra args (e.g. --interval N) through to the python CLI start loop
    nohup python3 -m claire_py.azure_issue_bridge.cli start "$@" \
        >> "$AZURE_BRIDGE_LOGFILE" 2>&1 &

    local pid=$!
    echo "$pid" > "$AZURE_BRIDGE_PIDFILE"

    sleep 2
    if cmd_azure_bridge_is_running; then
        log_success "Azure issue bridge started (PID: $pid)"
        log_info "Logs: $AZURE_BRIDGE_LOGFILE"
    else
        log_error "Failed to start Azure issue bridge"
        log_error "Check logs: $AZURE_BRIDGE_LOGFILE"
        rm -f "$AZURE_BRIDGE_PIDFILE"
        release_daemon_lock "$AZURE_BRIDGE_PIDFILE"
        return 1
    fi

    release_daemon_lock "$AZURE_BRIDGE_PIDFILE"
}

# Stop background daemon
cmd_azure_bridge_stop() {
    if ! cmd_azure_bridge_is_running; then
        log_info "Azure issue bridge not running"
        return 0
    fi

    local pid
    pid=$(cat "$AZURE_BRIDGE_PIDFILE")
    log_info "Stopping Azure issue bridge (PID: $pid)..."

    kill "$pid" 2>/dev/null

    local count=0
    while cmd_azure_bridge_is_running && [[ $count -lt 5 ]]; do
        sleep 1
        ((count++))
    done

    if ! cmd_azure_bridge_is_running; then
        rm -f "$AZURE_BRIDGE_PIDFILE"
        log_success "Azure issue bridge stopped"
    else
        kill -9 "$pid" 2>/dev/null
        sleep 1
        rm -f "$AZURE_BRIDGE_PIDFILE"
        log_success "Azure issue bridge forcefully stopped"
    fi
}

cmd_azure_issue_bridge_agent_help() {
    # Combine bash-layer daemon commands with Python CLI --agent-help content
    cat <<'EOF'
# fivepoints azure-issue-bridge: ADO PBI Assignment → GitHub Issue Pipeline

## Daemon Management (Bash layer)

  claire fivepoints azure-issue-bridge start [--interval N]   Start background daemon (PID file)
  claire fivepoints azure-issue-bridge stop                   Stop background daemon
  claire fivepoints azure-issue-bridge status                 Show daemon state + last run stats

  Daemon PID file: ~/.claire/runtime/azure-issue-bridge.pid
  Daemon log:      ~/.claire/runtime/logs/azure-issue-bridge.log
  Auto-start:      Runs during claire infra start if AZURE_DEVOPS_PAT is set

  Backward compat: claire azure-issue-bridge <cmd> delegates to this command via shim.

EOF
    cd "$CLAIRE_HOME"
    python3 -m claire_py.azure_issue_bridge.cli --agent-help
}

case "${1:-}" in
    run|test|restore-inbox)
        cd "$CLAIRE_HOME"
        exec python3 -m claire_py.azure_issue_bridge.cli "$@"
        ;;
    start)
        shift
        cd "$CLAIRE_HOME"
        cmd_azure_bridge_start "$@"
        ;;
    stop)
        cmd_azure_bridge_stop
        ;;
    status)
        # Show daemon state first, then last run stats
        if cmd_azure_bridge_is_running; then
            pid=$(cat "$AZURE_BRIDGE_PIDFILE")
            log_success "Azure issue bridge daemon: running (PID: $pid)"
        else
            log_info "Azure issue bridge daemon: stopped"
        fi
        echo ""
        cd "$CLAIRE_HOME"
        exec python3 -m claire_py.azure_issue_bridge.cli status
        ;;
    --agent-help)
        cmd_azure_issue_bridge_agent_help
        ;;
    --help|-h|help)
        cat <<EOF
claire fivepoints azure-issue-bridge — ADO PBI Assignment → GitHub Issue Pipeline

USAGE:
  claire fivepoints azure-issue-bridge run               One-shot: scan inbox + process emails
  claire fivepoints azure-issue-bridge start             Start background daemon
  claire fivepoints azure-issue-bridge stop              Stop background daemon
  claire fivepoints azure-issue-bridge status            Show daemon state + last run stats

SUBCOMMANDS:
  run [--dry-run] [--max-results N] [--lookback DAYS]   Scan inbox and create GitHub issues
  start [--interval N] [--dry-run] [--lookback DAYS]    Start background polling daemon (default: every 15 minutes, 8AM–5PM only)
  stop                                                   Stop background polling daemon
  test [--dry-run] [--max-results N]                    Reset state + process 1 PBI (for testing)
  restore-inbox                                          Restore archived ADO emails to inbox + reset processed.json
  status                                                 Print daemon state + last run stats

OPTIONS:
  --dry-run         Parse + format but do NOT create GitHub issues
  --max-results N   Max inbox emails to scan per run (default: 20)
  --interval N      Poll interval in minutes for start mode (default: 15)
  --lookback DAYS   Limit scan to emails from the last N days, e.g. '30d' or '30' (default: no limit)

BUSINESS HOURS:
  Polling only runs between 8AM and 5PM local time (default).
  Override via env vars:
    ADO_BRIDGE_HOUR_START=8    Start hour (0–23, default: 8)
    ADO_BRIDGE_HOUR_END=17     End hour   (0–23, default: 17)

PIPELINE:
  Gmail inbox
    → filter Azure DevOps assignment emails (from: azuredevops@microsoft.com)
    → parse PBI ID from subject
    → fetch PBI from Azure DevOps REST API
    → create GitHub issue via gh CLI
    → archive email (removed from inbox)

REQUIRED SETUP:
  1. claire email auth                 Gmail OAuth2 (one-time)
  2. export AZURE_DEVOPS_PAT=<pat>     Or set in ~/.config/claire/.env

BACKWARD COMPAT:
  claire azure-issue-bridge <cmd>    delegates here via shim

RUN: claire fivepoints azure-issue-bridge --agent-help for LLM-optimized documentation
EOF
        ;;
    *)
        if [[ -n "${1:-}" ]]; then
            log_error "Unknown subcommand: ${1}"
        fi
        echo "Usage: claire fivepoints azure-issue-bridge <subcommand>"
        echo "       claire fivepoints azure-issue-bridge --help"
        exit 1
        ;;
esac
