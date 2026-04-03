#!/usr/bin/env bash
set -euo pipefail

# fivepoints reset-pipeline — Reset all pipeline issues to clean backlog state
#
# Usage:
#   claire fivepoints reset-pipeline [--repo owner/name]
#
# What it does:
#   1. Finds all open issues with role:* labels in the repo
#   2. Removes assignee (myclaire-ai) and role:* labels from each issue
#   2b. Closes ALL open issues (so next azure-issue-bridge run starts fresh)
#   3. Moves each issue back to "Todo" in the GitHub Project
#   4. Removes associated worktrees (in claire-reboot and the target repo)
#   5. Removes role branches from the target repo (if cloned locally)
#
# For now: designed for fivepoints-test backlog.
# Default repo: $CLAIRE_WAIT_REPO or claire-labs/fivepoints-test

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Navigate 5 levels up from commands/ to claire-reboot root
CLAIRE_HOME="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

REPO="${CLAIRE_WAIT_REPO:-claire-labs/fivepoints-test}"
DRY_RUN=false

show_help() {
    echo "Usage: claire fivepoints reset-pipeline [--repo owner/name] [--dry-run]"
    echo ""
    echo "Reset all pipeline issues to clean backlog state."
    echo ""
    echo "Options:"
    echo "  --repo <owner/name>  Target repo (default: \$CLAIRE_WAIT_REPO or claire-labs/fivepoints-test)"
    echo "  --dry-run            Show what would be done without executing"
    echo ""
    echo "What it does:"
    echo "  1. Finds open issues with role:* labels"
    echo "  2. Removes assignees + role labels"
    echo "  2b. Closes ALL open issues (clean slate for next bridge run)"
    echo "  3. Moves issues back to Todo in GitHub Project"
    echo "  4. Cleans worktrees (claire-reboot + local repo)"
    echo "  5. Removes role branches from local repo clone"
}

show_agent_help() {
    cat <<'AGENT_HELP'
# fivepoints reset-pipeline — Agent Help

## Purpose
Reset the fivepoints-test pipeline to a clean state before an E2E test run.
Call this between test runs to avoid stale state contamination.

## Usage
```bash
claire fivepoints reset-pipeline --repo claire-labs/fivepoints-test
```

## What it resets
1. All open issues with `role:*` labels → remove label + unassign myclaire-ai
2. Close ALL open issues (so next azure-issue-bridge run recreates them fresh)
3. GitHub Project: move issues back to "Todo" column
4. Worktrees: remove in claire-reboot AND fivepoints-test/.claire/worktrees/
5. Branches: remove local `issue-N` branches from the repo clone

## After running
Run `claire product-owner run --repo claire-labs/fivepoints-test` to restart the pipeline.

## Important
- Requires PO_GITHUB_TOKEN with project write access (read from product-owner.env or ~/.env)
- Repo must be locally cloned under ~/projects/<repo-name>
AGENT_HELP
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --repo)
            REPO="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
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

# Load PO_GITHUB_TOKEN
PO_GITHUB_TOKEN=""
for env_file in ~/.config/claire/product-owner.env ~/.env; do
    if [[ -f "$env_file" ]]; then
        val=$(grep "^PO_GITHUB_TOKEN=" "$env_file" 2>/dev/null | cut -d= -f2 || true)
        if [[ -n "$val" ]]; then
            PO_GITHUB_TOKEN="$val"
            break
        fi
    fi
done

if [[ -z "$PO_GITHUB_TOKEN" ]]; then
    echo "ERROR: PO_GITHUB_TOKEN not found in ~/.config/claire/product-owner.env or ~/.env" >&2
    exit 1
fi

REPO_NAME="${REPO##*/}"

# Detect local clone path
LOCAL_CLONE=""
for candidate in \
    "$HOME/projects/${REPO_NAME}" \
    "$HOME/${REPO_NAME}"; do
    if [[ -d "$candidate/.git" ]] || [[ -f "$candidate/.git" ]]; then
        LOCAL_CLONE="$candidate"
        break
    fi
done

echo "=== fivepoints reset-pipeline ==="
echo "Repo: $REPO"
echo "Local clone: ${LOCAL_CLONE:-not found}"
[[ "$DRY_RUN" == "true" ]] && echo "DRY RUN — no changes will be made"
echo ""

# ── Step 1: Find all open issues with role:* labels ────────────────────────────

echo "── Step 1: Find open issues with role:* labels"

ISSUE_NUMBERS=$(gh issue list \
    --repo "$REPO" \
    --state open \
    --json number,labels \
    --jq '[.[] | select(.labels[].name | startswith("role:")) | .number] | unique[]' \
    2>/dev/null)

if [[ -z "$ISSUE_NUMBERS" ]]; then
    echo "  No open issues with role:* labels found."
else
    echo "  Found issues: $(echo "$ISSUE_NUMBERS" | tr '\n' ' ')"
fi

# ── Step 2: Remove assignees + role labels ──────────────────────────────────────

echo ""
echo "── Step 2: Remove assignees + role:* labels"

for issue_num in $ISSUE_NUMBERS; do
    echo "  Issue #${issue_num}:"

    # Get current role labels
    role_labels=$(gh issue view "$issue_num" --repo "$REPO" \
        --json labels \
        --jq '[.labels[].name | select(startswith("role:"))] | join(",")' 2>/dev/null || true)

    if [[ -n "$role_labels" ]]; then
        echo "    Removing labels: $role_labels"
        if [[ "$DRY_RUN" != "true" ]]; then
            IFS=',' read -ra label_arr <<< "$role_labels"
            for lbl in "${label_arr[@]}"; do
                gh issue edit "$issue_num" --repo "$REPO" --remove-label "$lbl" 2>/dev/null || true
            done
        fi
    fi

    echo "    Removing assignee: myclaire-ai"
    if [[ "$DRY_RUN" != "true" ]]; then
        gh issue edit "$issue_num" --repo "$REPO" --remove-assignee myclaire-ai 2>/dev/null || true
    fi
done

# ── Step 2b: Close all open issues ─────────────────────────────────────────────

echo ""
echo "── Step 2b: Close all open issues"

ALL_OPEN_ISSUES=$(gh issue list \
    --repo "$REPO" \
    --state open \
    --json number \
    --jq '.[].number' \
    2>/dev/null)

if [[ -z "$ALL_OPEN_ISSUES" ]]; then
    echo "  No open issues to close."
else
    echo "  Closing: $(echo "$ALL_OPEN_ISSUES" | tr '\n' ' ')"
    for issue_num in $ALL_OPEN_ISSUES; do
        echo "  Closing issue #${issue_num}"
        if [[ "$DRY_RUN" != "true" ]]; then
            gh issue close "$issue_num" --repo "$REPO" \
                --comment "Closed by reset-pipeline for E2E test reset." \
                2>/dev/null || true
        fi
    done
fi

# ── Step 3: Move issues back to Todo in GitHub Project ─────────────────────────

echo ""
echo "── Step 3: Move issues to 'Todo' in GitHub Project"

# Find the project for this repo
PROJECT_INFO=$(GITHUB_TOKEN="$PO_GITHUB_TOKEN" gh api graphql -f query='
{
  organization(login: "claire-labs") {
    projectsV2(first: 20) {
      nodes { id number title }
    }
  }
}' --jq ".data.organization.projectsV2.nodes[] | select(.title | ascii_downcase | contains(\"${REPO_NAME}\")) | {id: .id, number: .number, title: .title}" 2>/dev/null | head -1)

if [[ -z "$PROJECT_INFO" ]]; then
    echo "  WARNING: Could not find GitHub Project for $REPO — skipping project reset"
else
    PROJECT_ID=$(echo "$PROJECT_INFO" | jq -r '.id')
    PROJECT_NUM=$(echo "$PROJECT_INFO" | jq -r '.number')
    PROJECT_TITLE=$(echo "$PROJECT_INFO" | jq -r '.title')
    echo "  Found: $PROJECT_TITLE (project #${PROJECT_NUM})"

    # Get Status field ID and Todo option ID
    FIELD_INFO=$(GITHUB_TOKEN="$PO_GITHUB_TOKEN" gh api graphql -f query="
    {
      node(id: \"$PROJECT_ID\") {
        ... on ProjectV2 {
          fields(first: 20) {
            nodes {
              ... on ProjectV2SingleSelectField {
                id name
                options { id name }
              }
            }
          }
        }
      }
    }" --jq '.data.node.fields.nodes[] | select(.name == "Status")' 2>/dev/null)

    STATUS_FIELD_ID=$(echo "$FIELD_INFO" | jq -r '.id')
    TODO_OPTION_ID=$(echo "$FIELD_INFO" | jq -r '.options[] | select(.name == "Todo") | .id')

    echo "  Status field: $STATUS_FIELD_ID | Todo option: $TODO_OPTION_ID"

    # Get all project items
    PROJECT_ITEMS=$(GITHUB_TOKEN="$PO_GITHUB_TOKEN" gh api graphql -f query="
    {
      node(id: \"$PROJECT_ID\") {
        ... on ProjectV2 {
          items(first: 50) {
            nodes {
              id
              content { ... on Issue { number } }
              fieldValues(first: 10) {
                nodes {
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name field { ... on ProjectV2SingleSelectField { name } }
                  }
                }
              }
            }
          }
        }
      }
    }" 2>/dev/null)

    # Move each issue in our list back to Todo
    for issue_num in $ISSUE_NUMBERS; do
        item_id=$(echo "$PROJECT_ITEMS" | \
            jq -r --argjson n "$issue_num" \
            '.data.node.items.nodes[] | select(.content.number == $n) | .id' \
            2>/dev/null || true)

        if [[ -n "$item_id" ]]; then
            echo "  Issue #${issue_num}: moving to Todo (item $item_id)"
            if [[ "$DRY_RUN" != "true" ]]; then
                GITHUB_TOKEN="$PO_GITHUB_TOKEN" gh api graphql -f query="
mutation {
  updateProjectV2ItemFieldValue(input: {
    projectId: \"$PROJECT_ID\",
    itemId: \"$item_id\",
    fieldId: \"$STATUS_FIELD_ID\",
    value: { singleSelectOptionId: \"$TODO_OPTION_ID\" }
  }) { projectV2Item { id } }
}" > /dev/null 2>&1
            fi
        else
            echo "  Issue #${issue_num}: not found in project — skipping"
        fi
    done
fi

# ── Step 4: Clean worktrees ─────────────────────────────────────────────────────

echo ""
echo "── Step 4: Clean worktrees"

for issue_num in $ISSUE_NUMBERS; do
    # Check claire-reboot worktrees
    claire_worktree=$(find "${CLAIRE_HOME}/.claire/worktrees" -maxdepth 1 -name "issue-${issue_num}-*" -type d 2>/dev/null | head -1)
    if [[ -n "$claire_worktree" ]]; then
        echo "  Removing claire-reboot worktree: $claire_worktree"
        if [[ "$DRY_RUN" != "true" ]]; then
            git -C "$CLAIRE_HOME" worktree remove "$claire_worktree" --force 2>/dev/null || \
                rm -rf "$claire_worktree"
        fi
    fi

    # Check local repo worktrees
    if [[ -n "$LOCAL_CLONE" ]]; then
        local_worktree=$(find "${LOCAL_CLONE}/.claire/worktrees" -maxdepth 1 -name "issue-${issue_num}-*" -type d 2>/dev/null | head -1)
        if [[ -n "$local_worktree" ]]; then
            echo "  Removing local repo worktree: $local_worktree"
            if [[ "$DRY_RUN" != "true" ]]; then
                git -C "$LOCAL_CLONE" worktree remove "$local_worktree" --force 2>/dev/null || \
                    rm -rf "$local_worktree"
            fi
        fi
    fi
done

# ── Step 5: Remove role branches from local repo ───────────────────────────────

echo ""
echo "── Step 5: Remove local branches"

if [[ -n "$LOCAL_CLONE" ]]; then
    for issue_num in $ISSUE_NUMBERS; do
        branch="issue-${issue_num}"
        if git -C "$LOCAL_CLONE" branch --list "$branch" | grep -q "$branch" 2>/dev/null; then
            echo "  Removing branch: $branch"
            if [[ "$DRY_RUN" != "true" ]]; then
                git -C "$LOCAL_CLONE" branch -D "$branch" 2>/dev/null || true
            fi
        fi
    done
else
    echo "  Local clone not found — skipping branch cleanup"
fi

# ── Done ────────────────────────────────────────────────────────────────────────

echo ""
echo "=== Reset complete ==="
echo ""
echo "Next step: claire product-owner run --repo $REPO"
