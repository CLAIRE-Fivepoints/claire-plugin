---
domain: five_points
category: operational
name: PIPELINE_WORKFLOW
title: "Five Points — Client Pipeline Workflow (PBI → ADO Merge)"
keywords: [five-points, pipeline, workflow, analyst, dev, tester, ado-push, ado-transition, transition, labels, checklist, pbi, role-dev, fivepoints-dev, role-tester, role-analyst]
updated: 2026-03-30
pr: "#2188"
---

# Five Points — Client Pipeline Workflow

> This is the **canonical reference** for the Five Points PBI-to-ADO-merge pipeline.
> Every Claire session working on a Five Points issue MUST follow this workflow.
> The PO agent orchestrates assignments. Each role follows its checklist. Scripts handle transitions.

---

## Overview

```
PBI assigned in ADO
  → azure-issue-bridge creates GitHub issue (automated)
  → PO assigns issue to myclaire-ai with label role:analyst

role:analyst — Analysis + branch creation
  → reads FDS, writes specs to GitHub issue, creates branch
  → runs: fivepoints transition --role analyst --issue N
  → claire stop

role:dev — Implementation
  → implements on the branch, commits, pushes to client GitHub
  → creates GitHub PR, runs claire review, waits for APPROVED
  → runs: fivepoints transition --role dev --issue N (blocked until PR approved)
  → claire stop

role:tester — Verification + proof
  → copies branch to isolated worktree, runs E2E tests
  → records MP4 proof, validates against FDS
  → on PASS: runs fivepoints ado-push --issue N
  → on FAIL: creates bug issue, transitions back to dev
  → claire stop

ado-push — ADO reconciliation (script, not agent)
  → pushes branch to ADO remote
  → creates PR via REST API
  → runs fivepoints ado-watch --pr N
  → on ADO merge: closes GitHub issue
```

---

## Labels as Role Signal

Each role is signaled by a GitHub label. The label determines which persona and checklist
are loaded when `claire start` / `claire boot` generates CLAUDE.md.

| Label | Persona Template | Behavior |
|-------|-----------------|----------|
| `role:analyst` | `generator.py → _build_fivepoints_analyst_persona_section()` | Read FDS, write specs to issue, create branch. NO implementation. |
| `role:dev` | `generator.py → _build_fivepoints_dev_persona_section()` | Checkout analyst branch + implement. Standard dev work. |
| `role:tester` | `generator.py → _build_fivepoints_tester_persona_section()` | Adversarial testing. Isolated worktree. MP4 proof. |
| _(no role label)_ | Default fivepoints-dev | Standard behavior (backward compatible) |

> ⚠️ **Note:** There are no `soul-fivepoints-*.md` template files. The analyst (and all pipeline role)
> checklists are **generated dynamically** by `generator.py` at `claire boot` time.
> To update the analyst checklist, edit BOTH:
> 1. `30_universe/domains/five_points/knowledge/ANALYST_PERSONA.md` — the Pipeline Workflow section
> 2. `10_systems/claire_py/template/generator.py` → `_build_fivepoints_analyst_persona_section()`

**Label detection**: `claire boot` reads issue labels via `gh issue view N --json labels`
and includes the role-specific checklist in CLAUDE.md.

---

## Role: Analyst (`role:analyst`)

### Entry
- PO assigns issue to `myclaire-ai` with label `role:analyst`
- GitHub Manager spawns worktree + terminal (first spawn)

### Checklist
```
- [ ] Read issue body (PBI reference, requirements)
- [ ] Read FDS sections referenced in the issue
      Find FDS section: claire domain search "<section name from issue>"
      Section patterns: claire domain read five_points technical FACE_SHEET_SECTION_PATTERNS
- [ ] Write all specs to the GitHub issue comment:
      - FDS sections referenced
      - Known constraints or dependencies
      - Implementation notes for the dev
- [ ] Create client branch following naming convention:
      Branch pattern: feature/{ticket-id}-{description}
      Push to: client GitHub repo (NOT claire-labs/claire)
- [ ] Execute: fivepoints transition --role analyst --issue N
      ↳ Transition complete? → STOP HERE. Run claire stop immediately.
- [ ] 🚨 Execute: claire stop   ← MANDATORY. Session ends here. Do NOT skip.
```

> ⚠️ **After transition, the analyst session is DONE.**
> `claire stop` is not optional. There is no `claire wait` for the analyst.
> The session terminates at handoff — do not continue working.

### What the Analyst does NOT do
- No code implementation
- No PR creation
- No testing

---

## Role: Dev (`role:dev`)

### Entry
- `fivepoints transition` from analyst changed label to `role:dev`
- `claire reopen --issue N` opened a new terminal in the same worktree

### Session Start — Create All Tasks First (MANDATORY)

Before doing ANY work, create all 11 checklist tasks so each step is auditable:

```
TaskCreate(title="[1/11] Load context + read issue + checkout branch")
TaskCreate(title="[2/11] [GATE-0] Baseline gates — all 5 gates pass on UNMODIFIED branch BEFORE any code")
TaskCreate(title="[3/11] Implement requirements")
TaskCreate(title="[4/11] Run all 5 gates + commit + push to GitHub")
TaskCreate(title="[5/11] GitHub PR + gatekeeper code review")
TaskCreate(title="[6/11] Copy to isolated worktree + start test environment")
TaskCreate(title="[7/11] Swagger verification (backend gate)")
TaskCreate(title="[8/11] Verify login fixture + run E2E tests (Playwright)")
TaskCreate(title="[9/11] Record MP4 proof — ALL FDS sections")
TaskCreate(title="[10/11] PAT gate + fivepoints ado-transition → push branch to ADO")
TaskCreate(title="[11/11] Stop test environment + claire stop (after ADO task closed)")
```

### Checklist
```
- [ ] [1/11] Load domain context, read issue, checkout branch
      → TaskUpdate(<task_1_id>, status="completed")

- [ ] [2/11] [GATE-0] Baseline gates — run ALL 5 gates on UNMODIFIED branch (BEFORE writing any code):
      ⚠️  HARD STOP: Do NOT write a single line of code until ALL baseline gates pass.
      Gate 1: dotnet build com.tfione.api/com.tfione.api.csproj -c Gate -WarnAsError -nowarn:nu1901,nu1902 → 0 errors
      Gate 2: dotnet test com.tfione.service.test/com.tfione.service.test.csproj --configuration Gate → all passing
      Gate 3: cd com.tfione.web && npm run build-gate → 0 errors
      Gate 4: cd com.tfione.web && npm run lint → 0 errors
      Gate 5: flyway verify → clean
      Then start test environment to verify app runs:
      → Script reference: claire domain read five_points operational TEST_ENV_START
      claire fivepoints test-env-start  (or ./scripts/test-env-start.sh)
      → Wait for "✅ Environment ready — API: https://localhost:58337 | UI: http://localhost:5173"
      Verify: browser loads at http://localhost:5173
      Verify: Swagger UI responds at https://localhost:58337/swagger
      Record baseline video proof (MANDATORY — proves app was working BEFORE implementation):
      → claire domain read video_proof operational RECORDING_WORKFLOW
      → Record MP4: app loads, Swagger responds — this is the "before" proof
      Stop: kill $API_PID $VITE_PID && docker stop tfione-sqlserver
      ❌ If ANY gate fails → environment issue, NOT a feature issue — fix before implementing
      → TaskUpdate(<task_2_id>, status="completed")

- [ ] [3/11] Implement the requirements
      → TaskUpdate(<task_3_id>, status="completed")

- [ ] [4/11] Run all 5 gates, commit, push to GitHub ONLY:
      git push github feature/{ticket-id}-{description}
      ⚠️ NEVER use git push origin — origin is the ADO remote
      → TaskUpdate(<task_4_id>, status="completed")

- [ ] [5/11] Create GitHub PR, wait for gatekeeper review, post PR link on issue (MANDATORY — do not wait to be asked):
      gh pr create --base staging --title "feat(five-points): <description>" --body "Closes #<N>"
      # Gatekeeper review fires automatically via GitHub Actions runner (< 1s)
      Wait for gatekeeper APPROVE before continuing (arrives via claire wait)
      Post PR link on the issue immediately (do NOT wait to be asked):
      gh issue comment <N> --body "PR created: https://github.com/<repo>/pull/<PR_NUMBER>"
      → TaskUpdate(<task_5_id>, status="completed")

--- SELF-TESTING (in isolated worktree — MANDATORY) ---

- [ ] [6/11] Copy feature branch to isolated worktree, start test environment:
      Copy feature branch to a new isolated worktree (not the dev worktree)
      ./scripts/test-env-start.sh → Wait for "✅ Environment ready"
      → TaskUpdate(<task_6_id>, status="completed")

- [ ] [7/11] Swagger verification (backend gate — before Playwright):
      claire domain read five_points operational SWAGGER_VERIFICATION
      Verify endpoints + HTTP 200 with Bearer token
      ❌ Fail → fix in dev worktree (feature branch) → push → copy to isolated worktree → retest
      → TaskUpdate(<task_7_id>, status="completed")

- [ ] [8/11] Verify login fixture + run E2E tests (Playwright):
      Check e2e/global-setup.ts exists — create if missing
      Run Playwright tests only after Swagger passed
      ❌ Fail → fix in dev worktree → push → copy to isolated worktree → retest from step 7
      → TaskUpdate(<task_8_id>, status="completed")

- [ ] [9/11] 🚨 HARD STOP — Record MP4 proof for ALL FDS sections (MANDATORY):
      Every FDS requirement must be demonstrated on video
      Post proof URL on the issue before continuing
      ❌ fivepoints ado-transition will reject if no .mp4 found in issue
      → TaskUpdate(<task_9_id>, status="completed")

--- ADO TRANSITION (after ALL FDS sections proved working) ---

- [ ] [10/11] PAT gate + push feature branch to ADO:
      fivepoints ado-transition --issue N
      → [1/3] Verifies branch naming convention
      → [2/3] PAT gate: if AZURE_DEVOPS_WRITE_PAT is not set, posts wait comment
              on the GitHub issue and pauses until user provides the write PAT
      → [3/3] Pushes branch to ADO + creates ADO PR + monitors build
      ❌ FAIL → fix in dev worktree → copy to isolated worktree → retest → rerun ado-transition
      ✅ PASS → ADO PR created, build passed, GitHub issue closed by ADO
      ⚠️  Do NOT proceed to [11/11] until ado-transition has FULLY COMPLETED
          and confirmed the GitHub issue is closed.
      → TaskUpdate(<task_10_id>, status="completed")

- [ ] [11/11] Stop test environment + claire stop:
      ⚠️  Only after step [10/11] is completed and ADO has closed the GitHub issue.
      kill $API_PID $VITE_PID && docker stop tfione-sqlserver
      Execute: claire stop
      → TaskUpdate(<task_11_id>, status="completed")
```

### What the Dev does NOT do
- Does not push to `origin` (ADO remote) manually — use `fivepoints ado-transition`
- Does not test in the dev worktree — always uses an isolated copy
- Does not merge PRs — never
- Does not commit test code or test artifacts to the feature branch — the isolated worktree ([6/11]) is
  the enforcement boundary: changes in the isolated copy cannot enter the feature branch without an explicit
  cherry-pick. The dev worktree (the one that gets pushed) must stay clean of all test artifacts.

### Never Do
- ❌ Never push to `origin` (ADO remote) manually — `fivepoints ado-transition` handles ADO push
- ❌ Never create an ADO PR manually — `fivepoints ado-transition` handles this
- ❌ Never merge PRs
- ❌ Never skip self-testing — Swagger + Playwright in isolated worktree before ADO transition
- ❌ Never run Playwright before Swagger verification passes
- ❌ Never run ado-transition without MP4 proof covering ALL FDS sections

---

## Role: Tester (`role:tester`)

### Entry
- `fivepoints transition` from dev changed label to `role:tester`
- `claire reopen --issue N` opened a new terminal in the same worktree

### Session Start — Create All Tasks First (MANDATORY)

Before doing ANY work, create all 8 checklist tasks so each step is auditable:

```
TaskCreate(title="[1/8] Copy branch to isolated worktree + start test environment")
TaskCreate(title="[2/8] Swagger verification (backend gate)")
TaskCreate(title="[3/8] Verify shared login fixture exists")
TaskCreate(title="[4/8] Run E2E tests (Playwright)")
TaskCreate(title="[5/8] Record MP4 proof (MANDATORY)")
TaskCreate(title="[6/8] Post test report + proof URL on issue")
TaskCreate(title="[7/8] fivepoints ado-push --issue N")
TaskCreate(title="[8/8] Stop test environment + claire stop")
```

### Checklist
```
- [ ] Load domain context (MANDATORY before any testing):
      # Pipeline & project rules
      claire domain read five_points operational PIPELINE_WORKFLOW
      claire domain read five_points operational TESTING
      claire domain read five_points operational SWAGGER_VERIFICATION
      claire domain read five_points operational DEVELOPER_GATES
      claire domain read five_points knowledge DEV_RULES
      # Proof recording
      claire domain read video_proof operational RECORDING_WORKFLOW
      claire domain read video_proof technical PLAYWRIGHT_PATTERNS
      claire domain read video_proof technical BACKEND_RECORDING

- [ ] [1/8] Copy the branch to an isolated worktree, then start the test environment:
            (prevents test artifacts from polluting the dev branch)
      cd <isolated-worktree-path>
      ./scripts/test-env-start.sh
      → Wait for "✅ Environment ready — API: https://localhost:58337 | UI: http://localhost:5173"
      → If script missing: start SQL Server, dotnet run, and npm run dev manually
      → TaskUpdate(<task_1_id>, status="completed")

- [ ] [2/8] Swagger verification (backend gate — run BEFORE Playwright):
      claire domain read five_points operational SWAGGER_VERIFICATION
      → Verify all new endpoints appear in swagger.json
      → Verify all endpoints return HTTP 200 with valid Bearer token
      ❌ If any endpoint is missing or returns 4xx → FAIL immediately
         Report on the issue, send back to dev — no Playwright needed
      → TaskUpdate(<task_2_id>, status="completed")

- [ ] [3/8] Verify shared login fixture exists:
      Check: e2e/global-setup.ts exists in com.tfione.web/
      If missing → create it before writing any feature tests
      Reference credentials: claire domain read five_points operational TESTING
      → TaskUpdate(<task_3_id>, status="completed")

- [ ] [4/8] Run E2E tests (Playwright) — only after Swagger passed
      Validate each requirement against the FDS (requirement traceability)
      → TaskUpdate(<task_4_id>, status="completed")

- [ ] [5/8] 🚨 HARD STOP — Record MP4 proof (MANDATORY before ado-push):
            ❌ Do NOT use ffmpeg or screencapture — use Playwright for proof recording
            Frontend UI proof: claire domain read video_proof technical PLAYWRIGHT_PATTERNS
            Terminal/API proof: claire domain read video_proof technical BACKEND_RECORDING
            ❌ Do NOT skip this step. fivepoints ado-push will reject if no .mp4 found in issue.
      → TaskUpdate(<task_5_id>, status="completed")

- [ ] [6/8] Post test report on the issue (MANDATORY — proof URL required):
            - PASSED ✅ or FAILED ❌
            - Test results summary
            - MP4 proof URL/file path (attach or paste the full path)
            ❌ Never post PASSED without proof evidence in the issue comment
      → TaskUpdate(<task_6_id>, status="completed")

- [ ] If FAILED:
      - [ ] Create bug issue describing the failure
      - [ ] Execute: fivepoints transition --role tester --next dev --issue N
      - [ ] Execute: claire stop

- [ ] If PASSED — PAT GATE (check BEFORE ado-push):
      Is AZURE_DEVOPS_WRITE_PAT set in env?
      (note: AZURE_DEVOPS_PAT is read-only and cannot push to ADO)

      YES → proceed to [7/8]
      NO  → post on issue: "Proof recorded. Waiting for AZURE_DEVOPS_WRITE_PAT."
            Execute: claire wait --issue N
            User sets AZURE_DEVOPS_WRITE_PAT → resume → proceed to [7/8]

- [ ] [7/8] Execute: fivepoints ado-push --issue N
            ↳ The script verifies proof exists before proceeding — it will abort if proof is missing
      → TaskUpdate(<task_7_id>, status="completed")

- [ ] [8/8] Stop test environment, then execute claire stop:
      kill $API_PID $VITE_PID        # PIDs printed by test-env-start.sh
      docker stop tfione-sqlserver   # stop SQL Server container
      Execute: claire stop
      → TaskUpdate(<task_8_id>, status="completed")
```

### Never Do
- ❌ Never skip TaskCreate at session start — all 8 tasks must be created before any work begins
- ❌ Never run Playwright before Swagger verification passes — backend must be validated first
- ❌ Never run `fivepoints ado-push` without a recorded proof — the script enforces this as a hard gate
- ❌ Never run `fivepoints ado-push` without AZURE_DEVOPS_WRITE_PAT set (read-only PAT won't work)
- ❌ Never post PASSED in the issue comment without attaching the proof URL
- ❌ Never test in the dev worktree — use an isolated copy
- ❌ Never use `ffmpeg` or `screencapture` for proof recording — use Playwright (`video_proof` domain)

### Isolation
The tester works in a **separate worktree** (copy of the branch), not in the dev worktree.
This prevents test artifacts, temporary files, or test data from being committed to the branch.

---

## Script: `fivepoints transition`

Handles role transitions between sessions. Called as the second-to-last step in every checklist.

```bash
fivepoints transition --role <current_role> --issue <N>
```

**What it does:**
1. Reads current `role:*` label from the issue
2. Removes current label, adds `role:<next_role>`
3. Runs `claire reopen --issue N` (opens new terminal in same worktree)
4. The current session then runs `claire stop` (separate step)

**Important:** `claire reopen` must run BEFORE `claire stop`. The new terminal starts
while the old one is still alive, ensuring no gap.

---

## Script: `fivepoints ado-push`

Pushes the branch to Azure DevOps and creates a PR. Called by the tester after all tests pass.

```bash
fivepoints ado-push --issue <N>
```

**What it does:**
1. Reads the branch name from the issue/worktree
2. Adds ADO as a git remote (if not already present)
3. Pushes the branch to the ADO remote
4. Creates a PR via ADO REST API (`POST /pullrequests`)
5. Posts the ADO PR link on the GitHub issue
6. Changes label to `role:ado-review`
7. Starts `fivepoints ado-watch --pr <ADO_PR_NUMBER>`
8. On ADO merge → closes the GitHub issue with final summary

---

## Transition Flow Diagram

```
                    ┌─────────────┐
                    │  PO assigns │
                    │ role:analyst│
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Analyst   │
                    │  (session)  │
                    └──────┬──────┘
                           │ fivepoints transition --role analyst
                    ┌──────▼──────┐
                    │     Dev     │
                    │  (session)  │
                    └──────┬──────┘
                           │ fivepoints transition --role dev
                    ┌──────▼──────┐
                    │   Tester    │
                    │  (session)  │
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │             │
              PASSED ✅      FAILED ❌
                    │             │
             ┌──────▼──────┐  ┌──▼───────────┐
             │  ado-push   │  │ Bug issue    │
             │  (script)   │  │ → back to Dev│
             └──────┬──────┘  └──────────────┘
                    │
             ┌──────▼──────┐
             │  ADO review │
             │ (ado-watch) │
             └──────┬──────┘
                    │
              ADO merged
                    │
             ┌──────▼──────┐
             │ Close issue  │
             └─────────────┘
```

---

## State Machine (Labels)

| Current Label | Event | Next Label |
|---------------|-------|------------|
| `role:analyst` | Analyst completes | `role:dev` |
| `role:dev` | Dev completes | `role:tester` |
| `role:tester` | Tests PASS | `role:ado-review` |
| `role:tester` | Tests FAIL | `role:dev` (loop back) |
| `role:ado-review` | ADO merged | _(issue closed)_ |
| `role:ado-review` | ADO changes requested | `role:dev` (loop back) |

---

## Session Mechanics

### How sessions start
1. **First session** (analyst): GitHub Manager detects assignment → spawns worktree + terminal
2. **Subsequent sessions** (dev, tester): `claire reopen --issue N` opens new terminal in existing worktree

### How sessions end
Every session ends with `claire stop`, which:
- Generates a recap
- Closes the terminal
- Does NOT remove the worktree (needed by next role)

### Worktree reuse
All roles (analyst, dev) share the same worktree. The tester creates a **separate** worktree
for isolation. The `ado-push` script runs from the dev worktree (not the tester's).

---

## Never Do — Pipeline Automation Rules

### ❌ Never run `claire spawn` manually

**In the Five Points pipeline, `claire spawn` is NEVER called by an agent or human manually.**

The full automated flow handles session creation:

| Step | Who | Action |
|------|-----|--------|
| ADO assigns PBI | ADO | Email sent to Gmail |
| Email detected | `azure-issue-bridge` | Creates GitHub issue with `role:analyst` label |
| Issue created | PO Manager | Assigns issue to `myclaire-ai` |
| Assignment detected | GitHub Manager | Publishes spawn event via Redis |
| Spawn event received | Spawn Daemon | Creates worktree + terminal automatically |
| Subsequent roles (dev, tester) | `fivepoints transition` | Calls `claire reopen --issue N` — opens new terminal in existing worktree |

**`claire spawn -i N` is only for explicit user requests outside this pipeline.**

Writing `claire spawn -i N` in pipeline scripts, issue descriptions, E2E tests,
or agent documentation is **always wrong** in the Five Points context.

### Why this matters

Manual spawn bypasses the PO Manager + GitHub Manager orchestration:
- Worktree may conflict with one already created by the daemon
- Issue state tracking gets out of sync
- The automated pipeline assumes a single canonical worktree per issue

### Correct session resumption

To open a new terminal for an existing issue (between roles):
```bash
# ✅ Correct — opens new terminal in the EXISTING worktree
claire reopen --issue N

# ❌ Wrong — creates a NEW worktree, conflicts with daemon-created one
claire spawn -i N
```

---

## Per-Client Configuration

Pipeline behavior is configured per client via `claire onboard-client`:

| Field | Example | Used By |
|-------|---------|---------|
| `branch_pattern` | `feature/{ticket-id}-{desc}` | Analyst (branch creation) |
| `fds_location` | `/path/to/FDS/` or URL | Analyst, Tester |
| `ado_org` | `FivePointsTechnology` | ado-push |
| `ado_project` | `TFIOne` | ado-push |
| `ado_repo` | `TFIOneGit` | ado-push |
| `test_runner` | `npx playwright test` | Tester |
| `client_github_repo` | `claire-labs/fivepoints` | All roles |

---

## Verification Procedure

How to verify the pipeline label detection and persona loading **without spawning a worktree**.

### Prerequisites

- Labels `role:analyst`, `role:dev`, `role:tester` exist on the repo
- `CLAIRE_HOME` is set

### Step 1 — Create labels (one-time)

```bash
gh label create "role:analyst" --repo claire-labs/claire --color "0E8A16" --description "Pipeline: analyst role"
gh label create "role:dev"     --repo claire-labs/claire --color "1D76DB" --description "Pipeline: developer role"
gh label create "role:tester"  --repo claire-labs/claire --color "D93F0B" --description "Pipeline: tester role"
```

### Step 2 — Create a test issue

```bash
gh issue create --repo claire-labs/claire \
  --title "[TEST] Pipeline persona verification" \
  --label "role:analyst" \
  --body "Testing label detection. Will be closed after verification."
# Note the issue number (e.g., 1997)
```

### Step 3 — Verify each role

For each role, change the label and run the detection:

```bash
# Test role:analyst
python3 -c "
from claire_py.template.generator import ContextGenerator
gen = ContextGenerator()
persona = gen._detect_pipeline_role(<ISSUE_NUMBER>)
print(f'Detected: {persona}')
# Expected: fivepoints-analyst
"

# Switch to role:dev
gh issue edit <N> --repo claire-labs/claire --remove-label "role:analyst"
gh issue edit <N> --repo claire-labs/claire --add-label "role:dev"
# Re-run detection → Expected: fivepoints-dev

# Switch to role:tester
gh issue edit <N> --repo claire-labs/claire --remove-label "role:dev"
gh issue edit <N> --repo claire-labs/claire --add-label "role:tester"
# Re-run detection → Expected: fivepoints-tester

# Remove all labels → fallback
gh issue edit <N> --repo claire-labs/claire --remove-label "role:tester"
# Re-run detection → Expected: None
```

### Step 4 — Verify full CLAUDE.md generation

```bash
python3 -c "
from claire_py.template.generator import ContextGenerator
gen = ContextGenerator()
output = gen.generate_session_context(issue_num=<ISSUE_NUMBER>)
for line in output.splitlines():
    if 'Persona:' in line:
        print(line.strip())
        break
"
```

Expected persona sections per role:

| Label | Persona Section |
|---|---|
| `role:analyst` | `## Persona: Five Points Analyst (Pipeline Role)` |
| `role:dev` | `## Persona: Five Points Developer` |
| `role:tester` | `## Persona: Five Points Tester (Pipeline Role)` |
| (none) | Standard detection (based on repo/domains) |

### Step 5 — Cleanup

```bash
gh issue close <N> --repo claire-labs/claire --comment "Test complete."
```

### Automated tests

74 unit tests cover the pipeline logic (no GitHub access needed):

```bash
pytest 10_systems/claire_py/template/tests/test_generator.py -v -k "Pipeline"
```

---

## Frequently Asked Questions

### Does the dev create a GitHub PR before handing off to the tester?

**Yes.** The dev must create a GitHub PR on fivepoints-test and get it **approved** before
calling `fivepoints transition --role dev`. The transition guard blocks if no approved PR is found.

Steps:
1. Push the feature branch to the github remote (`git push github feature/...`)
2. Create a GitHub PR: `gh pr create --base staging ...`
3. Wait for gatekeeper APPROVE (auto-triggered via GitHub Actions runner)
4. Post the PR URL in an issue comment (the transition guard scans for it)
5. Then call `fivepoints transition --role dev --issue N`

The ADO PR is separate — it is created by `fivepoints ado-push` after the tester validates.
The GitHub PR = code review gate. The ADO PR = delivery gate. They serve different purposes.

### Who reviews the code before it reaches ADO?

The **tester is the reviewer** in this pipeline. The tester:
- Runs E2E tests against the actual FDS requirements
- Validates acceptance criteria
- Records MP4 proof

This is stricter than a code review — if tests fail, the issue goes back to dev.

### What triggers the transition dev → tester?

The **developer explicitly calls `fivepoints transition --role dev --issue N`**
as the second-to-last step of their checklist. There is no automatic trigger.

The rationale: the dev knows when their gates are passing and code is ready.
Automatic triggers (e.g. on push) would fire too early (before all gates pass).

### Is `fivepoints ado-push` part of the automatic pipeline?

**Yes** — called automatically by the tester if tests PASS. The tester calls:
```bash
fivepoints ado-push --issue N
```

This pushes the branch to ADO, creates a PR via REST API, and starts `ado-watch`.
The GitHub issue is closed when the ADO PR merges.

### Why did the dev session get stuck during E2E testing?

The dev persona template had **contradictory instructions** in pipeline mode:
- `_build_fivepoints_dev_persona_section()` said "Code Review Before PR (MANDATORY)"
- `_build_pipeline_dev_transition_section()` said "Do NOT create a GitHub PR"

An agent reading both would be paralyzed. **Fixed in issue #2063 (PR #2067)**: pipeline mode now
omits the PR review sections from the dev persona.

---

## Why Two Repos? (fivepoints-test vs TFIOneGit)

The dev pushes to **`fivepoints-test`** (GitHub), NOT directly to **`TFIOneGit`** (ADO/TFVC).

### Root cause: TFIOneGit uses TFVC, not Git

`TFIOneGit` is hosted on Azure DevOps and uses **TFVC** (Team Foundation Version Control),
a centralized VCS that predates Git. Claire agents cannot push to TFVC directly — there is no
standard `git push` remote that maps to a TFVC-backed repository.

### The two-step flow

```
Dev pushes feature branch
    │
    ▼
fivepoints-test (GitHub)    ← Git-native, AI-reviewable, standard PRs
    │ AI code review (auto-triggered via GitHub Actions runner)
    │ Gatekeeper APPROVE
    ▼
fivepoints ado-transition   ← copies branch to ADO via TFVC bridge + creates ADO PR
    │
    ▼
TFIOneGit (ADO)             ← Final delivery, client review, production merge
```

### Why this split exists

| Concern | fivepoints-test (GitHub) | TFIOneGit (ADO) |
|---------|--------------------------|------------------|
| Git native | ✅ Yes | ❌ No (TFVC) |
| AI code review | ✅ claire review | ❌ Not possible |
| Standard PRs | ✅ gh pr create | ❌ REST API only |
| Client review | ❌ Not the final gate | ✅ Official merge point |
| Production delivery | ❌ Mirror only | ✅ Yes |

### What this means for agents

- **Never push to `origin` directly** — `origin` is the ADO/TFVC remote; `git push origin` fails or corrupts state
- **Always push to `github` remote**: `git push github feature/...`
- **`fivepoints ado-transition`** handles the ADO side automatically — branch push, PR creation, build monitoring

---

## Related

- [AZURE_ISSUE_BRIDGE](../../claire/operational/AZURE_ISSUE_BRIDGE.md) — Step 1: email → GitHub issue
- [ADO_WATCH](ADO_WATCH.md) — Continuous ADO PR monitor
- [AZURE_DEVOPS_ACCESS](AZURE_DEVOPS_ACCESS.md) — PAT chain, API access
- [CODE_REVIEW_WORKFLOW](CODE_REVIEW_WORKFLOW.md) — Review process
- [ENGAGEMENT_PROCESS](ENGAGEMENT_PROCESS.md) — Client onboarding phases
