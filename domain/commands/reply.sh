#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$PLUGIN_ROOT/domain/scripts/ado_common.sh"

# Parse arguments
PR_NUMBER=""
THREAD_ID=""
MESSAGE=""
APPROVE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --pr)
            PR_NUMBER="$2"
            shift 2
            ;;
        --approve)
            APPROVE=true
            shift
            ;;
        --thread)
            THREAD_ID="$2"
            shift 2
            ;;
        --agent-help)
            cat <<'HELP'
# fivepoints reply — LLM Agent Guide

## Modes

### Reply to a thread
```bash
claire fivepoints reply --pr <N> --thread <ID> "message"
```
Reply to a specific comment thread on an Azure DevOps PR.

### Approve a PR
```bash
claire fivepoints reply --approve --pr <N>
```
Cast an "Approved" vote on the PR using the current authenticated user's identity.
Calls the Azure DevOps Reviewers API (vote=10).

## Arguments
- `--pr <N>`      PR number (required for both modes)
- `--thread <ID>` Thread ID to reply to (required for reply mode)
- `--approve`     Vote approve instead of posting a reply
- `"message"`     Reply text (ASCII only, no emoji)

## Notes
- Requires AZURE_DEVOPS_PAT (auto-discovered from git remote or ~/.config/claire/.env)
- --approve uses the authenticated user identity from connectionData API
HELP
            exit 0
            ;;
        *)
            MESSAGE="$1"
            shift
            ;;
    esac
done

# --- Approve mode ---
if [[ "$APPROVE" == "true" ]]; then
    if [[ -z "$PR_NUMBER" ]]; then
        echo "Usage: claire fivepoints reply --approve --pr <N>"
        exit 1
    fi

    ado_init

    REVIEWER_ID=$(ado_get_current_user_id)
    if [[ -z "$REVIEWER_ID" ]]; then
        echo "ERROR: Could not determine current user ID from Azure DevOps" >&2
        exit 1
    fi

    # vote=10 means Approved in Azure DevOps reviewer vote API
    VOTE_PAYLOAD=$(jq -n '{"vote": 10, "isRequired": false}')
    RESPONSE=$(ado_put "/git/repositories/${_ADO_REPO}/pullRequests/${PR_NUMBER}/reviewers/${REVIEWER_ID}?api-version=7.1" "$VOTE_PAYLOAD")

    if echo "$RESPONSE" | jq -e '.vote' &>/dev/null; then
        VOTE=$(echo "$RESPONSE" | jq -r '.vote')
        echo "PR #${PR_NUMBER} approved on Azure DevOps (vote: ${VOTE})"
    else
        ERROR=$(echo "$RESPONSE" | jq -r '.message // "Unknown error"')
        echo "ERROR: Failed to approve PR: $ERROR" >&2
        exit 1
    fi
    exit 0
fi

# --- Reply mode ---
if [[ -z "$PR_NUMBER" ]] || [[ -z "$THREAD_ID" ]] || [[ -z "$MESSAGE" ]]; then
    echo "Usage: claire fivepoints reply --pr <N> --thread <ID> \"message\""
    echo "       claire fivepoints reply --approve --pr <N>"
    echo ""
    echo "Arguments:"
    echo "  --pr <N>       PR number"
    echo "  --thread <ID>  Thread ID to reply to"
    echo "  \"message\"      Reply text (ASCII only, no emoji)"
    echo "  --approve      Vote approved on the PR"
    exit 1
fi

ado_init

# Sanitize message (Azure DevOps rejects emoji)
CLEAN_MESSAGE=$(ado_sanitize_text "$MESSAGE")

if [[ "$CLEAN_MESSAGE" != "$MESSAGE" ]]; then
    echo "Warning: Non-ASCII characters were stripped from the message"
fi

# Build JSON payload — commentType 1 = text, parentCommentId 1 = reply to first comment
PAYLOAD=$(jq -n \
    --arg content "$CLEAN_MESSAGE" \
    '{content: $content, parentCommentId: 1, commentType: 1}')

RESPONSE=$(ado_post "/git/repositories/${_ADO_REPO}/pullRequests/${PR_NUMBER}/threads/${THREAD_ID}/comments?api-version=7.1" "$PAYLOAD")

# Check for errors
if echo "$RESPONSE" | jq -e '.id' &>/dev/null; then
    COMMENT_ID=$(echo "$RESPONSE" | jq -r '.id')
    echo "Reply posted (comment #${COMMENT_ID} in thread #${THREAD_ID} on PR #${PR_NUMBER})"
else
    ERROR=$(echo "$RESPONSE" | jq -r '.message // "Unknown error"')
    echo "ERROR: Failed to post reply: $ERROR" >&2
    exit 1
fi
