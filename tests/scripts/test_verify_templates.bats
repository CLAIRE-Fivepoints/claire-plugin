#!/usr/bin/env bats
# tests/scripts/test_verify_templates.bats
#
# Tests for domain/commands/verify-templates.sh (issue #80).
# Verifies the single-source-of-truth guard: the fivepoints-dev persona must
# not embed [N/11] checklist step markers from CHECKLIST_DEV_PIPELINE.

VERIFY_TEMPLATES="${BATS_TEST_DIRNAME}/../../domain/commands/verify-templates.sh"
PERSONA_FILE="${BATS_TEST_DIRNAME}/../../domain/persona/fivepoints-dev.md"
CHECKLIST_FILE="${BATS_TEST_DIRNAME}/../../domain/operational/CHECKLIST_DEV_PIPELINE.md"

# ---------------------------------------------------------------------------
# Live file assertions — the real repo state must satisfy the invariant
# ---------------------------------------------------------------------------

@test "fivepoints-dev.md contains no embedded checklist step definitions" {
    # A step *definition* is a line starting with a markdown checkbox: "- [ ] [N/11]".
    # Inline cross-references like "see [10/11]" are allowed and not counted.
    for step in 1 2 3 4 5 6 7 8 9 10 11; do
        run grep -cE "^- \[[ x]\] \[${step}/11\]" "$PERSONA_FILE"
        [ "$output" -eq 0 ]
    done
}

@test "CHECKLIST_DEV_PIPELINE.md contains all 11 steps (single source of truth)" {
    # Use the same line-start pattern as the script so inline cross-references
    # ("see [7/11]") do not produce false positives.
    for step in 1 2 3 4 5 6 7 8 9 10 11; do
        run grep -cE "^- \[[ x]\] \[${step}/11\]" "$CHECKLIST_FILE"
        [ "$output" -ge 1 ]
    done
}

@test "verify-templates passes on the real files" {
    run bash "$VERIFY_TEMPLATES"
    [ "$status" -eq 0 ]
    [[ "$output" == *"no duplication"* ]]
}

@test "verify-templates --verbose passes on the real files" {
    run bash "$VERIFY_TEMPLATES" --verbose
    [ "$status" -eq 0 ]
    [[ "$output" == *"No checklist steps embedded"* ]]
    [[ "$output" == *"All 11 steps present"* ]]
}

# ---------------------------------------------------------------------------
# Isolation tests — synthetic persona/checklist dirs in tmpdir
# ---------------------------------------------------------------------------

setup() {
    FAKE_DOMAIN="$BATS_TEST_TMPDIR/domain"
    mkdir -p "$FAKE_DOMAIN/persona" "$FAKE_DOMAIN/operational"

    FAKE_PERSONA="$FAKE_DOMAIN/persona/fivepoints-dev.md"
    FAKE_CHECKLIST="$FAKE_DOMAIN/operational/CHECKLIST_DEV_PIPELINE.md"
}

teardown() {
    rm -rf "$BATS_TEST_TMPDIR"
}

_write_clean_persona() {
    cat > "$FAKE_PERSONA" <<'EOF'
# FIVEPOINTS-DEV

Identity only. No checklist steps here.
Checklist is in operational/CHECKLIST_DEV_PIPELINE.
EOF
}

_write_checklist_with_all_steps() {
    {
        for step in 1 2 3 4 5 6 7 8 9 10 11; do
            echo "- [ ] [${step}/11] Step ${step}"
        done
    } > "$FAKE_CHECKLIST"
}

@test "verify-templates passes when persona has no step markers" {
    _write_clean_persona
    _write_checklist_with_all_steps

    # Point script at fake domain by symlinking script to run from FAKE_DOMAIN
    # The script resolves DOMAIN_DIR as two levels up from its own location;
    # write a wrapper that sets up that path structure.
    FAKE_COMMANDS="$FAKE_DOMAIN/commands"
    mkdir -p "$FAKE_COMMANDS"
    cp "$VERIFY_TEMPLATES" "$FAKE_COMMANDS/verify-templates.sh"

    run bash "$FAKE_COMMANDS/verify-templates.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"no duplication"* ]]
}

@test "verify-templates fails when persona embeds a checklist step" {
    # Persona with [3/11] as an embedded step definition — simulates pre-lean-v3 state.
    # (Inline cross-references like "see [3/11]" would NOT trigger the check.)
    cat > "$FAKE_PERSONA" <<'EOF'
# FIVEPOINTS-DEV

- [ ] [3/11] Implement the requirements
EOF
    _write_checklist_with_all_steps

    FAKE_COMMANDS="$FAKE_DOMAIN/commands"
    mkdir -p "$FAKE_COMMANDS"
    cp "$VERIFY_TEMPLATES" "$FAKE_COMMANDS/verify-templates.sh"

    run bash "$FAKE_COMMANDS/verify-templates.sh"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "FAILED" ]]
}

@test "verify-templates fails when persona embeds multiple checklist steps" {
    cat > "$FAKE_PERSONA" <<'EOF'
# FIVEPOINTS-DEV

- [ ] [6/11] Start test environment
- [ ] [8/11] Run E2E tests
- [ ] [9/11] Screenshot + visual verification
EOF
    _write_checklist_with_all_steps

    FAKE_COMMANDS="$FAKE_DOMAIN/commands"
    mkdir -p "$FAKE_COMMANDS"
    cp "$VERIFY_TEMPLATES" "$FAKE_COMMANDS/verify-templates.sh"

    run bash "$FAKE_COMMANDS/verify-templates.sh"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "3 duplicate step(s)" ]]
}

@test "verify-templates fails when checklist file is missing a step" {
    _write_clean_persona
    # Only 10 steps — missing [7/11]
    {
        for step in 1 2 3 4 5 6 8 9 10 11; do
            echo "- [ ] [${step}/11] Step ${step}"
        done
    } > "$FAKE_CHECKLIST"

    FAKE_COMMANDS="$FAKE_DOMAIN/commands"
    mkdir -p "$FAKE_COMMANDS"
    cp "$VERIFY_TEMPLATES" "$FAKE_COMMANDS/verify-templates.sh"

    run bash "$FAKE_COMMANDS/verify-templates.sh"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "FAILED" ]]
}

@test "verify-templates exits 1 when persona file is missing" {
    _write_checklist_with_all_steps
    # No persona file — skip _write_clean_persona

    FAKE_COMMANDS="$FAKE_DOMAIN/commands"
    mkdir -p "$FAKE_COMMANDS"
    cp "$VERIFY_TEMPLATES" "$FAKE_COMMANDS/verify-templates.sh"

    run bash "$FAKE_COMMANDS/verify-templates.sh"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "MISSING" ]]
}
