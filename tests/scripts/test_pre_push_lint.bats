#!/usr/bin/env bats
# tests/scripts/test_pre_push_lint.bats
#
# Tests for pre-push Check 3 (npm run lint when push touches com.tfione.web)
# added in issue #119. Compensating control for the missing ADO CI ESLint
# step — see GIT_HOOKS.md "Residual risk".
#
# Strategy: real git repo in a tmpdir + a stub `npm` on PATH so the hook
# exercises the code path without requiring a real node_modules install.

HOOK="${BATS_TEST_DIRNAME}/../../domain/hooks/pre-push"

setup() {
    export GIT_AUTHOR_NAME="bats"
    export GIT_AUTHOR_EMAIL="bats@test.local"
    export GIT_COMMITTER_NAME="bats"
    export GIT_COMMITTER_EMAIL="bats@test.local"

    REPO="$BATS_TEST_TMPDIR/repo"
    git init -q --initial-branch=feature/119-push-test "$REPO"
    pushd "$REPO" >/dev/null
    echo "seed" > README.md
    git add README.md
    git commit -q -m "seed"
    BASE_SHA=$(git rev-parse HEAD)
    popd >/dev/null

    # Stub npm on PATH. Honors NPM_STUB_EXIT for exit code and records every
    # invocation to NPM_STUB_LOG so a test can assert npm was (or was not) called.
    STUB_BIN="$BATS_TEST_TMPDIR/bin"
    mkdir -p "$STUB_BIN"
    cat > "$STUB_BIN/npm" <<'EOF'
#!/usr/bin/env bash
if [[ -n "${NPM_STUB_LOG:-}" ]]; then
    printf 'npm %s\n' "$*" >> "$NPM_STUB_LOG"
fi
exit "${NPM_STUB_EXIT:-0}"
EOF
    chmod +x "$STUB_BIN/npm"
    export PATH="$STUB_BIN:$PATH"
    export NPM_STUB_LOG="$BATS_TEST_TMPDIR/npm.log"
    : > "$NPM_STUB_LOG"
}

teardown() {
    rm -rf "$BATS_TEST_TMPDIR"
}

# Helper: stage a commit that adds a file at the given path, return the sha.
commit_file() {
    local path="$1" content="${2:-placeholder}"
    pushd "$REPO" >/dev/null
    mkdir -p "$(dirname "$path")"
    echo "$content" > "$path"
    git add "$path"
    git commit -q -m "add $path"
    git rev-parse HEAD
    popd >/dev/null
}

# Helper: run the hook with the remote info and a synthesized refspec on stdin.
run_hook() {
    local remote_name="$1" remote_url="$2" local_sha="$3" remote_sha="$4"
    local refspec_line="refs/heads/feature/119-push-test ${local_sha} refs/heads/feature/119-push-test ${remote_sha}"
    pushd "$REPO" >/dev/null
    run bash "$HOOK" "$remote_name" "$remote_url" <<<"$refspec_line"
    popd >/dev/null
}

# ---------------------------------------------------------------------------
# Check 3 fires when push touches com.tfione.web AND lint fails
# ---------------------------------------------------------------------------

@test "pre-push Check 3 blocks push when push touches web and npm run lint fails" {
    local new_sha
    new_sha=$(commit_file "com.tfione.web/src/foo.ts" "export const x = 1;")
    # Need a package.json so cd com.tfione.web && npm run --silent lint is plausible.
    pushd "$REPO" >/dev/null
    echo '{"scripts": {"lint": "eslint ."}}' > com.tfione.web/package.json
    git add com.tfione.web/package.json
    git commit -q -m "add package.json"
    local sha_after_pkg
    sha_after_pkg=$(git rev-parse HEAD)
    popd >/dev/null

    export NPM_STUB_EXIT=1
    run_hook github "git@github.com:foo/bar.git" "$sha_after_pkg" "$BASE_SHA"

    [ "$status" -eq 1 ]
    [[ "$output" == *"'npm run lint' reported errors"* ]]
    grep -q "npm run --silent lint" "$NPM_STUB_LOG"
}

# ---------------------------------------------------------------------------
# Check 3 skips cleanly when the push does not touch com.tfione.web
# ---------------------------------------------------------------------------

@test "pre-push Check 3 does NOT invoke npm when push has no web TS/TSX changes" {
    local new_sha
    new_sha=$(commit_file "docs/changelog.md" "notes")

    # If the hook mistakenly invoked npm, the log would contain an entry.
    export NPM_STUB_EXIT=99

    run_hook github "git@github.com:foo/bar.git" "$new_sha" "$BASE_SHA"

    [ "$status" -eq 0 ]
    [[ "$output" != *"running 'npm run lint'"* ]]
    [[ "$output" != *"'npm run lint' reported errors"* ]]
    [ ! -s "$NPM_STUB_LOG" ]
}

# ---------------------------------------------------------------------------
# Check 3 warn-skips when push touches web but com.tfione.web/ is absent
# (e.g. hook installed in a repo that doesn't carry the web package).
# ---------------------------------------------------------------------------

@test "pre-push Check 3 warn-skips when com.tfione.web/ dir is absent" {
    local new_sha
    new_sha=$(commit_file "com.tfione.web/src/foo.ts" "export const x = 1;")
    pushd "$REPO" >/dev/null
    rm -rf com.tfione.web   # file still reachable from git log, dir gone on disk
    popd >/dev/null

    export NPM_STUB_EXIT=99

    run_hook github "git@github.com:foo/bar.git" "$new_sha" "$BASE_SHA"

    [ "$status" -eq 0 ]
    [[ "$output" == *"com.tfione.web/ but the dir is absent locally"* ]]
    [ ! -s "$NPM_STUB_LOG" ]
}

# ---------------------------------------------------------------------------
# Check 3 allows push when lint passes
# ---------------------------------------------------------------------------

@test "pre-push Check 3 allows push when npm run lint succeeds" {
    local new_sha
    new_sha=$(commit_file "com.tfione.web/src/foo.ts" "export const x = 1;")
    pushd "$REPO" >/dev/null
    echo '{"scripts": {"lint": "eslint ."}}' > com.tfione.web/package.json
    git add com.tfione.web/package.json
    git commit -q -m "add package.json"
    local sha_after_pkg
    sha_after_pkg=$(git rev-parse HEAD)
    popd >/dev/null

    export NPM_STUB_EXIT=0

    run_hook github "git@github.com:foo/bar.git" "$sha_after_pkg" "$BASE_SHA"

    [ "$status" -eq 0 ]
    grep -q "npm run --silent lint" "$NPM_STUB_LOG"
}

# ---------------------------------------------------------------------------
# Regression: existing Check 1 (block push to origin / ADO) still blocks
# regardless of the new Check 3 logic.
# ---------------------------------------------------------------------------

@test "pre-push Check 1 still blocks push to origin (ADO) — regression" {
    local new_sha
    new_sha=$(commit_file "docs/changelog.md" "notes")

    run_hook origin "https://dev.azure.com/example/project/_git/repo" "$new_sha" "$BASE_SHA"

    [ "$status" -eq 1 ]
    [[ "$output" == *"Direct push to origin (ADO) is not allowed"* ]]
    [ ! -s "$NPM_STUB_LOG" ]
}
