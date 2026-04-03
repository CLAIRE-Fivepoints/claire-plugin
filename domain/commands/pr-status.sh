#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$PLUGIN_ROOT/domain/scripts/ado_common.sh"

PR_NUMBER="${1:-}"

if [[ -z "$PR_NUMBER" ]]; then
    echo "Usage: claire fivepoints pr-status <PR_NUMBER>"
    exit 1
fi

ado_init

# Fetch PR details
PR_RESPONSE=$(ado_get "/git/repositories/${_ADO_REPO}/pullrequests/${PR_NUMBER}?api-version=7.1")

if ! echo "$PR_RESPONSE" | jq -e '.pullRequestId' &>/dev/null; then
    echo "ERROR: PR #${PR_NUMBER} not found" >&2
    exit 1
fi

echo "=== PR #${PR_NUMBER} ==="
echo ""

# Basic info
TITLE=$(echo "$PR_RESPONSE" | jq -r '.title')
STATUS=$(echo "$PR_RESPONSE" | jq -r '.status')
CREATED_BY=$(echo "$PR_RESPONSE" | jq -r '.createdBy.displayName')
SOURCE=$(echo "$PR_RESPONSE" | jq -r '.sourceRefName' | sed 's|refs/heads/||')
TARGET=$(echo "$PR_RESPONSE" | jq -r '.targetRefName' | sed 's|refs/heads/||')
MERGE_STATUS=$(echo "$PR_RESPONSE" | jq -r '.mergeStatus // "unknown"')

echo "Title:   $TITLE"
echo "Status:  $STATUS"
echo "Author:  $CREATED_BY"
echo "Branch:  $SOURCE -> $TARGET"
echo "Merge:   $MERGE_STATUS"
echo ""

# Reviewers
echo "=== Reviewers ==="
REVIEWERS=$(echo "$PR_RESPONSE" | jq -r '.reviewers // [] | .[] | "\(.displayName): \(
    if .vote == 10 then "Approved"
    elif .vote == 5 then "Approved with suggestions"
    elif .vote == -5 then "Waiting for author"
    elif .vote == -10 then "Rejected"
    else "No vote"
    end
)"')

if [[ -n "$REVIEWERS" ]]; then
    echo "$REVIEWERS"
else
    echo "(no reviewers)"
fi
echo ""

# Build/pipeline statuses
echo "=== Build Status ==="
STATUS_RESPONSE=$(ado_get "/git/repositories/${_ADO_REPO}/pullRequests/${PR_NUMBER}/statuses?api-version=7.1")

STATUSES=$(echo "$STATUS_RESPONSE" | jq -r '.value // [] | .[] | "\(.state) | \(.context.name // "unknown") | \(.description // "")"')

if [[ -n "$STATUSES" ]]; then
    echo "$STATUSES"
else
    echo "(no build statuses)"
fi
