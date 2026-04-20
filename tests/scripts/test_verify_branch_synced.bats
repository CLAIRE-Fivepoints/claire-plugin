#!/usr/bin/env bats
# tests/scripts/test_verify_branch_synced.bats
#
# Tests for verify_branch_synced_with_ado_dev() in domain/scripts/ado_common.sh
# (issue #86).
#
# The incident this guard prevents: a feature branch whose merge-base with ADO
# dev is several commits behind the ADO dev tip gets pushed to ADO, producing
# a PR that mixes dozens of unrelated mirror-history commits with the feature
# work (issue #71 / PR #76 — 65 commits of chaos).
#
# Strategy: build real fixture git repos (not mocks) — two repos wired as
# "origin" + feature branch — so the merge-base / rev-parse math is genuine.
# Each test sets up its own topology under $BATS_TEST_TMPDIR.

ADO_COMMON="${BATS_TEST_DIRNAME}/../../domain/scripts/ado_common.sh"

setup() {
    # Isolated git identity so commits don't fail in CI
    export GIT_AUTHOR_NAME="bats"
    export GIT_AUTHOR_EMAIL="bats@test.local"
    export GIT_COMMITTER_NAME="bats"
    export GIT_COMMITTER_EMAIL="bats@test.local"

    ORIGIN_REPO="$BATS_TEST_TMPDIR/origin.git"
    WORK_REPO="$BATS_TEST_TMPDIR/work"

    # Bare origin (stands in for the ADO remote)
    git init --bare --initial-branch=dev "$ORIGIN_REPO" >/dev/null

    # Work clone — seed with one commit on dev, push to origin
    git init --initial-branch=dev "$WORK_REPO" >/dev/null
    pushd "$WORK_REPO" >/dev/null
    echo "initial" > README.md
    git add README.md
    git commit -q -m "initial commit on dev"
    git remote add origin "$ORIGIN_REPO"
    git push -q origin dev
    popd >/dev/null
}

teardown() {
    rm -rf "$BATS_TEST_TMPDIR"
}

# Helper: add a commit to origin/dev from a scratch clone, so the work repo's
# origin/dev falls behind until it fetches.
advance_origin_dev() {
    local scratch="$BATS_TEST_TMPDIR/scratch-$RANDOM"
    git clone -q "$ORIGIN_REPO" "$scratch"
    pushd "$scratch" >/dev/null
    git checkout -q dev
    echo "advance" >> README.md
    git commit -qa -m "advance dev on ADO"
    git push -q origin dev
    popd >/dev/null
    rm -rf "$scratch"
}

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

@test "verify_branch_synced_with_ado_dev errors with code 2 on missing args" {
    run bash -c "source '$ADO_COMMON' && verify_branch_synced_with_ado_dev"
    [ "$status" -eq 2 ]
    [[ "$output" == *"requires"* ]]
}

@test "verify_branch_synced_with_ado_dev errors with code 2 when repo_path is not a git repo" {
    run bash -c "source '$ADO_COMMON' && verify_branch_synced_with_ado_dev feature/1-x dev /nonexistent/path"
    [ "$status" -eq 2 ]
    [[ "$output" == *"not a git repository"* ]]
}

@test "verify_branch_synced_with_ado_dev errors with code 2 when branch does not exist" {
    run bash -c "source '$ADO_COMMON' && verify_branch_synced_with_ado_dev feature/1-missing dev '$WORK_REPO'"
    [ "$status" -eq 2 ]
    [[ "$output" == *"does not exist"* ]]
}

# ---------------------------------------------------------------------------
# Happy path: fast-forward branch
# ---------------------------------------------------------------------------

@test "verify_branch_synced_with_ado_dev passes when branch is fast-forward with origin/dev" {
    # Create feature branch off dev (same tip) with one extra commit.
    # merge-base(feature, origin/dev) == origin/dev tip — the invariant holds.
    pushd "$WORK_REPO" >/dev/null
    git checkout -q -b feature/1-clean dev
    echo "feature" > feature.txt
    git add feature.txt
    git commit -q -m "feature commit"
    popd >/dev/null

    run bash -c "source '$ADO_COMMON' && verify_branch_synced_with_ado_dev feature/1-clean dev '$WORK_REPO'"
    [ "$status" -eq 0 ]
    [[ "$output" == *"fast-forward with origin/dev"* ]]
}

# ---------------------------------------------------------------------------
# Fail path: divergent (ahead + behind) — the #71 scenario
# ---------------------------------------------------------------------------

@test "verify_branch_synced_with_ado_dev fails when origin/dev advanced after branching (the #71 scenario)" {
    # 1. Create feature branch off the current dev tip.
    pushd "$WORK_REPO" >/dev/null
    git checkout -q -b feature/71-divergent dev
    echo "feature" > feature.txt
    git add feature.txt
    git commit -q -m "feature commit"
    popd >/dev/null

    # 2. Advance origin/dev from an outside clone — simulates ADO dev moving
    #    forward after the dev agent branched off the (now stale) mirror tip.
    advance_origin_dev

    # 3. The function must fetch, see the new origin/dev, and detect that
    #    merge-base(feature, origin/dev) is now BEHIND origin/dev tip.
    run bash -c "source '$ADO_COMMON' && verify_branch_synced_with_ado_dev feature/71-divergent dev '$WORK_REPO'"
    [ "$status" -eq 1 ]
    [[ "$output" == *"not up-to-date with ADO dev"* ]]
    [[ "$output" == *"Pushing this branch to ADO will create a chaotic PR"* ]]
    # Both recovery options must be printed — the dev never has to guess.
    [[ "$output" == *"Cherry-pick your feature commits onto a fresh branch"* ]]
    [[ "$output" == *"Reset your existing branch to ADO dev + cherry-pick"* ]]
}

# ---------------------------------------------------------------------------
# Fail path: branch strictly behind (no feature commits)
# ---------------------------------------------------------------------------

@test "verify_branch_synced_with_ado_dev fails when branch is strictly behind origin/dev" {
    # Feature branch at the old dev tip, origin/dev advances, feature has
    # no commits of its own — still a mismatch.
    pushd "$WORK_REPO" >/dev/null
    git checkout -q -b feature/2-stale dev
    popd >/dev/null

    advance_origin_dev

    run bash -c "source '$ADO_COMMON' && verify_branch_synced_with_ado_dev feature/2-stale dev '$WORK_REPO'"
    [ "$status" -eq 1 ]
    [[ "$output" == *"not up-to-date with ADO dev"* ]]
    [[ "$output" == *"Commits behind:"* ]]
}

# ---------------------------------------------------------------------------
# --target parameter is honored (not hard-coded to "dev")
# ---------------------------------------------------------------------------

@test "verify_branch_synced_with_ado_dev honors custom target branch" {
    # Create a release branch on origin, make our feature branch diverge
    # from it, and check the function correctly compares against 'release'
    # (not the default 'dev'). Proves the target parameter is wired end-to-end.
    pushd "$WORK_REPO" >/dev/null
    git checkout -q -b release dev
    git push -q origin release
    git checkout -q -b feature/3-release-target release
    echo "feature" > feature.txt
    git add feature.txt
    git commit -q -m "feature commit"
    popd >/dev/null

    # Advance origin/release from outside.
    local scratch="$BATS_TEST_TMPDIR/scratch-rel-$RANDOM"
    git clone -q "$ORIGIN_REPO" "$scratch"
    pushd "$scratch" >/dev/null
    git checkout -q release
    echo "advance" >> README.md
    git commit -qa -m "advance release on ADO"
    git push -q origin release
    popd >/dev/null
    rm -rf "$scratch"

    run bash -c "source '$ADO_COMMON' && verify_branch_synced_with_ado_dev feature/3-release-target release '$WORK_REPO'"
    [ "$status" -eq 1 ]
    [[ "$output" == *"not up-to-date with ADO release"* ]]
}
