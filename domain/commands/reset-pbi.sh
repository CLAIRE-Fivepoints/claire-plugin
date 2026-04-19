#!/usr/bin/env bash
set -euo pipefail

# fivepoints reset-pbi — Factory reset a single PBI so the pipeline can replay
# from zero. Complements `fivepoints reset-pipeline` (bulk) with per-PBI scope.
#
# Usage:
#   claire fivepoints reset-pbi --pbi <ado-id> --issue <github-num> [options]
#
# See `claire fivepoints reset-pbi --help` for the full option list and the
# corresponding domain doc: `claire domain read fivepoints operational RESET_PBI`.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS_DIR="$PLUGIN_ROOT/domain/scripts"
PY_MODULE="$SCRIPTS_DIR/reset_pbi.py"

# Default repo for fivepoints PBIs. Override with --repo.
DEFAULT_REPO="CLAIRE-Fivepoints/fivepoints"

# Default TFIOne clone (the mirror that hosts feature/<pbi-id>-* branches).
DEFAULT_TFIONE_PATH="${TFIONE_REPO_PATH:-$HOME/TFIOneGit}"

PBI_ID=""
ISSUE_NUM=""
REPO="$DEFAULT_REPO"
TFIONE_PATH="$DEFAULT_TFIONE_PATH"
MODE=""     # dry-run | confirm
KEEP_DB=false

show_help() {
    cat <<'EOF'
Usage: claire fivepoints reset-pbi --pbi <id> --issue <n> [options]

Factory reset a PBI so a fresh agent session can replay the full pipeline.

Required:
  --pbi <id>          ADO PBI (work item) id, e.g. 18839
  --issue <n>         GitHub issue number linked to the PBI

Mode (exactly one required):
  --dry-run           Print the plan and exit — no changes applied
  --confirm           Execute the plan (destructive)

Options:
  --repo owner/name   GitHub repo (default: CLAIRE-Fivepoints/fivepoints)
  --tfione-path PATH  TFIOneGit clone path (default: $TFIONE_REPO_PATH or ~/TFIOneGit)
  --keep-db           Reserved; currently a no-op

What gets reset (when --confirm):
  1. Local + github-remote feature/<pbi>-* branches on TFIOneGit
     (never the ADO 'origin' remote)
  2. Worktrees matching issue-<n>-* in TFIOneGit and its .claire/worktrees/
  3. Open PR on the fivepoints repo whose head is the feature branch: closed
  4. Agent-authored comments on the GitHub issue: deleted
  5. Labels on the issue: reset to [role:analyst]
  6. Issue is reopened if closed
  7. github-manager state: issue purged from processed_issues / issue_assignees
  8. Release assets referencing the issue number: deleted
  9. Claire-side cleanup (delegated to 'claire issue reset --force'):
     issue-<n> worktree, branch, PR, and Claire github-manager state

Guardrails:
  * Refuses to run if the linked PR is already merged
  * Refuses if the GitHub issue title does not reference the given --pbi
  * Never touches the ADO 'origin' remote on TFIOneGit
  * Every destructive action is logged to
    $HOME/.claire/logs/reset-pbi-<pbi>-<timestamp>.log

Examples:
  claire fivepoints reset-pbi --pbi 18839 --issue 71 --dry-run
  claire fivepoints reset-pbi --pbi 18839 --issue 71 --confirm
EOF
}

show_agent_help() {
    cat <<'EOF'
# fivepoints reset-pbi — Agent Help

## Purpose
Reset a single PBI + its linked GitHub issue, branches, worktrees, PR, comments,
labels, and release assets so a fresh agent session can replay the pipeline
from the analyst role without memory of the previous run.

## When to use
* Validating a pipeline fix (e.g. after merging an analyst/dev/tester change)
* Recovering from a botched run where manual cleanup would be error-prone

## Required inputs
--pbi <id>    ADO work item id (must match the GitHub issue title)
--issue <n>   GitHub issue number on --repo

## Modes
--dry-run     Show the plan, make no changes
--confirm     Execute the plan (destructive)

## Guardrails (abort conditions)
* GitHub issue title does not reference PBI <id>    -> exit 2
* Linked PR is already merged                       -> exit 3
* --confirm without GITHUB_TOKEN in environment     -> exit 4

## Required env
GITHUB_TOKEN    read from ~/.config/claire/github_manager.env or env var
                (needed for both --dry-run comment fetch and --confirm execution)

## Produces
Log file at: $HOME/.claire/logs/reset-pbi-<pbi>-<timestamp>.log

## Composes
* Final step shells out to: GITHUB_REPO=<repo> claire issue reset <n> --force
  This delegates Claire-side cleanup (issue-<n> worktree/branch/PR/state)
  rather than reimplementing it. See issue #54.

## Never does
* Touch the ADO 'origin' remote (only the 'github' mirror)
* Delete commits (PR is closed, not force-deleted)
* Reset if the PR is already merged (explicit refusal)
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --pbi)      PBI_ID="$2"; shift 2 ;;
        --issue)    ISSUE_NUM="$2"; shift 2 ;;
        --repo)     REPO="$2"; shift 2 ;;
        --tfione-path) TFIONE_PATH="$2"; shift 2 ;;
        --dry-run)  MODE="dry-run"; shift ;;
        --confirm)  MODE="confirm"; shift ;;
        --keep-db)  KEEP_DB=true; shift ;;
        --help|-h)  show_help; exit 0 ;;
        --agent-help) show_agent_help; exit 0 ;;
        *) die "Unknown argument: $1 (see --help)" ;;
    esac
done

[[ -n "$PBI_ID"    ]] || die "--pbi is required"
[[ -n "$ISSUE_NUM" ]] || die "--issue is required"
[[ -n "$MODE"      ]] || die "one of --dry-run / --confirm is required"
[[ "$PBI_ID"    =~ ^[0-9]+$ ]] || die "--pbi must be numeric"
[[ "$ISSUE_NUM" =~ ^[0-9]+$ ]] || die "--issue must be numeric"
[[ "$REPO" == */* ]] || die "--repo must be in owner/name form"

# ── Token: GITHUB_TOKEN from env or github_manager.env ──────────────────────
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    for env_file in ~/.config/claire/github_manager.env ~/.config/claire/.env; do
        [[ -f "$env_file" ]] || continue
        tok=$(grep -E '^(GITHUB_TOKEN|GH_TOKEN)=' "$env_file" 2>/dev/null | head -1 | cut -d= -f2- || true)
        if [[ -n "$tok" ]]; then
            export GITHUB_TOKEN="$tok"
            break
        fi
    done
fi

if [[ "$MODE" == "confirm" && -z "${GITHUB_TOKEN:-}" ]]; then
    die "--confirm requires GITHUB_TOKEN (set in env or ~/.config/claire/github_manager.env)"
fi

# ── Paths ───────────────────────────────────────────────────────────────────
TS=$(date +%Y%m%d-%H%M%S)
LOG_DIR="$HOME/.claire/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/reset-pbi-${PBI_ID}-${TS}.log"

OWNER="${REPO%/*}"
NAME="${REPO#*/}"
STATE_FILE_DEFAULT="${CLAIRE_HOME:-$HOME/claire}/99_runtime/github-manager/github_manager_state_${OWNER}_${NAME}.json"
STATE_FILE="${CLAIRE_GITHUB_MANAGER_STATE:-$STATE_FILE_DEFAULT}"

echo "=== fivepoints reset-pbi ==="
echo "PBI:        $PBI_ID"
echo "Issue:      #$ISSUE_NUM on $REPO"
echo "Mode:       $MODE"
echo "State file: $STATE_FILE"
echo "TFIOneGit:  $TFIONE_PATH"
echo "Log file:   $LOG_FILE"
echo ""

# ── Collect context via gh (orchestration layer) ────────────────────────────

echo "── Collecting issue + PR + release context via gh..."

ISSUE_JSON=$(gh issue view "$ISSUE_NUM" --repo "$REPO" \
    --json title,state,labels 2>/dev/null) || ISSUE_JSON=""
[[ -n "$ISSUE_JSON" ]] || die "could not fetch issue #$ISSUE_NUM on $REPO"

# Find the linked PR: branch names for fivepoints are feature/<pbi>-*.
# Look up all open PRs on the repo whose head startswith 'feature/<pbi>-'.
PR_JSON_ARRAY=$(gh pr list --repo "$REPO" --state all --limit 20 \
    --search "head:feature/${PBI_ID}" \
    --json number,state,headRefName,mergedAt 2>/dev/null || echo "[]")

# Pick the first PR whose headRefName starts with feature/<pbi>-.
PR_JSON=$(jq -c --arg p "feature/${PBI_ID}-" \
    'map(select(.headRefName | startswith($p))) | .[0] // null' \
    <<<"$PR_JSON_ARRAY")

if [[ "$PR_JSON" == "null" ]]; then
    PR_JSON=""
fi

# Pre-fetch comments (keeps Python offline-friendly for dry-run + tests).
COMMENTS_JSON=$(gh api --paginate \
    "/repos/${REPO}/issues/${ISSUE_NUM}/comments" \
    --jq '[.[] | {id, user: {login: .user.login}, body, created_at}]' \
    2>/dev/null || echo "[]")

# Release assets whose name references the issue (proof-issue-71-*, etc.).
# We inspect up to 10 most recent releases (untagged builds included).
RELEASES_JSON=$(gh release list --repo "$REPO" --limit 10 \
    --json tagName 2>/dev/null || echo "[]")

ASSETS_FILTERED="[]"
if [[ -n "$RELEASES_JSON" && "$RELEASES_JSON" != "[]" ]]; then
    for tag in $(jq -r '.[].tagName' <<<"$RELEASES_JSON"); do
        # `gh release view` handles both tagged and untagged releases correctly,
        # unlike the REST endpoint /releases/tags/{tag} which 404s on untagged ones.
        tag_assets=$(gh release view "$tag" --repo "$REPO" \
            --json assets --jq '[.assets[]? | {id, name}]' 2>/dev/null || echo "[]")
        if ! echo "$tag_assets" | jq -e 'type == "array"' >/dev/null 2>&1; then
            tag_assets="[]"
        fi
        filtered=$(jq --arg tag "$tag" --arg n "$ISSUE_NUM" \
            '[.[] | select((.name // "") | test("issue[-_]" + $n + "([^0-9]|$)")) | . + {release_tag: $tag}]' \
            <<<"$tag_assets")
        ASSETS_FILTERED=$(jq -s '.[0] + .[1]' <(echo "$ASSETS_FILTERED") <(echo "$filtered"))
    done
fi

# ── Hand off to Python (logic layer) ────────────────────────────────────────

PY_ARGS=(
    --pbi "$PBI_ID"
    --issue "$ISSUE_NUM"
    --repo "$REPO"
    --state-file "$STATE_FILE"
    --log-file "$LOG_FILE"
    --issue-json "$ISSUE_JSON"
    --comments-json "$COMMENTS_JSON"
    --releases-json "$ASSETS_FILTERED"
)
if [[ -n "$PR_JSON" ]]; then
    PY_ARGS+=(--pr-json "$PR_JSON")
fi
if [[ "$MODE" == "dry-run" ]]; then
    PY_ARGS+=(--dry-run)
else
    PY_ARGS+=(--confirm)
fi
if [[ "$KEEP_DB" == true ]]; then
    PY_ARGS+=(--keep-db)
fi

set +e
PYTHONPATH="$SCRIPTS_DIR" python3 "$PY_MODULE" "${PY_ARGS[@]}"
PY_RC=$?
set -e

if [[ $PY_RC -ne 0 ]]; then
    echo ""
    echo "ERROR: Python reset_pbi exited with code $PY_RC (see $LOG_FILE)"
    exit "$PY_RC"
fi

# ── Close open PR (orchestration) ───────────────────────────────────────────

if [[ -n "$PR_JSON" ]]; then
    PR_NUM=$(jq -r '.number' <<<"$PR_JSON")
    PR_STATE=$(jq -r '.state' <<<"$PR_JSON")
    if [[ "$PR_STATE" == "OPEN" ]]; then
        echo ""
        echo "── PR #${PR_NUM}: $(if [[ "$MODE" == "dry-run" ]]; then echo '[would close]'; else echo 'closing'; fi)"
        echo "[pr] close PR #${PR_NUM}" >>"$LOG_FILE"
        if [[ "$MODE" == "confirm" ]]; then
            gh pr close "$PR_NUM" --repo "$REPO" \
                --comment "Closed by fivepoints reset-pbi (factory reset for PBI #${PBI_ID})" \
                >/dev/null 2>&1 || echo "  WARN: could not close PR #${PR_NUM}"
        fi
    fi
fi

# ── Git + worktree operations on TFIOneGit ──────────────────────────────────

echo ""
echo "── Git + worktree cleanup on $TFIONE_PATH"

if [[ ! -d "$TFIONE_PATH/.git" && ! -f "$TFIONE_PATH/.git" ]]; then
    echo "  SKIP: TFIOneGit clone not found at $TFIONE_PATH"
    echo "[git] SKIP: TFIOneGit clone missing at $TFIONE_PATH" >>"$LOG_FILE"
else
    # Find matching worktrees. We match by branch name (feature/<pbi>-*) and
    # we SKIP the primary working tree — even if it's on a matching branch,
    # `git worktree remove` rightly refuses it and rm -rf would be catastrophic.
    PRIMARY_WT=$(git -C "$TFIONE_PATH" rev-parse --show-toplevel 2>/dev/null || echo "")
    WT_LIST=$(git -C "$TFIONE_PATH" worktree list --porcelain 2>/dev/null || true)
    CUR_PATH=""
    CUR_BRANCH=""
    WT_MATCHES=()

    _collect_wt_match() {
        if [[ -z "$CUR_PATH" || "$CUR_BRANCH" != feature/${PBI_ID}-* ]]; then
            return
        fi
        if [[ "$CUR_PATH" == "$PRIMARY_WT" ]]; then
            echo "  SKIP primary worktree at $CUR_PATH (branch $CUR_BRANCH — checkout a different branch to reset this branch)"
            echo "[git] SKIP primary worktree $CUR_PATH on $CUR_BRANCH" >>"$LOG_FILE"
            return
        fi
        WT_MATCHES+=("$CUR_PATH")
    }

    while IFS= read -r line; do
        if [[ "$line" =~ ^worktree\ (.+)$ ]]; then
            CUR_PATH="${BASH_REMATCH[1]}"
        elif [[ "$line" == "branch refs/heads/"* ]]; then
            CUR_BRANCH="${line#branch refs/heads/}"
        elif [[ -z "$line" ]]; then
            _collect_wt_match
            CUR_PATH=""
            CUR_BRANCH=""
        fi
    done <<<"$WT_LIST"
    _collect_wt_match  # flush trailing block

    for wt in ${WT_MATCHES[@]+"${WT_MATCHES[@]}"}; do
        echo "  worktree: $wt"
        echo "[git] worktree remove $wt" >>"$LOG_FILE"
        if [[ "$MODE" == "confirm" ]]; then
            git -C "$TFIONE_PATH" worktree remove "$wt" --force 2>/dev/null || {
                echo "  WARN: worktree remove failed, falling back to rm -rf $wt"
                rm -rf "$wt"
            }
        fi
    done

    # Find feature/<pbi>-* branches (local).
    LOCAL_BRANCHES=$(git -C "$TFIONE_PATH" for-each-ref \
        --format='%(refname:short)' "refs/heads/feature/${PBI_ID}-*" 2>/dev/null || true)
    for br in $LOCAL_BRANCHES; do
        echo "  local branch: $br"
        echo "[git] branch -D $br" >>"$LOG_FILE"
        if [[ "$MODE" == "confirm" ]]; then
            git -C "$TFIONE_PATH" branch -D "$br" 2>/dev/null || \
                echo "  WARN: could not delete local branch $br"
        fi
    done

    # Remote branches on the 'github' mirror only.
    if git -C "$TFIONE_PATH" remote get-url github >/dev/null 2>&1; then
        REMOTE_BRANCHES=$(git -C "$TFIONE_PATH" ls-remote --heads github \
            "refs/heads/feature/${PBI_ID}-*" 2>/dev/null \
            | awk '{sub("refs/heads/", "", $2); print $2}' || true)
        for br in $REMOTE_BRANCHES; do
            # Safety: check if an ADO PR exists on 'origin' for this branch.
            ORIG_HAS=$(git -C "$TFIONE_PATH" ls-remote --heads origin \
                "refs/heads/$br" 2>/dev/null | wc -l | tr -d ' ' || echo "0")
            if [[ "$ORIG_HAS" != "0" ]]; then
                echo "  NOTE: branch $br also exists on 'origin' (ADO) — leaving ADO side untouched"
            fi
            echo "  github remote branch: $br"
            echo "[git] push github --delete $br" >>"$LOG_FILE"
            if [[ "$MODE" == "confirm" ]]; then
                git -C "$TFIONE_PATH" push github --delete "$br" 2>/dev/null || \
                    echo "  WARN: could not delete remote branch $br on 'github'"
            fi
        done
    else
        echo "  SKIP: TFIOneGit has no 'github' remote — nothing to push-delete"
    fi
fi

# ── Compose: delegate Claire-side cleanup to `claire issue reset` ───────────
# Owns the issue-<n> worktree + branch + PR + github-manager state on the
# Claire side. We delegate rather than reimplement (issue #54).

echo ""
echo "── Claire-side cleanup (delegated to 'claire issue reset')"
echo "  [claire:issue:reset] claire issue reset $ISSUE_NUM --force (GITHUB_REPO=$REPO)"
echo "[claire:issue:reset] GITHUB_REPO=$REPO claire issue reset $ISSUE_NUM --force" >>"$LOG_FILE"

if [[ "$MODE" == "confirm" ]]; then
    set +e
    GITHUB_REPO="$REPO" claire issue reset "$ISSUE_NUM" --force 2>&1 | tee -a "$LOG_FILE"
    CIR_RC=${PIPESTATUS[0]}
    set -e
    if [[ $CIR_RC -ne 0 ]]; then
        echo "  WARN: claire issue reset exited with code $CIR_RC (see $LOG_FILE)"
        echo "[claire:issue:reset] WARN exit=$CIR_RC" >>"$LOG_FILE"
    fi
fi

echo ""
if [[ "$MODE" == "dry-run" ]]; then
    echo "=== DRY RUN complete — no changes applied ==="
    echo "Log: $LOG_FILE"
else
    echo "=== Reset complete ==="
    echo "Log: $LOG_FILE"
    echo ""
    echo "Next: wait for the GitHub Manager to re-process issue #$ISSUE_NUM"
    echo "      (label role:analyst was applied — a fresh analyst session will spawn)"
fi
