#!/usr/bin/env bash
set -euo pipefail

# fivepoints ado-push — Push branch to ADO + create PR + watch for merge
#
# Usage:
#   claire fivepoints ado-push --issue <N> --branch <name> [--target <branch>]
#
# What it does:
#   1. Validates --branch (required, no fallback to current branch)
#   2. Adds ADO as git remote "ado" (if not present)
#   3. Pushes the branch to ADO
#   4. Creates a PR via ADO REST API
#   5. Posts ADO PR link on the GitHub issue
#   6. Changes label to role:ado-review
#   7. Starts fivepoints ado-watch --pr <N>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$PLUGIN_ROOT/domain/scripts/ado_common.sh"

# Parse arguments
ISSUE_NUMBER=""
BRANCH=""
TARGET_BRANCH="main"
ASK_PAT=false

# Step tracker — updated before each major operation so the ERR trap can report where we failed
ADO_PUSH_CURRENT_STEP="initializing"

# ERR trap: fires on any non-zero exit after the trap is installed.
# Posts a structured failure comment on the GitHub issue so agents know
# NOT to regress role:tester → role:dev — the failure is infra/auth, not tests.
_on_ado_push_error() {
    local _exit_code=$?
    trap - ERR  # Prevent recursive firing if gh itself fails
    if [[ -n "${ISSUE_NUMBER:-}" && -n "${GH_REPO:-}" ]]; then
        gh issue comment "$ISSUE_NUMBER" --repo "$GH_REPO" --body "❌ ado-push FAILED at step: \`${ADO_PUSH_CURRENT_STEP}\`

Pipeline state preserved at \`role:tester\`. The implementation is fine — the failure is infrastructure/auth (exit code: ${_exit_code}).

**DO NOT** run \`fivepoints transition --role tester --next dev\`.
Fix the underlying cause (PAT / network / ADO API) and re-run \`fivepoints ado-push\`." 2>/dev/null || true
    fi
}

show_help() {
    echo "Usage: claire fivepoints ado-push --issue <N> --branch <name> [--target <branch>] [--ask-pat]"
    echo ""
    echo "Push a branch to Azure DevOps, create a PR, and watch for merge."
    echo ""
    echo "Options:"
    echo "  --issue <N>       GitHub issue number (required)"
    echo "  --branch <name>   Branch to push (required — no fallback to current branch)"
    echo "                    Convention: feature/{ticket-id}-description or bugfix/{ticket-id}-description"
    echo "  --target <branch> Target branch for PR (default: main)"
    echo "  --ask-pat         Prompt for write PAT interactively (not saved)"
    echo ""
    echo "This command is the final step of the Five Points pipeline."
    echo "Called by the tester after all tests pass."
}

show_agent_help() {
    cat <<'AGENT_HELP'
# fivepoints ado-push — Agent Help

## Purpose
Push a tested branch to Azure DevOps, create a PR for Steven's review,
and monitor the PR until merge. Final step of the Five Points pipeline.

## Usage
```bash
# --branch is REQUIRED — never inferred from current branch
claire fivepoints ado-push --issue 123 --branch feature/10856-client-export
claire fivepoints ado-push --issue 123 --branch bugfix/10901-fix-null-reference
```

## What it does
1. Validates branch follows naming convention
2. Adds ADO as a git remote (if not present)
3. Pushes the branch to ADO
4. Creates a PR via ADO REST API (PR title derived from branch name)
5. Posts ADO PR link on the GitHub issue
6. Changes issue label to `role:ado-review`
7. Starts `fivepoints ado-watch --pr <ADO_PR_NUMBER>`
8. On ADO merge → closes the GitHub issue

## Branch naming convention (REQUIRED)
```
feature/{ticket-id}-short-description   # new features
bugfix/{ticket-id}-short-description    # bug fixes
```
Examples: `feature/10856-client-export`, `bugfix/10901-fix-null-reference`

PR title is automatically derived from the branch name by stripping the prefix:
- Branch `feature/10856-client-export` → PR title `10856-client-export`
- Branch `bugfix/10901-fix-null` → PR title `10901-fix-null`

## Prerequisites
- Branch must follow `feature/` or `bugfix/` naming convention
- Branch must exist locally with all commits pushed to client GitHub
- Tester must have PASSED all tests
- Write PAT required: use `--ask-pat` to prompt interactively, or set AZURE_DEVOPS_WRITE_PAT in env
- No unit test files committed (com.tfione.service.test should only have controller/repo tests)
- No GRANT/DENY in migration files
- `com.tfione.api.d.ts` must NOT be staged or committed

## PAT handling
The write PAT (`AZURE_DEVOPS_WRITE_PAT`) is required to push and create PRs.
Priority:
1. `AZURE_DEVOPS_WRITE_PAT` env var (already exported)
2. `AZURE_DEVOPS_WRITE_PAT` in `~/.config/claire/.env`
3. `--ask-pat` flag → interactive prompt (not saved to disk)
4. Fallback to `AZURE_DEVOPS_DEV_PAT` / `AZURE_DEVOPS_PAT` if write PAT unavailable

## After running
This script blocks while monitoring the ADO PR. When the PR is merged,
it automatically closes the GitHub issue with a summary comment.
AGENT_HELP
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --issue)
            ISSUE_NUMBER="$2"
            shift 2
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --target)
            TARGET_BRANCH="$2"
            shift 2
            ;;
        --ask-pat)
            ASK_PAT=true
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        --agent-help)
            show_agent_help
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            show_help
            exit 1
            ;;
    esac
done

if [[ -z "$ISSUE_NUMBER" ]]; then
    echo "ERROR: --issue is required" >&2
    show_help
    exit 1
fi

if [[ -z "$BRANCH" ]]; then
    echo "ERROR: --branch is required. Never inferred from current branch." >&2
    echo "  Convention: feature/{ticket-id}-description or bugfix/{ticket-id}-description" >&2
    echo "  Example:    claire fivepoints ado-push --issue $ISSUE_NUMBER --branch feature/13644-my-feature" >&2
    exit 1
fi

# Validate branch naming convention: feature/{numeric-id}-description or bugfix/{numeric-id}-description
if [[ ! "$BRANCH" =~ ^(feature|bugfix)/[0-9]+-. ]]; then
    echo "ERROR: Branch '$BRANCH' does not follow the naming convention." >&2
    echo "  Required: feature/{ticket-id}-short-description" >&2
    echo "  Required: bugfix/{ticket-id}-short-description" >&2
    echo "  Examples: feature/10856-client-export, bugfix/10901-fix-null-reference" >&2
    exit 1
fi

# Detect repo for GitHub issue operations (must be defined before the proof gate).
# Override by setting CLAIRE_WAIT_REPO in the environment.
GH_REPO="${CLAIRE_WAIT_REPO:-CLAIRE-Fivepoints/fivepoints-test}"

# HARD GATE: Proof must be posted in the GitHub issue before ADO push.
# Tester must have run `claire proof record --project fivepoints` AND posted
# the .mp4 path in the GitHub issue comment. This is verified by checking
# the issue comments for a .mp4 link — tying proof to this specific issue.
echo "Checking proof evidence in GitHub issue #${ISSUE_NUMBER}..."

PROOF_FOUND=false
PROOF_COMMENT=$(gh issue view "$ISSUE_NUMBER" --repo "$GH_REPO" --json comments \
    --jq '[.comments[].body | select(contains(".mp4"))] | first // ""' \
    2>/dev/null || echo "")

if [[ -n "$PROOF_COMMENT" ]]; then
    PROOF_FOUND=true
fi

if [[ "$PROOF_FOUND" != "true" ]]; then
    echo "❌ HARD GATE: No MP4 proof found in GitHub issue #${ISSUE_NUMBER}." >&2
    echo "" >&2
    echo "The tester must record proof AND post the .mp4 path in the issue:" >&2
    echo "" >&2
    echo "  1. Record proof: claire domain search video mp4  (see recording instructions)" >&2
    echo "  2. Post the .mp4 path in the issue (this is a real gh command):" >&2
    echo "       gh issue comment ${ISSUE_NUMBER} --repo ${GH_REPO} --body 'Proof: /path/to/proof.mp4'" >&2
    echo "  3. Re-run: claire fivepoints ado-push --issue ${ISSUE_NUMBER}" >&2
    echo "" >&2
    echo "❌ fivepoints ado-push requires .mp4 proof posted in issue #${ISSUE_NUMBER}." >&2
    exit 1
fi

echo "✅ Proof verified: .mp4 evidence found in issue #${ISSUE_NUMBER} comments"
echo ""

# Install ERR trap now that ISSUE_NUMBER and GH_REPO are both known.
# Any non-zero exit from this point onward will post the structured failure marker.
trap '_on_ado_push_error' ERR

# Derive PR title from branch name (strip feature/ or bugfix/ prefix)
PR_TITLE="${BRANCH#feature/}"
PR_TITLE="${PR_TITLE#bugfix/}"

echo "=== Five Points ADO Push ==="
echo "Issue:    #${ISSUE_NUMBER}"
echo "Branch:   ${BRANCH}"
echo "PR Title: ${PR_TITLE}"
echo "Target:   ${TARGET_BRANCH}"
echo "GH Repo:  ${GH_REPO}"
echo ""

# Handle --ask-pat: prompt for write PAT if not already available
if [[ "$ASK_PAT" == "true" ]]; then
    _ask_pat_value="${AZURE_DEVOPS_WRITE_PAT:-}"
    if [[ -z "$_ask_pat_value" ]]; then
        _config_env="$HOME/.config/claire/.env"
        if [[ -f "$_config_env" ]]; then
            _ask_pat_value=$(grep -E '^AZURE_DEVOPS_WRITE_PAT=' "$_config_env" 2>/dev/null | head -1 | cut -d= -f2- || true)
        fi
    fi
    if [[ -z "$_ask_pat_value" ]]; then
        read -r -s -p "Enter AZURE_DEVOPS_WRITE_PAT (not saved): " _ask_pat_value
        echo ""
        if [[ -z "$_ask_pat_value" ]]; then
            echo "ERROR: No write PAT provided" >&2
            exit 1
        fi
    fi
    export AZURE_DEVOPS_WRITE_PAT="$_ask_pat_value"
fi

# Step 1: Initialize ADO connection
# We need to be in the client repo (TFIOneGit) for ado_init to work
# Try to find the client repo path
ADO_PUSH_CURRENT_STEP="ADO init"
CLIENT_REPO_PATH="${FIVEPOINTS_REPO_PATH:-/Users/andreperez/TFIOneGit}"

if [[ ! -d "$CLIENT_REPO_PATH/.git" ]]; then
    echo "ERROR: Client repo not found at $CLIENT_REPO_PATH" >&2
    echo "Set FIVEPOINTS_REPO_PATH to the local clone of TFIOneGit" >&2
    exit 1
fi

# Initialize ADO from client repo
pushd "$CLIENT_REPO_PATH" > /dev/null
ado_init
popd > /dev/null

echo "ADO: ${_ADO_ORG}/${_ADO_PROJECT}/${_ADO_REPO}"
echo ""

# Step 2: Add ADO as remote (if not present)
# Use write-capable PAT for git push (WRITE_PAT > DEV_PAT > fallback to read PAT)
ADO_PUSH_CURRENT_STEP="add ADO remote"
_ADO_PUSH_PAT="${AZURE_DEVOPS_WRITE_PAT:-${AZURE_DEVOPS_DEV_PAT:-${AZURE_DEVOPS_PAT}}}"
if [[ -z "$_ADO_PUSH_PAT" ]]; then
    echo "ERROR: No ADO PAT available for git push. Set AZURE_DEVOPS_WRITE_PAT in ~/.config/claire/.env" >&2
    exit 1
fi
ADO_REMOTE_URL="https://${_ADO_PUSH_PAT}@dev.azure.com/${_ADO_ORG}/${_ADO_PROJECT}/_git/${_ADO_REPO}"

if ! git remote get-url ado &>/dev/null; then
    echo "Adding ADO remote..."
    git remote add ado "$ADO_REMOTE_URL"
else
    echo "ADO remote already configured"
    # Update URL in case PAT changed
    git remote set-url ado "$ADO_REMOTE_URL"
fi

# Step 3: Push branch to ADO
ADO_PUSH_CURRENT_STEP="git push to ADO"
echo "Pushing branch ${BRANCH} to ADO..."
git push ado "${BRANCH}:refs/heads/${BRANCH}" --force-with-lease

echo "✅ Branch pushed to ADO"
echo ""

# Step 4: Create PR via ADO REST API
ADO_PUSH_CURRENT_STEP="create ADO PR"
echo "Creating PR on ADO..."

PR_BODY=$(cat <<PR_EOF
## GitHub Issue
${GH_REPO}#${ISSUE_NUMBER}

## Branch
\`${BRANCH}\`

---
Created by C.L.A.I.R.E. pipeline
PR_EOF
)

PR_JSON=$(cat <<JSON_EOF
{
    "sourceRefName": "refs/heads/${BRANCH}",
    "targetRefName": "refs/heads/${TARGET_BRANCH}",
    "title": "${PR_TITLE}",
    "description": $(echo "$PR_BODY" | jq -Rs .)
}
JSON_EOF
)

PR_RESPONSE=$(ado_post "/git/repositories/${_ADO_REPO}/pullrequests?api-version=7.1" "$PR_JSON")

# Extract PR number from response
ADO_PR_NUMBER=$(echo "$PR_RESPONSE" | jq -r '.pullRequestId // empty' 2>/dev/null || echo "")

if [[ -z "$ADO_PR_NUMBER" ]]; then
    echo "ERROR: Failed to create ADO PR" >&2
    echo "Response: $PR_RESPONSE" >&2
    exit 1
fi

ADO_PR_URL="https://dev.azure.com/${_ADO_ORG}/${_ADO_PROJECT}/_git/${_ADO_REPO}/pullrequest/${ADO_PR_NUMBER}"

echo "✅ ADO PR created: #${ADO_PR_NUMBER}"
echo "   URL: ${ADO_PR_URL}"
echo ""

# Step 5: Post ADO PR link on GitHub issue
ADO_PUSH_CURRENT_STEP="post GitHub comment"
gh issue comment "$ISSUE_NUMBER" --repo "$GH_REPO" --body "**ADO PR created:** [PR #${ADO_PR_NUMBER}](${ADO_PR_URL})

Branch \`${BRANCH}\` → \`${TARGET_BRANCH}\`

Waiting for Steven's review on ADO."

# Step 6: Change label to role:ado-review
ADO_PUSH_CURRENT_STEP="update GitHub label"
CURRENT_LABELS=$(gh issue view "$ISSUE_NUMBER" --repo "$GH_REPO" --json labels --jq '[.labels[].name | select(startswith("role:"))] | join(",")')
if [[ -n "$CURRENT_LABELS" ]]; then
    IFS=',' read -ra LABEL_ARRAY <<< "$CURRENT_LABELS"
    for label in "${LABEL_ARRAY[@]}"; do
        gh issue edit "$ISSUE_NUMBER" --repo "$GH_REPO" --remove-label "$label" 2>/dev/null || true
    done
fi
gh label create "role:ado-review" --repo "$GH_REPO" --color "D93F0B" --description "Pipeline: waiting for ADO review" 2>/dev/null || true
gh issue edit "$ISSUE_NUMBER" --repo "$GH_REPO" --add-label "role:ado-review"

echo "Label changed to role:ado-review"
echo ""

# Step 7: Start ADO watch (blocks until merge/abandon)
ADO_PUSH_CURRENT_STEP="ado-watch"
echo "Starting ADO PR watch..."
echo "Monitoring PR #${ADO_PR_NUMBER} for comments, votes, and merge..."
echo ""

# Run ado-watch — it exits when the PR is merged or abandoned
claire fivepoints ado-watch --pr "$ADO_PR_NUMBER"

# Step 8: If we get here, the PR was merged or abandoned
# Check final PR status
PR_STATUS=$(ado_get "/git/repositories/${_ADO_REPO}/pullrequests/${ADO_PR_NUMBER}?api-version=7.1" | jq -r '.status // "unknown"' 2>/dev/null || echo "unknown")

if [[ "$PR_STATUS" == "completed" ]]; then
    echo ""
    echo "✅ ADO PR #${ADO_PR_NUMBER} merged!"
    echo "Closing GitHub issue #${ISSUE_NUMBER}..."

    gh issue comment "$ISSUE_NUMBER" --repo "$GH_REPO" --body "**Pipeline complete.** ADO PR [#${ADO_PR_NUMBER}](${ADO_PR_URL}) merged.

Closing this issue."

    gh issue close "$ISSUE_NUMBER" --repo "$GH_REPO"
    echo "✅ Issue #${ISSUE_NUMBER} closed."
else
    echo ""
    echo "⚠️  ADO PR #${ADO_PR_NUMBER} ended with status: ${PR_STATUS}"
    echo "Manual intervention may be needed."

    gh issue comment "$ISSUE_NUMBER" --repo "$GH_REPO" --body "**ADO PR #${ADO_PR_NUMBER} ended with status: \`${PR_STATUS}\`**

Manual review needed."
fi
