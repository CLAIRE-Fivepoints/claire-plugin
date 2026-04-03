---
domain: five_points
category: operational
name: DEVELOPER_GATES
title: "Five Points — Developer Gates Before Pushing to Azure DevOps"
keywords: [five-points, fivepoints, developer-gates, build, test, typescript, stylecop, eslint, flyway, e2e, pre-push, quality-gate]
updated: 2026-03-07
---

# Five Points — Developer Gates Before Pushing to Azure DevOps

> Run ALL applicable gates locally before pushing to Azure DevOps.
> Failed gates on CI waste build minutes and block the team.

---

## Overview

The Azure Pipelines gated build (`azure_gated_build.yml`) enforces these checks automatically on
every PR. Running them locally first catches failures before they reach CI, avoiding wasted cycles
and PR rejections.

**Rule:** If a gate fails locally, fix it before pushing. No exceptions.

---

## Gate 0 — Source Control Hygiene

**Run before anything else.** These checks prevent common mistakes from reaching ADO.

### Branch naming convention

```bash
git branch --show-current
# Must match: feature/{ticket-id}-short-description
#         or: bugfix/{ticket-id}-short-description
# Examples:   feature/10856-client-export
#             bugfix/10901-fix-null-reference
```

❌ Branches that do NOT follow this convention will be rejected by `fivepoints ado-push`.

### No business logic tests committed

```bash
# Check staged test files for business domain namespaces
git diff --name-only --cached | grep "service.test"
# If any staged — inspect that the class is for: encryption, password, URL builders, external APIs
# NOT for: client, provider, organization, fds, intake, household logic
```

`com.tfione.service.test` is for infrastructure services and external API adapters only.
Tests for business domain logic (clients, providers, FDS, etc.) must not be committed.

Allowed test namespaces: `encryption`, `password`, `signing`, `mapping`, `email`, `messaging`

### No role permissions in migrations

```bash
# Check staged migration files for GRANT/DENY
git diff --name-only --cached | grep "migration/" | xargs grep -il "GRANT\|DENY" 2>/dev/null
# Expected: no output (role permissions must not be in migrations)
```

Roles are managed via the UI. Never add `GRANT`, `DENY`, or role assignment SQL to a migration file.

### `com.tfione.api.d.ts` not staged

```bash
git status | grep "com.tfione.api.d.ts"
# Expected: no output (file must not be staged or tracked)

# If accidentally staged:
git restore --staged com.tfione.api.d.ts

# If tracked in git history:
git rm --cached com.tfione.api.d.ts
```

---

## Gate 1 — Build

**Command:**

```bash
cd /Users/andreperez/projects/fivepoints/dev
dotnet build com.tfione.sln -c Gate
```

**Passing criteria:** 0 errors, 0 warnings.

The `Gate` configuration enables `TreatWarningsAsErrors=true` and runs StyleCop analyzers at
build-breaking severity — the same as CI. A clean `Debug` build is not sufficient.

**Common failures:**

| Failure | Fix |
|---------|-----|
| StyleCop SA#### | Fix the style violation (no suppressions without justification) |
| Nullable warning CS8xxx | Add null check, `!` operator, or adjust nullability annotation |
| Unused variable/parameter | Remove or prefix with `_` if intentionally unused |

---

## Gate 2 — Tests

**Command:**

```bash
cd /Users/andreperez/projects/fivepoints/dev
dotnet test com.tfione.sln
```

**Passing criteria:** All tests pass. No skipped tests introduced without justification.

Focus on tests related to changed code. If a test was previously passing and now fails, the
change broke it — fix the code, not the test.

**Project:** `com.tfione.service.test` (xUnit v2.5.3 + Moq)

---

## Gate 3 — Frontend Build (TypeScript + Vite)

**Command:**

```bash
cd /Users/andreperez/projects/fivepoints/dev/com.tfione.web
npm run build-gate
```

`build-gate` runs `tsc -b && vite build` — both TypeScript compilation and the Vite production build.

**Passing criteria:** 0 errors in files you changed.

TypeScript strict mode is enabled (`"strict": true`, `noUnusedLocals`, `noUnusedParameters`,
`noUncheckedIndexedAccess`). Pre-existing errors in untouched base code are acceptable only if
they were already present on the base branch before your changes.

**Verify pre-existing errors are not yours:**

```bash
# Compare against base branch
git stash && npx tsc -b 2>&1 | wc -l   # baseline count
git stash pop && npx tsc -b 2>&1 | wc -l  # your count (must not increase)
```

---

## Gate 4 — Lint

### Backend: StyleCop

StyleCop is enforced during the build (Gate 2 above). No separate command needed — a clean
Gate build implies StyleCop passes.

**Ruleset:** `com.tfione.ruleset`
**Config:** `stylecop.json` (4-space indent, System usings first, newline at EOF)

### Frontend: ESLint

**Command:**

```bash
cd /Users/andreperez/projects/fivepoints/dev/com.tfione.web
npm run lint
```

**Passing criteria:** 0 errors. Warnings are acceptable but should not increase.

ESLint uses flat config (`eslint.config.js`) with `typescript-eslint` recommended + `react-hooks`
plugin. Fix any new errors introduced by your changes.

---

## Gate 5 — Migration (if you added or modified migration files)

**Applies when:** You created or edited any file under `com.tfione.db/migration/`.

**Command:**

```bash
claire flyway verify
```

**Passing criteria:** No checksum mismatches against the base branch.

Flyway stores checksums in `flyway_schema_history`. Editing an already-applied migration file
changes its checksum and breaks incremental migration — this will fail CI. If you need to
change a migration that was already pushed, create a new migration instead.

**Migration naming convention:**

```
V{major}.{minor}.{date}.{workitem}.{sequence}__{description}.sql
```

Example: `V1.0.20260307.1234.1__add_client_education_table.sql`

---

## Gate 6 — End-to-End (if you changed UI flows or API contracts)

**Applies when:** You changed frontend routes, form submissions, API endpoints, or
authorization rules that affect visible user workflows.

**Command:**

```bash
claire fivepoints e2e-education
```

Or run the relevant E2E scenario for the area you changed.

**Passing criteria:** All targeted UI flows complete without errors.

---

## Quick Reference — Gate Checklist

### Before git push — Run ALL Applicable Gates Locally

```
[ ] Gate 0  Branch follows feature/ or bugfix/ convention
[ ] Gate 0  No business logic tests staged (infrastructure/external API tests only)
[ ] Gate 0  No GRANT/DENY in staged migration files
[ ] Gate 0  com.tfione.api.d.ts not staged or tracked
[ ] Gate 1  dotnet build com.tfione.api/com.tfione.api.csproj -c Gate -WarnAsError -nowarn:nu1901,nu1902
[ ] Gate 2  dotnet test com.tfione.service.test/com.tfione.service.test.csproj --configuration Gate
[ ] Gate 3  cd com.tfione.web && npm run build-gate   → 0 errors (tsc -b + vite build)
[ ] Gate 4  cd com.tfione.web && npm run lint         → 0 errors in your files
[ ] Gate 5  claire flyway verify     [if migrations]  → no checksum mismatches
[ ] Gate 6  claire fivepoints e2e-* [if UI changed]  → flows pass
```

❌ **NEVER `git push` before all applicable gates pass locally.**

These run in under 2 minutes total and catch every error the CI pipeline catches.
Fix locally — do not push and wait for CI to tell you.

---

## Integration Points

This document is referenced in:

- `five_points/operational/CODE_REVIEW_WORKFLOW` — Steven Franklin checks gate compliance
  during PR review
- Work checklist (prepended to spawned fivepoints tasks)
- Session CLAUDE.md for fivepoints worktrees

---

## Related Documents

- Code quality tool details: `claire domain read five_points technical CODE_QUALITY_TOOLS`
- Coding standards: `claire domain read five_points operational CODING_STANDARDS`
- Code review process: `claire domain read five_points operational CODE_REVIEW_WORKFLOW`
- Local test setup: `claire domain read five_points operational TESTING`
