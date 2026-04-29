#!/usr/bin/env bash
# fivepoints pre-push-check — Run all 5 developer gates before git push
#
# Runs gates 0-5 in order and stops on the first failure.
# Gate 5 (migrations) is only run when .sql files are staged.
#
# Usage:
#   claire fivepoints pre-push-check [--path /path/to/TFIOneGit] [--skip-api]

set -euo pipefail

REPO_PATH="${FIVEPOINTS_REPO_PATH:-$HOME/TFIOneGit}"
SKIP_API=false
API_PID=""

cleanup() {
    if [[ -n "$API_PID" ]]; then
        kill "$API_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# ─────────────────────────────────────────────────────────────
# Help text
# ─────────────────────────────────────────────────────────────

show_help() {
    cat <<'HELP'
Usage: claire fivepoints pre-push-check [--path PATH] [--skip-api]

Run all 5 developer gates locally before pushing to GitHub.
Stops on the first gate failure with an actionable diagnosis.

Options:
  --path PATH   Path to TFI One repository (default: $FIVEPOINTS_REPO_PATH or ~/TFIOneGit)
  --skip-api    Skip Gate 3 type-regen step; assume com.tfione.api.d.ts is already fresh.
                Use when the API is already running and types are up to date.

Gate sequence:
  Gate 0   Source control hygiene (branch name, d.ts, tests, GRANT/DENY)
  Gate 1   dotnet build -c Gate (backend, warnings-as-errors)
  Gate 2   dotnet test --configuration Gate
  Gate 3   Kill API → start fresh → regen types → npm run build-gate   [skipped with --skip-api]
  Gate 4   npm run lint (com.tfione.web)
  Gate 5   Migration gates (only when .sql files are staged):
  Gate 5a  claire flyway verify (checksum mismatch check)
  Gate 5b  FK reference check — verify every REFERENCES table has a CREATE TABLE migration
  Gate 5c  flyway migrate (apply pending migrations to local SQL Server)

Exits 0 when all gates pass, 1 on first failure.

Related:
  claire domain read fivepoints operational DEVELOPER_GATES
  claire domain read fivepoints operational GIT_HOOKS
HELP
}

show_agent_help() {
    cat <<'AGENT_HELP'
# fivepoints pre-push-check — Agent Help

## Purpose
Run all 5 developer gates in sequence before `git push`. Stops on the
first failure with a clear, actionable error message.

## When to run
Run this before EVERY `git push github feature/...`. It is the agent-side
enforcement of the gates defined in `fivepoints operational DEVELOPER_GATES`.

## Usage
```bash
# Standard — runs gates 0-5, starts fresh API for Gate 3
claire fivepoints pre-push-check

# With explicit repo path (useful in tests or non-default setups)
claire fivepoints pre-push-check --path /path/to/TFIOneGit

# Skip API startup/type-regen (Gate 3 type-regen step only) — use when
# API is already running and com.tfione.api.d.ts is already fresh
claire fivepoints pre-push-check --skip-api
```

## Gate 5b — FK reference check
This is the key new gate (motivated by issue #70). It reads all FK
constraints in staged migration files and verifies each referenced table
(`REFERENCES [schema].[Table]`) has a corresponding `CREATE TABLE` in
`com.tfione.db/migration/`. A missing table means the ADO CI empty-DB
build will fail.

## Failure handling
On any gate failure, the command exits 1 with the failing gate number
and a diagnostic message. Fix the reported issue, re-stage, and re-run.

## Related docs
- `claire domain read fivepoints operational DEVELOPER_GATES` — full gate specs
- `claire domain read fivepoints operational GIT_HOOKS` — hook context
AGENT_HELP
}

# ─────────────────────────────────────────────────────────────
# Output helpers
# ─────────────────────────────────────────────────────────────

gate_pass() {
    local gate="$1" msg="$2"
    printf "[✅ Gate %s] %s\n" "$gate" "$msg"
}

gate_fail() {
    local gate="$1" msg="$2"
    printf "\n[❌ Gate %s] %s\n" "$gate" "$msg"
}

gate_skip() {
    local gate="$1" msg="$2"
    printf "[⏭️  Gate %s] %s\n" "$gate" "$msg"
}

elapsed() {
    local start=$1
    echo $(( $(date +%s) - start ))
}

# ─────────────────────────────────────────────────────────────
# Arg parsing
# ─────────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case $1 in
        --path)
            REPO_PATH="$2"
            shift 2
            ;;
        --skip-api)
            SKIP_API=true
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
            show_help >&2
            exit 1
            ;;
    esac
done

# ─────────────────────────────────────────────────────────────
# Validate and enter the TFI One repo
# ─────────────────────────────────────────────────────────────

if [[ ! -f "$REPO_PATH/com.tfione.sln" ]]; then
    echo "ERROR: $REPO_PATH is not a TFI One repository (com.tfione.sln not found)." >&2
    echo "  Set FIVEPOINTS_REPO_PATH or pass --path /path/to/TFIOneGit" >&2
    exit 1
fi

cd "$REPO_PATH"

BRANCH=$(git branch --show-current 2>/dev/null || echo "")
echo ""
printf "[pre-push-check] %s\n" "${BRANCH:-<detached HEAD>}"
echo ""

# ─────────────────────────────────────────────────────────────
# Gate 0 — Source control hygiene
# ─────────────────────────────────────────────────────────────

GATE0_ERRORS=()

# 0a: Branch naming convention
if [[ -n "$BRANCH" ]]; then
    if [[ ! "$BRANCH" =~ ^(feature|bugfix)/[0-9]+- ]] && \
       [[ "$BRANCH" != "main" ]] && \
       [[ "$BRANCH" != "dev" ]] && \
       [[ ! "$BRANCH" =~ ^release/ ]]; then
        GATE0_ERRORS+=("Branch '$BRANCH' does not follow naming convention.")
        GATE0_ERRORS+=("  Required: feature/{ticket-id}-short-description")
        GATE0_ERRORS+=("           bugfix/{ticket-id}-short-description")
        GATE0_ERRORS+=("  Examples: feature/10856-client-export, bugfix/10901-fix-null")
    fi
fi

STAGED_FILES=$(git diff --cached --name-only 2>/dev/null || true)

# 0b: com.tfione.api.d.ts must not be staged
if printf '%s\n' "$STAGED_FILES" | grep -q "com\.tfione\.api\.d\.ts"; then
    GATE0_ERRORS+=("com.tfione.api.d.ts must not be committed (generated file).")
    GATE0_ERRORS+=("  Fix: git restore --staged com.tfione.api.d.ts")
fi

# 0c: No *.test.cs or *.spec.ts staged
if printf '%s\n' "$STAGED_FILES" | grep -qE "\.(test\.cs|spec\.ts)$"; then
    GATE0_ERRORS+=("Test files staged — do not commit test code to the feature branch.")
    GATE0_ERRORS+=("  Matched files:")
    while IFS= read -r f; do
        [[ "$f" =~ \.(test\.cs|spec\.ts)$ ]] && GATE0_ERRORS+=("    $f")
    done <<< "$STAGED_FILES"
    GATE0_ERRORS+=("  Keep E2E specs in ~/.claire/scratch/tests/<issue-N>/ (not in the branch).")
fi

# 0d: No GRANT/DENY in staged migration files
STAGED_MIGRATIONS_0=$(printf '%s\n' "$STAGED_FILES" | grep -iE "migration.*\.sql$" || true)
if [[ -n "$STAGED_MIGRATIONS_0" ]]; then
    while IFS= read -r mig_file; do
        if git show ":${mig_file}" 2>/dev/null | grep -iqE "^\s*(GRANT|DENY|EXEC\s+sp_addrolemember)"; then
            GATE0_ERRORS+=("Migration '$mig_file' contains role permissions (GRANT/DENY).")
            GATE0_ERRORS+=("  Roles are managed via the UI — never add them to migrations.")
        fi
    done <<< "$STAGED_MIGRATIONS_0"
fi

if [[ ${#GATE0_ERRORS[@]} -gt 0 ]]; then
    gate_fail "0" "Source control hygiene FAILED"
    for err in "${GATE0_ERRORS[@]}"; do
        printf "  %s\n" "$err"
    done
    echo ""
    exit 1
fi

gate_pass "0" "Branch OK | d.ts clean | no tests | no GRANT/DENY"

# ─────────────────────────────────────────────────────────────
# Gate 1 — Backend build
# ─────────────────────────────────────────────────────────────

t1=$(date +%s)
if ! dotnet build com.tfione.api/com.tfione.api.csproj \
        -c Gate -WarnAsError -nowarn:nu1901,nu1902 \
        > /tmp/pre-push-gate1.log 2>&1; then
    gate_fail "1" "dotnet build FAILED ($(elapsed "$t1")s)"
    echo ""
    tail -20 /tmp/pre-push-gate1.log
    echo ""
    echo "  Full log: /tmp/pre-push-gate1.log"
    echo "  Fix: resolve StyleCop/nullable/build errors above, then re-run."
    echo ""
    exit 1
fi
gate_pass "1" "dotnet build — 0 errors ($(elapsed "$t1")s)"

# ─────────────────────────────────────────────────────────────
# Gate 2 — Tests
# ─────────────────────────────────────────────────────────────

t2=$(date +%s)
if ! dotnet test com.tfione.service.test/com.tfione.service.test.csproj \
        --configuration Gate --no-build \
        > /tmp/pre-push-gate2.log 2>&1; then
    gate_fail "2" "dotnet test FAILED ($(elapsed "$t2")s)"
    echo ""
    tail -20 /tmp/pre-push-gate2.log
    echo ""
    echo "  Full log: /tmp/pre-push-gate2.log"
    echo ""
    exit 1
fi
PASSED_COUNT=$(grep -oE "[0-9]+ passed" /tmp/pre-push-gate2.log | tail -1 | grep -oE "[0-9]+" || echo "?")
gate_pass "2" "dotnet test — ${PASSED_COUNT} passed ($(elapsed "$t2")s)"

# ─────────────────────────────────────────────────────────────
# Gate 3 — Frontend build (requires running API for type regen)
# ─────────────────────────────────────────────────────────────

if [[ "$SKIP_API" == "true" ]]; then
    gate_skip "3" "API startup + type regen skipped (--skip-api). Running build-gate with existing types."
    t3=$(date +%s)
    if ! (cd com.tfione.web && npm run build-gate > /tmp/pre-push-gate3.log 2>&1); then
        gate_fail "3" "npm run build-gate FAILED ($(elapsed "$t3")s)"
        echo ""
        [[ -f /tmp/pre-push-gate3.log ]] && tail -20 /tmp/pre-push-gate3.log
        echo ""
        echo "  Full log: /tmp/pre-push-gate3.log"
        echo "  Tip: run without --skip-api to regenerate com.tfione.api.d.ts first."
        echo ""
        exit 1
    fi
    gate_pass "3" "build-gate — 0 errors ($(elapsed "$t3")s)"
else
    # Kill any existing API instance
    pkill -f "com.tfione.api" 2>/dev/null || true
    sleep 1

    # Start fresh API in background
    dotnet run --project com.tfione.api/com.tfione.api.csproj \
        --urls "https://localhost:58337" \
        > /tmp/pre-push-api.log 2>&1 &
    API_PID=$!

    # Wait for swagger (up to 120s)
    echo "  [Gate 3] Starting API (PID $API_PID) — waiting for swagger…"
    SWAGGER_READY=false
    for i in $(seq 1 24); do
        sleep 5
        if curl -sk -f https://localhost:58337/swagger/v1/swagger.json -o /dev/null 2>/dev/null; then
            SWAGGER_READY=true
            break
        fi
        printf "  [Gate 3] %ds — waiting for API…\n" $(( i * 5 ))
    done

    if [[ "$SWAGGER_READY" != "true" ]]; then
        gate_fail "3" "API did not start within 120s"
        echo ""
        echo "  API log (last 20 lines): /tmp/pre-push-api.log"
        tail -20 /tmp/pre-push-api.log
        echo ""
        echo "  Fix: check for port conflicts or build errors, then re-run."
        echo "       Or use --skip-api if types are already regenerated."
        echo ""
        exit 1
    fi

    # Regenerate com.tfione.api.d.ts from live swagger
    t3=$(date +%s)
    if ! (cd com.tfione.web && \
          GENERATE_ENV=local \
          GENERATE_API="https://localhost:58337/swagger/v1/swagger.json" \
          NODE_TLS_REJECT_UNAUTHORIZED=0 \
          npx tsx src/types/com.tfione.api.generate.ts \
          > /tmp/pre-push-regen.log 2>&1); then
        gate_fail "3" "Type regeneration FAILED ($(elapsed "$t3")s)"
        echo ""
        tail -10 /tmp/pre-push-regen.log
        echo ""
        exit 1
    fi

    if ! (cd com.tfione.web && npm run build-gate > /tmp/pre-push-gate3.log 2>&1); then
        gate_fail "3" "npm run build-gate FAILED ($(elapsed "$t3")s)"
        echo ""
        tail -20 /tmp/pre-push-gate3.log
        echo ""
        echo "  Full log: /tmp/pre-push-gate3.log"
        echo ""
        exit 1
    fi
    gate_pass "3" "Types regenerated | build-gate — 0 errors ($(elapsed "$t3")s)"
fi

# ─────────────────────────────────────────────────────────────
# Gate 4 — Lint
# ─────────────────────────────────────────────────────────────

t4=$(date +%s)
if ! (cd com.tfione.web && npm run lint > /tmp/pre-push-gate4.log 2>&1); then
    gate_fail "4" "npm run lint FAILED ($(elapsed "$t4")s)"
    echo ""
    cat /tmp/pre-push-gate4.log
    echo ""
    echo "  Fix: cd com.tfione.web && npm run lint — resolve errors — re-run."
    echo ""
    exit 1
fi
gate_pass "4" "lint — 0 errors in changed files ($(elapsed "$t4")s)"

# ─────────────────────────────────────────────────────────────
# Gate 5 — Migrations (only when .sql files are staged)
# ─────────────────────────────────────────────────────────────

STAGED_MIGRATIONS=$(git diff --cached --name-only 2>/dev/null | grep -iE "\.sql$" || true)

if [[ -z "$STAGED_MIGRATIONS" ]]; then
    gate_skip "5" "No staged SQL files — migration gates skipped."
else
    # Gate 5a — Flyway checksum verify
    t5a=$(date +%s)
    if ! claire flyway verify > /tmp/pre-push-gate5a.log 2>&1; then
        gate_fail "5a" "flyway verify FAILED — checksum mismatch ($(elapsed "$t5a")s)"
        echo ""
        cat /tmp/pre-push-gate5a.log
        echo ""
        echo "  Fix: never edit an already-applied migration. Create a new migration"
        echo "       with corrective SQL instead."
        echo ""
        exit 1
    fi
    gate_pass "5a" "flyway verify — no checksum mismatch ($(elapsed "$t5a")s)"

    # Gate 5b — FK reference check
    t5b=$(date +%s)
    GATE5B_ERRORS=()

    while IFS= read -r sql_file; do
        # Read the staged version of the migration file
        while IFS= read -r ref_line; do
            # Extract the table ref: REFERENCES [schema].[Table] or REFERENCES schema.Table
            table_ref=$(printf '%s' "$ref_line" | grep -oiE '\[?[a-zA-Z_]+\]?\.\[?[a-zA-Z_]+\]?' | head -1 || true)
            [[ -z "$table_ref" ]] && continue

            # Normalize: strip brackets → schema.table
            table_norm=$(printf '%s' "$table_ref" | tr -d '[]')
            schema="${table_norm%%.*}"
            tbl="${table_norm##*.}"

            # Check if any migration (on disk) creates this table
            if ! grep -rqiE "CREATE\s+TABLE\s+\[?${schema}\]?\.\[?${tbl}\]?" \
                 com.tfione.db/migration/ 2>/dev/null; then
                GATE5B_ERRORS+=("FK references [${schema}].[${tbl}] but no migration creates it.")
                GATE5B_ERRORS+=("  → [${schema}].[${tbl}] has no migration")
                GATE5B_ERRORS+=("  → Will fail on CI empty-DB (azure_gated_build.yml Gate 4)")
                GATE5B_ERRORS+=("  → Found in: ${sql_file}")
                GATE5B_ERRORS+=("  Fix: add CREATE TABLE [${schema}].[${tbl}] to your migration")
                GATE5B_ERRORS+=("       BEFORE the table that references it.")
                GATE5B_ERRORS+=("")
            fi
        done < <(git show ":${sql_file}" 2>/dev/null | \
                 grep -iE "REFERENCES\s+\[?[a-zA-Z_]+\]?\.\[?[a-zA-Z_]+\]?" || true)
    done <<< "$STAGED_MIGRATIONS"

    if [[ ${#GATE5B_ERRORS[@]} -gt 0 ]]; then
        gate_fail "5b" "FK reference check FAILED ($(elapsed "$t5b")s)"
        echo ""
        for err in "${GATE5B_ERRORS[@]}"; do
            printf "  %s\n" "$err"
        done
        exit 1
    fi
    gate_pass "5b" "FK check — all referenced tables have migrations ($(elapsed "$t5b")s)"

    # Gate 5c — Apply pending migrations to local SQL Server
    t5c=$(date +%s)
    SA_PASS=$(docker inspect tfione-sqlserver \
        --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
        | awk -F= '$1=="SA_PASSWORD"{print $2}' || true)

    if [[ -z "$SA_PASS" ]]; then
        echo "  ⚠️  Gate 5c: tfione-sqlserver container not found or SA_PASSWORD unset."
        echo "     Skipping flyway migrate — start the container and re-run to verify migration apply."
    else
        if ! FLYWAY_PASSWORD="$SA_PASS" flyway \
                -url="jdbc:sqlserver://localhost:1433;databaseName=tfi_one;trustServerCertificate=true" \
                -user=sa \
                -locations="filesystem:com.tfione.db/migration" \
                -outOfOrder=true migrate \
                > /tmp/pre-push-gate5c.log 2>&1; then
            gate_fail "5c" "flyway migrate FAILED ($(elapsed "$t5c")s)"
            echo ""
            tail -20 /tmp/pre-push-gate5c.log
            echo ""
            echo "  Full log: /tmp/pre-push-gate5c.log"
            echo "  Fix: resolve migration errors above, then re-run."
            echo ""
            exit 1
        fi
        APPLIED=$(grep -oE "[0-9]+ migration" /tmp/pre-push-gate5c.log | tail -1 || echo "migrations applied")
        gate_pass "5c" "flyway migrate — ${APPLIED} ($(elapsed "$t5c")s)"
    fi
fi

# ─────────────────────────────────────────────────────────────
# All gates passed
# ─────────────────────────────────────────────────────────────

echo ""
echo "All gates passed. Safe to push."
echo ""
