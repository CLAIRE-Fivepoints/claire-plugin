---
domain: five_points
category: operational
name: AZURE_ISSUE_BRIDGE
title: "Five Points — Azure DevOps Email Bridge (PBI Assignment → GitHub Issue Pipeline)"
keywords: [five-points, azure-devops, email-bridge, pbi, github-issue, gmail, automation, fivepoints, triage, dedup, duplicate-prevention]
updated: 2026-04-07
---

# Azure DevOps Email Bridge

Automated pipeline: watch Gmail for ADO PBI assignment emails → create structured GitHub issues in `claire-labs/fivepoints`.

This command lives inside the **fivepoints plugin**. The Python module is vendored under `domain/scripts/azure_issue_bridge/` and the bash router under `domain/commands/azure-issue-bridge.sh`.

---

## Purpose

When Azure DevOps assigns a Product Backlog Item (PBI) to `andre.perez@dothelpllc.com`, an email notification is sent to Gmail. This command automates the full response:

1. Poll Gmail inbox for Azure DevOps assignment notifications
2. Parse the PBI ID from the email subject
3. **Triage**: group emails by ADO work item ID; skip PBIs that already have a GitHub issue
4. Fetch the full work item from the Azure DevOps REST API (create decisions only)
5. Create a GitHub issue via `gh issue create`

---

## Email Trigger Pattern

Subject: `Product Backlog Item {ID} - {area} - {title}`

Filter criteria:
- Sender: `azuredevops@microsoft.com` (exact — used as Gmail `from:` query to pre-filter at API level)
- Subject matches: `Product Backlog Item \d+` (ID extracted from first token after prefix)
- Includes already-read emails (`unread_only=False`) — ADO notifications are auto-read by Gmail

---

## Pipeline

```
Gmail inbox
  → filter ADO assignment emails (unprocessed only)
  → TRIAGE: group emails by ADO work item ID
      → for each unique PBI ID: gh issue list --search "PBI #{id}" (open issues only)
      → if issue exists → action=skip (mark emails processed + archive)
      → if no issue   → action=create
  → [create only] GET https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{id}?$expand=all
  → gh issue create --repo claire-labs/fivepoints
  → persist all email IDs for this PBI to ~/.claire/azure-issue-bridge/processed.json
  → archive all emails for this PBI in Gmail (remove INBOX label)
```

**Triage rules (priority order):**

0. **State check (fail-safe)** — A GitHub issue is only created when the ADO work item state is explicitly known to be active. Any ambiguity → skip.
   - **State unavailable** (`pbi_id` absent from metadata — API error, timeout, bad JSON): skip with `skip_reason="state_unknown"`.
   - **State empty** (`""` returned by API): skip with `skip_reason="state_unknown"`.
   - **Terminal state** (`Done`, `Closed`, `Removed`, `Resolved` — case-insensitive): skip with `skip_reason="terminal_state"`.
   - **Unrecognised state** (any value not in `_ACTIVE_STATES`): skip with `skip_reason="state_unknown"`.
   - **Active state** (`To Do` — defined in `_ACTIVE_STATES`): proceed to Rule 1.
1. **Parent with children in batch** (Rule 1a) — if a non-Task work item has a child in the same email batch, skip the parent. The Task is the canonical GitHub issue for that piece of work.
2. **Unconditional type gate** (Rule 1b) — any work item whose type is not `Task` (PBI, Feature, User Story, Bug, Epic, etc.) is skipped immediately with `skip_reason="non_task_type"`, without making an ADO children API call. Only Tasks create GitHub issues.
3. **Duplicate** — the work item already has an open GitHub issue (`gh issue list --search "PBI #{id}"`). Closed issues do not block re-creation (closed = done, re-assignment = new work).

**GitHub issue body for Tasks** includes:
- **Parent PBI link** — ADO URL for hierarchy traceability
- **Parent PBI — Background** — the parent's description as business context (fetched from ADO)
- Parent AC is intentionally excluded — it covers all child tasks and would mix context intended for other developers working on sibling tasks

---

## Commands

```bash
claire fivepoints azure-issue-bridge run               # One-shot: scan inbox + process
claire fivepoints azure-issue-bridge run --dry-run     # Parse + format, but do NOT create issues
claire fivepoints azure-issue-bridge run --lookback 30d   # Limit scan to last 30 days
claire fivepoints azure-issue-bridge start             # Start background daemon (default: every 15 min)
claire fivepoints azure-issue-bridge start --interval N  # Custom poll interval in minutes
claire fivepoints azure-issue-bridge start --lookback 30d  # Daemon: limit each scan window to 30 days
claire fivepoints azure-issue-bridge stop              # Stop background daemon
claire fivepoints azure-issue-bridge status            # Show daemon state + last run stats
claire fivepoints azure-issue-bridge restore-inbox     # Restore archived ADO emails to inbox + reset processed.json
```

> **Backward compat:** `claire azure-issue-bridge <cmd>` delegates to `claire fivepoints azure-issue-bridge <cmd>` via the bridge shim in claire core.

#### `--lookback DAYS`

Limits the Gmail scan to emails received within the last N days by injecting a `newer_than:Nd` operator into the Gmail query. Accepts `'30d'` or bare integer `'30'`.

**When to use:** On first run or after a long idle period, the bridge may find very old archived PBI emails and create issues for already-completed work. Setting `--lookback 30d` prevents this.

**Default:** no limit (scans the full inbox).

### Daemon mode

`claire fivepoints azure-issue-bridge start` launches a **background polling daemon** (nohup + PID file at `~/.claire/runtime/azure-issue-bridge.pid`). The daemon runs the python CLI start loop every N minutes and exits cleanly on `claire fivepoints azure-issue-bridge stop`.

`claire fivepoints azure-issue-bridge status` reports both the daemon running state and the last scan statistics.

### Business hours

The daemon only polls during business hours — polls outside the window are skipped and logged. The window is configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ADO_BRIDGE_HOUR_START` | `8` | Start hour (0–23, local time, inclusive) |
| `ADO_BRIDGE_HOUR_END` | `17` | End hour (0–23, local time, exclusive) |

Example: to restrict to 9AM–6PM, set `ADO_BRIDGE_HOUR_START=9` and `ADO_BRIDGE_HOUR_END=18`.

### Auto-start via infra

When `AZURE_DEVOPS_PAT` is set (env or `~/.config/claire/.env`), `claire infra start` automatically starts the daemon (idempotent — safe to call multiple times). A **Client Daemons** section in the boot output shows daemon status alongside the core infrastructure table.

---

## GitHub Issue Format

Each issue is created with:
- **Title:** `{PBI title} (PBI #{id})`
- **Body:** ADO link, state, area path, description, acceptance criteria (when available)
- **Repo:** configured via `ADO_BRIDGE_REPO` (default: `claire-labs/fivepoints-test`)

---

## Required Credentials

| Credential | Scope | How to configure |
|-----------|-------|-----------------|
| `AZURE_DEVOPS_PAT` | Work Items → Read (issue bridge) | Export in environment or set in `~/.config/claire/.env` |
| `AZURE_DEVOPS_DEV_PAT` | Work Items R/W + Code + PRs (fivepoints plugin) | Set in `~/.config/claire/.env` — optional, falls back to `AZURE_DEVOPS_PAT` |
| Gmail OAuth2 | Gmail inbox read + archive | Run `claire email auth` (one-time setup) |

### ADO PAT priority chain

The azure-issue-bridge uses `AZURE_DEVOPS_PAT`. The fivepoints plugin (`ado_common.sh`) uses a longer chain to prefer the full-access dev PAT when available:

1. `$AZURE_DEVOPS_DEV_PAT` environment variable (full-access, for fivepoints)
2. `~/.config/claire/.env` — line: `AZURE_DEVOPS_DEV_PAT=<value>`
3. `$AZURE_DEVOPS_PAT` environment variable (read-only fallback)
4. `~/.config/claire/.env` — line: `AZURE_DEVOPS_PAT=<value>`
5. PAT embedded in git remote URL (fivepoints plugin only)

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_DEVOPS_PAT` | _(required)_ | Read-only PAT for issue bridge — auto-starts daemon via `claire infra start` when set |
| `AZURE_DEVOPS_DEV_PAT` | _(optional)_ | Full-access PAT for fivepoints plugin — falls back to `AZURE_DEVOPS_PAT` |
| `ADO_BRIDGE_REPO` | `claire-labs/fivepoints-test` | Target GitHub repo for created issues |
| `ADO_ORG` | `FivePointsTechnology` | Azure DevOps organization |
| `ADO_PROJECT` | `TFIOne` | Azure DevOps project |
| `ADO_BRIDGE_HOUR_START` | `8` | Business hours start (local time, inclusive) |
| `ADO_BRIDGE_HOUR_END` | `17` | Business hours end (local time, exclusive) |

---

## State Files

| File | Purpose |
|------|---------|
| `~/.claire/azure-issue-bridge/state.json` | Last run metadata (timestamp, counts) |
| `~/.claire/azure-issue-bridge/processed.json` | Processed email IDs (dedup guard) |
| `~/.claire/runtime/azure-issue-bridge.pid` | Daemon PID file (global singleton) |
| `~/.claire/runtime/logs/azure-issue-bridge.log` | Daemon stdout/stderr log |

---

## Source Files (in this plugin)

| File | Role |
|------|------|
| `domain/scripts/azure_issue_bridge/bridge.py` | Core pipeline logic |
| `domain/scripts/azure_issue_bridge/cli.py` | CLI entry point (`python3 -m azure_issue_bridge.cli`) |
| `domain/scripts/azure_issue_bridge/tests/` | Unit tests (triage, fetch metadata, concurrent lock) |
| `domain/commands/azure-issue-bridge.sh` | Bash router — sets PYTHONPATH and dispatches to the python CLI |

The bash router prepends `domain/scripts` to `PYTHONPATH` so the package is importable as `azure_issue_bridge`. The module still imports `claire_py.email.auth` and `claire_py.email.watcher` from claire core (which remain there).

---

## First-Time Setup

```bash
# 1. Authorize Gmail (one-time)
claire email auth

# 2. Set credentials
export AZURE_DEVOPS_PAT=<your-pat>
# Or add to ~/.config/claire/.env

# 3. Run (default target: claire-labs/fivepoints-test)
claire fivepoints azure-issue-bridge run --dry-run   # Verify parsing without creating issues
claire fivepoints azure-issue-bridge run             # Create issues in fivepoints-test

# 4. Go live (production)
export ADO_BRIDGE_REPO=claire-labs/fivepoints
claire fivepoints azure-issue-bridge run
```
