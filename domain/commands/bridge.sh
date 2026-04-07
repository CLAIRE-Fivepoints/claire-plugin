#!/bin/bash
#
# claire fivepoints bridge — Azure DevOps → GitHub issue bridge daemon
#
# Discoverable wrapper around `claire azure-issue-bridge` so the daemon can be
# managed from the fivepoints plugin namespace.
#
set -euo pipefail

LOG_FILE="${HOME}/.claire/runtime/logs/azure-issue-bridge.log"

usage() {
    cat <<'EOF'
claire fivepoints bridge — Azure DevOps → GitHub issue bridge

USAGE:
  claire fivepoints bridge start [--interval N] [--lookback DAYS]
                                          Start background daemon (default: every 15 min)
  claire fivepoints bridge stop           Stop background daemon
  claire fivepoints bridge status         Show daemon state + last run stats
  claire fivepoints bridge logs [-f]      Tail the daemon log
  claire fivepoints bridge run [--dry-run] [--lookback DAYS]
                                          One-shot scan (manual trigger)

This is a discoverable wrapper around `claire azure-issue-bridge`. See:
  claire domain read claire operational AZURE_ISSUE_BRIDGE
EOF
}

show_agent_help() {
    cat <<'AGENT_HELP'
# fivepoints bridge — Agent Help

## Purpose
Manage the Azure DevOps → GitHub issue bridge daemon from the fivepoints
plugin namespace. Discoverable wrapper around `claire azure-issue-bridge`.

## Subcommands
- `start [--interval N] [--lookback DAYS]` — start background daemon
- `stop`                                    — stop background daemon
- `status`                                  — show daemon state + last run stats
- `logs [-f]`                               — tail daemon log (`-f` to follow)
- `run [--dry-run] [--lookback DAYS]`       — one-shot scan (manual trigger)

## Usage
```bash
claire fivepoints bridge start
claire fivepoints bridge status
claire fivepoints bridge logs -f
claire fivepoints bridge run --dry-run
claire fivepoints bridge stop
```

## What it does
`start`, `stop`, `status`, and `run` are delegated directly (via `exec`) to
`claire azure-issue-bridge` — no duplicated daemon logic, no ownership change.
Orphan handling, business hours, and lookback semantics remain owned by the
underlying daemon.

`logs` reads `~/.claire/runtime/logs/azure-issue-bridge.log` directly:
- without `-f`: prints the last 100 lines and exits
- with `-f` / `--follow`: tails the log indefinitely

## Prerequisites
- `AZURE_DEVOPS_PAT` set (env var or `~/.config/claire/.env`)
- `claire azure-issue-bridge` installed (core `claire` repo)

## Exit codes
- 0 — success (or delegated successfully to underlying command)
- 1 — unknown subcommand, missing log file, or no arguments

## See also
- `claire domain read claire operational AZURE_ISSUE_BRIDGE`
- `claire azure-issue-bridge --help`
AGENT_HELP
}

if [[ $# -eq 0 ]]; then
    usage
    exit 1
fi

subcommand="$1"
shift

case "$subcommand" in
    start|stop|status|run)
        exec claire azure-issue-bridge "$subcommand" "$@"
        ;;
    logs)
        if [[ ! -f "$LOG_FILE" ]]; then
            echo "No daemon log found at: $LOG_FILE" >&2
            echo "Start the daemon first: claire fivepoints bridge start" >&2
            exit 1
        fi
        if [[ "${1:-}" == "-f" || "${1:-}" == "--follow" ]]; then
            exec tail -f "$LOG_FILE"
        fi
        exec tail -n 100 "$LOG_FILE"
        ;;
    -h|--help|help)
        usage
        ;;
    --agent-help)
        show_agent_help
        ;;
    *)
        echo "Unknown subcommand: $subcommand" >&2
        echo "" >&2
        usage >&2
        exit 1
        ;;
esac
