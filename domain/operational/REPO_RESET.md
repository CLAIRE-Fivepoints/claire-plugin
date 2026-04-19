---
domain: fivepoints
category: operational
name: REPO_RESET
title: "Five Points — Factory Reset the Fivepoints Test Mirror (repo-reset)"
keywords: [fivepoints, repo-reset, factory-reset, wipe, tombstone, archive, pr-archive, strip-rename, content-wipe, pipeline, tfi-one, ado, main-reset, guardrails]
updated: 2026-04-19
---

# Five Points — Factory Reset the Test Mirror (`repo-reset`)

Resets the **whole fivepoints test mirror** (`CLAIRE-Fivepoints/fivepoints`)
to a clean state derived from ADO `dev`, without deleting the repo itself.
Use this to start a fresh pipeline validation cycle from a known baseline
when per-PBI cleanup is no longer worth the bookkeeping.

`repo-reset` subsumes what `reset-pbi` would do for every PBI present — same
shape, repo-wide scope.

---

## Command

```bash
claire fivepoints repo-reset (--dry-run | --confirm)
                             [--keep-prs]
                             [--ado-ref <branch|sha>]
                             [--tfione-path PATH]
```

Mode (exactly one):

| Arg | Meaning |
|---|---|
| `--dry-run` | Render the plan, make no mutations |
| `--confirm` | Execute the plan (destructive) |

Options:

| Arg | Default | Purpose |
|---|---|---|
| `--keep-prs` | off | Skip PR strip+rename and PR comment cleanup |
| `--ado-ref <ref>` | `dev` | ADO source ref to reset `main` to (branch, tag, or sha) |
| `--tfione-path PATH` | `$TFIONE_REPO_PATH` or `~/TFIOneGit` | TFIOneGit clone that holds the `origin` (ADO) and `github` (mirror) remotes |

---

## What gets wiped

| # | Bucket | Mechanism |
|---|---|---|
| 1 | `main` | Force-pushed to `ADO/<ado-ref>` tip via the local TFIOneGit clone's `github` remote |
| 2 | Non-`main` branches | REST `DELETE /repos/<o>/<n>/git/refs/heads/<name>` |
| 3 | Tags | REST `DELETE /repos/<o>/<n>/git/refs/tags/<name>` |
| 4 | Issues | GraphQL `deleteIssue` mutation (admin token required) |
| 5 | Releases (and assets) | REST `DELETE /repos/<o>/<n>/releases/<id>` (assets cascade) |
| 6 | Workflow runs | REST `DELETE /repos/<o>/<n>/actions/runs/<id>` |
| 7 | PRs | **Strip + rename** — see below. Skipped under `--keep-prs`. |
| 8 | Agent-authored PR comments | REST `DELETE /repos/<o>/<n>/issues/comments/<id>`. Skipped under `--keep-prs`. |

### Why strip+rename PRs, not delete

GitHub's API **does not expose PR deletion**: `DELETE /repos/<o>/<n>/pulls/<n>`
returns 404, and no GraphQL `deletePullRequest` mutation exists. Instead we
neutralize each PR into an inert **tombstone**:

* **Title** → `[archived-repo-reset-<iso-timestamp>]`
* **Body** → `This PR was archived during a factory repo reset. Original content is no longer authoritative.`
* **State** → `closed`

After this transformation, agent searches like `gh pr list --search "PBI #18839"`
or `--search "head:feature/18839-*"` return zero matches. The PR number stays
in the repo as an audit record; its semantic signal is gone.

---

## What's preserved

* Labels
* Branch protection rules
* Webhooks
* Actions secrets
* Collaborators
* Repo-level settings (merge policies, issue templates, etc.)

### Why not `gh repo delete`

Tempting but rejected: re-provisioning labels/protection/webhooks/secrets/
collaborators on every reset is operationally painful and error-prone.
Content-only wipe is the deliberate tradeoff.

---

## Setup (one-time)

Add to `~/.claire/machine.yml`:

```yaml
fivepoints_test_repo: CLAIRE-Fivepoints/fivepoints
```

Without this key, `repo-reset` refuses to run — by design.

---

## Required env

| Var | Scope | Purpose |
|---|---|---|
| `GITHUB_ADMIN_TOKEN` | required for `--confirm` | Token with `delete_repo` + `admin:org` scopes. Resolved from env or `~/.config/claire/github_manager.env`. |

The admin token is distinct from the manager `GITHUB_TOKEN` because the
GraphQL `deleteIssue` mutation and `DELETE /actions/runs/<id>` both require
admin scope.

---

## Guardrails

* **Refuses if `fivepoints_test_repo` is unset** in `machine.yml` → exit 2
* **Refuses if the configured repo differs from the allowed repo** → exit 2
  (Python re-checks what bash already passed, belt-and-suspenders.)
* **Refuses `--confirm` without `GITHUB_ADMIN_TOKEN`** → exit 4
* **Refuses to force-push `main` without a clean TFIOneGit clone** → exit 5
  (The clone must have both an `origin` remote pointing at ADO and a `github`
  remote pointing at the allowed repo.)
* Every mutation is logged to `~/.claire/logs/repo-reset-<YYYYMMDD-HHMMSS>.log`

---

## Relationship to the per-PBI reset

* **`reset-pbi`** — per-PBI scope. Cleans one PBI's branches, worktrees, PR,
  agent comments, labels, and the issue's github-manager state.
* **`repo-reset`** — whole-repo scope. Wipes everything and force-resets
  `main` to ADO/<ref>.

They compose by scope, not by chaining: `repo-reset` is what you run when
you would otherwise `reset-pbi` every open PBI individually.

---

## Idempotency

The delete operations (branches, tags, issues, releases, runs, PR comments)
treat HTTP 404 as SKIP, not FAIL — rerunning `repo-reset --confirm` after a
partial failure is safe.

PR archive is a mutation, not a delete: a 404 there means the PR itself
vanished (unusual), and is surfaced as a FAIL for investigation.

---

## Validation checks

After `--confirm`:

```bash
# Zero issues remain
gh issue list --repo $REPO --state all | wc -l   # -> 0

# Only tombstone PRs remain
gh pr list --repo $REPO --state all --json title \
    --jq '[.[] | select(.title | startswith("[archived-repo-reset-")) | .] | length'
# -> should equal total PR count

# Only main remains
gh api /repos/$REPO/branches --jq '[.[] | .name]'
# -> ["main"]

# main matches ADO/<ado-ref>
git -C ~/TFIOneGit rev-parse origin/<ado-ref>
git -C ~/TFIOneGit rev-parse github/main
# -> same sha

# Settings still present
gh api /repos/$REPO/labels --jq 'length'        # > 0
gh api /repos/$REPO/hooks --jq 'length'         # unchanged
gh api /repos/$REPO/branches/main/protection    # still returns protection
```

---

## Architecture

* **Bash orchestrator** (`domain/commands/repo-reset.sh`) — flag parsing,
  token resolution, machine.yml guardrail, `gh` inventory pre-fetch, git
  force-push of `main`, hand-off to Python.
* **Python logic** (`domain/scripts/repo_reset.py`) — builds and executes
  the plan via the REST + GraphQL client (urllib only, no subprocess, per
  DEV_RULES #2).

Tests: `domain/scripts/tests/test_repo_reset.py` — plan building,
guardrails, tombstone format, idempotent 404 handling.
