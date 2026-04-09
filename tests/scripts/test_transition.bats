#!/usr/bin/env bats
# tests/scripts/test_transition.bats
#
# Tests for the tester → dev guard in transition.sh.
# Verifies that:
#   1. The transition is BLOCKED when the most recent failure is from ado-push.
#   2. The transition is ALLOWED when a test failure marker is more recent.
#
# These tests mock `gh`, `git`, `claire`, and `python3` to avoid any real
# network or filesystem side-effects.

TRANSITION_SH="${BATS_TEST_DIRNAME}/../../domain/commands/transition.sh"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Write a mock `gh` script to $BATS_TEST_TMPDIR/bin and prepend it to PATH.
setup() {
    mkdir -p "$BATS_TEST_TMPDIR/bin"

    # Default stubs — overridden per test via GH_MOCK_COMMENTS_JSON
    cat > "$BATS_TEST_TMPDIR/bin/gh" <<'SH'
#!/usr/bin/env bash
# Minimal gh mock for transition.bats tests.
# Tests set GH_MOCK_COMMENTS_JSON to control what 'gh issue view ... --json comments' returns.
# Tests set GH_MOCK_LABELS to control what 'gh issue view ... --json labels' returns.

if [[ "$*" == *"--json comments"* ]]; then
    # Return raw JSON — transition.sh pipes it through jq separately
    echo "${GH_MOCK_COMMENTS_JSON:-{\"comments\":[]}}"
    exit 0
fi

if [[ "$*" == *"--json labels"* ]]; then
    # Return empty string to simulate "no role: label found after jq filter".
    # The role-mismatch guard only fires when CURRENT_LABELS is non-empty AND wrong,
    # so returning empty skips the guard cleanly.
    echo ""
    exit 0
fi

# Swallow label edits, comment posts, label creates
if [[ "$1" == "issue" && ( "$2" == "edit" || "$2" == "comment" ) ]]; then
    exit 0
fi
if [[ "$1" == "label" && "$2" == "create" ]]; then
    exit 0
fi

echo "gh mock: unhandled call: $*" >&2
exit 1
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/gh"

    # Stub git — transition.sh calls git for remote/repo detection
    cat > "$BATS_TEST_TMPDIR/bin/git" <<'SH'
#!/usr/bin/env bash
if [[ "$*" == *"remote get-url origin"* ]]; then
    echo "https://github.com/CLAIRE-Fivepoints/fivepoints-test.git"
    exit 0
fi
if [[ "$*" == *"rev-parse --show-toplevel"* ]]; then
    echo "/tmp/fake-worktree"
    exit 0
fi
exit 0
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/git"

    # Stub claire — transition.sh calls `claire reopen` at the end
    cat > "$BATS_TEST_TMPDIR/bin/claire" <<'SH'
#!/usr/bin/env bash
exit 0
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/claire"

    # Stub python3 — transition.sh calls python3 for CLAUDE.md regeneration
    cat > "$BATS_TEST_TMPDIR/bin/python3" <<'SH'
#!/usr/bin/env bash
exit 1  # Simulate regeneration failure — transition.sh treats this as a warning, not fatal
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/python3"

    # Stub jq — use the real jq but ensure it's on PATH
    if command -v jq &>/dev/null; then
        ln -sf "$(command -v jq)" "$BATS_TEST_TMPDIR/bin/jq"
    fi

    export PATH="$BATS_TEST_TMPDIR/bin:$PATH"
    export CLAIRE_WAIT_REPO="CLAIRE-Fivepoints/fivepoints-test"
}

teardown() {
    rm -rf "$BATS_TEST_TMPDIR"
}

# ---------------------------------------------------------------------------
# Helper: build a minimal GitHub issue comments JSON with N entries.
# Each entry is a plain object with a `body` field.
# Usage: make_comments_json "body1" "body2" ...
# ---------------------------------------------------------------------------
make_comments_json() {
    local json='{"comments":['
    local first=true
    for body in "$@"; do
        if [[ "$first" == "true" ]]; then
            first=false
        else
            json+=','
        fi
        # Escape double-quotes inside body
        local escaped="${body//\"/\\\"}"
        json+="{\"body\":\"${escaped}\"}"
    done
    json+=']}'
    echo "$json"
}

# ---------------------------------------------------------------------------
# Test 1: tester → dev blocked when only failure is ado-push
# ---------------------------------------------------------------------------
@test "tester→dev is blocked when most recent failure is ado-push FAILED" {
    export GH_MOCK_COMMENTS_JSON
    GH_MOCK_COMMENTS_JSON=$(make_comments_json \
        "All tests passed." \
        "ado-push FAILED at step: git push to ADO. DO NOT run fivepoints transition --role tester --next dev.")

    run bash "$TRANSITION_SH" --role tester --next dev --issue 42
    [ "$status" -ne 0 ]
    [[ "$output" == *"Transition blocked"* ]] || [[ "$output" == *"ado-push"* ]]
}

# ---------------------------------------------------------------------------
# Test 2: tester → dev allowed when test failure is more recent than ado-push
# ---------------------------------------------------------------------------
@test "tester→dev is allowed when test failure is more recent than ado-push failure" {
    export GH_MOCK_COMMENTS_JSON
    GH_MOCK_COMMENTS_JSON=$(make_comments_json \
        "ado-push FAILED at step: git push to ADO. DO NOT run fivepoints transition --role tester --next dev." \
        "Test Results: FAILED — 3 tests failed in suite integration.")

    run bash "$TRANSITION_SH" --role tester --next dev --issue 42
    [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Test 3: tester → dev blocked when ado-push failure is the LAST comment
# (even if a test failure appeared before it)
# ---------------------------------------------------------------------------
@test "tester→dev is blocked when ado-push failure is more recent than test failure" {
    export GH_MOCK_COMMENTS_JSON
    GH_MOCK_COMMENTS_JSON=$(make_comments_json \
        "Test Results: FAILED — build failed." \
        "Fixed something, retrying push." \
        "ado-push FAILED at step: git push to ADO. DO NOT run fivepoints transition --role tester --next dev.")

    run bash "$TRANSITION_SH" --role tester --next dev --issue 42
    [ "$status" -ne 0 ]
    [[ "$output" == *"Transition blocked"* ]] || [[ "$output" == *"ado-push"* ]]
}

# ---------------------------------------------------------------------------
# Test 4: tester → dev allowed when no ado-push failure marker exists at all
# ---------------------------------------------------------------------------
@test "tester→dev is allowed when there is no ado-push failure marker" {
    export GH_MOCK_COMMENTS_JSON
    GH_MOCK_COMMENTS_JSON=$(make_comments_json \
        "Test Results: FAILED — authentication module broke.")

    run bash "$TRANSITION_SH" --role tester --next dev --issue 42
    [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Test 5: normal tester → ado-review path is unaffected
# ---------------------------------------------------------------------------
@test "tester→ado-review (default) is not affected by the ado-push guard" {
    export GH_MOCK_COMMENTS_JSON
    # Even if there's an ado-push failure, the default next role is ado-review, not dev.
    # The guard only fires for --next dev, so this path should be unblocked.
    GH_MOCK_COMMENTS_JSON=$(make_comments_json \
        "ado-push FAILED at step: git push to ADO.")

    # tester → ado-review also has a PAT gate; set a dummy PAT so it can proceed.
    export AZURE_DEVOPS_WRITE_PAT="dummy-pat-for-test"

    run bash "$TRANSITION_SH" --role tester --issue 42
    # We expect success (exit 0); the ado-push guard must NOT fire on this path.
    [ "$status" -eq 0 ]
}
