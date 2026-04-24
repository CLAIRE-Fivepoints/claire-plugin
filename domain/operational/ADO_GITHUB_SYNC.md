---
domain: fivepoints
category: operational
name: ADO_GITHUB_SYNC
title: "FivePoints — ADO ↔ GitHub Sync (TFIOneGit mirror)"
keywords: [five-points, fivepoints, ado, github, sync, ado-github-sync, tfionegit, mirror, dev-branch, feature-branch, branch-visibility, 3-location, remote, origin, review-repo, analyst, dev, "persona:fivepoints-dev"]
updated: 2026-04-20
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

## Feature Branch Visibility (3 Locations)

`dev` is not the only branch that lives in multiple places. **Feature
branches** (`feature/<ticket-id>-<slug>`) also move through three distinct
locations during the pipeline, and each one lights up at a different step.
Checking only one location and concluding "branch doesn't exist" is the
failure mode this section prevents.

| Location | What it is | When the branch lands here | How to check |
|---|---|---|---|
| `~/TFIOneGit/` local | The agent's working clone. Source of truth for the active session. | Immediately after `git checkout -b feature/<ticket-id>-<slug>` during analyst pre-flight. | `git -C ~/TFIOneGit branch --list "feature/<ticket-id>-*"` |
| `github` remote on TFIOneGit (review repo — `$CLAIRE_WAIT_REPO`) | GitHub mirror. Pipeline issues + PRs coordinate here; this is where Steven Reviewer runs. | When the session runs `git push github feature/<ticket-id>-*` (analyst branch creation, or dev step [4/11]). | `gh api "repos/$CLAIRE_WAIT_REPO/branches/feature/<ticket-id>-<slug>" --jq .name 2>/dev/null` |
| `origin` remote on TFIOneGit (ADO — source of truth) | Azure DevOps TFIOneGit. Production pipeline target. | ONLY after `claire fivepoints ado-transition --issue <N>` at dev step [10/11]. | `git -C ~/TFIOneGit ls-remote origin "refs/heads/feature/<ticket-id>-*"` |

**Absence on `origin` (ADO) is NORMAL until dev step [10/11].** Do not
conclude "branch doesn't exist" from `origin` alone.

### Pre-flight snippet — run at the top of every `[1/11]`-equivalent step

```bash
# Expect the ticket ID from the GitHub issue title (e.g. "Task #18842 (PBI #18840)" → 18842)
ticket_id="<ticket-id>"                    # example: 18842
slug="<slug-from-issue>"                   # example: service-provider-face-sheet
branch="feature/${ticket_id}-${slug}"

local=$(git -C ~/TFIOneGit branch --list "feature/${ticket_id}-*" | awk '{print $NF}' | head -1)
github=$(gh api "repos/$CLAIRE_WAIT_REPO/branches/${branch}" --jq .name 2>/dev/null || echo "")
ado=$(git -C ~/TFIOneGit ls-remote origin "refs/heads/feature/${ticket_id}-*" | awk '{print $2}' | head -1)

echo "local=${local:-absent}"
echo "github=${github:-absent}"
echo "ado=${ado:-absent}"
```

### Interpretation

| local | github | ado | Meaning | Action |
|---|---|---|---|---|
| present | present | present | Branch already merged to ADO (or previously transitioned). | Investigate — this ticket may already be done. Do not recreate. |
| present | present | absent | **Normal pre-transition state.** Interrupted or in-progress pipeline. | **Reuse it.** Check out the existing branch. Do not recreate. |
| present | absent  | absent | Analyst started locally but never pushed to `github`. | `git push github "$branch"` — then reuse. |
| absent  | present | absent | Previous session on a different host. | `git fetch github "$branch" && git checkout "$branch"` — then reuse. |
| absent  | absent  | absent | **Truly new** — no prior session exists for this ticket. | Create the branch per the analyst checklist. |
| absent  | absent  | present | ADO has a branch but local + github have been wiped. | Re-mirror: `git fetch origin "$branch" && git push github "$branch"` — then reuse. |
| present | absent  | present | Post-transition but github mirror was wiped. | Re-mirror to github: `git push github "$branch"` — then reuse. |
| absent  | present | present | Post-transition but local working clone is missing. | Re-clone locally: `git fetch github "$branch" && git checkout "$branch"` — then reuse. |

The last two rows cover every remaining `local/github/ado` combination. They
are uncommon (typically a post-merge state where one of the mirrors has been
wiped) and both resolve to the same pattern: re-mirror the missing location
from whichever one still holds the branch, then reuse.

The rule of thumb:

> A branch ABSENT from `origin` (ADO) but PRESENT on `github` + `~/TFIOneGit`
> means a prior session was interrupted before `[10/11] ado-transition`.
> **Reuse it.** Do not recreate.
>
> A branch absent from all three locations → truly new → create per the
> analyst checklist.

---

## Related Docs

- `claire domain read fivepoints operational CHECKLIST_ANALYST` — analyst pipeline (uses this sync; cites the 3-location matrix at pre-flight)
- `claire domain read fivepoints operational CHECKLIST_DEV_PIPELINE` — dev pipeline (cites the 3-location matrix at `[1/11]`)
- `claire domain read fivepoints operational PIPELINE_WORKFLOW` — full client pipeline
- `claire domain read fivepoints operational ADO_PAT_GUIDE` — PAT scopes for `git push origin`
