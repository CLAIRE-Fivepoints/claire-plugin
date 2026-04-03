#!/usr/bin/env bash
set -euo pipefail

# fivepoints ado-transition — PAT-gated ADO push for dev role
#
# Bash orchestration:
#   [1/3] Verify feature branch (naming convention)
#   [2/3] PAT gate — request AZURE_DEVOPS_WRITE_PAT if not set
#   [3/3] Set up ADO remote + git push, then call ado_agent.py (build agent)
#
# Usage:
#   claire fivepoints ado-transition --issue <N> [--branch <name>] [--target <branch>]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$PLUGIN_ROOT/domain/scripts/ado_common.sh"

ISSUE_NUMBER=""
BRANCH=""
TARGET_BRANCH="dev"

show_help() {
    cat <<'HELP'
Usage: claire fivepoints ado-transition --issue <N> [--branch <name>] [--target <branch>]

PAT-gated transition from dev to ADO. Bash orchestration + Python build agent.

  [1/3] Verify feature branch (feature/XXXXX-description or bugfix/XXXXX-description)
  [2/3] PAT gate — pause and wait for AZURE_DEVOPS_WRITE_PAT if not set
  [3/3] Set up ADO remote + git push + call ado_agent.py (build verification agent)

Options:
  --issue <N>       GitHub issue number (required)
  --branch <name>   Branch to push (default: current branch)
  --target <branch> Target branch for ADO PR (default: dev)

Prerequisites:
  - All tests passed and MP4 proof recorded + posted on issue
  - Branch follows: feature/XXXXX-description or bugfix/XXXXX-description
  - FIVEPOINTS_REPO_PATH set (or default: /Users/andreperez/TFIOneGit)
HELP
}

show_agent_help() {
    cat <<'AGENT_HELP'
# fivepoints ado-transition — Agent Help

## Purpose
PAT-gated transition from dev self-testing to ADO. Called by the dev persona
after ALL FDS sections are tested and proved on video.

## Architecture
- Bash (this script): orchestration — branch verify, PAT gate, ADO remote setup, git push
- Python (ado_agent.py): agent logic — create ADO PR, poll build pipeline, report to GitHub

## Checklist (printed at runtime)
1. Verify branch naming convention
2. PAT gate: request AZURE_DEVOPS_WRITE_PAT if not set (posts wait comment on issue)
3. Initialize ADO connection + git push + call ado_agent.py agent

## Usage
```bash
claire fivepoints ado-transition --issue 2345
claire fivepoints ado-transition --issue 2345 --branch feature/13644-adoption-history
```

## When to call
- After step [9/11] in dev checklist: all FDS sections proved working on video
- Do NOT call before recording proof — ado_agent.py checks for .mp4 in issue

## PAT behavior
- AZURE_DEVOPS_WRITE_PAT present → proceeds immediately
- AZURE_DEVOPS_WRITE_PAT missing → posts wait comment on GitHub issue, pauses

## ado_agent.py (called internally)
Handles: create ADO PR → post PR link on issue → poll build → close issue on success
AGENT_HELP
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --issue)       ISSUE_NUMBER="$2"; shift 2 ;;
        --branch)      BRANCH="$2"; shift 2 ;;
        --target)      TARGET_BRANCH="$2"; shift 2 ;;
        --help|-h)     show_help; exit 0 ;;
        --agent-help)  show_agent_help; exit 0 ;;
        *)             echo "Unknown argument: $1"; show_help; exit 1 ;;
    esac
done

if [[ -z "$ISSUE_NUMBER" ]]; then
    echo "Error: --issue is required"
    show_help
    exit 1
fi

BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     fivepoints ado-transition                ║"
echo "║     Issue: #${ISSUE_NUMBER}                            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ─────────────────────────────────────────────
# [1/3] Verify feature branch
# ─────────────────────────────────────────────
echo "[1/3] Verifying feature branch..."
echo "      Branch: $BRANCH"

if ! echo "$BRANCH" | grep -qE '^(feature|bugfix)/[0-9]+-'; then
    echo ""
    echo "❌  Branch must follow naming convention:"
    echo "    feature/XXXXX-description"
    echo "    bugfix/XXXXX-description"
    echo ""
    echo "    Current branch: $BRANCH"
    echo "    Rename branch before calling ado-transition."
    exit 1
fi

echo "✅  Branch OK: $BRANCH"

# ─────────────────────────────────────────────
# [2/3] PAT gate
# ─────────────────────────────────────────────
echo ""
echo "[2/3] PAT gate (checking AZURE_DEVOPS_WRITE_PAT)..."

if [[ -z "${AZURE_DEVOPS_WRITE_PAT:-}" ]]; then
    echo ""
    echo "⏸   AZURE_DEVOPS_WRITE_PAT is not set."
    echo "    Posting wait comment on issue #${ISSUE_NUMBER}..."
    echo ""

    gh issue comment "$ISSUE_NUMBER" --body "✅ All tests passed and proof recorded. Ready to push to ADO.

⏳ **Waiting for \`AZURE_DEVOPS_WRITE_PAT\`.**
Please set the write PAT in my environment and reply to this issue to unblock.

Branch: \`${BRANCH}\`"

    echo "    Waiting for reply on issue #${ISSUE_NUMBER}..."
    claire wait --issue "$ISSUE_NUMBER"

    if [[ -z "${AZURE_DEVOPS_WRITE_PAT:-}" ]]; then
        echo ""
        echo "❌  AZURE_DEVOPS_WRITE_PAT still not set after wait."
        echo "    Export it in your shell, then rerun: claire fivepoints ado-transition --issue $ISSUE_NUMBER"
        exit 1
    fi
fi

echo "✅  AZURE_DEVOPS_WRITE_PAT set."

# ─────────────────────────────────────────────
# [3/3] ADO remote setup + git push + transition agent
# ─────────────────────────────────────────────
echo ""
echo "[3/3] Setting up ADO remote and pushing branch..."

# Initialize ADO connection (must run from TFIOneGit clone)
CLIENT_REPO_PATH="${FIVEPOINTS_REPO_PATH:-/Users/andreperez/TFIOneGit}"
if [[ ! -d "$CLIENT_REPO_PATH/.git" ]]; then
    echo "❌  Client repo not found at $CLIENT_REPO_PATH"
    echo "    Set FIVEPOINTS_REPO_PATH to the local clone of TFIOneGit"
    exit 1
fi

pushd "$CLIENT_REPO_PATH" > /dev/null
ado_init
popd > /dev/null

echo "      ADO: ${_ADO_ORG}/${_ADO_PROJECT}/${_ADO_REPO}"

# Set up ADO remote with write PAT
ADO_REMOTE_URL="https://${AZURE_DEVOPS_WRITE_PAT}@dev.azure.com/${_ADO_ORG}/${_ADO_PROJECT}/_git/${_ADO_REPO}"
if ! git remote get-url ado &>/dev/null; then
    git remote add ado "$ADO_REMOTE_URL"
else
    git remote set-url ado "$ADO_REMOTE_URL"
fi

# Push branch to ADO
echo "      Pushing ${BRANCH} → ADO..."
git push ado "${BRANCH}:refs/heads/${BRANCH}" --force-with-lease
echo "✅  Branch pushed to ADO"

# Hand off to Python build verification agent
echo ""
echo "── ado_agent.py (build verification agent) ──"
exec python3 "$PLUGIN_ROOT/domain/scripts/ado_agent.py" \
    --issue "$ISSUE_NUMBER" \
    --branch "$BRANCH" \
    --target "$TARGET_BRANCH"
