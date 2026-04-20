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

@test "check_proof_gate errors with code 2 on missing arguments" {
    run bash -c "source '$ADO_COMMON' && check_proof_gate"
    [ "$status" -eq 2 ]
    [[ "$output" == *"requires"* ]]
}
