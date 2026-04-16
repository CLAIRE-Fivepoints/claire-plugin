#!/usr/bin/env bash
# fivepoints ado-fetch-attachments
#
# Fetch FDS attachments from an Azure DevOps PBI, MD5-compare against the domain
# cache, extract images with section cross-references, and open a drift issue
# when the cache is stale.
#
# Usage:
#   claire fivepoints ado-fetch-attachments --pbi <id> [--diff-only] [--auto-issue]
#   claire fivepoints ado-fetch-attachments --agent-help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PLUGIN_PYTHON_DIR="$PLUGIN_ROOT/domain/scripts"
DEFAULT_CACHE_DIR="$PLUGIN_ROOT/domain/knowledge"

show_agent_help() {
    cat <<'HELP'
# fivepoints ado-fetch-attachments — LLM Agent Guide

## Purpose
Keep the `fivepoints` domain FDS cache in sync with the latest attachment on an
Azure DevOps PBI. Extracts images with section cross-references so an agent can
map a wireframe to the exact FDS heading.

## Modes
- `--diff-only`   Report whether the domain cache matches the fresh attachment.
                  No issue created, no section/image writes. Exit 0 if cache is
                  up-to-date, 1 if drift detected.
- `--auto-issue`  On drift, write the drift issue body to staging AND open the
                  issue in the plugin repo via `gh issue create`.
- (neither)       Extract images + section markdown into the staging dir but do
                  not open an issue. Useful for an agent that wants to inspect
                  the fresh FDS locally.

## Arguments
- `--pbi <id>`         (required) ADO PBI ID
- `--cache-dir <path>` Override domain cache location (default: plugin domain/knowledge)
- `--staging-dir <path>` Where to write downloads (default: ~/TFIOneGit/.fds-cache/{pbi})
- `--org <name>`       ADO organization (default: FivePointsTechnology)
- `--project <name>`   ADO project (default: TFIOne)
- `--issue-repo <repo>` Drift issue target (default: claire-labs/fivepoints-plugin)

## Exit codes
- 0 — cache is up-to-date (or PBI has no attachments)
- 1 — drift detected (staging populated; issue body generated)
- 2 — error (PAT missing, API failure, gh create failed)

## PAT
Read-only PAT is sufficient. Resolved in order:
AZURE_DEVOPS_WRITE_PAT → AZURE_DEVOPS_DEV_PAT → AZURE_DEVOPS_PAT → ~/.config/claire/.env

## Output when drift detected
- {staging}/{pbi}/{attachment-name}.docx         — the fresh document
- {staging}/{pbi}/FDS_<NAME>_images/              — extracted PNG/JPEG + .md sidecars
- {staging}/{pbi}/FDS_<NAME>_IMAGE_INDEX.md       — image→section cross-reference
- {staging}/{pbi}/drift_issue_<NAME>.md           — issue body
- {staging}/{pbi}/drift_action_<NAME>.json        — `{action, title, body_file, repo, labels}`

`ado-fetch-attachments.sh` reads the action files and calls `gh issue create`
when `--auto-issue` is on.
HELP
}

# Parse args — pass-through to Python with local toggles for --agent-help and --auto-issue
ARGS=()
AUTO_ISSUE=false
STAGING_DIR_OVERRIDE=""
CACHE_DIR_OVERRIDE=""
PBI_ID=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --agent-help|-h|--help)
            show_agent_help
            exit 0
            ;;
        --auto-issue)
            AUTO_ISSUE=true
            ARGS+=("--auto-issue")
            shift
            ;;
        --staging-dir)
            STAGING_DIR_OVERRIDE="$2"
            ARGS+=("--staging-dir" "$2")
            shift 2
            ;;
        --cache-dir)
            CACHE_DIR_OVERRIDE="$2"
            ARGS+=("--cache-dir" "$2")
            shift 2
            ;;
        --pbi)
            PBI_ID="$2"
            ARGS+=("--pbi" "$2")
            shift 2
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done

if [[ -z "$PBI_ID" ]]; then
    echo "ERROR: --pbi <id> is required" >&2
    echo "Run 'claire fivepoints ado-fetch-attachments --agent-help' for usage." >&2
    exit 2
fi

# Default cache-dir to the plugin's domain/knowledge if not overridden
if [[ -z "$CACHE_DIR_OVERRIDE" ]]; then
    ARGS+=("--cache-dir" "$DEFAULT_CACHE_DIR")
    CACHE_DIR_OVERRIDE="$DEFAULT_CACHE_DIR"
fi

# Default staging-dir if not set
if [[ -z "$STAGING_DIR_OVERRIDE" ]]; then
    STAGING_DIR_OVERRIDE="$HOME/TFIOneGit/.fds-cache"
fi

# Export PYTHONPATH so Python can import ado_fetch_attachments
export PYTHONPATH="$PLUGIN_PYTHON_DIR:${PYTHONPATH:-}"

# Run the Python analysis (all logic lives there — bash only orchestrates)
set +e
python3 -m ado_fetch_attachments.cli "${ARGS[@]+"${ARGS[@]}"}"
PY_EXIT=$?
set -e

# If Python signalled drift (exit 1) and --auto-issue was set, orchestrate gh
if [[ "$PY_EXIT" == "1" && "$AUTO_ISSUE" == "true" ]]; then
    pbi_staging="$STAGING_DIR_OVERRIDE/$PBI_ID"
    if [[ ! -d "$pbi_staging" ]]; then
        echo "ERROR: staging dir $pbi_staging not found — cannot open issue" >&2
        exit 2
    fi

    shopt -s nullglob
    action_files=("$pbi_staging"/drift_action_*.json)
    shopt -u nullglob

    if [[ ${#action_files[@]} -eq 0 ]]; then
        echo "ERROR: no drift_action_*.json written — nothing to issue" >&2
        exit 2
    fi

    for action_file in "${action_files[@]+"${action_files[@]}"}"; do
        action=$(jq -r '.action' "$action_file")
        if [[ "$action" != "create_issue" ]]; then
            continue
        fi
        title=$(jq -r '.title' "$action_file")
        body_file=$(jq -r '.body_file' "$action_file")
        repo=$(jq -r '.repo' "$action_file")

        # Build --label flags from the labels[] array
        label_args=()
        while IFS= read -r label; do
            [[ -z "$label" ]] && continue
            label_args+=("--label" "$label")
        done < <(jq -r '.labels[]?' "$action_file")

        echo "[gh] creating issue in $repo: $title"
        issue_url=$(gh issue create \
            --repo "$repo" \
            --title "$title" \
            --body-file "$body_file" \
            "${label_args[@]+"${label_args[@]}"}")
        echo "[gh] $issue_url"
    done
fi

exit "$PY_EXIT"
