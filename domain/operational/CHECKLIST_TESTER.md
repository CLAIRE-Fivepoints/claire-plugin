---
name: CHECKLIST_TESTER
description: "Five Points — Pipeline role:tester session checklist"
type: operational
keywords: [fivepoints, tester, pipeline, checklist, role, e2e, playwright]
updated: 2026-04-14
---

### SESSION START — Create All Tasks First (MANDATORY)

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

❌ Do NOT start any testing step before all 8 tasks are created.

### Your Checklist (MANDATORY — follow in order)

```
- [ ] Load domain context (MANDATORY before any testing):
      # Pipeline & project rules
      claire domain read fivepoints operational PIPELINE_WORKFLOW
      claire domain read fivepoints operational TESTING
      claire domain read fivepoints operational SWAGGER_VERIFICATION
      claire domain read fivepoints operational DEVELOPER_GATES
      claire domain read fivepoints knowledge DEV_RULES
      # Proof recording
      claire domain read video_proof operational RECORDING_WORKFLOW
      claire domain read video_proof technical PLAYWRIGHT_PATTERNS
      claire domain read video_proof technical BACKEND_RECORDING

- [ ] [1/8] Copy the branch to an isolated worktree, then start the test environment:
      DO NOT test in the dev worktree — use a separate copy
      cd <isolated-worktree-path>
      ./scripts/test-env-start.sh
      → Wait for "✅ Environment ready — API: https://localhost:58337 | UI: http://localhost:5173"
      → If script missing: start SQL Server, dotnet run, and npm run dev manually
      → TaskUpdate(<task_1_id>, status="completed")

- [ ] [2/8] Swagger verification (backend gate — FAST, run before Playwright):
      claire domain read fivepoints operational SWAGGER_VERIFICATION
      → Verify all new endpoints appear in swagger.json
      → Verify all endpoints return HTTP 200 with valid Bearer token
      ❌ If any endpoint is missing or returns 4xx → FAIL immediately
         Report the failure on the issue, send back to dev — no Playwright needed
      → TaskUpdate(<task_2_id>, status="completed")

- [ ] [3/8] Verify shared login fixture exists:
      Check: e2e/global-setup.ts exists in com.tfione.web/
      If missing → create it before writing any feature tests
      Reference credentials: claire domain read fivepoints operational TESTING
      → TaskUpdate(<task_3_id>, status="completed")

- [ ] [4/8] Read the FDS/requirements referenced in the issue
      Run E2E tests (Playwright) — only after Swagger passed
      Validate each requirement against the FDS (requirement traceability)
      → TaskUpdate(<task_4_id>, status="completed")

- [ ] [5/8] 🚨 HARD STOP — Record MP4 proof (MANDATORY before ado-push):
      ❌ Do NOT use ffmpeg or screencapture — use Playwright for proof recording
      Frontend UI proof: claire domain read video_proof technical PLAYWRIGHT_PATTERNS
      Terminal/API proof: claire domain read video_proof technical BACKEND_RECORDING
      ❌ Do NOT skip this step. fivepoints ado-push will reject if no .mp4 found in issue.
      → TaskUpdate(<task_5_id>, status="completed")

- [ ] [6/8] Post test report on the issue (MANDATORY — include proof URL):
      - PASSED ✅ or FAILED ❌
      - Test results summary
      - MP4 proof URL/file path (attach or paste the full path)
      - Any edge cases found
      ❌ Never post PASSED without proof evidence in the issue comment
      → TaskUpdate(<task_6_id>, status="completed")

- [ ] If TESTS FAILED (Swagger / Playwright / requirement traceability — steps [2-4/8]):
      The implementation is broken. Send back to dev.
      - [ ] Describe exactly what failed and why
      - [ ] Create a bug issue if needed
      - [ ] Execute: claire fivepoints transition --role tester --next dev --issue <N>
      - [ ] Execute: claire stop

      ⚠️  This branch is ONLY for test failures (broken implementation).
          A failure of `fivepoints ado-push` is NOT a test failure — see below.

- [ ] If PASSED — PAT GATE (check BEFORE ado-push):
      Is AZURE_DEVOPS_WRITE_PAT set in env?
      (note: AZURE_DEVOPS_PAT is read-only — it cannot push to ADO)

      YES (WRITE PAT available) → proceed directly to [7/8] ado-push

      NO (WRITE PAT missing) → pause and request:
        Proof is already posted above ✅ — post on issue:
          "Proof recorded and posted. Waiting for AZURE_DEVOPS_WRITE_PAT to push to ADO."
        Execute: claire wait --issue <N>   ← wait for user to set WRITE PAT in env
        User sets AZURE_DEVOPS_WRITE_PAT → resume from here → proceed to [7/8] ado-push

- [ ] [7/8] Execute: claire fivepoints ado-push --issue <N>
            ↳ The script verifies proof exists — it will abort if proof is missing
      → TaskUpdate(<task_7_id>, status="completed")

- [ ] If ado-push FAILED (HTTP 401, network, ADO API error, missing PAT, etc.):
      ❌ DO NOT transition to role:dev. The tests already PASSED — the
         implementation is fine. The push failure is an infrastructure/auth
         problem, not a test failure. Regressing to role:dev would corrupt
         the pipeline state and cause the dev to re-implement working code.
      - [ ] Preserve role:tester (do NOT run any `fivepoints transition` command)
      - [ ] Post a diagnostic comment on the issue with the exact error output
            from `ado-push` (HTTP code, stderr, the failing step)
      - [ ] If the cause is a missing/invalid AZURE_DEVOPS_WRITE_PAT:
            ask the user to set/refresh it, then re-run step [7/8]
      - [ ] If the cause is transient (network/ADO outage): wait and retry [7/8]
      - [ ] Do NOT run `claire stop` until ado-push succeeds

- [ ] [8/8] Post-session retrospective + stop test environment + execute claire stop:
      Retrospective — pick the correct target repo when filing improvement issues:
      When `claire wait` returns the retrospective prompt, walk the 4-question decision flow:
      `claire domain read claire knowledge ISSUE_REPO_ROUTING`
      Always pass `--github-repo <owner/name>` explicitly to `claire issue create`.
      The pre-flight warning fires if the flag disagrees with the cwd-detected repo —
      heed it; cwd auto-detection has silently mis-routed plugin issues into core before.
      Quick guide for tester-side retrospectives:
        • Playwright patterns for TFI One, Swagger verification, tester checklist, proof recording
          specific to TFI One → `CLAIRE-Fivepoints/claire-plugin`
        • TFI One application bugs uncovered by tests (endpoints, UI, migrations)
          → `CLAIRE-Fivepoints/fivepoints`
        • Claire core (generic Playwright helpers, video proof engine, hooks) → `claire-labs/claire`

      Tear down + stop:
      kill $API_PID $VITE_PID        # PIDs printed by test-env-start.sh
      docker stop tfione-sqlserver   # stop SQL Server container
      Execute: claire stop
      → TaskUpdate(<task_8_id>, status="completed")
```
