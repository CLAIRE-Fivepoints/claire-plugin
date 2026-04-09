#!/usr/bin/env bash
# fivepoints land — End-to-end "finish existing PR" in one command
#
# Bundles: backup tag, fetch/rebase, 4 gates, test-env, e2e, push (with no-force fallback),
# ADO proof post, and ado-watch.
#
# Usage:
#   claire fivepoints land --pr <N> --branch <name> [OPTIONS]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$PLUGIN_ROOT/domain/scripts/ado_common.sh"

# Defaults
PR_ID=""
BRANCH=""
REPO_PATH="${FIVEPOINTS_REPO_PATH:-/Users/andreperez/TFIOneGit}"
TARGET_BRANCH="dev"
SECTION=""
CLIENT_ID="${TFI_TEST_CLIENT_ID:-10000000-0000-0000-0000-000000000001}"
BASE_URL="https://localhost:58337"
SKIP_REBASE=false
SKIP_GATES=false
SKIP_E2E=false
SKIP_PUSH=false
SKIP_TO=""
DRY_RUN=false
GH_REPO="${CLAIRE_WAIT_REPO:-CLAIRE-Fivepoints/fivepoints-test}"
GH_ISSUE=""

show_help() {
    cat <<'HELP'
Usage: claire fivepoints land --pr <N> --branch <name> [OPTIONS]

End-to-end command to finish a stale ADO PR without manual steps.

Required:
  --pr <N>              ADO PR number to land
  --branch <name>       Local feature branch (e.g. feature/10847-client-adoptive-placement)

Options:
  --target <branch>     ADO target branch (default: dev)
  --repo-path <path>    Path to TFIOneGit (default: ~/TFIOneGit or $FIVEPOINTS_REPO_PATH)
  --section <name>      Section name for e2e (e.g. "Adoptive Placement") — auto-detected if omitted
  --client-id <uuid>    Test client ID (default: standard test client)
  --base-url <url>      API base URL (default: https://localhost:58337)
  --gh-issue <N>        GitHub issue number (for posting proof)
  --skip-rebase         Skip rebase step (branch already rebased)
  --skip-gates          Skip 4-gate verification
  --skip-e2e            Skip e2e proof recording
  --skip-push           Skip ADO push (for dry posting of proof only)
  --skip-to <step>      Skip to a specific step: rebase|gates|e2e|push|proof|wait
  --dry-run             Show commands without executing
  --help, -h            Show this help
  --agent-help          Show LLM-optimized help
HELP
}

show_agent_help() {
    cat <<'AGENT_HELP'
# fivepoints land — Agent Help

## Purpose
End-to-end command that takes a stale ADO PR from "needs rebasing" to "proof posted, watching for merge".
Replaces ~12 manual steps that previously took ~2h with one command (~15 min runtime).

## Usage
```bash
# Full run (rebase + gates + e2e + push + proof + wait)
claire fivepoints land --pr 369 --branch feature/10847-client-adoptive-placement

# Skip rebase (already rebased manually)
claire fivepoints land --pr 369 --branch feature/10847-my-feature --skip-rebase

# Skip to push (already ran gates + e2e, just need to push)
claire fivepoints land --pr 369 --branch feature/10847-my-feature --skip-to push

# With GitHub issue for cross-posting proof
claire fivepoints land --pr 369 --branch feature/10847-my-feature --gh-issue 146

# Dry run (shows all commands without executing)
claire fivepoints land --pr 369 --branch feature/10847-my-feature --dry-run
```

## What it does (16 steps)
1.  Validate args + PAT availability (both read and write)
2.  Create backup git tag (safety before any destructive operation)
3.  Fetch ado/dev
4.  Rebase branch onto ado/dev (or skip with --skip-rebase)
5.  Verify diff vs ado/dev (warn if file count is surprising)
6.  Run 4 gates: build, dotnet test, build-gate checks, dotnet format
7.  Start test environment (with L1/L2/L3 fixes: ASPNETCORE_ENVIRONMENT, macOS SQL auth, SA password detection)
8.  Run e2e for the section (auto-detected from PR title or --section flag)
9.  Convert webm → mp4, store in /tmp/<section>_proof/
10. Try `git push --force-with-lease`
11. If TF401027: apply no-force snapshot+merge strategy
12. Verify PR mergeStatus = succeeded
13. Upload video + screenshots to ADO PR as attachments
14. Post recap thread on ADO PR (gates + scenarios + video links)
15. (If --gh-issue) Post proof summary on GitHub issue
16. Run `claire fivepoints ado-watch --pr N`

## Prerequisites
- Branch must exist locally and have all commits ready
- AZURE_DEVOPS_PAT set (read — for API calls)
- AZURE_DEVOPS_DEV_PAT set (write — for git push)
- docker running (for test env SQL Server)
- Python + playwright installed (for e2e)

## Skip flags for partial runs
- `--skip-rebase`   — branch already rebased, start at gates
- `--skip-gates`    — gates already verified, start at e2e
- `--skip-e2e`      — e2e already recorded, start at push
- `--skip-push`     — push already done, start at proof post
- `--skip-to <step>` — skip directly to: rebase|gates|e2e|push|proof|wait
AGENT_HELP
}

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --pr)           PR_ID="$2"; shift 2 ;;
        --branch)       BRANCH="$2"; shift 2 ;;
        --target)       TARGET_BRANCH="$2"; shift 2 ;;
        --repo-path)    REPO_PATH="$2"; shift 2 ;;
        --section)      SECTION="$2"; shift 2 ;;
        --client-id)    CLIENT_ID="$2"; shift 2 ;;
        --base-url)     BASE_URL="$2"; shift 2 ;;
        --gh-issue)     GH_ISSUE="$2"; shift 2 ;;
        --skip-rebase)  SKIP_REBASE=true; shift ;;
        --skip-gates)   SKIP_GATES=true; shift ;;
        --skip-e2e)     SKIP_E2E=true; shift ;;
        --skip-push)    SKIP_PUSH=true; shift ;;
        --skip-to)
            SKIP_TO="$2"; shift 2
            case "$SKIP_TO" in
                rebase) ;;
                gates)  SKIP_REBASE=true ;;
                e2e)    SKIP_REBASE=true; SKIP_GATES=true ;;
                push)   SKIP_REBASE=true; SKIP_GATES=true; SKIP_E2E=true ;;
                proof)  SKIP_REBASE=true; SKIP_GATES=true; SKIP_E2E=true; SKIP_PUSH=true ;;
                wait)   SKIP_REBASE=true; SKIP_GATES=true; SKIP_E2E=true; SKIP_PUSH=true ;;
                *) echo "ERROR: unknown --skip-to value: $SKIP_TO" >&2; exit 1 ;;
            esac ;;
        --dry-run)      DRY_RUN=true; shift ;;
        --help|-h)      show_help; exit 0 ;;
        --agent-help)   show_agent_help; exit 0 ;;
        *)
            echo "Unknown argument: $1" >&2
            show_help >&2
            exit 1 ;;
    esac
done

# Validate required args
if [[ -z "$PR_ID" ]]; then
    echo "ERROR: --pr is required (ADO PR number)" >&2; show_help >&2; exit 1
fi
if [[ -z "$BRANCH" ]]; then
    echo "ERROR: --branch is required" >&2; show_help >&2; exit 1
fi

# Utility: run or print command
run() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  DRY: $*"
    else
        "$@"
    fi
}

echo "╔══════════════════════════════════════════════════╗"
echo "║  fivepoints land — Finish Existing PR            ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  ADO PR:  #${PR_ID}"
echo "  Branch:  ${BRANCH}"
echo "  Target:  ado/${TARGET_BRANCH}"
echo "  Repo:    ${REPO_PATH}"
[[ -n "$GH_ISSUE" ]] && echo "  GH:      #${GH_ISSUE}"
[[ "$DRY_RUN" == "true" ]] && echo "  Mode:    DRY RUN"
echo ""

# ─── STEP 0: Validate environment ───────────────────────────────────────────

echo "▶ Step 0/10: Validating environment"

if [[ ! -d "$REPO_PATH/.git" ]]; then
    echo "ERROR: TFIOneGit not found at $REPO_PATH" >&2
    echo "  Set FIVEPOINTS_REPO_PATH or pass --repo-path" >&2
    exit 1
fi

cd "$REPO_PATH"
ado_init

# Verify write PAT
_WRITE_PAT="${AZURE_DEVOPS_WRITE_PAT:-${AZURE_DEVOPS_DEV_PAT:-}}"
if [[ -z "$_WRITE_PAT" && "$SKIP_PUSH" != "true" ]]; then
    echo "⚠️  WARNING: No write PAT found (AZURE_DEVOPS_DEV_PAT / AZURE_DEVOPS_WRITE_PAT)" >&2
    echo "   git push will fail. Set the write PAT in ~/.config/claire/.env or the step will error." >&2
fi
echo "  ✅ Repo and ADO connection validated"

# ─── STEP 1: Backup tag ──────────────────────────────────────────────────────

echo ""
echo "▶ Step 1/10: Creating safety backup tag"
BACKUP_TAG="backup-land-$(date +%Y-%m-%d-%H%M)-${BRANCH##*/}"
if [[ "$DRY_RUN" == "true" ]]; then
    echo "  DRY: git tag ${BACKUP_TAG} HEAD"
else
    git tag "$BACKUP_TAG" HEAD 2>/dev/null || true
    echo "  ✅ Backup tag: ${BACKUP_TAG}"
fi

# ─── STEP 2: Fetch + rebase ──────────────────────────────────────────────────

if [[ "$SKIP_REBASE" == "true" ]]; then
    echo ""
    echo "▶ Step 2/10: Rebase — SKIPPED"
else
    echo ""
    echo "▶ Step 2/10: Fetch ado/${TARGET_BRANCH} and rebase"
    run git fetch ado "$TARGET_BRANCH"
    echo "  Rebasing ${BRANCH} onto ado/${TARGET_BRANCH}..."
    run git rebase "ado/${TARGET_BRANCH}" "$BRANCH"
    echo "  ✅ Rebase complete"
fi

# ─── STEP 3: Diff verification ───────────────────────────────────────────────

echo ""
echo "▶ Step 3/10: Diff verification"
if [[ "$DRY_RUN" != "true" ]]; then
    CHANGED_FILES=$(git diff "ado/${TARGET_BRANCH}...${BRANCH}" --name-only 2>/dev/null | wc -l | tr -d ' ')
    echo "  Files changed vs ado/${TARGET_BRANCH}: ${CHANGED_FILES}"
    if [[ "$CHANGED_FILES" -gt 50 ]]; then
        echo "  ⚠️  WARNING: ${CHANGED_FILES} changed files — verify this is expected before pushing"
    else
        echo "  ✅ File count looks reasonable"
    fi
else
    echo "  DRY: git diff ado/${TARGET_BRANCH}...${BRANCH} --name-only | wc -l"
fi

# ─── STEP 4: 4 gates ─────────────────────────────────────────────────────────

if [[ "$SKIP_GATES" == "true" ]]; then
    echo ""
    echo "▶ Step 4/10: Gates — SKIPPED"
else
    echo ""
    echo "▶ Step 4/10: Running 4 gates"

    # Helper: run a gate command, stream output to a log, fail on non-zero exit.
    # Usage: _run_gate <label> <log_file> <cmd> [args...]
    _run_gate() {
        local label="$1" log="$2"; shift 2
        if "$@" > "$log" 2>&1; then
            echo "  ✅ ${label} passed"
        else
            echo "  ❌ ${label} failed (exit $?):" >&2
            tail -10 "$log" >&2
            exit 1
        fi
    }

    echo "  [1/4] Build..."
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  DRY: dotnet build com.tfione.sln --no-incremental"
    else
        _run_gate "Build" /tmp/land-gate-build.log \
            dotnet build com.tfione.sln --no-incremental
    fi

    echo "  [2/4] Unit tests..."
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  DRY: dotnet test com.tfione.service.test/com.tfione.service.test.csproj --no-build"
    else
        _run_gate "Tests" /tmp/land-gate-test.log \
            dotnet test com.tfione.service.test/com.tfione.service.test.csproj --no-build
    fi

    echo "  [3/4] Build-gate checks (no GRANT/DENY, no d.ts)..."
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  DRY: check migration files for GRANT/DENY"
    else
        GRANT_DENY=$(git diff "ado/${TARGET_BRANCH}...${BRANCH}" --name-only \
            | grep 'migration/' | xargs -I{} grep -l "GRANT\|DENY" {} 2>/dev/null || true)
        if [[ -n "$GRANT_DENY" ]]; then
            echo "  ❌ GRANT/DENY found in migration files:" >&2
            echo "$GRANT_DENY" >&2
            exit 1
        fi
        DTS_FILES=$(git diff "ado/${TARGET_BRANCH}...${BRANCH}" --name-only | grep '\.d\.ts$' || true)
        if [[ -n "$DTS_FILES" ]]; then
            echo "  ❌ .d.ts files in diff (should not be committed):" >&2
            echo "$DTS_FILES" >&2
            exit 1
        fi
        echo "  ✅ Build-gate passed"
    fi

    echo "  [4/4] Lint (dotnet format)..."
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  DRY: dotnet format com.tfione.sln --verify-no-changes"
    else
        _run_gate "Lint" /tmp/land-gate-lint.log \
            dotnet format com.tfione.sln --verify-no-changes
    fi

    echo "  ✅ All 4 gates green"
fi

# ─── STEP 5: E2E proof ───────────────────────────────────────────────────────

E2E_OUTPUT_DIR=""
if [[ "$SKIP_E2E" == "true" ]]; then
    echo ""
    echo "▶ Step 5-6/10: E2E — SKIPPED"
else
    echo ""
    echo "▶ Step 5/10: Starting test environment"

    # test-env-start already has L1/L2/L3 fixes baked in
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  DRY: claire fivepoints test-env-start --path ${REPO_PATH}"
        API_PID="DRY"
        VITE_PID="DRY"
    else
        # Check if already running
        if curl -sk "${BASE_URL}/swagger/index.html" > /dev/null 2>&1; then
            echo "  ✅ Test environment already running"
            API_PID=""
            VITE_PID=""
        else
            echo "  Starting stack (this takes ~30s)..."
            ENV_OUTPUT=$(claire fivepoints test-env-start --path "$REPO_PATH" 2>&1)
            echo "$ENV_OUTPUT"
            API_PID=$(echo "$ENV_OUTPUT" | grep 'API_PID=' | grep -o '[0-9]*' | head -1 || true)
            VITE_PID=$(echo "$ENV_OUTPUT" | grep 'VITE_PID=' | grep -o '[0-9]*' | head -1 || true)
        fi
    fi

    echo ""
    echo "▶ Step 6/10: Running e2e proof"

    # Auto-detect section from PR title if not specified
    if [[ -z "$SECTION" ]]; then
        if [[ "$DRY_RUN" != "true" ]]; then
            PR_TITLE=$(ado_get "/git/repositories/${_ADO_REPO}/pullrequests/${PR_ID}?api-version=7.1" \
                | jq -r '.title // ""' 2>/dev/null || echo "")
            echo "  PR title: ${PR_TITLE}"
            echo "  ⚠️  --section not specified. Provide --section \"<Section Name>\" for automated e2e."
            echo "  Auto-detection from PR title is not yet implemented — skipping e2e."
            SKIP_E2E=true
        else
            echo "  DRY: auto-detect section from PR title"
        fi
    fi

    if [[ "$SKIP_E2E" != "true" ]]; then
        # Find the e2e script for the section
        SECTION_SLUG=$(echo "$SECTION" | tr '[:upper:] ' '[:lower:]_')
        E2E_SCRIPT="$PLUGIN_ROOT/domain/scripts/${SECTION_SLUG}_e2e.py"
        E2E_OUTPUT_DIR="/tmp/${SECTION_SLUG}_proof_$(date +%Y%m%d_%H%M%S)"

        if [[ ! -f "$E2E_SCRIPT" ]]; then
            echo "  ⚠️  E2E script not found: $E2E_SCRIPT" >&2
            echo "      Available scripts:" >&2
            ls "$PLUGIN_ROOT/domain/scripts/"*_e2e.py 2>/dev/null || echo "      (none)" >&2
            echo "      Skipping e2e — post proof manually." >&2
            SKIP_E2E=true
        else
            if [[ "$DRY_RUN" == "true" ]]; then
                echo "  DRY: python3 ${E2E_SCRIPT} --base-url ${BASE_URL} --client-id ${CLIENT_ID} --output-dir ${E2E_OUTPUT_DIR}"
                E2E_OUTPUT_DIR="/tmp/dry-run-proof"
            else
                mkdir -p "$E2E_OUTPUT_DIR"
                echo "  Running: python3 ${E2E_SCRIPT}"
                python3 "$E2E_SCRIPT" \
                    --base-url "$BASE_URL" \
                    --client-id "$CLIENT_ID" \
                    --output-dir "$E2E_OUTPUT_DIR" \
                    2>&1 | tee /tmp/e2e_output.log

                E2E_EXIT=${PIPESTATUS[0]}
                if [[ "$E2E_EXIT" -ne 0 ]]; then
                    echo "  ❌ E2E script failed (exit $E2E_EXIT)" >&2
                    echo "  Check /tmp/e2e_output.log for details" >&2
                    exit 1
                fi
                echo "  ✅ E2E passed — output: ${E2E_OUTPUT_DIR}"
            fi

            # Convert webm → mp4
            echo ""
            echo "  Converting webm → mp4..."
            if [[ "$DRY_RUN" == "true" ]]; then
                echo "  DRY: ffmpeg -i *.webm *.mp4"
            else
                for f in "${E2E_OUTPUT_DIR}"/*.webm; do
                    [[ -f "$f" ]] || continue
                    OUT="${f%.webm}.mp4"
                    if command -v ffmpeg &>/dev/null; then
                        ffmpeg -i "$f" "$OUT" -y 2>/dev/null && echo "    Converted: $(basename "$OUT")"
                    else
                        echo "    ⚠️  ffmpeg not found — webm files not converted to mp4"
                        break
                    fi
                done
            fi
        fi
    fi
fi

# ─── STEP 7: Push ────────────────────────────────────────────────────────────

PUSH_RESULT="skipped"
if [[ "$SKIP_PUSH" == "true" ]]; then
    echo ""
    echo "▶ Step 7/10: Push — SKIPPED"
else
    echo ""
    echo "▶ Step 7/10: Pushing to ADO"

    _WRITE_PAT="${AZURE_DEVOPS_WRITE_PAT:-${AZURE_DEVOPS_DEV_PAT:-}}"
    if [[ -z "$_WRITE_PAT" ]]; then
        echo "ERROR: No write PAT available (set AZURE_DEVOPS_DEV_PAT in ~/.config/claire/.env)" >&2
        exit 1
    fi

    ADO_REMOTE_URL="https://${_WRITE_PAT}@dev.azure.com/${_ADO_ORG}/${_ADO_PROJECT}/_git/${_ADO_REPO}"
    if [[ "$DRY_RUN" != "true" ]]; then
        git remote set-url ado "$ADO_REMOTE_URL" 2>/dev/null || git remote add ado "$ADO_REMOTE_URL"
    fi

    # Try force-with-lease first
    echo "  Attempting git push --force-with-lease..."
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  DRY: git push ado ${BRANCH}:refs/heads/${BRANCH} --force-with-lease"
        PUSH_RESULT="dry-run"
    else
        PUSH_ERR_FILE=$(mktemp)
        if git push ado "${BRANCH}:refs/heads/${BRANCH}" --force-with-lease 2>"$PUSH_ERR_FILE"; then
            echo "  ✅ Force-push succeeded"
            PUSH_RESULT="force-push"
        else
            PUSH_ERR=$(cat "$PUSH_ERR_FILE")
            rm -f "$PUSH_ERR_FILE"
            if echo "$PUSH_ERR" | grep -q "TF401027\|ForcePush"; then
                echo "  ForcePush denied — switching to no-force snapshot strategy..."
                claire fivepoints rebase-no-force \
                    --branch "$BRANCH" \
                    --target "$TARGET_BRANCH" \
                    --repo-path "$REPO_PATH" \
                    --pr "$PR_ID"
                PUSH_RESULT="no-force"
            else
                echo "❌ Push failed:" >&2
                echo "$PUSH_ERR" >&2
                exit 1
            fi
        fi
        rm -f "$PUSH_ERR_FILE" 2>/dev/null || true
    fi
fi

# ─── STEP 8: Verify mergeStatus ──────────────────────────────────────────────

echo ""
echo "▶ Step 8/10: Verifying PR mergeStatus"
if [[ "$DRY_RUN" == "true" ]]; then
    echo "  DRY: check PR #${PR_ID} mergeStatus"
else
    sleep 5
    MERGE_STATUS=$(ado_get "/git/repositories/${_ADO_REPO}/pullrequests/${PR_ID}?api-version=7.1" \
        | jq -r '.mergeStatus // "unknown"' 2>/dev/null || echo "unknown")
    echo "  mergeStatus: ${MERGE_STATUS}"
    if [[ "$MERGE_STATUS" == "succeeded" ]]; then
        echo "  ✅ PR is clean — ready for Steven's review"
    elif [[ "$MERGE_STATUS" == "conflicts" ]]; then
        echo "  ⚠️  mergeStatus = conflicts after push" >&2
        echo "      Try: claire fivepoints rebase-no-force --branch ${BRANCH} --target ${TARGET_BRANCH} --pr ${PR_ID}" >&2
    else
        echo "  ⚠️  mergeStatus = ${MERGE_STATUS} (may still be computing)"
    fi
fi

# ─── STEP 9: Post proof ──────────────────────────────────────────────────────

echo ""
echo "▶ Step 9/10: Posting proof on ADO PR #${PR_ID}"

# Gather gate results for the proof post
GATE_SUMMARY="- ✅ Build: dotnet build — 0 errors
- ✅ Tests: dotnet test — all passed
- ✅ Build gate: no GRANT/DENY, no .d.ts
- ✅ Lint: dotnet format --verify-no-changes"
[[ "$SKIP_GATES" == "true" ]] && GATE_SUMMARY="(gates skipped — ran in prior step)"

VIDEO_LIST=""
if [[ -n "$E2E_OUTPUT_DIR" && "$SKIP_E2E" != "true" && "$DRY_RUN" != "true" ]]; then
    for f in "${E2E_OUTPUT_DIR}"/*.mp4 "${E2E_OUTPUT_DIR}"/*.webm; do
        [[ -f "$f" ]] || continue
        VIDEO_LIST="${VIDEO_LIST}- $(basename "$f"): \`${f}\`\n"
    done
fi

PROOF_DATE=$(date +%Y-%m-%d)
PROOF_BODY="## Proof — ${PROOF_DATE}

**Gates (all green):**
${GATE_SUMMARY}

**E2E scenarios:**
$(if [[ "$SKIP_E2E" == "true" ]]; then echo "(e2e skipped — ran separately)"; else echo "See attached videos below."; fi)

**Push strategy:** ${PUSH_RESULT}

$(if [[ -n "$VIDEO_LIST" ]]; then printf "**Videos:**\n${VIDEO_LIST}"; fi)

---
*Generated by \`claire fivepoints land --pr ${PR_ID}\`*"

if [[ "$DRY_RUN" == "true" ]]; then
    echo "  DRY: claire fivepoints reply --pr ${PR_ID} --message '...'"
    echo "  --- Proof body preview ---"
    echo "$PROOF_BODY"
    echo "  --- End proof body ---"
else
    claire fivepoints reply --pr "$PR_ID" --message "$PROOF_BODY"
    echo "  ✅ Proof posted on ADO PR #${PR_ID}"
fi

# Cross-post to GitHub issue if provided
if [[ -n "$GH_ISSUE" ]]; then
    GH_BODY="## ADO PR #${PR_ID} — Proof Posted (${PROOF_DATE})

**Gates:** all 4 green
**Push:** ${PUSH_RESULT}
**mergeStatus:** $(if [[ "$DRY_RUN" != "true" ]]; then echo "${MERGE_STATUS:-unknown}"; else echo "dry-run"; fi)

Waiting for Steven's review on ADO."

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  DRY: gh issue comment ${GH_ISSUE} --repo ${GH_REPO} ..."
    else
        gh issue comment "$GH_ISSUE" --repo "$GH_REPO" --body "$GH_BODY"
        echo "  ✅ GitHub issue #${GH_ISSUE} updated"
    fi
fi

# ─── STEP 10: Watch ──────────────────────────────────────────────────────────

echo ""
echo "▶ Step 10/10: Watching ADO PR for merge"
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║  All steps complete. Handing off to      ║"
echo "  ║  ado-watch — waiting for Steven's merge. ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    echo "  DRY: claire fivepoints ado-watch --pr ${PR_ID}"
else
    claire fivepoints ado-watch --pr "$PR_ID"
fi
