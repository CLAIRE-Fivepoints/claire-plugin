---
domain: five_points
category: operational
name: ADO_WATCH
title: "Five Points — ADO PR Continuous Monitor (ado-watch)"
keywords: [five-points, ado-watch, azure-devops, monitor, polling, pr, continuous, comments, votes, merge]
updated: 2026-03-25
---

# Five Points — ADO PR Continuous Monitor

## Purpose

`claire fivepoints ado-watch --pr N` continuously monitors a specific Azure DevOps PR
and reports ALL activity — unlike `fivepoints wait --pr N` which exits after the first event.

Use this after creating a PR in ADO: it keeps running, reporting every new comment,
vote change, and eventually the merge/abandon. Exits automatically when the PR closes.

---

## Usage

```bash
claire fivepoints ado-watch --pr 123              # Watch PR #123, every 5 minutes
claire fivepoints ado-watch --pr 123 --interval 60  # Watch every minute (dev mode)
```

**As a background task:**
```bash
Bash(command: "claire fivepoints ado-watch --pr 123", run_in_background: true)
```

---

## Key Difference vs `fivepoints wait`

| Feature | `fivepoints wait --pr N` | `fivepoints ado-watch --pr N` |
|---------|--------------------------|-------------------------------|
| Events reported | First event only, then exits | ALL events, keeps running |
| PR closed/merged | Continues running | Exits automatically |
| Use case | One-shot unblock | Long-running session monitor |

---

## What It Reports

| Event | Output |
|-------|--------|
| New comments | `NEW COMMENT (old -> new): last by "Name"` |
| Vote change | `VOTE CHANGE: N reviewer(s) voted` |
| PR merged | `PR #N COMPLETED (merged)` → exits |
| PR abandoned | `PR #N ABANDONED` → exits |
| No changes | `No new activity (N comment(s), N vote(s))` |

---

## Detection Method

- **Comments**: Counts non-system text comments across all PR threads (`/pullRequests/N/threads`)
- **Votes**: Counts reviewers with non-zero vote from PR object (`/pullrequests/N`)
- **Status**: Checks PR `status` field (active → completed/abandoned)

Poll interval: 5 minutes (2 API calls per cycle).

---

## Authentication

PAT auto-discovered in order:
1. `AZURE_DEVOPS_PAT` environment variable
2. `~/.config/claire/.env` — key `AZURE_DEVOPS_PAT`
3. `/Users/andreperez/TFIOneGit` git remote URL (embedded PAT)

No manual setup needed on this machine.

---

## Repo Details

| Field | Value |
|-------|-------|
| Org | `FivePointsTechnology` |
| Project | `TFIOne` |
| Repo | `TFIOneGit` |
| Script | `30_universe/plugins/fivepoints/domain/commands/ado-watch.sh` |

---

## Related Commands

| Command | When to use |
|---------|-------------|
| `claire fivepoints wait --pr N` | One-shot: block until first event, then exit |
| `claire fivepoints ado-watch --pr N` | Continuous: run all session, report all events |
| `claire fivepoints pr-status --pr N` | Show current status/votes/build |
| `claire fivepoints pr-comments --pr N` | List all comment threads |
