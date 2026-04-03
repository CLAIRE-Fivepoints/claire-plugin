#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$PLUGIN_ROOT/domain/scripts/ado_common.sh"

PR_NUMBER="${1:-}"

if [[ -z "$PR_NUMBER" ]]; then
    echo "Usage: claire fivepoints build-log <PR_NUMBER>"
    exit 1
fi

ado_init

# Fetch build statuses for the PR
STATUS_RESPONSE=$(ado_get "/git/repositories/${_ADO_REPO}/pullRequests/${PR_NUMBER}/statuses?api-version=7.1")

if ! echo "$STATUS_RESPONSE" | jq -e '.value' &>/dev/null; then
    echo "ERROR: Could not fetch build statuses for PR #${PR_NUMBER}" >&2
    exit 1
fi

STATUS_COUNT=$(echo "$STATUS_RESPONSE" | jq '.value | length')

echo "=== Build Results for PR #${PR_NUMBER} (${STATUS_COUNT} checks) ==="
echo ""

if [[ "$STATUS_COUNT" -eq 0 ]]; then
    echo "(no build statuses found)"
    exit 0
fi

# Show each status with details
echo "$STATUS_RESPONSE" | jq -r '.value | sort_by(.creationDate) | reverse | .[] |
    "\(.state | ascii_upcase) | \(.context.name // "unknown")",
    "  Genre: \(.context.genre // "N/A")",
    "  Description: \(.description // "N/A")",
    "  URL: \(.targetUrl // "N/A")",
    "  Created: \(.creationDate | split("T")[0])",
    ""
'

# Summary
SUCCEEDED=$(echo "$STATUS_RESPONSE" | jq '[.value[] | select(.state == "succeeded")] | length')
FAILED=$(echo "$STATUS_RESPONSE" | jq '[.value[] | select(.state == "failed")] | length')
PENDING=$(echo "$STATUS_RESPONSE" | jq '[.value[] | select(.state == "pending")] | length')

echo "--- Summary ---"
echo "Succeeded: $SUCCEEDED | Failed: $FAILED | Pending: $PENDING"
