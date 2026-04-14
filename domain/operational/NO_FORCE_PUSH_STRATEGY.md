---
domain: fivepoints
category: operational
name: NO_FORCE_PUSH_STRATEGY
title: "FivePoints — No-Force-Push Strategy for Stale PRs"
keywords: [five-points, force-push, ForcePush, rebase, stale-pr, snapshot-commit, merge-commit, no-force, ado, azure-devops, TF401027, rebase-no-force, land]
updated: 2026-04-08
pr: "#18"
---

# FivePoints — No-Force-Push Strategy for Stale PRs

> Use this when `git push --force-with-lease` is rejected by ADO branch policy
> (`TF401027: You need the Git 'ForcePush' permission to perform this action`).

## Background

André's ADO account does not have `ForcePush` permission on `dev`.
After rebasing a feature branch onto fresh `ado/dev`, a normal force-push is rejected.
The workaround uses git plumbing to create a fast-forward-only push that achieves
the same end state without requiring force.

**Discovered during:** issue #146 (PBI #10847 session, 2026-04-08)

---

## The Two-Commit Strategy

### Why two commits?

After a rebase, the branch history diverges from the remote — so a regular push fails
(non-fast-forward). Force-push is blocked by policy. But we can construct a commit whose
**parent is the current ADO branch tip**, which makes the push a fast-forward.

A single snapshot commit usually suffices. The second (re-anchor merge) is only needed
when ADO reports `mergeStatus: conflicts` after the snapshot — which happens when the
3-way merge-base is too far back.

---

### Step 1 — Snapshot Commit

Capture the desired tree state in a single commit whose parent is the current ADO tip:

```bash
# Ensure ADO remote is up to date
git fetch ado

# Read the current ADO branch tip
ADO_TIP=$(git rev-parse ado/dev)

# Capture the working tree (your clean rebased state)
TREE=$(git write-tree)

# Craft a commit: tree = your state, parent = ADO tip
SNAP_COMMIT=$(git commit-tree "$TREE" -p "$ADO_TIP" -m "chore: catch up to ado/dev (no-force-push)")

# Fast-forward push (parent = ADO tip → always fast-forward)
git push ado "${SNAP_COMMIT}:refs/heads/feature/XXXXX-your-branch"
```

After this push, the ADO branch tip equals `SNAP_COMMIT` — which contains exactly
your clean rebased tree.

---

### Step 2 — Re-Anchor Merge Commit (only if mergeStatus = conflicts)

ADO performs a 3-way merge to compute the PR diff. If the historical merge-base is
hundreds of commits behind `dev`, ADO may report `mergeStatus: conflicts` even though
the snapshot push succeeded.

**Diagnosis:**
```bash
# Check PR merge status via API
ADO_PAT="$AZURE_DEVOPS_PAT"
curl -s -u ":${ADO_PAT}" \
  "https://dev.azure.com/FivePointsTechnology/TFIOne/_apis/git/repositories/TFIOneGit/pullrequests/${PR_ID}?api-version=7.1" \
  | jq -r '.mergeStatus'
# → "conflicts"  ← needs re-anchor
# → "succeeded"  ← you're done, skip Step 2
```

**Fix — create a merge commit with two parents (snapshot + ado/dev tip):**

```bash
ADO_TIP=$(git rev-parse ado/dev)
SNAP_COMMIT=<hash from step 1>
TREE=$(git rev-parse "${SNAP_COMMIT}^{tree}")

MERGE_COMMIT=$(git commit-tree "$TREE" \
    -p "$SNAP_COMMIT" \
    -p "$ADO_TIP" \
    -m "chore: re-anchor merge base onto ado/dev")

# Fast-forward push (parent chain includes SNAP_COMMIT which is already the ADO tip)
git push ado "${MERGE_COMMIT}:refs/heads/feature/XXXXX-your-branch"
```

**Why this works:** the merge commit has `ado/dev` as its second parent, so ADO's
3-way merge now uses `ado/dev` as the merge-base — the PR diff shows only
the feature-specific files, and `mergeStatus` flips to `succeeded`.

---

## Automated Command

The `rebase-no-force` command wraps both steps:

```bash
# Rebase and push without ForcePush permission
claire fivepoints rebase-no-force --branch feature/10847-client-adoptive-placement --target dev

# Dry run (shows what it would do without pushing)
claire fivepoints rebase-no-force --branch feature/10847-my-feature --target dev --dry-run
```

See `--agent-help` for full usage.

---

## When to Use

| Situation | Command |
|-----------|---------|
| Clean rebase, ForcePush denied | `claire fivepoints rebase-no-force` |
| Have ForcePush permission | `git push --force-with-lease ado feature/...` (normal flow) |
| ADO says `mergeStatus: conflicts` after push | Step 2 of this strategy (re-anchor merge) |

---

## Related

- `claire fivepoints rebase-no-force --agent-help` — automated wrapper
- `claire fivepoints land --agent-help` — full end-to-end command (includes this strategy)
- Issue #146 — original session where this strategy was discovered
