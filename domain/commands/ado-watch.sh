#!/usr/bin/env bash
# fivepoints ado-watch — Continuous monitor for a specific Azure DevOps PR
#
# Unlike `fivepoints wait --pr N` (which blocks until ONE event then exits),
# ado-watch runs indefinitely and reports ALL events: new comments, vote changes,
# merges, and abandons. Stops automatically when the PR is completed or abandoned.

set -euo pipefail

# Hardcoded ADO target (TFI One project)
readonly ADO_ORG="FivePointsTechnology"
readonly ADO_PROJECT="TFIOne"
readonly ADO_REPO="TFIOneGit"
readonly ADO_BASE_URL="https://dev.azure.com/${ADO_ORG}/${ADO_PROJECT}/_apis"
readonly TFI_LOCAL_PATH="/Users/andreperez/TFIOneGit"

# Configuration (overridable via env)
POLL_INTERVAL="${FIVEPOINTS_ADO_WATCH_INTERVAL:-300}"

ADO_AUTH_HEADER=""

# =============================================================================
# HELP
# =============================================================================

if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
    cat << 'EOF'
Usage: claire fivepoints ado-watch --pr N [--interval SECONDS]

Continuously monitor an Azure DevOps PR and report ALL activity.

Unlike `fivepoints wait --pr N` (which exits after the first event),
ado-watch keeps running and reports every new comment, vote, and merge.
Stops automatically when the PR is completed or abandoned.

Arguments:
  --pr N          PR number to watch (required)

Options:
  --interval N    Poll interval in seconds (default: 300 = 5 minutes)
                  Env var: FIVEPOINTS_ADO_WATCH_INTERVAL

Authentication (auto-discovery, in order):
  1. AZURE_DEVOPS_PAT environment variable
  2. ~/.config/claire/.env file
  3. /Users/andreperez/TFIOneGit git remote URL (embedded PAT)

Examples:
  claire fivepoints ado-watch --pr 123              # Watch PR #123, every 5 minutes
  claire fivepoints ado-watch --pr 123 --interval 60  # Watch every minute (dev mode)

Press Ctrl+C to stop early.
EOF
    exit 0
fi

if [[ "${1:-}" == "--agent-help" ]]; then
    cat << 'EOF'
COMMAND: claire fivepoints ado-watch --pr N
PURPOSE: Continuously monitor a specific Azure DevOps PR for ALL activity.

WHEN TO USE:
  - After creating a PR in ADO, to monitor it for comments, votes, and merge
  - Unlike `fivepoints wait --pr N` (exits on first event), this keeps running
    and reports every event until the PR is closed
  - Useful as a background long-running monitor for the five points workflow

USAGE:
  claire fivepoints ado-watch --pr 123              # 5-minute polling (default)
  claire fivepoints ado-watch --pr 123 --interval 300  # explicit 5 minutes

WHAT IT REPORTS:
  - New comments on any thread
  - Vote changes (approved, rejected, waiting)
  - PR completed (merged) → exits automatically
  - PR abandoned → exits automatically

OUTPUT FORMAT:
  [HH:MM:SS] Watching PR #123: "title" (status: active)
  [HH:MM:SS] NEW COMMENT (3 -> 5): last by "John Doe"
  [HH:MM:SS] VOTE CHANGE: 2 reviewer(s) voted
  [HH:MM:SS] PR #123 COMPLETED (merged)

AUTHENTICATION:
  Auto-discovers PAT from env var, ~/.config/claire/.env, or TFIOneGit remote.
  No manual setup needed on this machine.

EXIT:
  Exits automatically when PR is completed/abandoned, or on Ctrl+C.
  As background task: Bash(command: "claire fivepoints ado-watch --pr 123", run_in_background: true)
EOF
    exit 0
fi

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

PR_NUMBER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pr)
            PR_NUMBER="$2"
            shift 2
            ;;
        --interval)
            POLL_INTERVAL="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Run 'claire fivepoints ado-watch --help' for usage." >&2
            exit 1
            ;;
    esac
done

if [[ -z "$PR_NUMBER" ]]; then
    echo "ERROR: --pr N is required." >&2
    echo "Usage: claire fivepoints ado-watch --pr N [--interval SECONDS]" >&2
    exit 1
fi

# =============================================================================
# PAT DISCOVERY
# =============================================================================

_discover_pat() {
    # 1. Environment variable
    if [[ -n "${AZURE_DEVOPS_PAT:-}" ]]; then
        return 0
    fi

    # 2. ~/.config/claire/.env
    local config_env="$HOME/.config/claire/.env"
    if [[ -f "$config_env" ]]; then
        local config_pat
        config_pat=$(grep -E '^AZURE_DEVOPS_PAT=' "$config_env" 2>/dev/null | head -1 | cut -d= -f2- || true)
        if [[ -n "$config_pat" ]]; then
            export AZURE_DEVOPS_PAT="$config_pat"
            return 0
        fi
    fi

    # 3. TFIOneGit git remote URL (embedded PAT)
    if [[ -d "$TFI_LOCAL_PATH" ]]; then
        local remote_url
        remote_url=$(git -C "$TFI_LOCAL_PATH" remote get-url origin 2>/dev/null || echo "")
        local embedded_pat
        embedded_pat=$(echo "$remote_url" | sed -n 's|https://[^:]*:\([^@]*\)@.*dev\.azure\.com.*|\1|p')
        if [[ -n "$embedded_pat" ]]; then
            export AZURE_DEVOPS_PAT="$embedded_pat"
            return 0
        fi
    fi

    echo "ERROR: AZURE_DEVOPS_PAT not found." >&2
    echo "Set it with: export AZURE_DEVOPS_PAT='your-pat'" >&2
    echo "Or: claire config set azure_devops.pat <your-pat>" >&2
    return 1
}

# =============================================================================
# API HELPERS
# =============================================================================

_ado_get() {
    local endpoint="$1"
    local url

    if [[ "$endpoint" == https://* ]]; then
        url="$endpoint"
    else
        url="${ADO_BASE_URL}${endpoint}"
    fi

    curl -sf -H "$ADO_AUTH_HEADER" -H "Content-Type: application/json" "$url" 2>/dev/null || echo "{}"
}

# =============================================================================
# PR STATE FUNCTIONS
# =============================================================================

# Returns PR info: "title|status|reviewerCount"
_get_pr_state() {
    local response
    response=$(_ado_get "/git/repositories/${ADO_REPO}/pullrequests/${PR_NUMBER}?api-version=7.1")

    local title status reviewer_count
    title=$(echo "$response" | jq -r '.title // "PR #'"$PR_NUMBER"'"' 2>/dev/null)
    status=$(echo "$response" | jq -r '.status // "unknown"' 2>/dev/null)
    reviewer_count=$(echo "$response" | jq '[.reviewers // [] | .[] | select(.vote != 0)] | length' 2>/dev/null || echo "0")

    echo "${title}|${status}|${reviewer_count}"
}

# Returns count of non-system text comments across all threads
_get_comment_count() {
    local response
    response=$(_ado_get "/git/repositories/${ADO_REPO}/pullRequests/${PR_NUMBER}/threads?api-version=7.1")
    echo "$response" | jq '[.value // [] | .[] | select(.isDeleted != true) | .comments[]? | select(.commentType == "text")] | length' 2>/dev/null || echo "0"
}

# Returns display name of most recent commenter
_get_last_commenter() {
    local response
    response=$(_ado_get "/git/repositories/${ADO_REPO}/pullRequests/${PR_NUMBER}/threads?api-version=7.1")
    echo "$response" | jq -r '[.value // [] | .[] | select(.isDeleted != true) | .comments[]? | select(.commentType == "text")] | sort_by(.publishedDate) | last | .author.displayName // "unknown"' 2>/dev/null || echo "unknown"
}

# =============================================================================
# MAIN LOOP
# =============================================================================

main() {
    _discover_pat || exit 1

    local encoded
    encoded=$(printf '%s' ":${AZURE_DEVOPS_PAT}" | base64)
    ADO_AUTH_HEADER="Authorization: Basic ${encoded}"

    local interval_display
    if (( POLL_INTERVAL % 60 == 0 )); then
        interval_display="$(( POLL_INTERVAL / 60 ))m"
    else
        interval_display="${POLL_INTERVAL}s"
    fi

    # ── Initial PR state ───────────────────────────────────────────────────
    local ts
    ts=$(date '+%H:%M:%S')

    local state_info title pr_status reviewer_count
    state_info=$(_get_pr_state)
    title="${state_info%%|*}"
    pr_status=$(echo "$state_info" | cut -d'|' -f2)
    reviewer_count="${state_info##*|}"

    if [[ "$pr_status" == "completed" ]]; then
        echo "[${ts}] PR #${PR_NUMBER} is already completed (merged)."
        exit 0
    elif [[ "$pr_status" == "abandoned" ]]; then
        echo "[${ts}] PR #${PR_NUMBER} is already abandoned."
        exit 0
    fi

    local comment_count
    comment_count=$(_get_comment_count)

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  fivepoints ado-watch"
    echo "  PR #${PR_NUMBER}: \"${title}\""
    echo "  Status: ${pr_status} | Comments: ${comment_count} | Votes: ${reviewer_count}"
    echo "  Poll interval: ${interval_display}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "[${ts}] Watching PR #${PR_NUMBER} (Ctrl+C to stop)"
    echo ""

    # ── Poll loop ──────────────────────────────────────────────────────────
    while true; do
        sleep "$POLL_INTERVAL"

        ts=$(date '+%H:%M:%S')
        local changed=false

        # Check PR status
        local new_state_info new_title new_status new_reviewer_count
        new_state_info=$(_get_pr_state)
        new_title="${new_state_info%%|*}"
        new_status=$(echo "$new_state_info" | cut -d'|' -f2)
        new_reviewer_count="${new_state_info##*|}"

        # Detect completed or abandoned
        if [[ "$new_status" == "completed" ]]; then
            echo "[${ts}] PR #${PR_NUMBER} COMPLETED (merged) ✓"
            exit 0
        elif [[ "$new_status" == "abandoned" ]]; then
            echo "[${ts}] PR #${PR_NUMBER} ABANDONED"
            exit 0
        fi

        # Detect new comments
        local new_comment_count
        new_comment_count=$(_get_comment_count)
        if [[ "$new_comment_count" -gt "$comment_count" ]]; then
            local last_commenter
            last_commenter=$(_get_last_commenter)
            echo "[${ts}] NEW COMMENT (${comment_count} -> ${new_comment_count}): last by \"${last_commenter}\""
            comment_count="$new_comment_count"
            changed=true
        fi

        # Detect vote changes
        if [[ "$new_reviewer_count" -ne "$reviewer_count" ]]; then
            echo "[${ts}] VOTE CHANGE: ${new_reviewer_count} reviewer(s) voted"
            reviewer_count="$new_reviewer_count"
            changed=true
        fi

        # Status line when nothing changed
        if [[ "$changed" == "false" ]]; then
            echo "[${ts}] No new activity (${comment_count} comment(s), ${reviewer_count} vote(s))"
        fi
    done
}

main "$@"
