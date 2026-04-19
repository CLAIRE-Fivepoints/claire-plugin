#!/usr/bin/env bash
set -euo pipefail

# fivepoints install-hooks — Install TFI One pre-commit hooks into all fivepoints repos
#
# Installs into:
#   1. claire-labs/fivepoints   (local path from claire repo registry)
#   2. claire-labs/fivepoints-test (local path from claire repo registry)
#   3. TFIOneGit                ($FIVEPOINTS_REPO_PATH or /Users/andreperez/TFIOneGit)
#
# Usage:
#   claire fivepoints install-hooks
#   claire fivepoints install-hooks --dry-run

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK_SOURCE_PRECOMMIT="$PLUGIN_ROOT/domain/hooks/pre-commit"
HOOK_SOURCE_PREPUSH="$PLUGIN_ROOT/domain/hooks/pre-push"

DRY_RUN=false

show_help() {
    echo "Usage: claire fivepoints install-hooks [--dry-run]"
    echo ""
    echo "Install TFI One pre-commit hook into all fivepoints git repositories."
    echo ""
    echo "Targets:"
    echo "  1. claire-labs/fivepoints   (discovered via claire repo list)"
    echo "  2. claire-labs/fivepoints-test (discovered via claire repo list)"
    echo "  3. TFIOneGit                (\$FIVEPOINTS_REPO_PATH or /Users/andreperez/TFIOneGit)"
    echo ""
    echo "Options:"
    echo "  --dry-run   Show what would be installed without making changes"
    echo ""
    echo "Hooks installed:"
    echo "  pre-commit:"
    echo "    1. Branch naming: feature/{numeric-id}-* or bugfix/{numeric-id}-*"
    echo "    2. com.tfione.api.d.ts not staged"
    echo "    3. No GRANT/DENY in Flyway migrations"
    echo "    4. No business logic tests in com.tfione.service.test"
    echo "    5. .fds-cache/ not staged (per-session FDS cache)"
    echo "  pre-push:"
    echo "    6. Block push to origin (ADO) — use git push github instead"
    echo "    7. .fds-cache/ not present in pushed commits (belt-and-suspenders)"
}

show_agent_help() {
    cat <<'AGENT_HELP'
# fivepoints install-hooks — Agent Help

## Purpose
Install the TFI One pre-commit hook into ALL fivepoints git repositories.
Run once after cloning or at the start of a new dev session.

## Usage
```bash
claire fivepoints install-hooks           # install in all 3 repos
claire fivepoints install-hooks --dry-run # preview without changes
```

## What it installs
A pre-commit hook at `.git/hooks/pre-commit` that enforces:
1. Branch naming: feature/{numeric-id}-* or bugfix/{numeric-id}-*
2. com.tfione.api.d.ts must not be staged (generated file)
3. No GRANT/DENY/role assignments in Flyway migrations
4. No business logic tests in com.tfione.service.test
5. Nothing under .fds-cache/ is staged (per-session FDS cache, PR #53)

A pre-push hook at `.git/hooks/pre-push` that enforces:
6. No push to origin (ADO) — the dev must use `git push github` only
7. Nothing under .fds-cache/ appears in any pushed commit
   (belt-and-suspenders for Check 5 in pre-commit)

## Target repos (auto-discovered)
1. claire-labs/fivepoints   → local path from `claire repo list`
2. claire-labs/fivepoints-test → local path from `claire repo list`
3. TFIOneGit                → $FIVEPOINTS_REPO_PATH or /Users/andreperez/TFIOneGit

## When to run
- After initial clone of any fivepoints repo
- After `claire repo add` for a new fivepoints repo
AGENT_HELP
}

while [[ $# -gt 0 ]]; do
    case $1 in
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

# ─────────────────────────────────────────────────────────────
# Discover target repos
# ─────────────────────────────────────────────────────────────

declare -A REPOS  # label → local path

# 1. Discover fivepoints repos from claire registry
while IFS= read -r line; do
    # Format: "claire-labs/fivepoints    yes    —    /path/to/repo"
    repo_name=$(echo "$line" | awk '{print $1}')
    local_path=$(echo "$line" | awk '{print $NF}')

    if [[ "$repo_name" == "claire-labs/fivepoints" ]] && [[ -d "$local_path/.git" ]]; then
        REPOS["claire-labs/fivepoints"]="$local_path"
    elif [[ "$repo_name" == "claire-labs/fivepoints-test" ]] && [[ -d "$local_path/.git" ]]; then
        REPOS["claire-labs/fivepoints-test"]="$local_path"
    fi
done < <(claire repo list 2>/dev/null | grep "claire-labs/fivepoints" || true)

# 2. TFIOneGit (ADO client repo)
TFIONE_PATH="${FIVEPOINTS_REPO_PATH:-/Users/andreperez/TFIOneGit}"
if [[ -d "$TFIONE_PATH/.git" ]]; then
    REPOS["TFIOneGit (ADO)"]="$TFIONE_PATH"
fi

if [[ ${#REPOS[@]} -eq 0 ]]; then
    echo "ERROR: No fivepoints repos found." >&2
    echo "  Expected: claire-labs/fivepoints, claire-labs/fivepoints-test in claire repo list" >&2
    echo "  Expected: $TFIONE_PATH (set FIVEPOINTS_REPO_PATH to override)" >&2
    exit 1
fi

# ─────────────────────────────────────────────────────────────
# Install
# ─────────────────────────────────────────────────────────────

echo ""
echo "TFI One Pre-Commit Hook — Install"
echo ""
if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY RUN — no changes will be made]"
    echo ""
fi

INSTALLED=0
SKIPPED=0
FAILED=0

for label in "${!REPOS[@]}"; do
    local_path="${REPOS[$label]}"

    echo "  [$label]"
    echo "    Path: $local_path"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "    → Would install pre-commit hook"
        echo "    → Would install pre-push hook"
        echo ""
        continue
    fi

    # Install pre-commit hook
    hook_dest="$local_path/.git/hooks/pre-commit"
    if [[ -f "$hook_dest" ]]; then
        backup="${hook_dest}.bak.$(date +%Y%m%d%H%M%S)"
        cp "$hook_dest" "$backup"
        echo "    Backed up existing pre-commit → $(basename "$backup")"
    fi
    if cp "$HOOK_SOURCE_PRECOMMIT" "$hook_dest" && chmod +x "$hook_dest"; then
        echo "    ✅ pre-commit installed"
        (( INSTALLED++ )) || true
    else
        echo "    ❌ pre-commit failed"
        (( FAILED++ )) || true
    fi

    # Install pre-push hook
    hook_dest="$local_path/.git/hooks/pre-push"
    if [[ -f "$hook_dest" ]]; then
        backup="${hook_dest}.bak.$(date +%Y%m%d%H%M%S)"
        cp "$hook_dest" "$backup"
        echo "    Backed up existing pre-push → $(basename "$backup")"
    fi
    if cp "$HOOK_SOURCE_PREPUSH" "$hook_dest" && chmod +x "$hook_dest"; then
        echo "    ✅ pre-push installed"
        (( INSTALLED++ )) || true
    else
        echo "    ❌ pre-push failed"
        (( FAILED++ )) || true
    fi

    echo ""
done

# ─────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────

if [[ "$DRY_RUN" == "true" ]]; then
    echo "  Would install in ${#REPOS[@]} repo(s). Run without --dry-run to apply."
    echo ""
    exit 0
fi

echo "Checks active after install:"
echo "  pre-commit:"
echo "    1. Branch naming:  feature/{id}-* or bugfix/{id}-*"
echo "    2. Generated file: com.tfione.api.d.ts must not be staged"
echo "    3. Migrations:     no GRANT/DENY/role permissions"
echo "    4. Tests:          no business logic tests in service.test"
echo "    5. FDS cache:      nothing under .fds-cache/ may be staged"
echo "  pre-push:"
echo "    6. Remote guard:   push to origin (ADO) is blocked"
echo "    7. FDS cache:      no pushed commit may touch .fds-cache/"
echo ""
echo "Results: $INSTALLED installed, $SKIPPED skipped, $FAILED failed"

if [[ $FAILED -gt 0 ]]; then
    exit 1
fi
