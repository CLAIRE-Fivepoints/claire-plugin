#!/usr/bin/env bats
# tests/scripts/test_attempt_auto_rebase.bats
#
# Tests for attempt_auto_rebase_onto_ado() in domain/scripts/ado_common.sh
# (issue #86 — the "scripter tout sauf merge conflicts" path).
#
# The function must replay only the dev's OWN commits (those added after
# branching from the GitHub mirror) onto ADO origin/$target — never replay
# mirror-divergent history. On conflict, it must abort cleanly and leave the
# branch exactly where it was.
#
# Strategy: build real fixture git repos (two remotes — ADO-like origin +
# GitHub-like mirror) so the merge-base math and rebase outcomes are genuine.

ADO_COMMON="${BATS_TEST_DIRNAME}/../../domain/scripts/ado_common.sh"

setup() {
    export GIT_AUTHOR_NAME="bats"
    export GIT_AUTHOR_EMAIL="bats@test.local"
    export GIT_COMMITTER_NAME="bats"
    export GIT_COMMITTER_EMAIL="bats@test.local"

    ORIGIN_REPO="$BATS_TEST_TMPDIR/origin.git"    # ADO stand-in
    MIRROR_REPO="$BATS_TEST_TMPDIR/mirror.git"    # GitHub mirror stand-in
    WORK_REPO="$BATS_TEST_TMPDIR/work"

    git init --bare --initial-branch=dev "$ORIGIN_REPO" >/dev/null
    git init --bare --initial-branch=dev "$MIRROR_REPO" >/dev/null

    # Work clone — seed with one commit on dev; push to both remotes.
    git init --initial-branch=dev "$WORK_REPO" >/dev/null
    pushd "$WORK_REPO" >/dev/null
    echo "seed" > seed.txt
    git add seed.txt
    git commit -q -m "seed commit"
    git remote add origin "$ORIGIN_REPO"
    git remote add github "$MIRROR_REPO"
    git push -q origin dev
    git push -q github dev
    popd >/dev/null
}

teardown() {
    rm -rf "$BATS_TEST_TMPDIR"
}

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

@test "attempt_auto_rebase_onto_ado errors with code 2 on missing args" {
    run bash -c "source '$ADO_COMMON' && attempt_auto_rebase_onto_ado"
    [ "$status" -eq 2 ]
    [[ "$output" == *"requires"* ]]
}

@test "attempt_auto_rebase_onto_ado errors with code 2 when repo_path is not a git repo" {
    run bash -c "source '$ADO_COMMON' && attempt_auto_rebase_onto_ado feature/1-x dev /nonexistent"
    [ "$status" -eq 2 ]
    [[ "$output" == *"not a git repository"* ]]
}

@test "attempt_auto_rebase_onto_ado errors with code 2 when mirror remote is missing" {
    pushd "$WORK_REPO" >/dev/null
    git checkout -q -b feature/1-clean dev
    git remote remove github
    popd >/dev/null

    run bash -c "source '$ADO_COMMON' && attempt_auto_rebase_onto_ado feature/1-clean dev '$WORK_REPO'"
    [ "$status" -eq 2 ]
    [[ "$output" == *"mirror remote"* ]]
}

@test "attempt_auto_rebase_onto_ado errors with code 2 when branch does not exist" {
    run bash -c "source '$ADO_COMMON' && attempt_auto_rebase_onto_ado feature/missing dev '$WORK_REPO'"
    [ "$status" -eq 2 ]
    [[ "$output" == *"does not exist"* ]]
}

@test "attempt_auto_rebase_onto_ado errors with code 2 when worktree is dirty" {
    pushd "$WORK_REPO" >/dev/null
    git checkout -q -b feature/dirty dev
    echo "dirty" > uncommitted.txt
    git add uncommitted.txt
    popd >/dev/null

    run bash -c "source '$ADO_COMMON' && attempt_auto_rebase_onto_ado feature/dirty dev '$WORK_REPO'"
    [ "$status" -eq 2 ]
    [[ "$output" == *"uncommitted"* ]]
}

# ---------------------------------------------------------------------------
# Happy path — the #71 scenario with non-conflicting commits.
# ---------------------------------------------------------------------------

@test "attempt_auto_rebase_onto_ado cleanly replays dev commits onto ADO dev (happy path)" {
    pushd "$WORK_REPO" >/dev/null

    # ADO dev advances: adds a non-conflicting file.
    local scratch="$BATS_TEST_TMPDIR/scratch-ado"
    git clone -q "$ORIGIN_REPO" "$scratch"
    pushd "$scratch" >/dev/null
    git checkout -q dev
    echo "ado-only" > ado-only.txt
    git add ado-only.txt
    git commit -q -m "ADO dev advance (non-conflict)"
    git push -q origin dev
    popd >/dev/null
    rm -rf "$scratch"

    # Mirror dev advances differently: adds another non-conflicting file.
    # This is the divergence that makes a plain `git rebase origin/dev` fail
    # on #71-like scenarios — we want to exclude mirror-only history.
    local mscratch="$BATS_TEST_TMPDIR/scratch-mirror"
    git clone -q "$MIRROR_REPO" "$mscratch"
    pushd "$mscratch" >/dev/null
    git checkout -q dev
    echo "mirror-only" > mirror-only.txt
    git add mirror-only.txt
    git commit -q -m "mirror dev advance (divergent from ADO)"
    # The scratch clone's remote is named "origin" (it was cloned FROM
    # MIRROR_REPO) — push to that, not to "github".
    git push -q origin dev
    popd >/dev/null
    rm -rf "$mscratch"

    # Fetch mirror into the work repo, branch off mirror/dev (so the branch
    # carries the mirror-only commit), then add a real feature commit.
    git fetch -q github dev
    git checkout -q -b feature/71-onto-test github/dev
    echo "feature" > feature.txt
    git add feature.txt
    git commit -q -m "real feature commit"

    popd >/dev/null

    run bash -c "source '$ADO_COMMON' && attempt_auto_rebase_onto_ado feature/71-onto-test dev '$WORK_REPO'"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Auto-rebase"* ]]

    # After the rebase, the branch must contain:
    #   - seed (from both)
    #   - ado-only.txt (from origin/dev)
    #   - feature.txt (our real commit)
    # and must NOT contain mirror-only.txt (divergent mirror history, excluded).
    pushd "$WORK_REPO" >/dev/null
    git checkout -q feature/71-onto-test
    [ -f seed.txt ]
    [ -f ado-only.txt ]
    [ -f feature.txt ]
    [ ! -f mirror-only.txt ]
    popd >/dev/null
}

# ---------------------------------------------------------------------------
# Conflict path — branch CANNOT be rebased cleanly; must abort and leave
# the branch exactly where it was.
# ---------------------------------------------------------------------------

@test "attempt_auto_rebase_onto_ado aborts cleanly on conflict and leaves branch untouched" {
    pushd "$WORK_REPO" >/dev/null

    # Both ADO dev and the feature branch modify the SAME file with
    # incompatible changes → guaranteed rebase conflict.
    local scratch="$BATS_TEST_TMPDIR/scratch-ado"
    git clone -q "$ORIGIN_REPO" "$scratch"
    pushd "$scratch" >/dev/null
    git checkout -q dev
    echo "ADO version" > shared.txt
    git add shared.txt
    git commit -q -m "ADO adds shared.txt"
    git push -q origin dev
    popd >/dev/null
    rm -rf "$scratch"

    git checkout -q -b feature/conflict dev
    echo "dev version" > shared.txt
    git add shared.txt
    git commit -q -m "feature adds shared.txt with conflicting content"

    local pre_head
    pre_head=$(git rev-parse feature/conflict)

    popd >/dev/null

    run bash -c "source '$ADO_COMMON' && attempt_auto_rebase_onto_ado feature/conflict dev '$WORK_REPO'"
    [ "$status" -eq 1 ]
    [[ "$output" == *"conflict"* || "$output" == *"aborting"* ]]

    # Post-abort: branch HEAD must be unchanged; no rebase in progress.
    pushd "$WORK_REPO" >/dev/null
    local post_head
    post_head=$(git rev-parse feature/conflict)
    [ "$pre_head" = "$post_head" ]
    # No .git/rebase-apply / rebase-merge dir should remain
    [ ! -d .git/rebase-apply ]
    [ ! -d .git/rebase-merge ]
    popd >/dev/null
}

# ---------------------------------------------------------------------------
# Already-synced branch — no-op, returns 0.
# ---------------------------------------------------------------------------

@test "attempt_auto_rebase_onto_ado succeeds as a no-op when branch is already on ADO dev tip" {
    pushd "$WORK_REPO" >/dev/null
    git checkout -q -b feature/already-synced dev
    popd >/dev/null

    run bash -c "source '$ADO_COMMON' && attempt_auto_rebase_onto_ado feature/already-synced dev '$WORK_REPO'"
    [ "$status" -eq 0 ]
}
