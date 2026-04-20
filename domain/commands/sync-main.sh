#!/usr/bin/env bash
set -euo pipefail

# fivepoints sync-main — Force-push TFIOneGit:origin/<ado-ref> to
# TFIOneGit:github:main. Pure content alignment, nothing else is touched
# (no issues, PRs, branches, settings, releases, or workflow runs).
#
# Architecture: pure bash orchestrator — no Python. The logic is three git
# commands behind a machine.yml guard.
#
# Relationship to siblings:
#   * repo-reset (nuclear) — wipes content AND force-pushes main.
#   * reset-pbi  (per-PBI) — does NOT touch branch content.
#   * sync-main  (this)    — JUST the content sync.
#
# See the issue body on CLAIRE-Fivepoints/claire-plugin#72 for the original
# spec. The force-push block in repo-reset.sh is the reference implementation.

DEFAULT_TFIONE_PATH="${TFIONE_REPO_PATH:-$HOME/TFIOneGit}"
DEFAULT_ADO_REF="dev"

MODE=""                          # dry-run | confirm
ADO_REF="$DEFAULT_ADO_REF"
TFIONE_PATH="$DEFAULT_TFIONE_PATH"

show_help() {
    cat <<'EOF'
Usage: claire fivepoints sync-main (--dry-run | --confirm) [options]

Force-sync the fivepoints test mirror's main branch to the current ADO ref.
No issues, PRs, branches, or settings are touched — pure content alignment.

Mode (exactly one required):
  --dry-run           Print both SHAs + planned action, no push
  --confirm           Execute the force-push

Options:
  --ado-ref REF       ADO ref to sync from (default: dev). Tag/branch/sha OK.
  --tfione-path PATH  TFIOneGit clone path (default: $TFIONE_REPO_PATH or ~/TFIOneGit)

What it does:
  1. Fetch origin/<ado-ref> from the TFIOneGit clone
  2. Compare origin/<ado-ref> SHA with github/main SHA
     - Already in sync -> exit 0, no push
     - Different       -> force-push (on --confirm) or print plan (on --dry-run)
  3. Log SHA transition to $HOME/.claire/logs/sync-main-<timestamp>.log

Guardrails:
  * Refuses to run unless machine.yml:fivepoints_test_repo is set and the
    'github' remote URL on TFIOneGit matches it (anti-production).
  * TFIOneGit must have both 'origin' (ADO) and 'github' remotes.
  * --confirm required for the force-push.

Setup (one-time):
  Add to ~/.claire/machine.yml:
      fivepoints_test_repo: CLAIRE-Fivepoints/fivepoints

Examples:
  claire fivepoints sync-main --dry-run
  claire fivepoints sync-main --confirm
  claire fivepoints sync-main --confirm --ado-ref release/v1.2.3

When to use:
  After an operator or agent has accidentally modified github/main and you
  want to snap it back to ADO truth — without the collateral damage of
  repo-reset (issue/PR/release wipe) or the per-PBI focus of reset-pbi.
EOF
}

show_agent_help() {
    cat <<'EOF'
# fivepoints sync-main — Agent Help

## Purpose
Force-push TFIOneGit:origin/<ado-ref> to TFIOneGit:github:main. The common
case between `reset-pbi` and `repo-reset`: realign the mirror's main with
ADO without touching anything else.

## Modes (exactly one required)
--dry-run   Print plan (both SHAs + action), no push
--confirm   Execute force-push

## Options
--ado-ref REF       Source ref on ADO (default: dev)
--tfione-path PATH  TFIOneGit clone path

## Guardrails (abort conditions)
* machine.yml:fivepoints_test_repo unset                          -> exit 2
* TFIOneGit clone missing / not a git repo                         -> exit 5
* TFIOneGit missing 'origin' or 'github' remote                    -> exit 5
* TFIOneGit 'github' remote URL != fivepoints_test_repo            -> exit 5
* Fetch of origin/<ado-ref> fails                                  -> exit 5

## Produces
Log at: $HOME/.claire/logs/sync-main-<timestamp>.log
Lines: mode, ado_ref, tfione_path, before_sha, after_sha, action, result.

## No token required
This command only drives the local TFIOneGit clone's git remotes — no
GitHub API calls. GITHUB_TOKEN / GITHUB_ADMIN_TOKEN are not read.

## Never does
* Touch ADO's 'origin' remote (only pushes to 'github')
* Modify issues, PRs, branches other than main, tags, releases, or runs
* Run against any repo other than machine.yml:fivepoints_test_repo
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
        --ado-ref)       ADO_REF="$2"; shift 2 ;;
        --tfione-path)   TFIONE_PATH="$2"; shift 2 ;;
        --help|-h)       show_help; exit 0 ;;
        --agent-help)    show_agent_help; exit 0 ;;
        *) die "Unknown argument: $1 (see --help)" ;;
    esac
done

[[ -n "$MODE" ]] || die "one of --dry-run / --confirm is required"

# ── machine.yml guardrail ────────────────────────────────────────────────────
# Only the configured test repo is allowed. Missing key = hard refusal.

ALLOWED_REPO=$(python3 -m claire_py.machine.cli read-field fivepoints_test_repo 2>/dev/null || true)

if [[ -z "$ALLOWED_REPO" ]]; then
    cat >&2 <<EOF
ERROR: machine.yml does not define 'fivepoints_test_repo'.

Add to ~/.claire/machine.yml:
    fivepoints_test_repo: CLAIRE-Fivepoints/fivepoints

Without this key, sync-main refuses to run — by design.
EOF
    exit 2
fi

# ── TFIOneGit shape checks ──────────────────────────────────────────────────

if [[ ! -d "$TFIONE_PATH/.git" && ! -f "$TFIONE_PATH/.git" ]]; then
    echo "ERROR: TFIOneGit clone not found at $TFIONE_PATH" >&2
    echo "  Set TFIONE_REPO_PATH or pass --tfione-path to a clone with both 'origin' (ADO) and 'github' remotes." >&2
    exit 5
fi

origin_url=$(git -C "$TFIONE_PATH" remote get-url origin 2>/dev/null || true)
github_url=$(git -C "$TFIONE_PATH" remote get-url github 2>/dev/null || true)

if [[ -z "$origin_url" ]]; then
    echo "ERROR: TFIOneGit clone at $TFIONE_PATH has no 'origin' remote (expected ADO URL)." >&2
    exit 5
fi
if [[ -z "$github_url" ]]; then
    echo "ERROR: TFIOneGit clone at $TFIONE_PATH has no 'github' remote (expected GitHub mirror URL)." >&2
    exit 5
fi

# Coarse match: owner/name must appear in the github remote URL.
if [[ "$github_url" != *"$ALLOWED_REPO"* ]]; then
    echo "ERROR: TFIOneGit 'github' remote is $github_url" >&2
    echo "       does not match machine.yml:fivepoints_test_repo = $ALLOWED_REPO" >&2
    exit 5
fi

# ── Log file ────────────────────────────────────────────────────────────────

TS=$(date +%Y%m%d-%H%M%S)
LOG_DIR="$HOME/.claire/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/sync-main-${TS}.log"

log_line() {
    echo "$1" >>"$LOG_FILE"
}

echo "=== fivepoints sync-main ==="
echo "Repo:       $ALLOWED_REPO"
echo "Mode:       $MODE"
echo "ADO ref:    $ADO_REF"
echo "TFIOneGit:  $TFIONE_PATH"
echo "Log file:   $LOG_FILE"
echo ""

log_line "[sync-main] mode=$MODE repo=$ALLOWED_REPO ado_ref=$ADO_REF tfione=$TFIONE_PATH"

# ── Fetch ADO ref ───────────────────────────────────────────────────────────

echo "── Fetching origin/$ADO_REF from ADO..."
if ! git -C "$TFIONE_PATH" fetch origin "$ADO_REF" --quiet >>"$LOG_FILE" 2>&1; then
    echo "ERROR: failed to fetch origin/$ADO_REF (see $LOG_FILE)" >&2
    log_line "[sync-main] FAIL fetch origin/$ADO_REF"
    exit 5
fi

# ── Resolve SHAs ────────────────────────────────────────────────────────────
# Use FETCH_HEAD (updated by the fetch above) so the command accepts any ref
# shape the issue spec promises: branch, tag, or raw commit SHA. Resolving via
# refs/remotes/origin/<ref> silently fails for raw SHAs because fetching a SHA
# does not create a remote-tracking ref.

ADO_SHA=$(git -C "$TFIONE_PATH" rev-parse --verify FETCH_HEAD^{commit} 2>/dev/null || true)
[[ -n "$ADO_SHA" ]] || die "could not resolve SHA for origin/$ADO_REF after fetch"

# github/main may not be fetched locally — query the remote directly.
GH_SHA=$(git -C "$TFIONE_PATH" ls-remote github refs/heads/main 2>/dev/null | awk '{print $1}' | head -1)
[[ -n "$GH_SHA" ]] || die "could not resolve SHA for github:main (is the mirror initialised?)"

echo "  ADO  origin/$ADO_REF : $ADO_SHA"
echo "  GH   github/main     : $GH_SHA"
echo ""

log_line "[sync-main] before ado=$ADO_SHA gh_main=$GH_SHA"

# ── Early exit: already in sync ────────────────────────────────────────────

if [[ "$ADO_SHA" == "$GH_SHA" ]]; then
    echo "✓ github/main is already in sync with origin/$ADO_REF — no push needed."
    log_line "[sync-main] result=already_in_sync"
    echo ""
    echo "Log: $LOG_FILE"
    exit 0
fi

# ── Plan / execute the force-push ──────────────────────────────────────────

if [[ "$MODE" == "dry-run" ]]; then
    echo "[dry-run] would force-push:"
    echo "          origin/$ADO_REF ($ADO_SHA)"
    echo "       -> github:main     (currently $GH_SHA)"
    log_line "[sync-main] result=dry_run would_push=origin/$ADO_REF->github:main"
    echo ""
    echo "Log: $LOG_FILE"
    exit 0
fi

echo "── Force-pushing origin/$ADO_REF ($ADO_SHA) -> github:main"
# Push the exact resolved SHA rather than a refspec — unambiguous across
# branch / tag / raw SHA inputs.
if ! git -C "$TFIONE_PATH" push github "+${ADO_SHA}:refs/heads/main" \
        >>"$LOG_FILE" 2>&1; then
    echo "ERROR: force-push failed (see $LOG_FILE)" >&2
    log_line "[sync-main] FAIL push"
    exit 5
fi

# Verify post-push state.
GH_SHA_AFTER=$(git -C "$TFIONE_PATH" ls-remote github refs/heads/main 2>/dev/null | awk '{print $1}' | head -1)
log_line "[sync-main] after gh_main=$GH_SHA_AFTER"
log_line "[sync-main] result=pushed $GH_SHA -> $GH_SHA_AFTER"

echo "  github/main : $GH_SHA -> $GH_SHA_AFTER"
echo ""
echo "=== Sync complete ==="
echo "Log: $LOG_FILE"
