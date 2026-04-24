#!/usr/bin/env bats
# tests/scripts/test_install_hooks.bats
#
# Smoke test for domain/commands/install-hooks.sh: installing twice must
# leave the active hooks executable and byte-equal to the plugin sources —
# i.e. install is idempotent. (Issue #119 wires this command into the dev
# session checklist; a broken idempotency guarantee would cause the second
# session-start run to corrupt the hook.)

INSTALL_HOOKS="${BATS_TEST_DIRNAME}/../../domain/commands/install-hooks.sh"
HOOK_SRC_PRECOMMIT="${BATS_TEST_DIRNAME}/../../domain/hooks/pre-commit"
HOOK_SRC_PREPUSH="${BATS_TEST_DIRNAME}/../../domain/hooks/pre-push"

setup() {
    export GIT_AUTHOR_NAME="bats"
    export GIT_AUTHOR_EMAIL="bats@test.local"
    export GIT_COMMITTER_NAME="bats"
    export GIT_COMMITTER_EMAIL="bats@test.local"

    # Only target repo: a fake TFIOneGit under a tmpdir.
    FAKE_TFIONE="$BATS_TEST_TMPDIR/TFIOneGit"
    git init -q "$FAKE_TFIONE"
    pushd "$FAKE_TFIONE" >/dev/null
    echo "seed" > README.md
    git add README.md
    git commit -q -m "seed"
    popd >/dev/null

    # Stub `claire` on PATH so the script's `claire repo list` returns empty —
    # isolating the test from the user's real claire registry.
    STUB_BIN="$BATS_TEST_TMPDIR/bin"
    mkdir -p "$STUB_BIN"
    cat > "$STUB_BIN/claire" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$STUB_BIN/claire"
    export PATH="$STUB_BIN:$PATH"

    export FIVEPOINTS_REPO_PATH="$FAKE_TFIONE"
}

teardown() {
    rm -rf "$BATS_TEST_TMPDIR"
}

@test "install-hooks twice is idempotent and produces hooks byte-equal to the plugin sources" {
    run bash "$INSTALL_HOOKS"
    [ "$status" -eq 0 ]

    [ -x "$FAKE_TFIONE/.git/hooks/pre-commit" ]
    [ -x "$FAKE_TFIONE/.git/hooks/pre-push" ]
    cmp -s "$HOOK_SRC_PRECOMMIT" "$FAKE_TFIONE/.git/hooks/pre-commit"
    cmp -s "$HOOK_SRC_PREPUSH"   "$FAKE_TFIONE/.git/hooks/pre-push"

    # Second run — must succeed and leave the active hooks byte-equal to
    # the plugin sources (the backup from this run should match them too).
    run bash "$INSTALL_HOOKS"
    [ "$status" -eq 0 ]

    cmp -s "$HOOK_SRC_PRECOMMIT" "$FAKE_TFIONE/.git/hooks/pre-commit"
    cmp -s "$HOOK_SRC_PREPUSH"   "$FAKE_TFIONE/.git/hooks/pre-push"

    # At least one backup file must exist per hook (the second install backs up the first).
    ls "$FAKE_TFIONE"/.git/hooks/pre-commit.bak.* >/dev/null
    ls "$FAKE_TFIONE"/.git/hooks/pre-push.bak.*   >/dev/null
}
