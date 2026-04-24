#!/usr/bin/env bats
# tests/scripts/test_pre_commit_eslint.bats
#
# Tests for pre-commit Check 6 (ESLint on staged com.tfione.web TS/TSX files)
# added in issue #119. The check is the client-side substitute for the ADO
# CI ESLint step that cannot be added without committing to origin/master.
#
# Strategy: real git repo in a tmpdir + a stub ESLint binary so the hook
# drives through the code path without requiring node_modules to be installed.

HOOK="${BATS_TEST_DIRNAME}/../../domain/hooks/pre-commit"

setup() {
    export GIT_AUTHOR_NAME="bats"
    export GIT_AUTHOR_EMAIL="bats@test.local"
    export GIT_COMMITTER_NAME="bats"
    export GIT_COMMITTER_EMAIL="bats@test.local"

    REPO="$BATS_TEST_TMPDIR/repo"
    git init -q --initial-branch=feature/119-eslint-test "$REPO"
    pushd "$REPO" >/dev/null
    echo "seed" > README.md
    git add README.md
    git commit -q -m "seed"
    popd >/dev/null
}

teardown() {
    rm -rf "$BATS_TEST_TMPDIR"
}

# exit_code, stdout_message
stub_eslint() {
    local exit_code="$1"
    local msg="${2:-}"
    mkdir -p "$REPO/com.tfione.web/node_modules/.bin"
    cat > "$REPO/com.tfione.web/node_modules/.bin/eslint" <<EOF
#!/usr/bin/env bash
printf '%s\n' "${msg}"
exit ${exit_code}
EOF
    chmod +x "$REPO/com.tfione.web/node_modules/.bin/eslint"
}

# ---------------------------------------------------------------------------
# Check 6 fires on staged .ts/.tsx with lint errors → block
# ---------------------------------------------------------------------------

@test "pre-commit Check 6 blocks commit when ESLint reports errors on staged web files" {
    pushd "$REPO" >/dev/null
    stub_eslint 1 "src/foo.ts: error  Unexpected 'any'"

    mkdir -p com.tfione.web/src
    echo "export const x: any = 1;" > com.tfione.web/src/foo.ts
    git add com.tfione.web/src/foo.ts

    run bash "$HOOK"
    [ "$status" -eq 1 ]
    [[ "$output" == *"ESLint reported errors on staged com.tfione.web TS/TSX files"* ]]
    [[ "$output" == *"src/foo.ts: error  Unexpected 'any'"* ]]
    popd >/dev/null
}

# ---------------------------------------------------------------------------
# Check 6 skips when no web files are staged — ESLint must never be called.
# ---------------------------------------------------------------------------

@test "pre-commit Check 6 skips and does NOT invoke ESLint when no web files are staged" {
    pushd "$REPO" >/dev/null
    # Stub that would fail the test if invoked: exit 99 and write a sentinel.
    stub_eslint 99 "SENTINEL: eslint was invoked"

    echo "notes" > changelog.md
    git add changelog.md

    run bash "$HOOK"
    [ "$status" -eq 0 ]
    [[ "$output" == *"pre-commit checks passed"* ]]
    [[ "$output" != *"SENTINEL"* ]]
    popd >/dev/null
}

# ---------------------------------------------------------------------------
# Check 6 skips cleanly when com.tfione.web/ is absent (e.g. hook installed
# in claire-labs/fivepoints / -test where no web dir exists — but the staged
# path still matches the filter because someone added the file under that
# prefix before removing the dir).
# ---------------------------------------------------------------------------

@test "pre-commit Check 6 warn-skips when com.tfione.web/ dir is absent" {
    pushd "$REPO" >/dev/null

    # Stage a path under com.tfione.web/ so STAGED_WEB_TS is non-empty,
    # but DO NOT create the dir on disk.
    mkdir -p com.tfione.web/src
    echo "export const x = 1;" > com.tfione.web/src/foo.ts
    git add com.tfione.web/src/foo.ts
    rm -rf com.tfione.web   # path still in index, dir gone from worktree

    run bash "$HOOK"
    [ "$status" -eq 0 ]
    [[ "$output" == *"com.tfione.web/ not present in this repo"* ]]
    [[ "$output" == *"skipping ESLint check"* ]]
    popd >/dev/null
}

# ---------------------------------------------------------------------------
# Check 6 skips cleanly when the ESLint binary isn't installed.
# ---------------------------------------------------------------------------

@test "pre-commit Check 6 warn-skips when node_modules/.bin/eslint is missing" {
    pushd "$REPO" >/dev/null

    mkdir -p com.tfione.web/src
    echo "export const x = 1;" > com.tfione.web/src/foo.ts
    git add com.tfione.web/src/foo.ts
    # Intentionally do NOT create com.tfione.web/node_modules/.bin/eslint

    run bash "$HOOK"
    [ "$status" -eq 0 ]
    [[ "$output" == *"node_modules/.bin/eslint missing"* ]]
    [[ "$output" == *"npm --prefix com.tfione.web install"* ]]
    popd >/dev/null
}
