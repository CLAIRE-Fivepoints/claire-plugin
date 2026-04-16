---
name: CHECKLIST_DEV_PIPELINE
description: "Five Points — Pipeline role:dev session checklist"
type: operational
keywords: [fivepoints, dev, developer, pipeline, checklist, role]
updated: 2026-04-14
---

### SESSION START — Create All Tasks First (MANDATORY)

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

❌ Do NOT start any work before all 11 tasks are created.

### Your Checklist (MANDATORY — follow in order)

```
- [ ] [1/11] Load domain context, read issue, checkout branch:
      claire domain read fivepoints operational PIPELINE_WORKFLOW
      claire domain read fivepoints operational CODE_REVIEW_WORKFLOW
      claire domain read fivepoints operational SWAGGER_VERIFICATION
      claire domain read fivepoints technical FACE_SHEET_SECTION_PATTERNS
      claire domain read claire knowledge DEBUG_METHODOLOGY
      Read the GitHub issue — analyst has written all specs there (no ADO lookup needed)
      If specs are incomplete → follow the Gap Recovery section below before proceeding
      git fetch github
      git checkout feature/{ticket-id}-{description}

      FDS cache cross-check (MANDATORY before implementing):
      ```bash
      claire fivepoints ado-fetch-attachments --pbi <parent-pbi> --diff-only
      ```
      - Exit 0 → cache is fresh. Cross-check analyst specs against
        `FDS_<NAME>_SCREENS_<section>.md` + `FDS_<NAME>_IMAGE_INDEX.md`.
      - Exit 1 → cache is stale. The analyst should have blocked on this —
        do NOT implement against stale specs. Surface on the issue and wait.
      Reference: `claire domain read fivepoints operational ADO_ATTACHMENTS`
      → TaskUpdate(<task_1_id>, status="completed")

- [ ] [2/11] [GATE-0] Baseline gates — run ALL 5 gates on the UNMODIFIED branch (BEFORE writing any code):
      ⚠️  HARD STOP: Do NOT write a single line of code until ALL baseline gates pass.
      Gate 1: dotnet build com.tfione.api/com.tfione.api.csproj -c Gate -WarnAsError -nowarn:nu1901,nu1902 → 0 errors
      Gate 2: dotnet test com.tfione.service.test/com.tfione.service.test.csproj --configuration Gate → all passing
      Gate 3: cd com.tfione.web && npm run build-gate → 0 errors (tsc -b + vite build)
      Gate 4: cd com.tfione.web && npm run lint → 0 errors
      Gate 5: flyway verify → clean (no checksum mismatch)
      Then start test environment to verify app runs:
      → Script reference: claire domain read fivepoints operational TEST_ENV_START
      claire fivepoints test-env-start  (or ./scripts/test-env-start.sh)
      → Wait for "✅ Environment ready — API: https://localhost:58337 | UI: http://localhost:5173"
      → Verify the app loads in the browser (http://localhost:5173)
      → Verify Swagger UI responds (https://localhost:58337/swagger)
      Record baseline video proof (MANDATORY — proves app was working BEFORE implementation):
      → claire domain read video_proof operational RECORDING_WORKFLOW
      → Record MP4: app loads, Swagger responds — this is the "before" proof
      Stop environment: kill $API_PID $VITE_PID && docker stop tfione-sqlserver
      ❌ If ANY gate fails → environment issue, NOT a feature issue — fix before implementing
      → TaskUpdate(<task_2_id>, status="completed")

- [ ] [3/11] Implement the requirements
      → TaskUpdate(<task_3_id>, status="completed")

- [ ] [4/11] Run ALL 5 gates locally, commit, and push to GitHub:
      Gate 1: dotnet build com.tfione.api/com.tfione.api.csproj -c Gate -WarnAsError -nowarn:nu1901,nu1902
      Gate 2: dotnet test com.tfione.service.test/com.tfione.service.test.csproj --configuration Gate
      Gate 3: cd com.tfione.web && npm run build-gate — 0 errors (tsc -b + vite build)
      Gate 4: cd com.tfione.web && npm run lint — 0 errors in your files
      Gate 5: flyway verify — automatic via pre-push hook (do NOT run manually)
      ❌ NEVER git push before all applicable gates pass
      git push github feature/{ticket-id}-{description}
      ⚠️ NEVER use git push origin — origin is the ADO remote
      → TaskUpdate(<task_4_id>, status="completed")

- [ ] [5/11] Create GitHub PR + wait for gatekeeper review + post PR link on issue (MANDATORY — do not wait to be asked):
      gh pr create --base staging --title "feat(five-points): <description>" --body "Closes #<N>"
      # Gatekeeper review fires automatically via GitHub Actions runner (< 1s)
      Wait for gatekeeper APPROVE before continuing (arrives via claire wait).
      ❌ Do NOT proceed without gatekeeper approval.
      Post PR link on the issue immediately after creation (do NOT wait to be asked):
      gh issue comment <N> --body "PR created: https://github.com/<repo>/pull/<PR_NUMBER>"
      → TaskUpdate(<task_5_id>, status="completed")

--- SELF-TESTING (in isolated worktree — MANDATORY) ---

- [ ] [6/11] Copy feature branch to isolated worktree, start test environment:
      DO NOT test in the dev worktree — use a separate copy
      Copy feature branch to a new isolated worktree
      cd <isolated-worktree-path>
      ./scripts/test-env-start.sh
      → Wait for "✅ Environment ready — API: https://localhost:58337 | UI: http://localhost:5173"
      → If script missing: start SQL Server, dotnet run, and npm run dev manually
      → TaskUpdate(<task_6_id>, status="completed")

- [ ] [7/11] Swagger verification (backend gate — run BEFORE Playwright):
      claire domain read fivepoints operational SWAGGER_VERIFICATION
      → Verify all new endpoints appear in swagger.json
      → Verify all endpoints return HTTP 200 with valid Bearer token
      ❌ If any endpoint missing or 4xx:
         Fix in dev worktree (feature branch) → push fix to GitHub
         Copy updated changes to isolated worktree → retest from this step
      → TaskUpdate(<task_7_id>, status="completed")

- [ ] [8/11] Verify shared login fixture exists, then run E2E tests:
      Check: e2e/global-setup.ts exists in com.tfione.web/
      If missing → create it before running feature tests
      Reference credentials: claire domain read fivepoints operational TESTING
      Run E2E tests (Playwright) — only after Swagger passed
      ❌ If tests fail:
         Fix in dev worktree (feature branch) → push fix to GitHub
         Copy updated changes to isolated worktree → retest from step 7
      → TaskUpdate(<task_8_id>, status="completed")

- [ ] [9/11] 🚨 HARD STOP — Record MP4 proof for ALL FDS sections (MANDATORY):
      Every FDS requirement must be demonstrated on video — not just the happy path.
      ❌ Do NOT use ffmpeg or screencapture — use Playwright proof recording
      Frontend UI proof: claire domain read video_proof technical PLAYWRIGHT_PATTERNS
      Terminal/API proof: claire domain read video_proof technical BACKEND_RECORDING
      ❌ Do NOT skip this step. fivepoints ado-push will reject if no .mp4 found in issue.
      Post proof on the issue with the MP4 URL/path before continuing.
      → TaskUpdate(<task_9_id>, status="completed")

--- ADO TRANSITION (after ALL FDS sections proved working) ---

- [ ] [10/11] PAT gate + push feature branch to ADO:
      claire fivepoints ado-transition --issue <N>
      → [1/3] Verifies branch naming convention
      → [2/3] PAT gate: if AZURE_DEVOPS_WRITE_PAT is not set, posts wait comment
              on the GitHub issue and pauses until user provides the write PAT
      → [3/3] Pushes branch to ADO + creates ADO PR + monitors build
      ❌ FAIL → fix in dev worktree → copy to isolated worktree → retest → rerun ado-transition
      ✅ PASS → ADO PR created, build passed, GitHub issue closed by ADO
      ⚠️  Do NOT proceed to [11/11] until ado-transition has FULLY COMPLETED
          and confirmed the GitHub issue is closed.
      → TaskUpdate(<task_10_id>, status="completed")

- [ ] [11/11] Stop test environment + execute claire stop:
      ⚠️  Only after step [10/11] is completed and ADO has closed the GitHub issue.
      kill $API_PID $VITE_PID        # PIDs printed by test-env-start.sh
      docker stop tfione-sqlserver
      Execute: claire stop
      → TaskUpdate(<task_11_id>, status="completed")
```
