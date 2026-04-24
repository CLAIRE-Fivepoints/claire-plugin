#!/usr/bin/env bats
# tests/scripts/test_check_proof_gate.bats
#
# Tests for check_proof_gate() in domain/scripts/ado_common.sh.
# Verifies the dev-pipeline proof gate (issue #74):
#   - rejects when MP4 ([8/11]) is missing on the issue
#   - rejects when FDS Verification ([9/11]) is missing on the issue
#   - accepts when both are present
#   - rejection text names the specific skipped step
#
# Mocks `gh` to return controlled comment JSON.

ADO_COMMON="${BATS_TEST_DIRNAME}/../../domain/scripts/ado_common.sh"

setup() {
    mkdir -p "$BATS_TEST_TMPDIR/bin"

    # gh mock — reads GH_MOCK_COMMENTS_JSON for issue view --json comments
    cat > "$BATS_TEST_TMPDIR/bin/gh" <<'SH'
#!/usr/bin/env bash
if [[ "$1" == "issue" && "$2" == "view" && "$*" == *"--json comments"* ]]; then
    body="${GH_MOCK_COMMENTS_JSON:-{\"comments\":[]}}"
    if [[ "$*" == *"--jq"* ]]; then
        # Extract the --jq arg and pipe body through real jq
        jq_arg=""
        while [[ $# -gt 0 ]]; do
            if [[ "$1" == "--jq" ]]; then
                jq_arg="$2"
                break
            fi
            shift
        done
        echo "$body" | jq -r "$jq_arg"
    else
        echo "$body"
    fi
    exit 0
fi
echo "gh mock: unhandled call: $*" >&2
exit 1
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/gh"

    # Real jq
    if command -v jq &>/dev/null; then
        ln -sf "$(command -v jq)" "$BATS_TEST_TMPDIR/bin/jq"
    fi

    export PATH="$BATS_TEST_TMPDIR/bin:$PATH"
}

teardown() {
    rm -rf "$BATS_TEST_TMPDIR"
}

# Build a comments JSON from one body per arg.
make_comments() {
    local out='{"comments":['
    local first=true
    for body in "$@"; do
        if [[ "$first" == "true" ]]; then first=false; else out+=','; fi
        # JSON-escape: double-quotes and newlines
        local esc="${body//\\/\\\\}"
        esc="${esc//\"/\\\"}"
        esc="${esc//$'\n'/\\n}"
        out+="{\"body\":\"${esc}\"}"
    done
    out+=']}'
    echo "$out"
}

@test "check_proof_gate fails when neither MP4 nor FDS Verification present" {
    GH_MOCK_COMMENTS_JSON=$(make_comments "Some random comment")
    export GH_MOCK_COMMENTS_JSON

    run bash -c "source '$ADO_COMMON' && check_proof_gate 42 fake/repo"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[8/11] MP4 missing"* ]]
    [[ "$output" == *"[9/11] FDS Verification missing"* ]]
    [[ "$output" == *"Discord Ping Protocol"* ]]
}

@test "check_proof_gate fails with [9/11] only when MP4 is present but FDS Verification is missing" {
    GH_MOCK_COMMENTS_JSON=$(make_comments "MP4: /tmp/proof.mp4")
    export GH_MOCK_COMMENTS_JSON

    run bash -c "source '$ADO_COMMON' && check_proof_gate 42 fake/repo"
    [ "$status" -eq 1 ]
    [[ "$output" != *"[8/11] MP4 missing"* ]]
    [[ "$output" == *"[9/11] FDS Verification missing"* ]]
}

@test "check_proof_gate fails with [8/11] only when FDS Verification is present but MP4 is missing" {
    GH_MOCK_COMMENTS_JSON=$(make_comments "**FDS Verification (screenshot + AI)**
- Screen X: pass")
    export GH_MOCK_COMMENTS_JSON

    run bash -c "source '$ADO_COMMON' && check_proof_gate 42 fake/repo"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[8/11] MP4 missing"* ]]
    [[ "$output" != *"[9/11] FDS Verification missing"* ]]
}

@test "check_proof_gate succeeds when both MP4 and FDS Verification are present" {
    GH_MOCK_COMMENTS_JSON=$(make_comments \
        "MP4: /tmp/proof.mp4" \
        "**FDS Verification (screenshot + AI)**
- Screen X: pass")
    export GH_MOCK_COMMENTS_JSON

    run bash -c "source '$ADO_COMMON' && check_proof_gate 42 fake/repo"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Proof gate"* ]]
    [[ "$output" == *"both posted"* ]]
}

@test "check_proof_gate ignores comments that merely quote the FDS sentinel inline (false-positive guard)" {
    # A discussion comment that mentions the sentinel in backticks must NOT
    # satisfy the gate — only a comment that STARTS with the sentinel does.
    GH_MOCK_COMMENTS_JSON=$(make_comments \
        "MP4: /tmp/proof.mp4" \
        "Looking for \`**FDS Verification (screenshot + AI)**\` headers in the issue.")
    export GH_MOCK_COMMENTS_JSON

    run bash -c "source '$ADO_COMMON' && check_proof_gate 42 fake/repo"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[9/11] FDS Verification missing"* ]]
}

@test "check_proof_gate ignores comments that merely mention .mp4 in prose (MP4 false-positive guard)" {
    # A discussion comment that says "use .mp4 Playwright recording, not ffmpeg"
    # must NOT satisfy the MP4 gate — only a comment whose body has a line
    # starting with MP4:/Proof:/Recording:/Video: followed by .mp4 does.
    GH_MOCK_COMMENTS_JSON=$(make_comments \
        "**FDS Verification (screenshot + AI)**
- Screen X: pass" \
        "Reminder for the dev: don't use ffmpeg, use .mp4 Playwright recording.")
    export GH_MOCK_COMMENTS_JSON

    run bash -c "source '$ADO_COMMON' && check_proof_gate 42 fake/repo"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[8/11] MP4 missing"* ]]
}

@test "check_proof_gate accepts MP4 with Proof:/Recording:/Video: prefixes (case-insensitive)" {
    # Each prefix variant should satisfy the MP4 gate.
    for prefix in "MP4:" "Proof:" "Recording:" "Video:" "mp4:" "PROOF:"; do
        GH_MOCK_COMMENTS_JSON=$(make_comments \
            "${prefix} /tmp/proof.mp4" \
            "**FDS Verification (screenshot + AI)**
- Screen X: pass")
        export GH_MOCK_COMMENTS_JSON

        run bash -c "source '$ADO_COMMON' && check_proof_gate 42 fake/repo"
        [ "$status" -eq 0 ] || { echo "prefix '$prefix' failed: $output"; return 1; }
    done
}

@test "check_proof_gate rejects .webm recordings (MP4-only policy, issue #122)" {
    # Playwright's record_video_dir default is .webm. The dev-facing pattern in
    # domain/technical/E2E_TESTING.md requires a ffmpeg transcode to .mp4 at
    # record time so the .webm never leaves the script. If it does leak into a
    # comment, the gate must still reject it — .webm/.mov are not valid proof
    # per the owner directive (#122). Guards against a future agent silently
    # re-broadening the regex.
    GH_MOCK_COMMENTS_JSON=$(make_comments \
        "MP4: /tmp/proof.webm" \
        "**FDS Verification (screenshot + AI)**
- Screen X: pass")
    export GH_MOCK_COMMENTS_JSON

    run bash -c "source '$ADO_COMMON' && check_proof_gate 42 fake/repo"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[8/11] MP4 missing"* ]]
}

@test "check_proof_gate rejects .mov recordings (MP4-only policy, issue #122)" {
    GH_MOCK_COMMENTS_JSON=$(make_comments \
        "Recording: /tmp/proof.mov" \
        "**FDS Verification (screenshot + AI)**
- Screen X: pass")
    export GH_MOCK_COMMENTS_JSON

    run bash -c "source '$ADO_COMMON' && check_proof_gate 42 fake/repo"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[8/11] MP4 missing"* ]]
}

@test "check_proof_gate errors with code 2 on missing arguments" {
    run bash -c "source '$ADO_COMMON' && check_proof_gate"
    [ "$status" -eq 2 ]
    [[ "$output" == *"requires"* ]]
}

# ---------------------------------------------------------------------------
# resolve_gh_repo (PR #78 review point 1) — single source of truth shared by
# ado-push and ado-transition.
# ---------------------------------------------------------------------------

@test "resolve_gh_repo returns CLAIRE_WAIT_REPO when set" {
    export CLAIRE_WAIT_REPO="explicit/repo"
    # Override gh to assert it's not consulted when env wins.
    cat > "$BATS_TEST_TMPDIR/bin/gh" <<'SH'
#!/usr/bin/env bash
echo "gh should not be called when CLAIRE_WAIT_REPO is set" >&2
exit 99
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/gh"

    run bash -c "source '$ADO_COMMON' && resolve_gh_repo fallback/repo"
    [ "$status" -eq 0 ]
    [ "$output" = "explicit/repo" ]
}

@test "resolve_gh_repo falls back to gh repo view when env unset" {
    unset CLAIRE_WAIT_REPO
    cat > "$BATS_TEST_TMPDIR/bin/gh" <<'SH'
#!/usr/bin/env bash
if [[ "$*" == *"repo view"* ]]; then echo "detected/repo"; exit 0; fi
exit 1
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/gh"

    run bash -c "source '$ADO_COMMON' && resolve_gh_repo fallback/repo"
    [ "$status" -eq 0 ]
    [ "$output" = "detected/repo" ]
}

@test "resolve_gh_repo falls back to caller default when env unset and gh repo view fails" {
    unset CLAIRE_WAIT_REPO
    cat > "$BATS_TEST_TMPDIR/bin/gh" <<'SH'
#!/usr/bin/env bash
exit 1
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/gh"

    run bash -c "source '$ADO_COMMON' && resolve_gh_repo fallback/repo"
    [ "$status" -eq 0 ]
    [ "$output" = "fallback/repo" ]
}

@test "resolve_gh_repo returns 1 when env unset, gh fails, and no default is provided" {
    unset CLAIRE_WAIT_REPO
    cat > "$BATS_TEST_TMPDIR/bin/gh" <<'SH'
#!/usr/bin/env bash
exit 1
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/gh"

    run bash -c "source '$ADO_COMMON' && resolve_gh_repo"
    [ "$status" -eq 1 ]
}
