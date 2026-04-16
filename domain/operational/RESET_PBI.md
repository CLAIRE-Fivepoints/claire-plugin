---
domain: fivepoints
category: operational
name: RESET_PBI
title: "Five Points — Factory Reset a PBI (reset-pbi)"
keywords: [fivepoints, reset-pbi, pbi, factory-reset, pipeline, validation, tfi-one, ado, analyst, dev, tester, worktree, release-assets, guardrails]
updated: 2026-04-16
---

# Five Points — Factory Reset a PBI (`reset-pbi`)

Resets a **single PBI** plus its linked GitHub issue, worktrees, branches, PR,
agent comments, labels, github-manager state, and release assets — so a fresh
agent session can replay the analyst → dev → tester pipeline from zero.

Complements `fivepoints reset-pipeline` (bulk). Use `reset-pbi` when validating
pipeline fixes on a specific regression target (e.g. PBI #18839 / issue #71).

---

## Command

```bash
claire fivepoints reset-pbi --pbi <id> --issue <n> (--dry-run | --confirm)
                            [--repo owner/name] [--tfione-path PATH] [--keep-db]
```

Required arguments:

| Arg | Meaning |
|---|---|
| `--pbi <id>` | ADO PBI (work item) id — must match the issue title |
| `--issue <n>` | GitHub issue number linked to the PBI |
| `--dry-run` / `--confirm` | Exactly one — see below |

Optional:

| Arg | Default | Purpose |
|---|---|---|
| `--repo owner/name` | `CLAIRE-Fivepoints/fivepoints` | Target repo for the PBI's GitHub issue |
| `--tfione-path PATH` | `$TFIONE_REPO_PATH` or `~/TFIOneGit` | Local TFIOneGit mirror clone |
| `--keep-db` | off | Reserved for future — currently a no-op |

---

## What gets reset

| # | Bucket | Effect |
|---|---|---|
| 1 | Local branches | `feature/<pbi>-*` deleted from TFIOneGit |
| 2 | `github` remote branches | `feature/<pbi>-*` deleted on the mirror remote (**`origin` / ADO is NEVER touched**) |
| 3 | Worktrees | `git worktree remove --force` for any worktree on a matching `feature/<pbi>-*` branch |
| 4 | GitHub PR | Open PR whose head is the feature branch → **closed** (GitHub doesn't truly delete PRs) |
| 5 | Agent comments | Comments authored by `claire-test-ai`, `claire-plugin-gatekeeper-ai`, `myclaire-ai`, `claire-gatekeeper-ai` are deleted via REST |
| 6 | Issue labels | Reset to exactly `[role:analyst]` (triggers a fresh analyst spawn) |
| 7 | Issue state | Reopened if closed |
| 8 | github-manager state | Issue removed from `processed_issues` + `issue_assignees` in `github_manager_state_<owner>_<repo>.json` |
| 9 | Release assets | Assets whose name matches `issue-<n>` (e.g. `proof-issue-71-*.mp4`, `BEFORE_issue-71.png`) are deleted |

---

## What does NOT get reset

- **ADO-side branch (`origin` remote on TFIOneGit)** — the command checks and
  logs a warning if a branch exists on both remotes, but only removes the one
  on `github`.
- **ADO work item state** — managed by ADO, not by this tool.
- **Domain knowledge docs** — FDS extracts, personas, checklists are left
  untouched.
- **Other PBIs' state** — strictly scoped to `--pbi` and `--issue`.

---

## Guardrails

The command refuses to proceed if:

| Condition | Exit code | Message |
|---|---|---|
| `--pbi` does not match the issue title | `2` | `issue #N is linked to PBI #X, not PBI #<pbi>` |
| Issue title has no PBI reference | `2` | `issue #N title does not reference any PBI` |
| Linked PR is already **merged** | `3` | `PR #X ... is already MERGED — refusing reset` |
| `--confirm` without `GITHUB_TOKEN` in env | `4` | `--confirm requires GITHUB_TOKEN` |

`--dry-run` **always** prints the full plan (including API/state/release/git
steps) without mutating anything.

Every run writes a full log to:

```
$HOME/.claire/logs/reset-pbi-<pbi>-<YYYYMMDD-HHMMSS>.log
```

---

## Tokens

`GITHUB_TOKEN` is required for `--confirm`. Lookup order (first hit wins):

1. `GITHUB_TOKEN` in the environment
2. `GITHUB_TOKEN` or `GH_TOKEN` in `~/.config/claire/github_manager.env`
3. `GITHUB_TOKEN` or `GH_TOKEN` in `~/.config/claire/.env`

The token must have `repo` scope (issue/comment/PR mutation) and
`admin:repo_hook` or equivalent for release asset deletion — the same scopes
used by the github-manager.

---

## Validation flow (the reason this tool exists)

After the fixes in claire-plugin#27 / #29 / #30 land, a validator session runs:

```bash
claire fivepoints reset-pbi --pbi 18839 --issue 71 --dry-run    # sanity check
claire fivepoints reset-pbi --pbi 18839 --issue 71 --confirm    # factory reset

# Wait for the GitHub Manager to re-spawn under role:analyst:
#   - analyst pulls the fresh FDS (validates #30)
#   - analyst posts an FDS read-receipt (validates #27)
#   - dev cross-checks against the FDS before implementing
#   - final PR scope matches FDS §10 (validates pipeline integrity)
```

Without `reset-pbi`, each validation attempt requires ~30 minutes of manual
cleanup that is error-prone.

---

## Example — dry-run

```bash
$ claire fivepoints reset-pbi --pbi 18839 --issue 71 --dry-run
=== fivepoints reset-pbi ===
PBI:        18839
Issue:      #71 on CLAIRE-Fivepoints/fivepoints
Mode:       dry-run
State file: /Users/.../99_runtime/github-manager/github_manager_state_CLAIRE-Fivepoints_fivepoints.json
TFIOneGit:  /Users/.../TFIOneGit
Log file:   /Users/.../.claire/logs/reset-pbi-18839-20260416-180000.log

── Collecting issue + PR + release context via gh...
=== reset_pbi plan (pbi=18839 issue=#71) ===
  [gh:comment] delete comment #4263612757 by claire-test-ai: '👍 Picking up this task.'
  [gh:labels]  set labels ['role:dev'] -> ['role:analyst']
  [gh:asset]   delete release asset 'proof-issue-71-swagger.mp4' from untagged-4eff
  [state:purge] remove issue #71 from ...github_manager_state_CLAIRE-Fivepoints_fivepoints.json

[dry-run] no changes applied

── Git + worktree cleanup on /Users/.../TFIOneGit
  worktree: /Users/.../TFIOneGit/.claire/worktrees/issue-71-feat-code-gen
  local branch: feature/18839-client-face-sheet
  github remote branch: feature/18839-client-face-sheet

=== DRY RUN complete — no changes applied ===
```

---

## See also

- `claire fivepoints reset-pipeline` — bulk reset of the whole pipeline backlog
- `claire issue reset <n>` — generic Claire issue reset (single issue, claire core)
- `claire domain read github_manager technical STATE_MANAGEMENT`
- `claire domain read claire operational SPAWN_TROUBLESHOOT`
