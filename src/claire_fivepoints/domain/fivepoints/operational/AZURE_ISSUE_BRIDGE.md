---
domain: fivepoints
category: operational
name: AZURE_ISSUE_BRIDGE
title: "Five Points — Azure DevOps Email Bridge (PBI Assignment → GitHub Issue Pipeline)"
keywords: [five-points, azure-devops, email-bridge, pbi, github-issue, gmail, automation, fivepoints, triage, dedup, duplicate-prevention]
updated: 2026-06-28
---

# Azure DevOps Email Bridge

Automated pipeline: watch Gmail for ADO PBI assignment emails → create structured GitHub issues → spawn a Claire agent.

This command lives inside the **fivepoints plugin**. The Python module is vendored under `domain/scripts/azure_issue_bridge/` and the bash router under `domain/commands/azure-issue-bridge.sh`.

---

## End-to-End Pipeline

```
ADO PBI assigned to andre.perez@dothelpllc.com
  → Azure DevOps sends notification email (from: azuredevops@microsoft.com)
  → Gmail inbox receives email (andre.perez@dothelpllc.com)
  → azure-issue-bridge daemon detects email (polling every 15 min, 8AM–5PM)
  → parses PBI ID from subject: "Product Backlog Item {ID} - {area} - {title}"
  → TRIAGE: skip if duplicate, terminal state, or non-Task type
  → fetches PBI details from ADO REST API (AZURE_DEVOPS_PAT)
  → creates GitHub issue in ADO_BRIDGE_REPO (default: claire-labs/fivepoints-test)
  → archives email in Gmail
  → claire spawn daemon (consumer.py) detects new issue in ADO_BRIDGE_REPO
  → spawns Claire agent in isolated worktree
  → agent receives CLAIRE_WAIT_REPO=<ADO_BRIDGE_REPO> for wait/PR targeting
```

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
- Sender: `azuredevops@microsoft.com` by default — configurable via `--from` on the `run` command
- Subject matches: `Product Backlog Item \d+` (ID extracted from first token after prefix)
- Includes already-read emails (`unread_only=False`) — ADO notifications are auto-read by Gmail

---

## Pipeline (Detail)

```
Gmail inbox
  → filter ADO assignment emails (unprocessed only)
  → TRIAGE: group emails by ADO work item ID
      → for each unique PBI ID: gh issue list --search "PBI #{id}" (open issues only)
      → if issue exists → action=skip (mark emails processed + archive)
      → if no issue   → action=create
  → [create only] GET https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{id}?$expand=all
  → gh issue create --repo <ADO_BRIDGE_REPO>
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

## Spawn Daemon Pickup

After the bridge creates a GitHub issue, the **claire spawn daemon** (`consumer.py`) takes over:

1. The spawn daemon monitors `ADO_BRIDGE_REPO` for newly opened issues
2. When an issue matching the spawn criteria is detected, it creates an isolated git worktree
3. A Claire agent is launched inside the worktree with the issue as its task
4. The agent receives `CLAIRE_WAIT_REPO=<ADO_BRIDGE_REPO>` in its environment so `claire wait` targets the correct repo for PR creation and review polling

**`ADO_BRIDGE_REPO` vs `CLAIRE_WAIT_REPO`:**
- `ADO_BRIDGE_REPO` — configures where the bridge creates GitHub issues (set at bridge/operator level)
- `CLAIRE_WAIT_REPO` — passed by the spawn daemon into the spawned agent's environment so the agent knows which repo to watch for wait events
- Both refer to the same repo; they are different variable names at different stages of the pipeline

To repoint the pipeline to a different repo, set `ADO_BRIDGE_REPO`:

```bash
export ADO_BRIDGE_REPO=claire-labs/fivepoints   # production
export ADO_BRIDGE_REPO=claire-labs/fivepoints-test  # staging (default)
```

---

## Commands

```bash
# Run sub-command options:
#   --from SENDER   Sender email filter (default: azuredevops@microsoft.com)
#   --repo TEXT     Target GitHub repo — owner/name (default: claire-labs/fivepoints-test)
#   --dry-run       Parse + format, but do NOT create issues
#   --max-results N Max inbox emails to scan (default: 20)

claire fivepoints azure-issue-bridge run                                          # One-shot: scan inbox + process (ADO prod sender)
claire fivepoints azure-issue-bridge run --dry-run                                # Parse + format, no issues created
claire fivepoints azure-issue-bridge run --from andreoperez@gmail.com --dry-run   # Test sender override (replaces PBI_TEST_SENDER)
claire fivepoints azure-issue-bridge run --repo claire-labs/fivepoints            # Production repo
claire fivepoints azure-issue-bridge start             # Start background daemon (default: every 15 min)
claire fivepoints azure-issue-bridge stop              # Stop background daemon
claire fivepoints azure-issue-bridge status            # Show daemon state + last run stats
claire fivepoints azure-issue-bridge restore-inbox     # Restore archived ADO emails to inbox + reset processed.json
```

---

## GitHub Issue Format

Each issue is created with:
- **Title:** `{PBI title} (PBI #{id})`
- **Body:** ADO link, state, area path, description, acceptance criteria (when available)
- **Repo:** configured via `ADO_BRIDGE_REPO` (default: `claire-labs/fivepoints-test`)

---

## Prerequisites

Before the bridge can run, three things must be in place:

| Requirement | What it enables | How to set up |
|-------------|-----------------|---------------|
| `AZURE_DEVOPS_PAT` | Fetch PBI details from ADO REST API | Set in `~/.config/claire/.env` or export in shell |
| Gmail OAuth2 | Read + archive Gmail inbox | Run `claire email auth` (one-time browser flow) |
| `ADO_BRIDGE_REPO` | Where GitHub issues are created | Set in `~/.config/claire/.env`; defaults to `claire-labs/fivepoints-test` |

---

## Required Credentials

| Credential | Scope | How to configure |
|-----------|-------|--------------------|
| `AZURE_DEVOPS_PAT` | Work Items → Read (issue bridge) | Export in environment or set in `~/.config/claire/.env` |
| `AZURE_DEVOPS_DEV_PAT` | Work Items R/W + Code + PRs (fivepoints plugin) | Set in `~/.config/claire/.env` — optional, falls back to `AZURE_DEVOPS_PAT` |
| Gmail OAuth2 | Gmail inbox read + archive | Run `claire email auth` (one-time setup) |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_DEVOPS_PAT` | _(required)_ | Read-only PAT for issue bridge — auto-starts daemon via `claire infra start` when set |
| `AZURE_DEVOPS_DEV_PAT` | _(optional)_ | Full-access PAT for fivepoints plugin — falls back to `AZURE_DEVOPS_PAT` |
| `ADO_BRIDGE_REPO` | `claire-labs/fivepoints-test` | Default repo for daemon (`azure-issue-bridge start`). The `run` sub-command uses `--repo` instead. |
| `ADO_ORG` | `FivePointsTechnology` | Azure DevOps organization |
| `ADO_PROJECT` | `TFIOne` | Azure DevOps project |
| `ADO_BRIDGE_HOUR_START` | `8` | Business hours start (local time, inclusive) |
| `ADO_BRIDGE_HOUR_END` | `17` | Business hours end (local time, exclusive) |
| `PBI_TEST_SENDER` | _(removed)_ | Replaced by `--from` on `fivepoints azure-issue-bridge run`. No longer read by the `run` sub-command. |
| `PBI_SENDER` | _(removed)_ | Replaced by `--from` on `fivepoints azure-issue-bridge run`. No longer read by the `run` sub-command. |

---

## State Files

| File | Purpose |
|------|---------|
| `~/.claire/azure-issue-bridge/state.json` | Last run metadata (timestamp, counts) |
| `~/.claire/azure-issue-bridge/processed.json` | Processed email IDs (dedup guard) |
| `~/.claire/runtime/azure-issue-bridge.pid` | Daemon PID file (global singleton) |
| `~/.claire/runtime/logs/azure-issue-bridge.log` | Daemon stdout/stderr log |

---

## Source Files

### Core pipeline (fivepoints-plugin)

| File | Role |
|------|------|
| `domain/scripts/azure_issue_bridge/bridge.py` | Core pipeline logic |
| `domain/scripts/azure_issue_bridge/cli.py` | CLI entry point (`python3 -m azure_issue_bridge.cli`) |
| `domain/scripts/azure_issue_bridge/tests/` | Unit tests (triage, fetch metadata, concurrent lock) |
| `domain/commands/azure-issue-bridge.sh` | Bash router — sets PYTHONPATH and dispatches to the python CLI |

The bash router prepends `domain/scripts` to `PYTHONPATH` so the package is importable as `azure_issue_bridge`. The module still imports `claire_py.email.auth` and `claire_py.email.watcher` from claire core (which remain there).

### Sender configuration (claire-labs/claire — this plugin)

| File | Role |
|------|------|
| `plugins/fivepoints/src/claire_fivepoints/azure_issue_bridge/bridge.py` | `is_pbi_email()` predicate + `MockEmailFilter` |
| `plugins/fivepoints/src/claire_fivepoints/azure_issue_bridge/adapters.py` | `EmailAdapter`, `GitHubAdapter` protocols + `BridgeAdapters` + test doubles |
| `plugins/fivepoints/src/claire_fivepoints/azure_issue_bridge/steps.py` | Pure pipeline steps: `fetch_emails_step`, `filter_pbi_step`, `create_issues_step` |
| `plugins/fivepoints/src/claire_fivepoints/azure_issue_bridge/pipeline.py` | `BridgeTask` + `bridge_pipeline = pipe(...)` |
| `plugins/fivepoints/src/claire_fivepoints/cli.py` | CLI entry point — `fivepoints azure-issue-bridge run [--from] [--repo] [--dry-run]`; concrete subprocess adapters |
| `plugins/fivepoints/src/claire_fivepoints/azure_issue_bridge/tests/` | Unit tests for email filtering and pipeline (zero subprocess, zero network) |

The sender is passed via `--from` flag (`azuredevops@microsoft.com` by default). The pipeline is composed via `claire_core.pipeline.pipe()`. The core triage/ADO fetch logic remains in the fivepoints-plugin repo.

---

## First-Time Setup

```bash
# 1. Authorize Gmail (one-time)
claire email auth

# 2. Set credentials
export AZURE_DEVOPS_PAT=<your-pat>
# Or add to ~/.config/claire/.env:
#   AZURE_DEVOPS_PAT=<your-pat>

# 3. Verify (dry-run — no issues created, no emails archived)
claire fivepoints azure-issue-bridge run --dry-run

# 4. Run against staging repo (default)
claire fivepoints azure-issue-bridge run             # creates issues in claire-labs/fivepoints-test

# 5. Go live (production)
export ADO_BRIDGE_REPO=claire-labs/fivepoints
claire fivepoints azure-issue-bridge run
```

### Testing with a custom sender

To route test emails through the bridge without ADO, use `--from`:

```bash
# Send yourself an email with ADO-format subject:
#   "Product Backlog Item 99999 - DEV - test title"

# Verify detection
claire fivepoints azure-issue-bridge run --from andreoperez@gmail.com --dry-run
```

---

## Troubleshooting

### Bridge creates no issues — dry-run shows nothing

**Symptom:** `run --dry-run` exits with 0 issues found.

**Causes:**
- No unprocessed ADO emails in inbox — check Gmail for messages from `azuredevops@microsoft.com`
- All matching emails already processed — check `~/.claire/azure-issue-bridge/processed.json`
- Emails were archived but not recorded — run `restore-inbox` to reset

```bash
# Check what's in processed state
cat ~/.claire/azure-issue-bridge/processed.json | python3 -m json.tool | head -30

# Reset state and restore emails (use cautiously — re-processes everything)
claire fivepoints azure-issue-bridge restore-inbox
claire fivepoints azure-issue-bridge run --dry-run
```

### `AZURE_DEVOPS_PAT not set` — daemon skips auto-start

**Fix:** Add the PAT to `~/.config/claire/.env`:
```bash
echo 'AZURE_DEVOPS_PAT=<your-pat>' >> ~/.config/claire/.env
claire fivepoints azure-issue-bridge start
```

### Gmail not authorized — authentication error

```bash
claire email auth
claire email status          # verify: should show inbox access
claire fivepoints azure-issue-bridge run --dry-run
```

### ADO REST API returns 401 / 403

PAT expired or lacks Work Items → Read scope. Generate a new one in Azure DevOps and update `~/.config/claire/.env`.
