---
domain: fivepoints
category: operational
name: AZURE_ISSUE_BRIDGE
title: "Five Points — Azure DevOps Email Bridge (PBI Assignment → GitHub Issue Pipeline)"
keywords: [five-points, azure-devops, email-bridge, pbi, github-issue, gmail, automation, fivepoints, triage, dedup, duplicate-prevention, PBI_SENDER, configurable-sender, branch-sync, inject, synthetic-email, ADO_BRIDGE_SYNC_SOURCE, ADO_BRIDGE_SYNC_TARGET, ADO_BRIDGE_SYNC_BRANCH, ADO_BRIDGE_AGENT, ADO_BRIDGE_CLIENT, worktree, role-label, PrepareWorktreeStep, claire:meta, feature-branch, branch-convention, pbi_id, slug]
updated: 2026-06-30
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
  → creates GitHub issue in ADO_BRIDGE_SYNC_TARGET repo
  → adds role label: role:{ADO_BRIDGE_CLIENT}-dev
  → syncs ADO_BRIDGE_SYNC_SOURCE/develop → ADO_BRIDGE_SYNC_TARGET/develop (GitHub REST API)
  → archives email in Gmail
  → (manual) operator assigns the issue — the bridge no longer auto-assigns (#175)
  → session-monitor detects the assignment, runs:
      claire run-pipeline run --workflow fivepoints.tfone.dev --issue N
  → PrepareWorktreeStep creates <local>/.claire/worktrees/issue-{N}
      on develop, synced from ado/dev (see § Worktree Creation below)
  → the dev agent creates feature/{pbi_id}-{slug} itself and posts it
      in a <!-- claire:meta --> comment (see fivepoints-dev persona)
  → agent receives CLAIRE_WAIT_REPO=<ADO_BRIDGE_SYNC_TARGET> for wait/PR targeting
```

> The bridge pipeline (`bridge_pipeline` in `azure_issue_bridge/pipeline.py`) itself ends at
> `sync_branch_step` — it creates the issue, labels it, and syncs the branch, nothing more.
> Assignment is a manual operator step; worktree creation belongs to the `fivepoints.tfone.dev`
> pipeline, not the bridge (issue #178).

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

## Pipeline (Detail)

```
Gmail inbox
  → filter ADO assignment emails (unprocessed only)
  → TRIAGE: group emails by ADO work item ID
      → for each unique PBI ID: gh issue list --search "PBI #{id}" (open issues only)
      → if issue exists → action=skip (mark emails processed + archive)
      → if no issue   → action=create
  → [create only] GET https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{id}?$expand=all
  → gh issue create --repo <ADO_BRIDGE_SYNC_TARGET>
  → gh issue edit --add-label role:{ADO_BRIDGE_CLIENT}-dev
  → sync ADO_BRIDGE_SYNC_SOURCE/<branch> → ADO_BRIDGE_SYNC_TARGET/<branch> (GitHub REST API)
      → failure aborts pipeline for this PBI (no archiving, no agent assignment)
  → gh issue edit --add-assignee <ADO_BRIDGE_AGENT>  ← ALWAYS LAST
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

## Worktree Creation — `PrepareWorktreeStep` (issue #178)

After the bridge finishes and the issue is assigned (manually, or by automation outside the
bridge), the **session-monitor** detects the assignment and runs:

```bash
claire run-pipeline run --workflow fivepoints.tfone.dev --issue N --repo <ADO_BRIDGE_SYNC_TARGET>
```

This executes `FivepointsTfoneDevWorkflow` (`claire_fivepoints.tfone_dev_steps`), whose second
step — `PrepareWorktreeStep`, right after `HydrateStateStep` and before `SpawnDevStep` — owns
worktree creation. The bridge itself (`prepare_worktree_step` in `azure_issue_bridge/steps.py`)
is **not** wired into `bridge_pipeline` — worktree creation lives entirely in the dev pipeline.

### What `PrepareWorktreeStep` does (issue #184)

`PrepareWorktreeStep` only prepares the worktree — it does not derive or create a named
branch. Branch naming is the dev agent's responsibility (see the `fivepoints-dev` persona
checklist).

1. Checks whether `<local_path>/.claire/worktrees/issue-{N}` already exists. If it does,
   returns immediately — **idempotent on pipeline restart**, no second worktree.
2. Otherwise, via `RealWorktreePrepare` (`azure_issue_bridge/worktree.py`):
   a. `git fetch ado dev` — pulls the latest `TFIOneGit/dev` from the ADO remote. The
      GitHub mirror (`origin/develop`) can lag behind ADO, so this step syncs directly
      from ADO rather than trusting the mirror. **Prerequisite:** the `ado` git remote
      is not auto-created — see `claire domain read fivepoints operational
      PIPELINE_WORKFLOW` § "V2 (fivepoints.tfone.dev) prerequisite — the ado remote
      is NOT auto-created" for the one-time per-machine setup command.
   b. `git branch -f develop ado/dev` — force-updates the local `develop` branch to match.
   c. `git worktree add --detach <path> develop` — checks out `develop` in the new
      worktree in a **detached HEAD** state. No branch is created or named here.

The dev agent (`fivepoints-dev` persona), after reading the issue and the FDS, creates
`feature/{pbi_id}-{slug}` itself — the FivePoints convention
(`claire domain read fivepoints knowledge DEV_RULES` rule #5) — and posts it in a
`<!-- claire:meta -->` comment on the issue. `PushToADOStep`
(`claire_fivepoints.tfone_dev_steps`, a local variant — not the one in core's
`claire_workflows.fivepoints_pipeline`) reads `branch_name` back from that comment
(validated against `^feature/\d+-[a-z0-9-]+$` — a malformed or forged comment is never
trusted as-is) and pushes that exact branch to the `ado` remote.

`CLAIRE_WAIT_REPO=<ADO_BRIDGE_SYNC_TARGET>` is still set in the agent's environment so
`claire wait` targets the correct repo for PR creation and review polling.

**`ADO_BRIDGE_SYNC_TARGET` vs `CLAIRE_WAIT_REPO`:**
- `ADO_BRIDGE_SYNC_TARGET` — configures where the bridge creates GitHub issues (set at bridge/operator level)
- `CLAIRE_WAIT_REPO` — passed by the spawn daemon into the spawned agent's environment so the agent knows which repo to watch for wait events
- Both refer to the same repo; they are different variable names at different stages of the pipeline

To repoint the pipeline to a different repo, set `ADO_BRIDGE_SYNC_TARGET`:

```bash
export ADO_BRIDGE_SYNC_TARGET=CLAIRE-Fivepoints/fivepoints   # production
export ADO_BRIDGE_SYNC_TARGET=CLAIRE-Fivepoints/fivepoints-test  # staging (default)
```

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

# inject — synthetic email injection (no Gmail or ADO auth required)
claire fivepoints azure-issue-bridge inject \
  --from "azuredevops@microsoft.com" \
  --subject "Product Backlog Item 12345 - DEV - Client Management test" \
  --dry-run   # Print parsed result, create nothing

claire fivepoints azure-issue-bridge inject \
  --from "azuredevops@microsoft.com" \
  --subject "Product Backlog Item 12345 - DEV - Client Management test"
  # Creates issue in fivepoints-test (default)
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

### inject — synthetic email injection

`claire fivepoints azure-issue-bridge inject` feeds a synthetic email directly into the bridge pipeline without polling Gmail or calling the ADO REST API. It is designed for e2e testing: no `AZURE_DEVOPS_PAT` required, no Gmail auth required.

The command:
1. Constructs an `EmailMessage` from `--from` and `--subject`
2. Validates it with `is_pbi_email()` (subject must match the ADO PBI pattern)
3. Builds a synthetic `WorkItem` from the parsed subject (no ADO fetch — subject data only)
4. In live mode: runs the full pipeline — `create_issue → add_label → sync_branch → assign` (GitHub auth required, no Gmail or ADO auth)
5. In `--dry-run` mode: prints the parsed PBI and the planned pipeline steps, creates nothing

```bash
# Dry-run — print parsed PBI + issue body, create nothing
claire fivepoints azure-issue-bridge inject \
  --from "azuredevops@microsoft.com" \
  --subject "Product Backlog Item 12345 - DEV - Client Management test" \
  --dry-run

# Live — create issue in fivepoints-test (default staging repo)
claire fivepoints azure-issue-bridge inject \
  --from "azuredevops@microsoft.com" \
  --subject "Product Backlog Item 12345 - DEV - Client Management test"

# Target a specific repo
claire fivepoints azure-issue-bridge inject \
  --from "azuredevops@microsoft.com" \
  --subject "Product Backlog Item 12345 - DEV - Client Management test" \
  --repo CLAIRE-Fivepoints/fivepoints
```

| Flag | Default | Description |
|------|---------|-------------|
| `--from ADDRESS` | _(required)_ | Sender address (e.g. `azuredevops@microsoft.com`) |
| `--subject SUBJECT` | _(required)_ | Email subject matching the ADO PBI pattern |
| `--dry-run` | false | Print parsed result + pipeline plan without creating anything |
| `--repo OWNER/NAME` | `ADO_BRIDGE_SYNC_TARGET` or `claire-labs/fivepoints-test` | Target GitHub repo override |
| `--agent USERNAME` | `ADO_BRIDGE_AGENT` or `claire-test-ai` | GitHub assignee for the created issue |

### Auto-start via infra

When `AZURE_DEVOPS_PAT` is set (env or `~/.config/claire/.env`), `claire infra start` automatically starts the daemon (idempotent — safe to call multiple times). A **Client Daemons** section in the boot output shows daemon status alongside the core infrastructure table.

---

## GitHub Issue Format

Each issue is created with:
- **Title:** `{PBI title} (PBI #{id})`
- **Body:** ADO link, state, area path, description, acceptance criteria (when available)
- **Repo:** configured via `ADO_BRIDGE_REPO` (default: `CLAIRE-Fivepoints/fivepoints`)

---

## Prerequisites

Before the bridge can run, three things must be in place:

| Requirement | What it enables | How to set up |
|-------------|-----------------|---------------|
| `AZURE_DEVOPS_PAT` | Fetch PBI details from ADO REST API | Set in `~/.config/claire/.env` or export in shell |
| Gmail OAuth2 | Read + archive Gmail inbox | Run `claire email auth` (one-time browser flow) |
| `ADO_BRIDGE_REPO` | Where GitHub issues are created | Set in `~/.config/claire/.env`; defaults to `CLAIRE-Fivepoints/fivepoints` |

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
| `ADO_BRIDGE_REPO` | `CLAIRE-Fivepoints/fivepoints` | Target GitHub repo for created issues (also sets `CLAIRE_WAIT_REPO` in spawned agents) |
| `ADO_ORG` | `FivePointsTechnology` | Azure DevOps organization |
| `ADO_PROJECT` | `TFIOne` | Azure DevOps project |
| `ADO_BRIDGE_HOUR_START` | `8` | Business hours start (local time, inclusive) |
| `ADO_BRIDGE_HOUR_END` | `17` | Business hours end (local time, exclusive) |
| `PBI_SENDER` | `azuredevops@microsoft.com` | Override the production ADO sender. Use when ADO notifications come from a custom address. Falls back to the ADO default when unset. |
| `ADO_BRIDGE_AGENT` | `claire-test-ai` | GitHub username assigned to each new issue. **Set this explicitly in production** — the default targets the test account. |
| `ADO_BRIDGE_CLIENT` | `fivepoints` | Client slug used to build the role label: `role:{ADO_BRIDGE_CLIENT}-dev`. Determines which agent persona is activated by the spawn daemon. |
| `ADO_BRIDGE_SYNC_SOURCE` | `CLAIRE-Fivepoints/fivepoints` | Source GitHub repo for branch sync (the repo Claire agents push to). |
| `ADO_BRIDGE_SYNC_TARGET` | `CLAIRE-Fivepoints/fivepoints` | Target GitHub repo where issues are created, where the worktree branch is pushed, and where the issue is assigned. |
| `ADO_BRIDGE_SYNC_BRANCH` | `develop` | Branch name synced from source to target (legacy scripts only). The Python package (`claire fivepoints azure-issue-bridge`) hardcodes `develop` in `sync_branch_step`; this variable has no effect on the Typer CLI. |

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

### Python package (`claire fivepoints azure-issue-bridge` CLI)

| File | Role |
|------|------|
| `src/claire_fivepoints/azure_issue_bridge/adapters.py` | Protocols (`EmailAdapter`, `GitHubAdapter`, `LabelAdapter`, `BranchSyncAdapter`), `RealBranchSync` (GitHub REST API, no subprocess), `GmailApiAdapter`, and test doubles (`MockBranchSync`, `MockLabelAdapter`, `MockEmailAdapter`, `MockGitHubAdapter`) |
| `src/claire_fivepoints/azure_issue_bridge/steps.py` | Pure pipeline steps: `fetch_emails_step`, `filter_pbi_step`, `create_issues_step`, `add_label_step`, `sync_branch_step` |
| `src/claire_fivepoints/azure_issue_bridge/pipeline.py` | `BridgeTask` (pydantic task), `bridge_pipeline` (`pipe()` composition) |
| `src/claire_fivepoints/azure_issue_bridge/bridge.py` | `is_pbi_email()` filter predicate |
| `src/claire_fivepoints/azure_issue_bridge/tests/` | Unit tests — zero network calls, zero subprocess |
| `src/claire_fivepoints/cli.py` | Typer CLI entry point (`claire fivepoints azure-issue-bridge run / inject`) — subprocess-backed adapters (`_GhCliAdapter`, `_RealLabelAdapter`) live here |

### Legacy scripts (domain/scripts — predecessor, retained for reference)

| File | Role |
|------|------|
| `domain/scripts/azure_issue_bridge/bridge.py` | Original core pipeline logic (predecessor to the Python package) |
| `domain/scripts/azure_issue_bridge/sync.py` | Original branch sync adapter (`RealBranchSync` using GitHub REST API) |
| `domain/scripts/azure_issue_bridge/worktree.py` | Original worktree adapter (`RealWorktreePrepare`) |
| `domain/scripts/azure_issue_bridge/cli.py` | Original CLI entry point (`python3 -m azure_issue_bridge.cli`) |
| `domain/commands/azure-issue-bridge.sh` | Bash router — sets PYTHONPATH and dispatches to the original python CLI |

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

---

## Troubleshooting

### Bridge creates no issues — dry-run shows nothing

**Symptom:** `run --dry-run` exits with 0 issues found.

**Causes:**
- No unprocessed ADO emails in inbox — check Gmail for messages from `azuredevops@microsoft.com`
- All matching emails already processed — check `~/.claire/azure-issue-bridge/processed.json`
- Lookback window too narrow — try without `--lookback` or extend the window
- Emails were archived but not recorded — run `restore-inbox` to reset

```bash
# Check what's in processed state
cat ~/.claire/azure-issue-bridge/processed.json | python3 -m json.tool | head -30

# Reset state and restore emails (use cautiously — re-processes everything)
claire fivepoints azure-issue-bridge restore-inbox
claire fivepoints azure-issue-bridge run --dry-run
```

### `AZURE_DEVOPS_PAT not set` — daemon skips auto-start

**Symptom:** `claire infra start` shows "Azure issue bridge: AZURE_DEVOPS_PAT not set — skipping auto-start"

**Fix:** Add the PAT to `~/.config/claire/.env`:
```bash
echo 'AZURE_DEVOPS_PAT=<your-pat>' >> ~/.config/claire/.env
claire fivepoints azure-issue-bridge start
```

### Gmail not authorized — authentication error

**Symptom:** Bridge exits with an OAuth2 error or `gmail_token.json` missing.

**Fix:** Re-run the OAuth2 flow:
```bash
claire email auth
claire email status          # verify: should show inbox access
claire fivepoints azure-issue-bridge run --dry-run
```

If `gmail_credentials.json` is missing entirely, download it from Google Cloud Console (OAuth 2.0 client) and place it at `~/.config/claire/gmail_credentials.json`.

### Issues created in wrong repo

**Symptom:** Issues appear in `claire-labs/fivepoints-test` instead of `claire-labs/fivepoints` (or vice versa).

**Fix:** Set `ADO_BRIDGE_REPO` explicitly:
```bash
export ADO_BRIDGE_REPO=claire-labs/fivepoints
# Or add to ~/.config/claire/.env
claire fivepoints azure-issue-bridge status    # confirm current config
```

### Daemon not starting — PID file stale

**Symptom:** `status` reports "stopped" but `start` says "already running" or fails silently.

**Fix:**
```bash
# Check for stale PID file
cat ~/.claire/runtime/azure-issue-bridge.pid
ps aux | grep azure_issue_bridge

# Remove stale PID and restart
rm -f ~/.claire/runtime/azure-issue-bridge.pid
claire fivepoints azure-issue-bridge start
```

### ADO REST API returns 401 / 403

**Symptom:** Bridge logs show HTTP 401 or 403 when fetching PBI details.

**Causes:**
- PAT expired — generate a new one in Azure DevOps (User Settings → Personal Access Tokens)
- PAT lacks Work Items → Read scope

**Fix:**
```bash
# Update the PAT
export AZURE_DEVOPS_PAT=<new-pat>
# Or update ~/.config/claire/.env

# Verify API access
PAT=$AZURE_DEVOPS_PAT
AUTH=$(echo -n ":${PAT}" | base64)
curl -s -H "Authorization: Basic ${AUTH}" \
  "https://dev.azure.com/FivePointsTechnology/TFIOne/_apis/wit/workitems/1?api-version=7.1" \
  | python3 -m json.tool | head -10
```

### Spawn daemon doesn't pick up the created issue

**Symptom:** Bridge creates the GitHub issue, but no agent is spawned.

**Check:**
1. Is the spawn daemon running? `claire infra status` — look for `spawn-daemon`
2. Does the issue match spawn criteria? The spawn daemon only picks up issues assigned to the configured GitHub assignee
3. Is `ADO_BRIDGE_REPO` the same repo the spawn daemon monitors?

```bash
claire infra status                             # check spawn-daemon health
claire spawn-daemon status                      # detailed spawn daemon state
gh issue list --repo claire-labs/fivepoints-test --state open   # confirm issue exists
```
