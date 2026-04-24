---
domain: fivepoints
category: operational
name: GIT_HOOKS
title: "Five Points — TFI One Git Hooks"
keywords: [five-points, fivepoints, git-hooks, pre-commit, pre-push, developer-gates, branch-naming, coding-standards, "persona:fivepoints-dev"]
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
| 6 | ESLint on staged web | Staged `com.tfione.web/**/*.{ts,tsx}` must pass `eslint --no-error-on-unmatched-pattern` | issue #119 |

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

**6. ESLint on staged web** (issue #119) — runs
`com.tfione.web/node_modules/.bin/eslint --no-error-on-unmatched-pattern <staged paths>`
against every staged `com.tfione.web/**/*.{ts,tsx}` path. Scope is limited to
`com.tfione.web/` because the hook ships into three repos (`claire-labs/fivepoints`,
`claire-labs/fivepoints-test`, `TFIOneGit`) and only the last one carries the web
package. The check **skips cleanly** (warn, do not block) when:

- `com.tfione.web/` is absent in the repo (non-TFIOneGit clone) — warn, exit 0.
- `com.tfione.web/node_modules/.bin/eslint` is missing — warn "run `npm --prefix com.tfione.web install`", exit 0.

This is the pre-commit half of the compensating control for the missing ADO-CI
ESLint gate (see **Residual risk** below). The pre-push Check 3 is the other half.

---

## `pre-push` — Build Gates

Runs on `git push`. Mirrors the Azure Pipelines gated build. Blocks push if any gate fails.

| Gate | Command | Condition |
|------|---------|-----------|
| Check 1 — Remote guard | Block push to `origin` or any `dev.azure.com` / `visualstudio.com` URL | Always |
| Check 2 — `.fds-cache/` guard | Reject pushes whose new commits touch `.fds-cache/` | Always |
| Check 3 — `npm run lint` | `cd com.tfione.web && npm run --silent lint` | Only if push commits touch `com.tfione.web/**/*.{ts,tsx}` (issue #119) |
| Gate 1 — Backend build *(aspirational)* | `dotnet build com.tfione.sln -c Gate` | Not currently wired into the hook |
| Gate 3 — Frontend build *(aspirational)* | `cd com.tfione.web && npm run build-gate` | Not currently wired into the hook |
| Gate 5 — Flyway checksums *(aspirational)* | `claire flyway verify` | Not currently wired into the hook |

> ⚠️ The "aspirational" rows above appeared in an earlier revision of this doc
> but were never wired into `domain/hooks/pre-push`. They are kept as the
> target shape; the actual checks the hook enforces today are Check 1, Check
> 2, and Check 3.

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

**Check 3 — ESLint on pushed web commits** (issue #119) — enumerates every
commit in the push range (new-branch: `<sha> --not --remotes`; existing
branch: `<remote_sha>..<local_sha>`), asks `git log --name-only` for paths,
and checks for any `com.tfione.web/**/*.{ts,tsx}`. If a match is found the
hook runs `cd com.tfione.web && npm run --silent lint`; lint failure aborts
the push with a named message. The check warn-skips (exit 0) if
`com.tfione.web/` is absent or `npm` is not on PATH.

---

## Residual risk — why ESLint enforcement is client-side only (issue #119)

The ADO CI pipeline (`com.tfione.ci/azure_gated_build.yml`) does not run
`npm run lint` today. Adding it there would require committing to an
ADO-tracked file, which the issue owner explicitly ruled out — so the
pre-commit (Check 6) + pre-push (Check 3) gates in this plugin are the
**only** automated ESLint enforcement for TFI One PRs.

Because those gates live on the developer's machine, they can be bypassed:

- **Bypassed — same as every other hook-enforced gate:**
  `git commit --no-verify` / `git push --no-verify` skip the entire hook,
  including ESLint. Consistent with StyleCop-via-Gate-build, Flyway
  checksums, and every other current pre-*-hook check.
- **Bypassed — hook not installed:** any clone that skipped
  `claire fivepoints install-hooks` (new machine, fresh clone, installer
  crash, `claire` not on PATH during setup) will commit & push without the
  gate running. Step `[1.1/11]` of CHECKLIST_DEV_PIPELINE tells the dev
  agent to run the installer at session start as a compensating procedure.

**Compensating controls:**

- `CHECKLIST_DEV_PIPELINE.md` step `[1.1/11]` — `claire fivepoints install-hooks` is a MANDATORY once-per-session step (idempotent; existing hooks are backed up).
- `CHECKLIST_DEV_PIPELINE.md` step `[5/11]` — Steven Reviewer receives every PR diff, runs its own checks, and rejects PRs missing the plugin-rendered PR checklist (which includes "`claire fivepoints install-hooks` has been run for this clone").
- `fivepoints-reviewer` persona — human review is the compensating control when automation is bypassed.

---

## Why plain hooks and not Husky / lint-staged

Issue #119 originally proposed adopting Husky + lint-staged to wire up the
pre-commit lint. Both tools were rejected for the same reason: they require
committing to ADO-tracked files.

| Tool | What lands in `com.tfione.web/package.json` | Other tracked file(s) |
|---|---|---|
| **Husky** | `"prepare": "husky install"` script + `"husky": "^9.x"` devDependency | New tracked `.husky/` directory with hook shims |
| **lint-staged** | `"lint-staged": { "*.{ts,tsx}": "eslint --fix" }` config + `"lint-staged": "^15.x"` devDependency | — |

Either change would land on ADO's `master`. The plugin's own installer
(`claire fivepoints install-hooks`) writes directly to `.git/hooks/`, which
is never tracked by git — so hook logic ships from this plugin and reaches
a dev's clone without any ADO-origin change.

The only trade-off: Husky auto-installs on `npm install` via its `prepare`
script, whereas the plugin installer is an explicit session-start step.
For an agent-driven workflow that's acceptable — the LLM runs `install-hooks`
at `[1/11]→[1.1/11]` as a checklist item.

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

- Full gate specifications: `claire domain read fivepoints operational DEVELOPER_GATES`
- Coding standards the hooks enforce: `claire domain read fivepoints operational CODING_STANDARDS`
- Flyway migration rules: `claire domain read fivepoints operational CODING_STANDARDS` (§9)
