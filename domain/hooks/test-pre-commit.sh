#!/usr/bin/env bash
# test-pre-commit.sh — Smoke test for the TFI One pre-commit hook
#
# Runs each check in isolation using a temp git repo.
# Usage: bash test-pre-commit.sh [--hook <path>]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="${1:-$SCRIPT_DIR/pre-commit}"

PASS=0
FAIL=0

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
TMPDIR_ROOT=$(mktemp -d)
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

make_repo() {
    local branch="${1:-feature/10856-test}"
    local dir
    dir=$(mktemp -d -p "$TMPDIR_ROOT")
    git -C "$dir" init -q
    git -C "$dir" config user.email "test@test.com"
    git -C "$dir" config user.name "Test"
    git -C "$dir" checkout -q -b "$branch" 2>/dev/null || git -C "$dir" switch -q -c "$branch"
    # initial empty commit so HEAD exists
    git -C "$dir" commit -q --allow-empty -m "init"
    echo "$dir"
}

expect_fail() {
    local label="$1"
    local repo="$2"
    local output
    # Capture output; || true prevents set -e from aborting on hook's exit code 1
    output=$(cd "$repo" && bash "$HOOK" 2>&1) || true
    if echo "$output" | grep -q "FAILED"; then
        echo "  ✅ PASS  $label"
        (( PASS++ )) || true
    else
        echo "  ❌ FAIL  $label — hook should have blocked but didn't"
        (( FAIL++ )) || true
    fi
}

expect_pass() {
    local label="$1"
    local repo="$2"
    local output
    output=$(cd "$repo" && bash "$HOOK" 2>&1) || true
    if echo "$output" | grep -q "FAILED"; then
        echo "  ❌ FAIL  $label — hook blocked but shouldn't have"
        echo "           $output"
        (( FAIL++ )) || true
    else
        echo "  ✅ PASS  $label"
        (( PASS++ )) || true
    fi
}

# ─────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  TFI One Pre-Commit Hook — Test Suite"
echo "═══════════════════════════════════────────────────────"
echo ""

# ─────────────────────────────────────────────────────────────
# Check 1 — Branch naming
# ─────────────────────────────────────────────────────────────
echo "[ Check 1 — Branch naming ]"

# Should FAIL: random branch name
R=$(make_repo "my-random-branch")
expect_fail "bad branch: 'my-random-branch'" "$R"

# Should FAIL: feature/ without ticket ID
R=$(make_repo "feature/add-something")
expect_fail "bad branch: 'feature/add-something' (no numeric ID)" "$R"

# Should FAIL: bugfix/ without ticket ID
R=$(make_repo "bugfix/fix-something")
expect_fail "bad branch: 'bugfix/fix-something' (no numeric ID)" "$R"

# Should PASS: feature with numeric ID
R=$(make_repo "feature/10856-client-export")
expect_pass "good branch: 'feature/10856-client-export'" "$R"

# Should PASS: bugfix with numeric ID
R=$(make_repo "bugfix/10901-fix-null-reference")
expect_pass "good branch: 'bugfix/10901-fix-null-reference'" "$R"

# Should PASS: main (exempt)
R=$(make_repo "main")
expect_pass "exempt branch: 'main'" "$R"

# Should PASS: dev (exempt)
R=$(make_repo "dev")
expect_pass "exempt branch: 'dev'" "$R"

echo ""

# ─────────────────────────────────────────────────────────────
# Check 2 — com.tfione.api.d.ts not staged
# ─────────────────────────────────────────────────────────────
echo "[ Check 2 — com.tfione.api.d.ts not staged ]"

# Should FAIL: d.ts file staged
R=$(make_repo "feature/10856-test")
echo "// generated" > "$R/com.tfione.api.d.ts"
git -C "$R" add "com.tfione.api.d.ts"
expect_fail "com.tfione.api.d.ts staged → blocked" "$R"

# Should PASS: d.ts not staged (only other file)
R=$(make_repo "feature/10856-test")
echo "class Foo {}" > "$R/Foo.cs"
git -C "$R" add "Foo.cs"
expect_pass "no com.tfione.api.d.ts staged → allowed" "$R"

echo ""

# ─────────────────────────────────────────────────────────────
# Check 3 — No GRANT/DENY in migrations
# ─────────────────────────────────────────────────────────────
echo "[ Check 3 — No GRANT/DENY in migrations ]"

# Should FAIL: migration with GRANT
R=$(make_repo "feature/10856-test")
mkdir -p "$R/com.tfione.db/migration"
cat > "$R/com.tfione.db/migration/V1.0.20260327.1234.1__add_table.sql" <<'SQL'
CREATE TABLE [client].[Client] ([ClientId] INT NOT NULL);
GRANT SELECT ON [client].[Client] TO [app_role];
SQL
git -C "$R" add "com.tfione.db/migration/V1.0.20260327.1234.1__add_table.sql"
expect_fail "migration with GRANT → blocked" "$R"

# Should FAIL: migration with DENY
R=$(make_repo "feature/10856-test")
mkdir -p "$R/com.tfione.db/migration"
cat > "$R/com.tfione.db/migration/V1.0.20260327.1234.1__add_table.sql" <<'SQL'
CREATE TABLE [client].[Client] ([ClientId] INT NOT NULL);
DENY DELETE ON [client].[Client] TO [public];
SQL
git -C "$R" add "com.tfione.db/migration/V1.0.20260327.1234.1__add_table.sql"
expect_fail "migration with DENY → blocked" "$R"

# Should PASS: migration without permissions
R=$(make_repo "feature/10856-test")
mkdir -p "$R/com.tfione.db/migration"
cat > "$R/com.tfione.db/migration/V1.0.20260327.1234.1__add_table.sql" <<'SQL'
CREATE TABLE [client].[Client] (
    [ClientId] INT NOT NULL,
    CONSTRAINT [PK_Client] PRIMARY KEY ([ClientId])
);
SQL
git -C "$R" add "com.tfione.db/migration/V1.0.20260327.1234.1__add_table.sql"
expect_pass "migration without permissions → allowed" "$R"

echo ""

# ─────────────────────────────────────────────────────────────
# Check 4 — No business logic tests
# ─────────────────────────────────────────────────────────────
echo "[ Check 4 — No business logic tests in service.test ]"

# Should FAIL: test with 'client' in namespace
R=$(make_repo "feature/10856-test")
mkdir -p "$R/com.tfione.service.test/client"
cat > "$R/com.tfione.service.test/client/ClientServiceTests.cs" <<'CS'
namespace com.tfione.service.test.client;

public class ClientServiceTests
{
    [Fact]
    public void Test() { }
}
CS
git -C "$R" add "com.tfione.service.test/client/ClientServiceTests.cs"
expect_fail "business test (namespace: .client) → blocked" "$R"

# Should FAIL: test with 'provider' in namespace
R=$(make_repo "feature/10856-test")
mkdir -p "$R/com.tfione.service.test/provider"
cat > "$R/com.tfione.service.test/provider/ProviderRepoTests.cs" <<'CS'
namespace com.tfione.service.test.provider;

public class ProviderRepoTests { }
CS
git -C "$R" add "com.tfione.service.test/provider/ProviderRepoTests.cs"
expect_fail "business test (namespace: .provider) → blocked" "$R"

# Should PASS: encryption test (allowed namespace)
R=$(make_repo "feature/10856-test")
mkdir -p "$R/com.tfione.service.test/encryption"
cat > "$R/com.tfione.service.test/encryption/EncryptorTests.cs" <<'CS'
namespace com.tfione.service.test.encryption;

public class EncryptorTests
{
    [Fact]
    public void SuccessfulEncrypt() { }
}
CS
git -C "$R" add "com.tfione.service.test/encryption/EncryptorTests.cs"
expect_pass "infra test (namespace: .encryption) → allowed" "$R"

# Should PASS: signing test (allowed namespace)
R=$(make_repo "feature/10856-test")
mkdir -p "$R/com.tfione.service.test/signing"
cat > "$R/com.tfione.service.test/signing/AdobeEndpointGeneratorTests.cs" <<'CS'
namespace com.tfione.service.test.signing;

public class AdobeEndpointGeneratorTests
{
    [Fact]
    public void UrlGeneration_BaseUrl() { }
}
CS
git -C "$R" add "com.tfione.service.test/signing/AdobeEndpointGeneratorTests.cs"
expect_pass "infra test (namespace: .signing) → allowed" "$R"

echo ""

# ─────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────
TOTAL=$(( PASS + FAIL ))
echo "═══════════════════════════════════════════════════════"
echo "  Results: $PASS/$TOTAL passed"
echo "═══════════════════════════════════════════════════════"
echo ""

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
