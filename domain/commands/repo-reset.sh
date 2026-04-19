#!/usr/bin/env bash
set -euo pipefail

# fivepoints repo-reset — Factory-reset the fivepoints test mirror to a clean
# state derived from ADO/<ref>, without deleting the repo itself.
#
# Architecture:
#   * Bash (this file) — orchestration: arg parsing, token resolution,
#     machine.yml guardrail, git force-push of `main` via ~/TFIOneGit,
#     pre-fetching JSON inventories via gh.
#   * Python (domain/scripts/repo_reset.py) — logic: plan build + execute
#     (REST + GraphQL wipe of issues, PRs, branches, tags, releases, runs).
#
# See `claire fivepoints repo-reset --help` for the option list and the
# corresponding domain doc: `claire domain read fivepoints operational REPO_RESET`.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS_DIR="$PLUGIN_ROOT/domain/scripts"
PY_MODULE="$SCRIPTS_DIR/repo_reset.py"

DEFAULT_TFIONE_PATH="${TFIONE_REPO_PATH:-$HOME/TFIOneGit}"
DEFAULT_ADO_REF="dev"

MODE=""          # dry-run | confirm
KEEP_PRS=false
ADO_REF="$DEFAULT_ADO_REF"
TFIONE_PATH="$DEFAULT_TFIONE_PATH"

show_help() {
    cat <<'EOF'
Usage: claire fivepoints repo-reset (--dry-run | --confirm) [options]

Factory-reset the fivepoints test mirror (CLAIRE-Fivepoints/fivepoints) to a
clean state derived from ADO/dev. Repo settings (labels, branch protection,
webhooks, Actions secrets, collaborators) are preserved; content is wiped.

Mode (exactly one required):
  --dry-run           Print the plan and exit — no mutations
  --confirm           Execute the plan (destructive)

Options:
  --keep-prs          Skip PR strip+rename and PR comment cleanup
  --ado-ref REF       ADO ref to reset `main` to (default: dev)
  --tfione-path PATH  TFIOneGit clone path (default: $TFIONE_REPO_PATH or ~/TFIOneGit)

What gets reset (when --confirm):
  1. main                — force-pushed to ADO/<ado-ref> tip
  2. All non-main branches — deleted (REST)
  3. All tags             — deleted (REST)
  4. All issues           — deleted (GraphQL deleteIssue, admin only)
  5. All releases         — deleted (assets cascade)
  6. All workflow runs    — deleted (REST)
  7. All PRs              — title -> [archived-repo-reset-<iso>], body
                            replaced, state -> closed (GitHub has no PR delete
                            API, so strip+rename is the neutralization path).
                            Skipped under --keep-prs.
  8. Agent-authored PR    — deleted (skipped under --keep-prs)
     discussion comments

What's preserved:
  * Labels, branch protection, webhooks, Actions secrets, collaborators,
    repo-level settings.

Guardrails:
  * Refuses to run on any repo other than machine.yml:fivepoints_test_repo
  * --confirm requires GITHUB_ADMIN_TOKEN (delete_repo + admin:org scopes)
  * main is force-pushed only from a clean TFIOneGit clone
  * Every action is logged to $HOME/.claire/logs/repo-reset-<timestamp>.log

Examples:
  claire fivepoints repo-reset --dry-run
  claire fivepoints repo-reset --confirm
  claire fivepoints repo-reset --confirm --keep-prs
  claire fivepoints repo-reset --confirm --ado-ref release/v1.2.3

Setup (one-time):
  Add to ~/.claire/machine.yml:
      fivepoints_test_repo: CLAIRE-Fivepoints/fivepoints
EOF
}

show_agent_help() {
    cat <<'EOF'
# fivepoints repo-reset — Agent Help

## Purpose
Wipe all content (issues, PRs, branches, tags, releases, workflow runs) from
the configured fivepoints test mirror and reset main to ADO/<ado-ref>, while
preserving repo settings. For factory-reset between pipeline validation cycles.

## When to use
* The test mirror is too polluted for per-PBI resets to be worth running
* Starting a fresh validation session from a known-clean baseline

## Modes (exactly one required)
--dry-run     Print the plan, make no changes
--confirm     Execute the plan (destructive)

## Options
--keep-prs          Preserve existing PRs instead of strip+rename
--ado-ref REF       ADO source ref (default: dev)
--tfione-path PATH  TFIOneGit clone path

## Required env
GITHUB_ADMIN_TOKEN    Token with delete_repo + admin:org scopes.
                      Read from env or ~/.config/claire/github_manager.env.
                      --confirm fails loud if missing.

## Guardrails (abort conditions)
* machine.yml:fivepoints_test_repo unset            -> exit 2
* Target repo != fivepoints_test_repo              -> exit 2
* --confirm without GITHUB_ADMIN_TOKEN             -> exit 4
* TFIOneGit clone missing (for force-push of main) -> exit 5

## Produces
Log at: $HOME/.claire/logs/repo-reset-<timestamp>.log

## Composes
* Per-PBI scope: prefer `claire fivepoints reset-pbi --pbi <id> --issue <n>`
* This command subsumes what reset-pbi does, applied repo-wide.

## Never does
* Delete the repo itself (settings are preserved)
* Touch any repo other than machine.yml:fivepoints_test_repo
* Push to ADO's `origin` remote
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)       MODE="dry-run"; shift ;;
        --confirm)       MODE="confirm"; shift ;;
        --keep-prs)      KEEP_PRS=true; shift ;;
        --ado-ref)       ADO_REF="$2"; shift 2 ;;
        --tfione-path)   TFIONE_PATH="$2"; shift 2 ;;
        --help|-h)       show_help; exit 0 ;;
        --agent-help)    show_agent_help; exit 0 ;;
        *) die "Unknown argument: $1 (see --help)" ;;
    esac
done

[[ -n "$MODE" ]] || die "one of --dry-run / --confirm is required"

# ── machine.yml guardrail ────────────────────────────────────────────────────
# The configured test repo is the ONLY repo this command will touch. If the
# key is unset we refuse — zero chance of nuking production.

ALLOWED_REPO=$(python3 -m claire_py.machine.cli read-field fivepoints_test_repo 2>/dev/null || true)

if [[ -z "$ALLOWED_REPO" ]]; then
    cat >&2 <<EOF
ERROR: machine.yml does not define 'fivepoints_test_repo'.

Add to ~/.claire/machine.yml:
    fivepoints_test_repo: CLAIRE-Fivepoints/fivepoints

Without this key, repo-reset refuses to run — by design.
EOF
    exit 2
fi

REPO="$ALLOWED_REPO"
OWNER="${REPO%/*}"
NAME="${REPO#*/}"

# ── Token resolution ────────────────────────────────────────────────────────
# GITHUB_ADMIN_TOKEN is distinct from GITHUB_TOKEN (manager token) because
# deleteIssue + deleting workflow runs requires admin:org scope.

if [[ -z "${GITHUB_ADMIN_TOKEN:-}" ]]; then
    for env_file in ~/.config/claire/github_manager.env ~/.config/claire/.env; do
        [[ -f "$env_file" ]] || continue
        tok=$(grep -E '^GITHUB_ADMIN_TOKEN=' "$env_file" 2>/dev/null | head -1 | cut -d= -f2- || true)
        if [[ -n "$tok" ]]; then
            export GITHUB_ADMIN_TOKEN="$tok"
            break
        fi
    done
fi

if [[ "$MODE" == "confirm" && -z "${GITHUB_ADMIN_TOKEN:-}" ]]; then
    die "--confirm requires GITHUB_ADMIN_TOKEN (delete_repo + admin:org scopes)"
fi

# gh uses GITHUB_TOKEN for read-only inventory fetching; fall back to the
# admin token if the regular one isn't set.
if [[ -z "${GITHUB_TOKEN:-}" && -n "${GITHUB_ADMIN_TOKEN:-}" ]]; then
    export GITHUB_TOKEN="$GITHUB_ADMIN_TOKEN"
fi

# ── Paths + log file ────────────────────────────────────────────────────────

TS=$(date +%Y%m%d-%H%M%S)
LOG_DIR="$HOME/.claire/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/repo-reset-${TS}.log"

echo "=== fivepoints repo-reset ==="
echo "Repo:       $REPO"
echo "Mode:       $MODE"
echo "ADO ref:    $ADO_REF"
echo "Keep PRs:   $KEEP_PRS"
echo "TFIOneGit:  $TFIONE_PATH"
echo "Log file:   $LOG_FILE"
echo ""

echo "[repo-reset] mode=$MODE repo=$REPO ado_ref=$ADO_REF keep_prs=$KEEP_PRS" >>"$LOG_FILE"

# ── Collect inventories via gh ──────────────────────────────────────────────
# Everything here is read-only. Results are passed to Python as JSON.

echo "── Collecting inventories via gh..."

# Branches (non-main)
BRANCHES_JSON=$(gh api --paginate "/repos/${REPO}/branches" \
    --jq '[.[] | .name | select(. != "main")]' 2>/dev/null || echo "[]")

# Tags
TAGS_JSON=$(gh api --paginate "/repos/${REPO}/tags" \
    --jq '[.[] | .name]' 2>/dev/null || echo "[]")

# Issues (all states, PRs excluded)
ISSUES_JSON=$(gh api --paginate "/repos/${REPO}/issues?state=all" \
    --jq '[.[] | select(.pull_request == null) | {number: .number, node_id: .node_id, title: .title}]' \
    2>/dev/null || echo "[]")

# PRs (all states)
PRS_JSON=$(gh pr list --repo "$REPO" --state all --limit 500 \
    --json number,state,title \
    --jq '[.[] | {number: .number, state: .state, title: .title}]' \
    2>/dev/null || echo "[]")

# Releases
RELEASES_JSON=$(gh api --paginate "/repos/${REPO}/releases" \
    --jq '[.[] | {id: .id, tag_name: .tag_name}]' 2>/dev/null || echo "[]")

# Workflow runs
RUNS_JSON=$(gh api --paginate "/repos/${REPO}/actions/runs?per_page=100" \
    --jq '[.workflow_runs[]?.id]' 2>/dev/null || echo "[]")

# PR issue-comments (discussion comments), filtered to agent-authored
# in Python. We fetch per-PR and concatenate.
PR_COMMENTS_JSON="[]"
if [[ "$KEEP_PRS" == false ]]; then
    PR_NUMBERS=$(jq -r '.[].number' <<<"$PRS_JSON")
    accum="[]"
    for pr in $PR_NUMBERS; do
        pr_comments=$(gh api --paginate \
            "/repos/${REPO}/issues/${pr}/comments" \
            --jq "[.[] | {id: .id, pr_number: ${pr}, author_login: .user.login}]" \
            2>/dev/null || echo "[]")
        accum=$(jq -s '.[0] + .[1]' <(echo "$accum") <(echo "$pr_comments"))
    done
    PR_COMMENTS_JSON="$accum"
fi

echo "  branches:      $(jq 'length' <<<"$BRANCHES_JSON")"
echo "  tags:          $(jq 'length' <<<"$TAGS_JSON")"
echo "  issues:        $(jq 'length' <<<"$ISSUES_JSON")"
echo "  PRs:           $(jq 'length' <<<"$PRS_JSON")"
echo "  releases:      $(jq 'length' <<<"$RELEASES_JSON")"
echo "  workflow runs: $(jq 'length' <<<"$RUNS_JSON")"
echo "  PR comments:   $(jq 'length' <<<"$PR_COMMENTS_JSON")"
echo ""

{
    echo "[inventory] branches=$(jq 'length' <<<"$BRANCHES_JSON")"
    echo "[inventory] tags=$(jq 'length' <<<"$TAGS_JSON")"
    echo "[inventory] issues=$(jq 'length' <<<"$ISSUES_JSON")"
    echo "[inventory] prs=$(jq 'length' <<<"$PRS_JSON")"
    echo "[inventory] releases=$(jq 'length' <<<"$RELEASES_JSON")"
    echo "[inventory] workflow_runs=$(jq 'length' <<<"$RUNS_JSON")"
    echo "[inventory] pr_comments=$(jq 'length' <<<"$PR_COMMENTS_JSON")"
} >>"$LOG_FILE"

# ── Force-push main (orchestration: git on local clone) ─────────────────────
# We do this BEFORE the Python wipe so that open PRs (about to be archived)
# don't show stale diffs against an outdated main during the brief overlap.

echo "── main reset: $REPO:main -> ADO/${ADO_REF}"
if [[ "$MODE" == "confirm" ]]; then
    if [[ ! -d "$TFIONE_PATH/.git" && ! -f "$TFIONE_PATH/.git" ]]; then
        echo "ERROR: TFIOneGit clone not found at $TFIONE_PATH"
        echo "  Set TFIONE_REPO_PATH or pass --tfione-path to a clone with both 'origin' (ADO) and 'github' remotes."
        echo "[git] FAIL: TFIOneGit clone missing at $TFIONE_PATH" >>"$LOG_FILE"
        exit 5
    fi

    # Confirm 'github' remote exists and points at our allowed repo.
    github_url=$(git -C "$TFIONE_PATH" remote get-url github 2>/dev/null || true)
    if [[ -z "$github_url" ]]; then
        echo "ERROR: TFIOneGit clone has no 'github' remote."
        echo "[git] FAIL: no 'github' remote in $TFIONE_PATH" >>"$LOG_FILE"
        exit 5
    fi
    # Coarse match: owner/name must appear in the remote URL.
    if [[ "$github_url" != *"$REPO"* ]]; then
        echo "ERROR: 'github' remote is $github_url — does not match allowed $REPO"
        echo "[git] FAIL: remote mismatch url=$github_url allowed=$REPO" >>"$LOG_FILE"
        exit 5
    fi

    echo "  fetching origin (ADO)..."
    git -C "$TFIONE_PATH" fetch origin "$ADO_REF" >>"$LOG_FILE" 2>&1 || {
        echo "  ERROR: could not fetch origin/$ADO_REF"
        exit 5
    }
    echo "  force-pushing origin/$ADO_REF -> github:main"
    git -C "$TFIONE_PATH" push github "+refs/remotes/origin/${ADO_REF}:refs/heads/main" \
        >>"$LOG_FILE" 2>&1 || {
        echo "  ERROR: push to github:main failed (see $LOG_FILE)"
        exit 5
    }
    echo "  main force-pushed."
else
    echo "  [dry-run] would force-push origin/$ADO_REF -> github:main from $TFIONE_PATH"
    echo "[git] dry-run: would push origin/$ADO_REF -> github:main" >>"$LOG_FILE"
fi
echo ""

# ── Hand off content wipe to Python ─────────────────────────────────────────

PY_ARGS=(
    --repo "$REPO"
    --allowed-repo "$ALLOWED_REPO"
    --log-file "$LOG_FILE"
    --branches-json "$BRANCHES_JSON"
    --tags-json "$TAGS_JSON"
    --issues-json "$ISSUES_JSON"
    --prs-json "$PRS_JSON"
    --releases-json "$RELEASES_JSON"
    --runs-json "$RUNS_JSON"
    --pr-comments-json "$PR_COMMENTS_JSON"
)
if [[ "$KEEP_PRS" == true ]]; then
    PY_ARGS+=(--keep-prs)
fi
if [[ "$MODE" == "dry-run" ]]; then
    PY_ARGS+=(--dry-run)
else
    PY_ARGS+=(--confirm)
fi

set +e
PYTHONPATH="$SCRIPTS_DIR" python3 "$PY_MODULE" "${PY_ARGS[@]}"
PY_RC=$?
set -e

if [[ $PY_RC -ne 0 ]]; then
    echo ""
    echo "ERROR: repo_reset (Python) exited with code $PY_RC (see $LOG_FILE)"
    exit "$PY_RC"
fi

echo ""
if [[ "$MODE" == "dry-run" ]]; then
    echo "=== DRY RUN complete — no changes applied ==="
else
    echo "=== Reset complete ==="
fi
echo "Log: $LOG_FILE"
