# FivePoints Plugin

Azure DevOps integration for TFI One — connects ADO work items to the Claire agent pipeline.

**Source of truth:** https://github.com/CLAIRE-Fivepoints/claire-plugin

---

## Pipeline Overview

```
ADO assigns PBI to André
        ↓
Gmail receives email from azuredevops@microsoft.com
        ↓
Bridge daemon (every 15 min, 8AM–5PM)
  → scans Gmail inbox
  → reads work item from ADO (AZURE_DEVOPS_PAT read)
  → creates GitHub issue in CLAIRE-Fivepoints/fivepoints
        ↓
Task-dispatcher (cron every 30 min)
  → assigns issue to claire-test-ai with label role:analyst
  → spawn triggers → terminal opens
        ↓
[Analyst] → [Dev] → [Tester] → ADO PR → merged → issue closed
```

---

## Agent Roles — Start to Finish

### Analyst (`role:analyst`)

**Goal:** Read the FDS, write specs, create the feature branch.

```
1. Read the FDS sections referenced in the issue (ADO read PAT)
2. Search domain knowledge: claire domain search "<section name>"
3. Write specs as a GitHub issue comment
4. Create branch: feature/{ticket-id}-{description}
   git push github feature/...    ← GitHub only, never ADO
5. fivepoints transition --role analyst --issue N
6. claire stop                    ← session ends here, no wait
```

**Does NOT:** write code, create PRs, test anything.

---

### Dev (`role:dev`) — 11 steps

**Goal:** Implement the requirements, pass all gates, get code reviewed, push to ADO.

```
[1]  Checkout analyst branch
[2]  GATE-0 — run ALL 5 gates on unmodified branch BEFORE writing any code:
       dotnet build ...        → 0 errors
       dotnet test ...         → all passing
       npm run build-gate      → 0 errors
       npm run lint            → 0 errors
       flyway verify           → clean
     Record baseline MP4 proof (app working before implementation)
[3]  Implement requirements
[4]  Re-run all 5 gates → commit → git push github feature/...
[5]  GitHub PR → gatekeeper review (auto-triggered) → wait for APPROVE
[6]  Copy branch to isolated worktree → start test environment
[7]  Swagger verification (all new endpoints return HTTP 200)
[8]  Playwright E2E tests (only after Swagger passes)
[9]  Record MP4 proof for ALL FDS sections (HARD STOP — mandatory)
[10] fivepoints ado-transition --issue N
       [1/3] verify branch naming convention
       [2/3] PAT gate — pause if AZURE_DEVOPS_WRITE_PAT not set
       [3/3] push branch to ADO + create ADO PR + monitor build
[11] Stop test environment → claire stop
```

**Never:** push to `origin` (ADO remote) manually — `ado-transition` handles it.

---

### Tester (`role:tester`) — 8 steps

**Goal:** Adversarial validation against FDS, record proof, push to ADO.

```
[1]  Copy branch to ISOLATED worktree → start test environment
[2]  Swagger verification (backend gate — before Playwright)
[3]  Verify shared Playwright login fixture exists
[4]  Run Playwright E2E tests
[5]  Record MP4 proof (HARD STOP — ado-push will reject without it)
[6]  Post test report on GitHub issue
       FAIL → create bug issue → fivepoints transition --role tester --next dev
       PASS → continue
[7]  fivepoints ado-push --issue N
       → push branch to ADO (AZURE_DEVOPS_WRITE_PAT required)
       → create ADO PR via REST API
       → fivepoints ado-watch monitors until merge
[8]  Stop test environment → claire stop
```

**Never:** run Playwright before Swagger passes. Never skip MP4 proof.

---

### ADO Watch (automatic)

```
Monitors ADO PR
        ↓
ADO reviewers approve + merge
        ↓
GitHub issue closed automatically
```

---

## Git Remotes

| Remote | Destination | Who pushes |
|--------|-------------|------------|
| `github` | `CLAIRE-Fivepoints/fivepoints-test` | Dev (code review gate) |
| `origin` | `TFIOneGit` (ADO/TFVC) | `fivepoints ado-transition` only |

**Never run `git push origin` manually.** `origin` is the ADO TFVC remote — agents use `fivepoints ado-transition` to cross this boundary.

---

## PAT Roles

| PAT | Scope | Used by |
|-----|-------|---------|
| `AZURE_DEVOPS_PAT` | Read | Bridge, Analyst, pr-status, pr-comments |
| `AZURE_DEVOPS_WRITE_PAT` | Read + Write | ado-transition, ado-push |

`AZURE_DEVOPS_WRITE_PAT` is requested on demand at the ADO push step — not stored permanently.

---

## Requirements

| Tool | Version | Install |
|------|---------|---------|
| dotnet | ≥8 | `brew install --cask dotnet-sdk` |
| docker | any | Docker Desktop |
| node | ≥18 | `brew install node` |

Tokens: `AZURE_DEVOPS_PAT` in `~/.config/claire/.env`
Path: `TFIOneGit` cloned from ADO at `~/TFIOneGit`

---

## Key Commands

```bash
# Bridge
fivepoints bridge status
fivepoints bridge run --dry-run

# Pipeline transitions
fivepoints transition --role analyst --issue N
fivepoints transition --role dev --issue N

# ADO push (tester)
fivepoints ado-push --issue N
fivepoints ado-transition --issue N

# Monitoring
fivepoints ado-watch --pr N
fivepoints pr-status --pr N
fivepoints pr-comments --pr N
```

---

## Full Pipeline Reference

```
claire domain read fivepoints operational PIPELINE_WORKFLOW
```
