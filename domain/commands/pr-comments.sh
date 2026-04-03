#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$PLUGIN_ROOT/domain/scripts/ado_common.sh"

PR_NUMBER="${1:-}"

if [[ -z "$PR_NUMBER" ]]; then
    echo "Usage: claire fivepoints pr-comments <PR_NUMBER>"
    exit 1
fi

ado_init

# Fetch all threads
RESPONSE=$(ado_get "/git/repositories/${_ADO_REPO}/pullRequests/${PR_NUMBER}/threads?api-version=7.1")

if ! echo "$RESPONSE" | jq -e '.value' &>/dev/null; then
    echo "ERROR: Could not fetch threads for PR #${PR_NUMBER}" >&2
    exit 1
fi

# Filter to text comment threads only (skip system threads)
THREADS=$(echo "$RESPONSE" | jq '[.value[] | select(.isDeleted != true) | select(.comments[]? | .commentType == "text")]')
THREAD_COUNT=$(echo "$THREADS" | jq 'length')

echo "=== PR #${PR_NUMBER} Comment Threads (${THREAD_COUNT}) ==="
echo ""

echo "$THREADS" | jq -r '.[] |
    "--- Thread #\(.id) \(if .threadContext.filePath then "[\(.threadContext.filePath)]" else "[General]" end) ---",
    (.comments[] | select(.commentType == "text") |
        "  \(.author.displayName) (\(.publishedDate | split("T")[0])): \(.content | gsub("\n"; "\n    "))"
    ),
    ""
'
