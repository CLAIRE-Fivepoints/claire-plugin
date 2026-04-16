---
name: CHECKLIST_DEV_PIPELINE
description: "Five Points — Pipeline role:dev session checklist"
type: operational
keywords: [fivepoints, dev, developer, pipeline, checklist, role]
updated: 2026-04-16
---

### SESSION START — Create All Tasks First (MANDATORY)

Before doing ANY work, create all 12 checklist tasks so each step is auditable:

```
TaskCreate(title="[1/12] Load context + read issue + checkout branch")
TaskCreate(title="[1.5/12] FDS Cross-Check — verify analyst specs against the FDS attached to the parent PBI")
TaskCreate(title="[2/12] [GATE-0] Baseline gates — all 5 gates pass on UNMODIFIED branch BEFORE any code")
TaskCreate(title="[3/12] Implement requirements")
TaskCreate(title="[4/12] Run all 5 gates + commit + push to GitHub")
TaskCreate(title="[5/12] GitHub PR + gatekeeper code review")
TaskCreate(title="[6/12] Copy to isolated worktree + start test environment")
TaskCreate(title="[7/12] Swagger verification (backend gate)")
TaskCreate(title="[8/12] Verify login fixture + run E2E tests (Playwright)")
TaskCreate(title="[9/12] Record MP4 proof — ALL FDS sections")
TaskCreate(title="[10/12] PAT gate + fivepoints ado-transition → push branch to ADO")
TaskCreate(title="[11/12] Stop test environment + claire stop (after ADO task closed)")
```

❌ Do NOT start any work before all 12 tasks are created.

### Your Checklist (MANDATORY — follow in order)

```
- [ ] [1/12] Load domain context, read issue, checkout branch:
      claire domain read fivepoints operational PIPELINE_WORKFLOW
      claire domain read fivepoints operational CODE_REVIEW_WORKFLOW
      claire domain read fivepoints operational SWAGGER_VERIFICATION
      claire domain read fivepoints technical FACE_SHEET_SECTION_PATTERNS
      claire domain read claire knowledge DEBUG_METHODOLOGY
      Read the GitHub issue — analyst has written specs there.
      ⚠️  Do NOT skip the FDS cross-check — full protocol in [1.5/12] below.
      The dev role is the last line of defense against silent spec drift (root cause of PR #74).
      If specs are still incomplete after cross-check → follow the Gap Recovery section below.
      git fetch github
      git checkout feature/{ticket-id}-{description}
      → TaskUpdate(<task_1_id>, status="completed")

- [ ] [1.5/12] 🚨 FDS Cross-Check (MANDATORY — 10 minutes max, before any code):
      ⚠️  HARD STOP: Do NOT write code until this step is complete.
      This step verifies the analyst read the FDS. The dev is the last line of defense.

      Step 1 — Fetch the FDS from the parent PBI:
        # Preferred (when claire-plugin#29 lands): claire fivepoints ado-fetch-attachments --pbi <parent-pbi-id>
        # Manual fallback (works today):
        claire domain read fivepoints operational AZURE_DEVOPS_ACCESS   ← PAT setup
        curl -s -u ":$AZURE_DEVOPS_PAT" \
          "https://dev.azure.com/Fivepoints/TFIOne/_apis/wit/workItems/{PARENT_PBI_ID}?\$expand=relations&api-version=7.1" \
          | jq '.relations[] | select(.rel == "AttachedFile") | {name: .attributes.name, url: .url}'
        → For each .docx attachment → download, convert to text (python-docx or textract)

      Step 2 — Locate the analyst's FDS Read Receipt comment on the issue:
        # Anchor on body prefix — substring grep picks up reply threads that quote the phrase
        gh issue view <N> --json comments \
          --jq '.comments[] | select(.body | startswith("**FDS Read Receipt**")) | .body'
        # Optional: also filter by author if your pipeline tags the analyst bot login:
        #   --jq '.comments[] | select(.author.login == "<analyst-bot-login>" and (.body | startswith("**FDS Read Receipt**"))) | .body'
        → Note: document name, section number + title, screens count, menu items count, sub-pages
        → If no receipt found → block; ask the analyst to post it (CHECKLIST_ANALYST requires it).

      Step 3 — Cross-check the analyst's spec against the FDS:
        - Screens / routes: does every screen the analyst listed appear in the FDS? Any extras? Any missing?
        - Labels: does every label match exactly (e.g. "Medical File" vs "Health/Medical")?
        - Sub-pages: did the analyst enumerate every sub-page under each screen?
        - Source code cross-contamination: did the analyst copy from base_menu_options.tsx (stale code)
          instead of reading the FDS? Red flag if the spec mentions routes that exist in code but not the FDS.

      Step 4 — Produce and post the delta. Use a heredoc: `\n` in a bash
      double-quoted string is literal backslash-n, not a newline, and GitHub
      markdown does not interpret it either. The `EOF` terminator of a
      `<<'EOF'` heredoc must be at column 0 — the block below is shown
      flush-left intentionally; do NOT re-indent it when executing.

gh issue comment <N> --body "$(cat <<'EOF'
**FDS Cross-Check delta (dev role)**
- FDS document: <docx filename>
- FDS section: <exact section number + title>
- Analyst said: N screens, M menu items
- FDS says: N' screens, M' menu items
- Extra (analyst added, not in FDS): <list>
- Missing (in FDS, analyst omitted): <list>
- Renamed (label mismatches): <list>
- Verdict: [MATCH | DELTA DETECTED]
EOF
)"

      Step 5 — Decide:
        ✅ MATCH → proceed to [2/12] (baseline gates)
        ❌ DELTA DETECTED → post the delta (already done in Step 4), then:
           claire wait --issue <N>
           Do NOT implement. Wait for the analyst / owner to confirm the correct scope.
      ❌ If FDS cannot be fetched (no attachment on PBI or parent chain) → post on issue,
         claire wait. Never assume specs without the source document.
      → TaskUpdate(<task_1.5_id>, status="completed")

- [ ] [2/12] [GATE-0] Baseline gates — run ALL 5 gates on the UNMODIFIED branch (BEFORE writing any code):
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

- [ ] [3/12] Implement the requirements
      → TaskUpdate(<task_3_id>, status="completed")

- [ ] [4/12] Run ALL 5 gates locally, commit, and push to GitHub:
      Gate 1: dotnet build com.tfione.api/com.tfione.api.csproj -c Gate -WarnAsError -nowarn:nu1901,nu1902
      Gate 2: dotnet test com.tfione.service.test/com.tfione.service.test.csproj --configuration Gate
      Gate 3: cd com.tfione.web && npm run build-gate — 0 errors (tsc -b + vite build)
      Gate 4: cd com.tfione.web && npm run lint — 0 errors in your files
      Gate 5: flyway verify — automatic via pre-push hook (do NOT run manually)
      ❌ NEVER git push before all applicable gates pass
      git push github feature/{ticket-id}-{description}
      ⚠️ NEVER use git push origin — origin is the ADO remote
      → TaskUpdate(<task_4_id>, status="completed")

- [ ] [5/12] Create GitHub PR + wait for gatekeeper review + post PR link on issue (MANDATORY — do not wait to be asked):
      gh pr create --base staging --title "feat(five-points): <description>" --body "Closes #<N>"
      # Gatekeeper review fires automatically via GitHub Actions runner (< 1s)
      Wait for gatekeeper APPROVE before continuing (arrives via claire wait).
      ❌ Do NOT proceed without gatekeeper approval.
      Post PR link on the issue immediately after creation (do NOT wait to be asked):
      gh issue comment <N> --body "PR created: https://github.com/<repo>/pull/<PR_NUMBER>"
      → TaskUpdate(<task_5_id>, status="completed")

--- SELF-TESTING (in isolated worktree — MANDATORY) ---

- [ ] [6/12] Copy feature branch to isolated worktree, start test environment:
      DO NOT test in the dev worktree — use a separate copy
      Copy feature branch to a new isolated worktree
      cd <isolated-worktree-path>
      ./scripts/test-env-start.sh
      → Wait for "✅ Environment ready — API: https://localhost:58337 | UI: http://localhost:5173"
      → If script missing: start SQL Server, dotnet run, and npm run dev manually
      → TaskUpdate(<task_6_id>, status="completed")

- [ ] [7/12] Swagger verification (backend gate — run BEFORE Playwright):
      claire domain read fivepoints operational SWAGGER_VERIFICATION
      → Verify all new endpoints appear in swagger.json
      → Verify all endpoints return HTTP 200 with valid Bearer token
      ❌ If any endpoint missing or 4xx:
         Fix in dev worktree (feature branch) → push fix to GitHub
         Copy updated changes to isolated worktree → retest from this step
      → TaskUpdate(<task_7_id>, status="completed")

- [ ] [8/12] Verify shared login fixture exists, then run E2E tests:
      Check: e2e/global-setup.ts exists in com.tfione.web/
      If missing → create it before running feature tests
      Reference credentials: claire domain read fivepoints operational TESTING
      Run E2E tests (Playwright) — only after Swagger passed
      ❌ If tests fail:
         Fix in dev worktree (feature branch) → push fix to GitHub
         Copy updated changes to isolated worktree → retest from step 7
      → TaskUpdate(<task_8_id>, status="completed")

- [ ] [9/12] 🚨 HARD STOP — Record MP4 proof for ALL FDS sections (MANDATORY):
      Every FDS requirement must be demonstrated on video — not just the happy path.
      ❌ Do NOT use ffmpeg or screencapture — use Playwright proof recording
      Frontend UI proof: claire domain read video_proof technical PLAYWRIGHT_PATTERNS
      Terminal/API proof: claire domain read video_proof technical BACKEND_RECORDING
      ❌ Do NOT skip this step. fivepoints ado-push will reject if no .mp4 found in issue.
      Post proof on the issue with the MP4 URL/path before continuing.
      → TaskUpdate(<task_9_id>, status="completed")

--- ADO TRANSITION (after ALL FDS sections proved working) ---

- [ ] [10/12] PAT gate + push feature branch to ADO:
      claire fivepoints ado-transition --issue <N>
      → [1/3] Verifies branch naming convention
      → [2/3] PAT gate: if AZURE_DEVOPS_WRITE_PAT is not set, posts wait comment
              on the GitHub issue and pauses until user provides the write PAT
      → [3/3] Pushes branch to ADO + creates ADO PR + monitors build
      ❌ FAIL → fix in dev worktree → copy to isolated worktree → retest → rerun ado-transition
      ✅ PASS → ADO PR created, build passed, GitHub issue closed by ADO
      ⚠️  Do NOT proceed to [11/12] until ado-transition has FULLY COMPLETED
          and confirmed the GitHub issue is closed.
      → TaskUpdate(<task_10_id>, status="completed")

- [ ] [11/12] Stop test environment + execute claire stop:
      ⚠️  Only after step [10/12] is completed and ADO has closed the GitHub issue.
      kill $API_PID $VITE_PID        # PIDs printed by test-env-start.sh
      docker stop tfione-sqlserver
      Execute: claire stop
      → TaskUpdate(<task_11_id>, status="completed")
```
