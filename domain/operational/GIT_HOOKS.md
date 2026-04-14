---
domain: fivepoints
category: operational
name: GIT_HOOKS
title: "Five Points — TFI One Git Hooks"
keywords: [five-points, fivepoints, git-hooks, pre-commit, pre-push, developer-gates, branch-naming, coding-standards]
updated: 2026-03-27
---

# Five Points — TFI One Git Hooks

TFI One ships git hooks in `.githooks/` (tracked in the repo) that enforce coding standards
and developer gates automatically at commit and push time. They mirror what CI runs — passing
locally guarantees passing on Azure Pipelines.

---

## Installation

Run once after cloning:

```bash
./scripts/install-hooks.sh
```

This sets `core.hooksPath = .githooks` in the local git config and makes all hooks executable.

**Manual alternative:**

```bash
git config core.hooksPath .githooks
chmod +x .githooks/*
```

**Verify installation:**

```bash
git config core.hooksPath    # should print: .githooks
ls .githooks/                # should list: pre-commit  pre-push
```

---

## `pre-commit` — Fast Checks

Runs in <1 second. Blocks the commit if any rule is violated. No network or build required.

| # | Check | Rule | Source |
|---|-------|------|--------|
| 1 | Branch naming | Branch must match `feature/{id}-*` or `bugfix/{id}-*` | CODING_STANDARDS §1 |
| 2 | Excluded file | `com.tfione.api.d.ts` must not be staged | CODING_STANDARDS §11 |
| 3 | No unit tests | `*.test.cs` or `*.spec.ts` must not be staged | CODING_STANDARDS §8 |
| 4 | No role permissions | Staged `.sql` files must not contain `GRANT` or `DENY` | CODING_STANDARDS §10 |
| 5 | No AI tool refs | Staged content must not mention `claude` or `claire` (case-insensitive) | existing hook pattern |

### Check details

**1. Branch naming** — enforces the `feature/{ticket-id}-description` or `bugfix/{ticket-id}-description`
convention. The `{id}` must be numeric. Detached HEAD and initial commits are excluded.

**2. Excluded file** — `com.tfione.api.d.ts` is generated and `.gitignored`. If it appears staged,
run `git restore --staged com.tfione.api.d.ts`.

**3. No unit tests** — TFI One has no unit tests by design (CODING_STANDARDS §8). Files matching
`*.test.cs` or `*.spec.ts` indicate a mistake.

**4. No role permissions** — `GRANT` / `DENY` in SQL migrations break the role management model.
Roles are assigned through the UI, not migrations (CODING_STANDARDS §10).

**5. No AI tool refs** — prevents accidental commit of AI session artifacts, debug comments, or
tool-specific annotations that mention `claude` or `claire`.

---

## `pre-push` — Build Gates

Runs on `git push`. Mirrors the Azure Pipelines gated build. Blocks push if any gate fails.

| Gate | Command | Condition |
|------|---------|-----------|
| Gate 1 — Backend build | `dotnet build com.tfione.sln -c Gate` | Always |
| Gate 3 — Frontend build | `cd com.tfione.web && npm run build-gate` | Always |
| Gate 4 — Frontend lint | `cd com.tfione.web && npm run lint` | Always |
| Gate 5 — Flyway checksums | `claire flyway verify` | Only if migration files changed |

**Intentionally excluded:**

- **Gate 2 (dotnet test)** — no unit tests in TFI One
- **Gate 6 (E2E)** — too slow for a hook; run manually before opening a PR

### Gate details

**Gate 1** runs the `Gate` build configuration which enables `TreatWarningsAsErrors=true` and
StyleCop at build-breaking severity. A clean `Debug` build is not sufficient.

**Gate 3** runs `tsc -b && vite build`. TypeScript strict mode is enabled — any new error in files
you changed will fail.

**Gate 4** runs ESLint with flat config (`eslint.config.js`). Zero errors required.

**Gate 5** detects whether any file under `com.tfione.db/migration/` changed since the upstream
branch. If so, runs `claire flyway verify` to detect CRC32 checksum mismatches. If `claire` is
not installed, this check is skipped with a warning.

---

## Emergency Bypass

Use `--no-verify` only when absolutely necessary. Document the reason in the commit message.

```bash
# Skip pre-commit checks
git commit --no-verify -m "emergency: <reason>"

# Skip pre-push gates
git push --no-verify
```

Never use `--no-verify` to hide a failing gate that should be fixed. CI will catch it and block
the PR.

---

## Troubleshooting

### Hook not running

```bash
git config core.hooksPath   # should print .githooks
ls -la .githooks/            # should show executable files (x bit set)
```

If not set: `./scripts/install-hooks.sh`

### pre-commit: branch name rejected

The branch name must follow `feature/{numeric-id}-*` or `bugfix/{numeric-id}-*`. Rename:

```bash
git branch -m feature/10856-my-description
```

### pre-commit: com.tfione.api.d.ts staged

```bash
git restore --staged com.tfione.api.d.ts
```

If the file keeps appearing, verify it is in `.gitignore`.

### pre-push: Gate 1 fails (dotnet build)

Run manually to see full output:

```bash
dotnet build com.tfione.sln -c Gate
```

Common causes: StyleCop violations, nullable warnings, unused variables. See DEVELOPER_GATES.md.

### pre-push: Gate 3 fails (TypeScript)

```bash
cd com.tfione.web && npm run build-gate
```

Count baseline errors vs. yours:
```bash
git stash && npx tsc -b 2>&1 | wc -l   # baseline
git stash pop && npx tsc -b 2>&1 | wc -l  # must not increase
```

### pre-push: Gate 5 fails (Flyway)

```bash
claire flyway verify
```

A checksum mismatch means a migration file was edited after it was applied. Create a new
migration with corrective SQL instead of modifying the existing file. See CODING_STANDARDS §9.

---

## Related Documents

- Full gate specifications: `claire domain read five_points operational DEVELOPER_GATES`
- Coding standards the hooks enforce: `claire domain read five_points operational CODING_STANDARDS`
- Flyway migration rules: `claire domain read five_points operational CODING_STANDARDS` (§9)
