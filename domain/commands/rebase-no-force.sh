#!/usr/bin/env bash
# fivepoints rebase-no-force
# Rebase a feature branch onto the ADO target and push without ForcePush permission.
#
# Uses the snapshot+merge strategy documented in NO_FORCE_PUSH_STRATEGY.md:
#   Step 1: snapshot commit (tree = rebased state, parent = ADO tip) → fast-forward push
#   Step 2: re-anchor merge commit (only if mergeStatus = conflicts after step 1)
#
# Usage:
#   claire fivepoints rebase-no-force --branch <name> [--target <branch>] [--repo-path <path>] [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$PLUGIN_ROOT/domain/scripts/ado_common.sh"

# Defaults
BRANCH=""
TARGET_BRANCH="dev"
REPO_PATH="${FIVEPOINTS_REPO_PATH:-/Users/andreperez/TFIOneGit}"
DRY_RUN=false
PR_ID=""

show_help() {
    echo "Usage: claire fivepoints rebase-no-force --branch <name> [OPTIONS]"
    echo ""
    echo "Rebase a branch onto ADO target and push without ForcePush permission."
    echo "Uses snapshot+merge strategy (fast-forward only, no force required)."
    echo ""
    echo "Options:"
    echo "  --branch <name>     Branch to push (required)"
    echo "  --target <branch>   ADO target branch (default: dev)"
    echo "  --repo-path <path>  Path to local TFIOneGit clone (default: ~/TFIOneGit)"
    echo "  --pr <N>            ADO PR number (to verify mergeStatus after push)"
    echo "  --dry-run           Show commands without executing"
    echo "  --help, -h          Show this help"
    echo "  --agent-help        Show LLM-optimized help"
}

show_agent_help() {
    cat <<'AGENT_HELP'
# fivepoints rebase-no-force — Agent Help

## Purpose
Push a rebased feature branch to ADO when `git push --force-with-lease` is denied
with `TF401027: You need the Git 'ForcePush' permission`.

Uses two-step git plumbing strategy (no force required):
1. Snapshot commit: tree = rebased state, parent = ADO tip → fast-forward push
2. Re-anchor merge commit (only if ADO reports mergeStatus = conflicts after step 1)

## Usage
```bash
# Basic: rebase current branch state onto ado/dev and push
claire fivepoints rebase-no-force --branch feature/10847-client-adoptive-placement --target dev

# With PR verification (checks mergeStatus, applies step 2 if needed)
claire fivepoints rebase-no-force --branch feature/10847-my-feature --target dev --pr 369

# Dry run (shows git commands without running them)
claire fivepoints rebase-no-force --branch feature/10847-my-feature --target dev --dry-run
```

## Prerequisites
- Must be run from TFIOneGit (or pass --repo-path)
- Branch must already be rebased onto ado/dev locally (this command only pushes)
- AZURE_DEVOPS_PAT or AZURE_DEVOPS_DEV_PAT must be set for git push
- If --pr is passed, AZURE_DEVOPS_PAT must have code:read scope

## What it does
1. Fetches ado/dev (or specified target)
2. Reads current local branch tree via `git write-tree`
3. Creates snapshot commit: parent = ADO tip, tree = local state
4. Pushes snapshot commit as fast-forward to ADO
5. (If --pr) Checks mergeStatus via ADO REST API
6. (If mergeStatus = conflicts) Creates re-anchor merge commit and pushes again

## After running
- ADO branch tip will contain your clean rebased tree
- PR mergeStatus should be "succeeded" (21 feature files only vs dev)
- Safe to run `claire fivepoints land` next, or post proof manually
AGENT_HELP
}

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --branch)   BRANCH="$2"; shift 2 ;;
        --target)   TARGET_BRANCH="$2"; shift 2 ;;
        --repo-path) REPO_PATH="$2"; shift 2 ;;
        --pr)       PR_ID="$2"; shift 2 ;;
        --dry-run)  DRY_RUN=true; shift ;;
        --help|-h)  show_help; exit 0 ;;
        --agent-help) show_agent_help; exit 0 ;;
        *)
            echo "Unknown argument: $1" >&2
            show_help >&2
            exit 1 ;;
    esac
done

if [[ -z "$BRANCH" ]]; then
    echo "ERROR: --branch is required" >&2
    show_help >&2
    exit 1
fi

# Work in TFIOneGit
if [[ ! -d "$REPO_PATH/.git" ]]; then
    echo "ERROR: TFIOneGit not found at $REPO_PATH" >&2
    echo "  Set FIVEPOINTS_REPO_PATH or pass --repo-path" >&2
    exit 1
fi

cd "$REPO_PATH"

# Initialize ADO connection for merge status checks
ado_init

# Build write PAT for git push
_PUSH_PAT="${AZURE_DEVOPS_WRITE_PAT:-${AZURE_DEVOPS_DEV_PAT:-${AZURE_DEVOPS_PAT:-}}}"
if [[ -z "$_PUSH_PAT" ]]; then
    echo "ERROR: No ADO PAT found for git push" >&2
    echo "  Set AZURE_DEVOPS_WRITE_PAT or AZURE_DEVOPS_DEV_PAT in ~/.config/claire/.env" >&2
    exit 1
fi

ADO_REMOTE_URL="https://${_PUSH_PAT}@dev.azure.com/${_ADO_ORG}/${_ADO_PROJECT}/_git/${_ADO_REPO}"

# Ensure ado remote is configured with current PAT
if ! git remote get-url ado &>/dev/null; then
    git remote add ado "$ADO_REMOTE_URL"
else
    git remote set-url ado "$ADO_REMOTE_URL"
fi

echo "=== No-Force-Push Strategy ==="
echo "Branch:  $BRANCH"
echo "Target:  ado/$TARGET_BRANCH"
echo "DryRun:  $DRY_RUN"
echo ""

# Step 0: fetch target
echo "[1/4] Fetching ado/${TARGET_BRANCH}..."
if [[ "$DRY_RUN" == "true" ]]; then
    echo "  DRY: git fetch ado ${TARGET_BRANCH}"
else
    git fetch ado "$TARGET_BRANCH"
fi

ADO_TIP=$(git rev-parse "ado/${TARGET_BRANCH}" 2>/dev/null || true)
if [[ -z "$ADO_TIP" ]]; then
    echo "ERROR: Could not resolve ado/${TARGET_BRANCH} after fetch" >&2
    exit 1
fi
echo "  ADO tip: ${ADO_TIP}"

# Step 1: capture tree of current local branch state
LOCAL_TIP=$(git rev-parse "$BRANCH" 2>/dev/null || true)
if [[ -z "$LOCAL_TIP" ]]; then
    echo "ERROR: Branch '$BRANCH' not found locally" >&2
    exit 1
fi

# Write the tree from the local branch tip
TREE=$(git rev-parse "${LOCAL_TIP}^{tree}")
echo "[2/4] Local branch tree: ${TREE}"

# Step 2: create snapshot commit
SNAP_MSG="chore: catch up to ado/${TARGET_BRANCH} (no-force-push snapshot)"
echo "[3/4] Creating snapshot commit (parent = ADO tip)..."
if [[ "$DRY_RUN" == "true" ]]; then
    echo "  DRY: git commit-tree ${TREE} -p ${ADO_TIP} -m '${SNAP_MSG}'"
    SNAP_COMMIT="<dry-run>"
else
    SNAP_COMMIT=$(git commit-tree "$TREE" -p "$ADO_TIP" -m "$SNAP_MSG")
    echo "  Snapshot commit: ${SNAP_COMMIT}"
fi

# Step 3: push snapshot commit as fast-forward
echo "[4/4] Pushing snapshot commit to ADO (fast-forward)..."
if [[ "$DRY_RUN" == "true" ]]; then
    echo "  DRY: git push ado ${SNAP_COMMIT}:refs/heads/${BRANCH}"
else
    git push ado "${SNAP_COMMIT}:refs/heads/${BRANCH}"
    echo "  ✅ Snapshot push succeeded"
fi

# Step 4 (optional): verify mergeStatus and apply re-anchor if needed
if [[ -n "$PR_ID" && "$DRY_RUN" != "true" ]]; then
    echo ""
    echo "[+] Checking PR #${PR_ID} mergeStatus..."
    sleep 5  # ADO needs a moment to recompute after push

    MERGE_STATUS=$(ado_get "/git/repositories/${_ADO_REPO}/pullrequests/${PR_ID}?api-version=7.1" \
        | jq -r '.mergeStatus // "unknown"' 2>/dev/null || echo "unknown")
    echo "  mergeStatus: ${MERGE_STATUS}"

    if [[ "$MERGE_STATUS" == "conflicts" ]]; then
        echo ""
        echo "  ⚠️  mergeStatus = conflicts — applying re-anchor merge commit..."
        echo "      (The 3-way merge-base is too far back; need to add ado/${TARGET_BRANCH} as a 2nd parent)"

        # Re-fetch to get latest ADO tip (may have advanced due to our push)
        git fetch ado "$TARGET_BRANCH"
        ADO_TIP_NOW=$(git rev-parse "ado/${TARGET_BRANCH}")

        MERGE_MSG="chore: re-anchor merge base onto ado/${TARGET_BRANCH}"
        MERGE_COMMIT=$(git commit-tree "$TREE" \
            -p "$SNAP_COMMIT" \
            -p "$ADO_TIP_NOW" \
            -m "$MERGE_MSG")
        echo "  Merge commit: ${MERGE_COMMIT}"

        git push ado "${MERGE_COMMIT}:refs/heads/${BRANCH}"
        echo "  ✅ Re-anchor push succeeded"

        sleep 5
        MERGE_STATUS_AFTER=$(ado_get "/git/repositories/${_ADO_REPO}/pullrequests/${PR_ID}?api-version=7.1" \
            | jq -r '.mergeStatus // "unknown"' 2>/dev/null || echo "unknown")
        echo "  mergeStatus after re-anchor: ${MERGE_STATUS_AFTER}"

        if [[ "$MERGE_STATUS_AFTER" == "succeeded" ]]; then
            echo "  ✅ PR #${PR_ID} mergeStatus = succeeded"
        else
            echo "  ⚠️  mergeStatus = ${MERGE_STATUS_AFTER} — manual investigation may be needed"
        fi
    elif [[ "$MERGE_STATUS" == "succeeded" ]]; then
        echo "  ✅ PR #${PR_ID} mergeStatus = succeeded (no re-anchor needed)"
    else
        echo "  ⚠️  Unexpected mergeStatus: ${MERGE_STATUS}"
    fi
fi

echo ""
echo "=== Done ==="
if [[ "$DRY_RUN" == "true" ]]; then
    echo "Dry run complete. Re-run without --dry-run to execute."
else
    echo "Branch ${BRANCH} pushed to ADO/${TARGET_BRANCH} via no-force strategy."
    if [[ -n "$PR_ID" ]]; then
        echo "PR #${PR_ID}: https://dev.azure.com/${_ADO_ORG}/${_ADO_PROJECT}/_git/${_ADO_REPO}/pullrequest/${PR_ID}"
    fi
fi
