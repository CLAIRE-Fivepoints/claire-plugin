#!/usr/bin/env bash
set -euo pipefail

# fivepoints transition — Change role label and reopen session for next role
#
# Usage:
#   claire fivepoints transition --role <current_role> --issue <N>
#   claire fivepoints transition --role <current_role> --next <override_role> --issue <N>
#
# IMPORTANT: --role takes YOUR CURRENT role (not the next one).
# The next role is computed automatically from the transition map:
#   analyst → dev
#   dev     → tester
#   tester  → ado-review
#
# Use --next to override (e.g. tester failure looping back to dev):
#   claire fivepoints transition --role tester --next dev --issue N
#
# After this script, the caller should run: claire stop

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse arguments
CURRENT_ROLE=""
NEXT_ROLE_OVERRIDE=""
ISSUE_NUMBER=""

show_help() {
    echo "Usage: claire fivepoints transition --role <current_role> --issue <N>"
    echo ""
    echo "Transition a Five Points issue from your current role to the next."
    echo ""
    echo "Options:"
    echo "  --role <role>    YOUR current role: analyst, dev, tester"
    echo "  --next <role>    Override the next role (optional)"
    echo "  --issue <N>      GitHub issue number"
    echo ""
    echo "Transition map (automatic):"
    echo "  analyst → dev"
    echo "  dev     → tester"
    echo "  tester  → ado-review"
    echo ""
    echo "Tester failure (override):"
    echo "  claire fivepoints transition --role tester --next dev --issue N"
    echo ""
    echo "After running this command, execute: claire stop"
}

show_agent_help() {
    cat <<'AGENT_HELP'
# fivepoints transition — Agent Help

## Purpose
Transition a Five Points pipeline issue from YOUR current role to the next.
The next role is computed automatically — you just say who you are.

## Usage
```bash
# Analyst finishing analysis:
claire fivepoints transition --role analyst --issue 123

# Dev finishing implementation:
claire fivepoints transition --role dev --issue 123

# Tester finishing tests (passed → ado-review):
claire fivepoints transition --role tester --issue 123

# Tester on failure (loop back to dev):
claire fivepoints transition --role tester --next dev --issue 123
```

## Transition map (automatic)
- analyst → dev
- dev → tester
- tester → ado-review (default)
- tester → dev (failure, use --next dev)

## What it does
1. Verifies the issue label matches your --role (prevents calling from wrong role)
2. Computes the next role (or uses --next override)
3. Removes current label, adds role:<next_role>
4. Runs `claire reopen --issue N` to open new terminal for next role

## After running
Execute `claire stop` to close the current session.
The new session (next role) is already starting in a new terminal.

## Pre-transition guard (analyst → dev)
Before transitioning from analyst to dev, the command verifies that:
- The issue has a comment referencing a `feature/...` branch name
- The branch exists on the github remote (fivepoints-test)

If the check fails, the transition is blocked with an actionable error message.
The analyst must create the branch, push it, and write specs (including branch name) to the issue before retrying.

## Pre-transition guard (dev → tester)
Before transitioning from dev to tester, the command verifies that:
- The issue has a comment containing a GitHub PR URL
- That PR has `reviewDecision: APPROVED`

If the check fails, the transition is blocked with an actionable error message.
The dev must wait for the PR to be approved before retrying.

## Important
- --role = YOUR current role (not the next one)
- This command must be called BEFORE `claire stop`
- The new terminal starts while the old one is still alive (no gap)
- Do NOT call this without completing your role's checklist first
AGENT_HELP
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --role)
            CURRENT_ROLE="$2"
            shift 2
            ;;
        --next)
            NEXT_ROLE_OVERRIDE="$2"
            shift 2
            ;;
        --issue)
            ISSUE_NUMBER="$2"
            shift 2
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

# Validate arguments
if [[ -z "$CURRENT_ROLE" || -z "$ISSUE_NUMBER" ]]; then
    echo "ERROR: --role and --issue are required" >&2
    show_help
    exit 1
fi

# Validate current role
VALID_ROLES="analyst dev tester"
if ! echo "$VALID_ROLES" | grep -qw "$CURRENT_ROLE"; then
    echo "ERROR: Invalid role '$CURRENT_ROLE'. Valid: $VALID_ROLES" >&2
    exit 1
fi

# Compute next role from transition map (or use override)
if [[ -n "$NEXT_ROLE_OVERRIDE" ]]; then
    NEXT_ROLE="$NEXT_ROLE_OVERRIDE"
else
    case "$CURRENT_ROLE" in
        analyst)  NEXT_ROLE="dev" ;;
        dev)      NEXT_ROLE="tester" ;;
        tester)   NEXT_ROLE="ado-review" ;;
    esac
fi

# Detect repo from CLAIRE_WAIT_REPO or auto-detect from git remote, falling back to fivepoints-test
if [[ -n "${CLAIRE_WAIT_REPO:-}" ]]; then
    REPO="$CLAIRE_WAIT_REPO"
else
    _git_remote_url=$(git remote get-url origin 2>/dev/null || true)
    if [[ "$_git_remote_url" =~ github\.com[:/]([^/]+/[^/.]+)(\.git)?$ ]]; then
        REPO="${BASH_REMATCH[1]}"
    else
        REPO="CLAIRE-Fivepoints/fivepoints-test"
    fi
fi

echo "Transitioning issue #${ISSUE_NUMBER}: role:${CURRENT_ROLE} → role:${NEXT_ROLE}..."

# Step 1: Read current role:* labels from GitHub and verify they match
CURRENT_LABELS=$(gh issue view "$ISSUE_NUMBER" --repo "$REPO" --json labels --jq '[.labels[].name | select(startswith("role:"))] | join(",")')

# Guard: verify the issue's actual label matches --role (prevents calling from wrong role)
if [[ -n "$CURRENT_LABELS" && "$CURRENT_LABELS" != "role:${CURRENT_ROLE}" ]]; then
    echo "" >&2
    echo "ERROR: Role mismatch — issue is labeled '${CURRENT_LABELS}' but you passed --role ${CURRENT_ROLE}." >&2
    echo "" >&2
    echo "You can only transition from your own current role." >&2
    echo "  Issue label: ${CURRENT_LABELS}" >&2
    echo "  Your --role: role:${CURRENT_ROLE}" >&2
    echo "" >&2
    echo "If you are the ${CURRENT_LABELS#role:}, run:" >&2
    echo "  claire fivepoints transition --role ${CURRENT_LABELS#role:} --issue $ISSUE_NUMBER" >&2
    exit 1
fi

# Pre-transition guard: analyst → dev requires feature branch referenced in issue
if [[ "$CURRENT_ROLE" == "analyst" ]]; then
    echo "  Checking analyst handoff requirements..."

    # Check: feature branch name referenced in issue comments
    BRANCH_IN_COMMENTS=$(gh issue view "$ISSUE_NUMBER" --repo "$REPO" --json comments \
        --jq '[.comments[].body] | join("\n")' | grep -oE 'feature/[a-zA-Z0-9_/.-]+' | head -1 || true)

    if [[ -z "$BRANCH_IN_COMMENTS" ]]; then
        echo "" >&2
        echo "ERROR: Analyst handoff blocked — feature branch not found in issue comments." >&2
        echo "" >&2
        echo "The analyst must:" >&2
        echo "  1. Create the branch:  git checkout -b feature/{ticket-id}-{desc}" >&2
        echo "                         git push -u github feature/{ticket-id}-{desc}" >&2
        echo "  2. Write specs to the issue (comment must include the branch name)" >&2
        echo "" >&2
        echo "Then re-run: claire fivepoints transition --role analyst --issue $ISSUE_NUMBER" >&2
        exit 1
    fi

    echo "  ✅ Feature branch referenced in issue: $BRANCH_IN_COMMENTS"

    # Check: feature branch exists on the github remote (fivepoints-test)
    TFIONE_REPO="${FIVEPOINTS_REPO_PATH:-$HOME/TFIOneGit}"
    if [[ -d "$TFIONE_REPO" ]]; then
        BRANCH_ON_REMOTE=$(git -C "$TFIONE_REPO" ls-remote github "refs/heads/$BRANCH_IN_COMMENTS" 2>/dev/null | head -1 || true)
        if [[ -z "$BRANCH_ON_REMOTE" ]]; then
            echo "" >&2
            echo "ERROR: Analyst handoff blocked — branch not pushed to fivepoints-test (GitHub)." >&2
            echo "" >&2
            echo "Branch '$BRANCH_IN_COMMENTS' exists in issue comment but is NOT on the github remote." >&2
            echo "" >&2
            echo "The analyst must push the branch:" >&2
            echo "  cd $TFIONE_REPO" >&2
            echo "  git push -u github $BRANCH_IN_COMMENTS" >&2
            echo "" >&2
            echo "Then re-run: claire fivepoints transition --role analyst --issue $ISSUE_NUMBER" >&2
            exit 1
        fi
        echo "  ✅ Feature branch verified on github remote: $BRANCH_IN_COMMENTS"
    else
        echo "  ⚠️  TFIOneGit not found at $TFIONE_REPO — skipping remote branch check"
    fi
fi

# Pre-transition guard: dev → tester requires an approved GitHub PR
if [[ "$CURRENT_ROLE" == "dev" && "$NEXT_ROLE" == "tester" ]]; then
    echo "  Checking dev handoff requirements..."

    # Find the linked PR URL in issue body and comments
    LINKED_PR=$(gh issue view "$ISSUE_NUMBER" --repo "$REPO" --json body,comments \
        --jq '[.body, (.comments[].body)] | join("\n")' \
        | grep -oE 'https://github\.com/[^/]+/[^/]+/pull/[0-9]+' | head -1 || true)

    # Fallback: search via GitHub API for a PR with a branch starting with issue-N in the issue tracking repo
    if [[ -z "$LINKED_PR" || "$LINKED_PR" == "null" ]]; then
        LINKED_PR=$(gh pr list \
            --repo "$REPO" \
            --state open \
            --json url,headRefName \
            --jq "[.[] | select(.headRefName | startswith(\"issue-${ISSUE_NUMBER}-\")) | .url] | .[0]" \
            2>/dev/null | tr -d '"' || true)
        if [[ -n "$LINKED_PR" && "$LINKED_PR" != "null" ]]; then
            echo "  Found PR via API in ${REPO}: $LINKED_PR"
        fi
    fi

    # Fallback: search in the fivepoints-test code review repo
    if [[ -z "$LINKED_PR" || "$LINKED_PR" == "null" ]]; then
        REVIEW_REPO="${FIVEPOINTS_REVIEW_REPO:-CLAIRE-Fivepoints/fivepoints-test}"
        if [[ "$REVIEW_REPO" != "$REPO" ]]; then
            LINKED_PR=$(gh pr list \
                --repo "$REVIEW_REPO" \
                --state open \
                --json url,headRefName \
                --jq "[.[] | select(.headRefName | startswith(\"issue-${ISSUE_NUMBER}-\")) | .url] | .[0]" \
                2>/dev/null | tr -d '"' || true)
            if [[ -n "$LINKED_PR" && "$LINKED_PR" != "null" ]]; then
                echo "  Found PR via API in ${REVIEW_REPO}: $LINKED_PR"
            fi
        fi
    fi

    if [[ -z "$LINKED_PR" || "$LINKED_PR" == "null" ]]; then
        echo "" >&2
        echo "ERROR: Dev handoff blocked — no GitHub PR URL found in issue #${ISSUE_NUMBER}." >&2
        echo "" >&2
        echo "The dev must:" >&2
        echo "  1. Create a PR for the feature branch" >&2
        echo "  2. Post the PR URL in a comment on issue #${ISSUE_NUMBER}" >&2
        echo "     (or set FIVEPOINTS_REVIEW_REPO=<owner/repo> if using a non-default code repo)" >&2
        echo "" >&2
        echo "Then re-run: claire fivepoints transition --role dev --issue $ISSUE_NUMBER" >&2
        exit 1
    fi

    PR_NUMBER=$(echo "$LINKED_PR" | grep -oE '[0-9]+$')
    PR_REPO=$(echo "$LINKED_PR" | grep -oE 'github\.com/[^/]+/[^/]+' | sed 's|github\.com/||')

    echo "  Found linked PR: #${PR_NUMBER} in ${PR_REPO}"

    REVIEW_DECISION=$(gh pr view "$PR_NUMBER" --repo "$PR_REPO" --json reviewDecision --jq '.reviewDecision' 2>/dev/null || true)

    if [[ "$REVIEW_DECISION" != "APPROVED" ]]; then
        echo "" >&2
        echo "ERROR: Dev handoff blocked — PR #${PR_NUMBER} is not approved." >&2
        echo "  reviewDecision: ${REVIEW_DECISION:-empty}" >&2
        echo "" >&2
        echo "The PR must be approved before transitioning to tester." >&2
        echo "  PR: $LINKED_PR" >&2
        echo "" >&2
        echo "Then re-run: claire fivepoints transition --role dev --issue $ISSUE_NUMBER" >&2
        exit 1
    fi

    echo "  ✅ PR #${PR_NUMBER} is approved (reviewDecision: $REVIEW_DECISION)"
fi

# Pre-transition guard: tester → ado-review requires AZURE_DEVOPS PAT in env
if [[ "$CURRENT_ROLE" == "tester" && "$NEXT_ROLE" == "ado-review" ]]; then
    echo "  Checking tester handoff requirements (PAT gate)..."

    PAT_VALUE="${AZURE_DEVOPS_WRITE_PAT:-}"

    if [[ -z "$PAT_VALUE" ]]; then
        echo "" >&2
        echo "ERROR: Tester handoff blocked — AZURE_DEVOPS_WRITE_PAT not set in env." >&2
        echo "" >&2
        echo "AZURE_DEVOPS_WRITE_PAT is required to push to ADO." >&2
        echo "(AZURE_DEVOPS_PAT is read-only and cannot be used for pushing.)" >&2
        echo "" >&2
        echo "To unblock:" >&2
        echo "  1. The tester must post proof on issue #${ISSUE_NUMBER} first (if not already done)" >&2
        echo "  2. Ask the user to provide the write PAT:" >&2
        echo "       export AZURE_DEVOPS_WRITE_PAT=<your-write-pat>" >&2
        echo "  3. Re-run: claire fivepoints transition --role tester --issue $ISSUE_NUMBER" >&2
        exit 1
    fi

    echo "  ✅ AZURE_DEVOPS_WRITE_PAT is set"
fi

# Step 2: Remove current role labels
if [[ -n "$CURRENT_LABELS" ]]; then
    IFS=',' read -ra LABEL_ARRAY <<< "$CURRENT_LABELS"
    for label in "${LABEL_ARRAY[@]}"; do
        echo "  Removing label: $label"
        gh issue edit "$ISSUE_NUMBER" --repo "$REPO" --remove-label "$label" 2>/dev/null || true
    done
fi

# Step 3: Add new role label (create if needed)
echo "  Adding label: role:${NEXT_ROLE}"
gh label create "role:${NEXT_ROLE}" --repo "$REPO" --color "0E8A16" --description "Pipeline role: ${NEXT_ROLE}" 2>/dev/null || true
gh issue edit "$ISSUE_NUMBER" --repo "$REPO" --add-label "role:${NEXT_ROLE}"

# Step 4: Post transition comment
gh issue comment "$ISSUE_NUMBER" --repo "$REPO" --body "**Pipeline transition:** \`role:${CURRENT_ROLE}\` → \`role:${NEXT_ROLE}\`"

# Step 5: Load role-specific credentials before opening session
if [[ "$NEXT_ROLE" == "tester" ]]; then
    echo "  Loading qa-claire-ai credentials for tester session..."
    GITHUB_MANAGER_ENV="$HOME/.config/claire/github_manager.env"
    if [[ -f "$GITHUB_MANAGER_ENV" ]]; then
        QA_GITHUB_TOKEN=$(grep -E '^QA_GITHUB_TOKEN=' "$GITHUB_MANAGER_ENV" | head -1 | cut -d'=' -f2- | tr -d '"' || true)
        if [[ -n "$QA_GITHUB_TOKEN" ]]; then
            export GITHUB_TOKEN="$QA_GITHUB_TOKEN"
            export GH_TOKEN="$QA_GITHUB_TOKEN"
            echo "  ✅ qa-claire-ai credentials loaded"
        else
            echo "  WARNING: QA_GITHUB_TOKEN not found in $GITHUB_MANAGER_ENV" >&2
        fi
    else
        echo "  WARNING: $GITHUB_MANAGER_ENV not found — tester will use dev credentials" >&2
    fi
fi

# Step 6: Regenerate CLAUDE.md for the new role
# The label has been updated, so claire boot will detect the new pipeline role
# and use the lean fivepoints-pipeline template
WORKTREE_PATH=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
echo "  Regenerating CLAUDE.md for role:${NEXT_ROLE}..."
if python3 -m claire_py.template.cli generate \
    --issue "$ISSUE_NUMBER" \
    --output "${WORKTREE_PATH}/CLAUDE.md" \
    --format claude-code 2>/dev/null; then
    echo "  ✅ CLAUDE.md regenerated for role:${NEXT_ROLE}"
else
    echo "  ⚠️  CLAUDE.md regeneration failed — claire boot will regenerate on session start" >&2
fi

# Step 7: Reopen session (new terminal in same worktree)
echo "  Opening new session for role:${NEXT_ROLE}..."
claire reopen --issue "$ISSUE_NUMBER"

echo ""
echo "✅ Transition complete: role:${CURRENT_ROLE} → role:${NEXT_ROLE}"
echo "   Now run: claire stop"
