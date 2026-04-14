---
domain: fivepoints
category: operational
name: ADO_GITHUB_SYNC
title: "FivePoints — ADO ↔ GitHub Sync (TFIOneGit mirror)"
keywords: [five-points, fivepoints, ado, github, sync, ado-github-sync, tfionegit, mirror, dev-branch, remote, origin, review-repo, analyst]
updated: 2026-04-14
pr: "#24"
---

# FivePoints — ADO ↔ GitHub Sync

> **L4 fix:** During an analyst session on issue #71, the agent stopped to ask the user a/b/c
> after `git fetch github "$existing_branch"` returned nothing — because `dev` itself was
> missing on GitHub. Pulling from ADO without pushing to GitHub leaves GitHub stale; every
> downstream `git fetch github <branch>` then silently misses real branches. This doc names
> the pattern so the next session self-recovers instead of asking.

---

## Source of Truth

**ADO is the source of truth, not GitHub.**

| Remote | URL | Role |
|--------|-----|------|
| `origin` | Azure DevOps (TFI One repo) | **Source of truth.** All merges land here. |
| `github` | `CLAIRE-Fivepoints/fivepoints-test` | Review repo — GitHub PRs, gatekeeper, claire-tests |

GitHub mirrors ADO. It is never the authoritative state. If GitHub and ADO disagree, ADO wins
and GitHub gets force-aligned (push, not pull from GitHub).

---

## The Recurring Sync Pattern

Run this at **session start**, **before creating any feature branch**, and **before any
`git fetch github <branch>` lookup** in the pre-flight check:

```bash
cd ~/TFIOneGit
git checkout dev
git pull origin dev          # pull latest from ADO (source of truth)
git push github dev          # mirror to GitHub (review repo)
```

Both lines are required. Pulling without pushing leaves GitHub stale; pushing without pulling
overwrites GitHub with an outdated local copy.

---

## When to Run It

| Trigger | Why |
|---------|-----|
| Analyst session start | Pre-flight `gh api .../branches` and `git fetch github <branch>` need an up-to-date `dev` baseline on GitHub |
| Before creating a feature branch | New branches are cut from `dev` — both remotes must agree on its tip |
| After ADO merges a feature back to `dev` | GitHub still points at the old `dev` until the push happens |
| When `git fetch github <branch>` returns nothing for a branch you know exists | Symptom of stale GitHub `dev` — sync, then re-check |

---

## Disambiguation: GitHub Empty ≠ Project Empty

Symptoms that look alarming but are not:

- `gh api repos/CLAIRE-Fivepoints/fivepoints-test/branches` returns `[]` or only `main`
- GitHub `main` is empty (post-wipe state — see commit `c5e1efc8`)
- `git fetch github dev` says `couldn't find remote ref dev`

**None of these mean the project is broken.** They mean GitHub has not been mirrored from ADO
yet. The recovery is `git push github dev` — not asking the user.

---

## Self-Recovery (Analyst Decision Tree)

```
git fetch github dev fails / returns nothing
        │
        ├─ Is dev present in TFIOneGit local? (git branch --list dev)
        │       ├─ Yes → git push github dev → retry fetch
        │       └─ No  → git pull origin dev → git push github dev → retry fetch
        │
        └─ Still failing after sync → escalate (post on issue, do NOT guess)
```

The analyst session should never ask "should I push dev to GitHub?" — the answer is always yes.

---

## Related Docs

- `claire domain read fivepoints operational CHECKLIST_ANALYST` — analyst pipeline (uses this sync)
- `claire domain read fivepoints operational PIPELINE_WORKFLOW` — full client pipeline
- `claire domain read fivepoints operational ADO_PAT_GUIDE` — PAT scopes for `git push origin`
