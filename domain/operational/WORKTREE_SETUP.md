---
domain: fivepoints
category: operational
name: WORKTREE_SETUP
title: "Five Points — Fresh Worktree Setup for TFI One"
keywords: [five-points, fivepoints, tfi-one, worktree, setup, com.tfione.api.d.ts, d-ts, node_modules, npm-install, gate-3, typescript, pre-existing-errors, delta, "persona:fivepoints-dev"]
updated: 2026-04-23
---

# Five Points — Fresh Worktree Setup for TFI One

> **Why this exists:** during issue-61 a session burned ~15 exploratory steps hunting for
> a missing `com.tfione.api.d.ts` in a freshly spawned worktree on
> `CLAIRE-Fivepoints/fivepoints` (which has no code after the "start fresh" reset in
> commit `c5e1efc8`). The recovery — copy the file from the operator's canonical dev
> checkout — was already known tribal knowledge; it just wasn't written down. This doc
> captures that recipe plus two other fresh-worktree gotchas (`node_modules` per worktree,
> Gate 3 evaluated by delta rather than absolute) so the next session goes straight to
> work instead of rediscovering the pattern.

---

## 1. `com.tfione.api.d.ts` — Fresh-Worktree Recipe

### Why it's missing

`com.tfione.web/src/types/com.tfione.api.d.ts` is a **generated** file — produced from the
live .NET API's OpenAPI spec by `com.tfione.api.generate.ts`. Per
`claire domain read fivepoints knowledge DEV_RULES` **rule #2**, it is listed in
`.gitignore` and must never be committed. So on any fresh worktree — especially one
spawned on the `CLAIRE-Fivepoints/fivepoints` mirror after the `c5e1efc8` reset — the
file is absent by design, not by oversight.

This means **the recovery is not a workaround**: regenerating or copying the file is the
normal flow, not an exception.

### Recovery — two options

**Option A (fastest): copy from the canonical dev checkout.**

```bash
cp /Users/andreperez/projects/fivepoints/dev/com.tfione.web/src/types/com.tfione.api.d.ts \
   com.tfione.web/src/types/
```

The canonical checkout at `/Users/andreperez/projects/fivepoints/dev` is the operator's
local source of truth — its `com.tfione.api.d.ts` reflects the latest `dev` branch types.
Copy is appropriate when you just need to unblock `tsc -b` and don't need types for any
.NET models added on your feature branch.

**Option B (authoritative): regenerate from your running API.**

Follow the `## Gate 3 — Frontend Build (TypeScript + Vite)` procedure in
`claire domain read fivepoints operational DEVELOPER_GATES` (§ Step 3a) — kill any stale
API, start a fresh `dotnet run`, wait for swagger, then `npm run generate-local`.
Required whenever your feature branch adds or changes .NET models; the copied file from
Option A won't know about them.

### When to use which

| Situation | Use |
|---|---|
| Fresh worktree, `com.tfione.api.d.ts` missing, you haven't added .NET models yet | **Option A** — copy |
| Your feature branch added/modified `.cs` models, controllers, or DTOs | **Option B** — regenerate |
| `tsc -b` reports `TS2724` / `TS2694` in files you didn't touch | **Option B** — stale types |

### What you must NEVER do

- ❌ Check `com.tfione.api.d.ts` into git. Pre-commit hook `2.` rejects it; if it slips past
  locally, `git rm --cached com.tfione.api.d.ts && git commit -m "chore: remove generated file from tracking"`. See `claire domain read fivepoints operational GIT_HOOKS`.
- ❌ Edit the file by hand to "fix" a TypeScript error. The file regenerates on the next
  `npm run generate-local` — any manual edits are erased.

---

## 2. Per-Worktree `npm install`

`node_modules` is **not** shared between worktrees. Each worktree has its own
`com.tfione.web/node_modules/`, and a freshly spawned worktree starts empty.

Run once after checkout:

```bash
npm --prefix com.tfione.web install
```

`--prefix` avoids `cd com.tfione.web && npm install && cd ..` and works from any
subdirectory in the worktree.

### Symptoms of a missing install

| Symptom | Cause |
|---|---|
| `vite: command not found` / `tsc: command not found` | `node_modules` absent — run `npm --prefix com.tfione.web install` |
| `Cannot find module 'react'` (or any dep) from `tsc -b` | Same — missing install |
| `npm run build-gate` exits instantly with a non-zero code and no output | `package.json` scripts can't resolve their binaries |

Running `npm install` in the dev checkout does **not** populate the feature-branch worktree's `node_modules`. Each worktree is its own install target.

---

## 3. Gate 3 — Evaluate by Delta, Not Absolute Zero

`DEVELOPER_GATES.md` § Gate 3 Step 3b says "0 errors in files you changed," but running
`npm run build-gate` against a branch like `feature/10847-client-adoptive-placement`
produces **~224 pre-existing TypeScript errors** from unrelated validators/services.
Those errors are not from your feature work — they're in the base branch.

**The rule: your changes MUST NOT INCREASE the error count.** Zero absolute is not the
bar on a branch that inherits pre-existing errors; zero **delta** is.

### Delta check (canonical snippet)

The snippet already lives in `DEVELOPER_GATES.md` § Gate 3 — Step 3b → "Verify pre-existing
errors are not yours." Re-pasted here so the rule is explicit:

```bash
cd com.tfione.web

# Baseline — error count without your changes
git stash && npx tsc -b 2>&1 | wc -l

# Your count — with your changes — MUST NOT be greater than baseline
git stash pop && npx tsc -b 2>&1 | wc -l
```

| Comparison | Gate verdict |
|---|---|
| your count ≤ baseline | ✅ pass — you did not add errors |
| your count > baseline | ❌ fail — fix the new errors before pushing |

### When absolute zero IS the bar

On `dev` / `main` branches that start clean, pre-existing errors are a bug, not a baseline
— fix them as part of the feature PR, don't inherit them. The delta rule exists for
long-lived feature branches that cut from an already-dirty base, not as a universal
excuse.

### Why not just fix the pre-existing errors?

Two reasons:
- **Scope creep.** A feature PR that touches 12 files but fixes 224 unrelated errors is
  indistinguishable from a drive-by refactor; reviewers can't find the actual change.
- **Cherry-pick risk.** Fixing upstream errors on a feature branch means the fix lives on
  the feature branch, not on `dev`. When the feature merges, the upstream fixes ride along
  as side-effects. Better: file a separate issue for the pre-existing errors and fix them
  on their own PR.

---

## Related

- `claire domain read fivepoints knowledge DEV_RULES` — rule #2 (no `.d.ts` committed)
- `claire domain read fivepoints operational DEVELOPER_GATES` — § Gate 3 (TS build gate and the delta-check snippet)
- `claire domain read fivepoints operational GIT_HOOKS` — pre-commit check that rejects a staged `com.tfione.api.d.ts`
- `claire domain read fivepoints operational TEST_ENV_START` — `claire fivepoints test-env-start` handles the "start fresh API" half of Option B
- Issue #110 (CLAIRE-Fivepoints/claire-plugin) — origin of this doc
- Issue #61 / #63 (CLAIRE-Fivepoints/fivepoints) — the session that burned the 15 steps
