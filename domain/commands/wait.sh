#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$PLUGIN_ROOT/domain/scripts/ado_common.sh"

# Parse arguments
PR_NUMBER=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --pr)
            PR_NUMBER="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$PR_NUMBER" ]]; then
    echo "Usage: claire fivepoints wait --pr <N>"
    echo ""
    echo "Wrapper around 'claire wait' that auto-sets AZURE_DEVOPS_PAT from git remote."
    exit 1
fi

# ado_init extracts and exports the PAT
ado_init

echo "PAT auto-configured from git remote"
echo "Org: ${_ADO_ORG} | Project: ${_ADO_PROJECT} | Repo: ${_ADO_REPO}"
echo ""

# Delegate to claire wait
exec claire wait --pr "$PR_NUMBER"
