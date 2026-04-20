---
name: CHECKLIST_DEV_PIPELINE
description: "Five Points — Pipeline role:dev session checklist"
type: operational
keywords: [fivepoints, dev, developer, pipeline, checklist, role]
updated: 2026-04-16
---

### SESSION START — Create All Tasks First (MANDATORY)

Before doing ANY work, create all 11 checklist tasks so each step is auditable:

```
TaskCreate(title="[1/11] Load context + read issue + checkout branch")
TaskCreate(title="[1.25/11] Directive Interpretation — scan PBI for 'use X as template' / 'mirror Y' and post interpretation (or no-directive line) before FDS fetch")
TaskCreate(title="[1.5/11] FDS Read + Scope Confirmation — read the FDS attached to the parent PBI yourself")
TaskCreate(title="[2/11] [GATE-0] Baseline gates + deploy + verify feature does NOT yet exist")
TaskCreate(title="[3/11] Implement requirements")
TaskCreate(title="[4/11] Run all 5 gates + commit + push to GitHub")
TaskCreate(title="[5/11] GitHub PR + gatekeeper code review")
TaskCreate(title="[6/11] Start test environment in current worktree (Steven Reviewer enforces no-test-pollution)")
TaskCreate(title="[7/11] Swagger verification (backend gate)")
TaskCreate(title="[8/11] Verify login fixture + run E2E tests (Playwright) + record MP4")
TaskCreate(title="[9/11] Take screenshot of final state + AI-verify against FDS obligations")
TaskCreate(title="[10/11] PAT gate + fivepoints ado-transition → push branch to ADO")
TaskCreate(title="[11/11] Stop test environment + claire stop (issue stays open for owner)")
```

❌ Do NOT start any work before all 11 tasks are created.

ℹ️ **Pipeline shape change (issue #42):** the analyst pipeline is currently
   retired. The dev role now reads the FDS directly (see [1.5/11]) instead of
   cross-checking against an analyst's prior spec. The isolated-worktree step
   is gone — Steven Reviewer enforces test-pollution prevention at PR review.

### Your Checklist (MANDATORY — follow in order)

```
- [ ] [1/11] Load domain context, read issue, checkout branch:
      claire domain read fivepoints operational PIPELINE_WORKFLOW
      claire domain read fivepoints operational CODE_REVIEW_WORKFLOW
      claire domain read fivepoints operational SWAGGER_VERIFICATION
      claire domain read fivepoints technical FACE_SHEET_SECTION_PATTERNS
      claire domain read claire knowledge DEBUG_METHODOLOGY
      Read the GitHub issue — locate the **FDS Section** comment (the issue
      author or a prior session should have posted one with the exact source
      file path; if missing, you'll fetch the FDS yourself in [1.5/11]).
      git fetch github
      git checkout feature/{ticket-id}-{description}

      FDS fetch (fetch-on-use — always pulls the live attachment):
      ```bash
      claire fivepoints ado-fetch-attachments --pbi <parent-pbi> --print-manifest > /tmp/fds-manifest.json
      ```
      - Docx is extracted to `~/TFIOneGit/.fds-cache/<parent-pbi>/`
        (gitignored; regenerated on every fetch).
      - Read `FDS_<NAME>.md` from staging. Do NOT grep `domain/knowledge/`
        for cached FDS — the cache-in-git model is gone.
      - The CI gate on this dev PR (`fds-verify.yml`) will re-run the same
        manifest and grep the receipt's verbatim labels. You no longer need
        to re-verify the analyst's receipt by hand — the gate does it for you.
      Reference: `claire domain read fivepoints operational ADO_ATTACHMENTS`
      → TaskUpdate(<task_1_id>, status="completed")

- [ ] [1.25/11] 🎯 Directive Interpretation (MANDATORY — before [1.5/11] FDS fetch, before any surface check):
      ⚠️  HARD STOP: Do NOT fetch the FDS, read the FDS, `ls`, or `grep` any
          source file until this step is complete. Existence ≠ conformity —
          a file that exists + a label that matches is NOT proof the work is
          done if the PBI contained a directive asking for structural
          conformity with a sibling module.

      Why this step exists: on issue #71 the dev agent ran `ls face_sheet/*.tsx`
      + `grep FDS labels` → found matches → concluded "nothing to do", and
      missed 7 structural divergences between Client and Provider face sheets
      (PermissionCode gate, Redux dispatch, skipToken, super-user bypass,
      matchPath conditional, Alert fallback, pending-documents banner). The
      directive "use Provider face sheet as template" was treated as
      decoration when it was the contract.

      Scan the PBI / issue body for **directive phrases** that constrain HOW
      the work must be done. Triggers (non-exhaustive):
        - "use X as your template"
        - "follow the pattern of Y"
        - "mirror the Z implementation"
        - "align with the existing W module"
        - "same structure as V"
        - "inspired by Q"
        - any reference to an existing sibling module/component/feature the PBI
          points you at as a reference point

      For each directive found, post an interpretation comment on the GitHub
      issue BEFORE [1.5/11], containing all 5 fields:

        1. **Literal meaning** — the phrase, word-for-word
        2. **Operational meaning** — what it means for code (structure? API shape?
           file layout? lifecycle? permission gates? error handling?)
        3. **Comparison target** — the exact file(s)/module(s) the directive
           points at (`ls`, `git ls-tree`, or `claire reveal` output)
        4. **Mandatory attributes** — 3–7 specific patterns from the comparison
           target that MUST appear in the current work. Example for "use Provider
           face sheet as template":
             - `PermissionCode.<X>` permission gate on the root component
             - Redux `set<Entity>` dispatch on successful load
             - `skipToken` wrapping when permission denied
             - Super-user bypass chain (`SUPER_USER_ROLE_CODE` + `permissionCheckBypass`)
             - `matchPath` + `on<Entity>FaceSheetRoot` conditional render
             - Fallback `<Alert severity="warning">` on permission denied
             - Inline pending-documents banner (FDS rule)
        5. **Verification plan** — the concrete grep/structural command that
           proves match or divergence for each attribute

      Use a heredoc with a flush-left `EOF` terminator:

gh issue comment <N> --body "$(cat <<'EOF'
**Directive Interpretation (dev role)**
- Literal meaning: "<exact phrase from PBI>"
- Operational meaning: <what it means for code>
- Comparison target: <file paths / modules>
- Mandatory attributes:
    1. <attribute 1 + short rationale>
    2. <attribute 2 + short rationale>
    3. <attribute 3 + short rationale>
    ... (3 min, 7 max)
- Verification plan:
    - <attribute 1> → `<grep/command>`
    - <attribute 2> → `<grep/command>`
    - ...
EOF
)"

      ⚠️ Ambiguity gate (ask, don't assume):
        If a directive is present but you cannot confidently fill all 5 fields
        (e.g. the comparison target is missing, the directive is vague, the
        mandatory attributes could plausibly be 2 or 20 — you are guessing),
        do NOT post a half-populated interpretation. Instead, run all three
        of these — in order — before waiting:
          1. Post ONE focused question on the issue:
             gh issue comment <N> \
               --body "**Directive Interpretation — needs clarification:**
             Phrase: \"<exact directive phrase>\"
             Ambiguity: <what you cannot decide confidently>
             Options: <A / B / …>"
          2. Ping Discord with the same question + the issue link
             (owner notification — real-time; see persona-top Discord Ping Protocol):
             claire discord send "Issue #<N> — Directive Interpretation ambiguous: <one-sentence summary>. Link: https://github.com/<owner>/<repo>/issues/<N>"
             ⚠️ If the disclosure guard blocks the URL (internal-reference
                match), fall back to sending without the URL and note in the
                message body that the link is in the GitHub comment.
          3. Block on the response:
             claire wait --issue <N>
        Plausibility ≠ confirmation. One good question beats a fabricated
        5-field block that the [3/11] implementation step will treat as
        contract. GitHub = audit trail, Discord = real-time owner
        notification — both are mandatory on ambiguity.

      If the PBI has NO directive phrases, post the explicit line verbatim so
      the absence is deliberate, not an oversight:
          gh issue comment <N> \
            --body "No directive phrases found — proceeding with standard analysis."

      ⚠️ The Mandatory attributes become the structural contract for [3/11]
         (implementation). [9/11] AI-verification reads this comment and
         checks each attribute in the shipped code — a missing attribute
         fails verification.
      → TaskUpdate(<task_1.25_id>, status="completed")

- [ ] [1.5/11] 🚨 FDS Read + Scope Confirmation (MANDATORY — 10 minutes max, before any code):
      ⚠️  HARD STOP: Do NOT write code until this step is complete.
      Pipeline shape: the analyst pipeline is currently retired. **You read the
      FDS yourself** and confirm scope before implementing. There is no analyst
      Read Receipt to cross-check against.

      Step 1 — Fetch the FDS from the parent PBI (already done in [1/11] if
               you ran `--print-manifest` there; re-run if you skipped it):
        ```bash
        claire fivepoints ado-fetch-attachments --pbi <parent-pbi-id> --print-manifest > /tmp/fds-manifest.json
        ```
        → Fresh copy goes into `~/TFIOneGit/.fds-cache/<parent-pbi>/`.
          PAT auto-resolved from `~/.config/claire/.env`.
          Reference: `claire domain read fivepoints operational ADO_ATTACHMENTS`
        → If the parent PBI has no attachment, walk up to Feature → Epic by
          re-running with their work-item IDs.
        → If after walking the chain there is still no FDS → trigger the
          **Discord Ping Protocol** (see persona top), do NOT speculate.

      Step 2 — Read the target section from staging:
        `cat ~/TFIOneGit/.fds-cache/<parent-pbi>/FDS_<NAME>.md`
        Locate the section by the title named in the issue's
        `**FDS Section:** <Title> (pages X-Y, sha256 ...)` comment.
        Read every paragraph, every sub-heading.

      Step 3 — Identify implementation scope:
        - Screens / routes in scope (which ones the FDS asks for)
        - Sub-pages under each screen
        - Labels verbatim from the FDS (no renaming, no guessing)
        - Out-of-scope: anything not named in this specific FDS section

      Step 4 — Post a Scope Confirmation comment on the issue. Use a heredoc:
      `\n` in a bash double-quoted string is literal backslash-n, not a
      newline, and GitHub markdown does not interpret it either. The `EOF`
      terminator of a `<<'EOF'` heredoc must be at column 0 — the block below
      is shown flush-left intentionally; do NOT re-indent it when executing.

gh issue comment <N> --body "$(cat <<'EOF'
**FDS Scope Confirmation (dev role)**
- FDS document: <docx filename>
- FDS section title: <exact title> (pages X-Y)
- section_path: `<from manifest — e.g. "Client Management > Client Face Sheet">`
- section_sha256: `<from the same section entry>`
- Screens in scope: <count + names>
- Sub-pages per screen: <list>
- Labels (verbatim from FDS): <list>
- Out of scope (explicit): <list — anything the issue might suggest but FDS does not include>
EOF
)"

      Step 5 — Decide:
        ✅ Scope clear and FDS read → proceed to [2/11] (baseline gates)
        ❌ FDS unclear or contradicts the issue → trigger Discord Ping Protocol
           + claire wait. Do NOT implement against ambiguity.
      → TaskUpdate(<task_1.5_id>, status="completed")

- [ ] [2/11] [GATE-0] Baseline gates + deploy + verify feature does NOT yet exist:
      ⚠️  HARD STOP: Do NOT write a single line of code until ALL baseline steps pass.

      Part A — Gates on the UNMODIFIED branch:
      Gate 1: dotnet build com.tfione.api/com.tfione.api.csproj -c Gate -WarnAsError -nowarn:nu1901,nu1902 → 0 errors
      Gate 2: dotnet test com.tfione.service.test/com.tfione.service.test.csproj --configuration Gate → all passing
      Gate 3: cd com.tfione.web && npm run build-gate → 0 errors (tsc -b + vite build)
      Gate 4: cd com.tfione.web && npm run lint → 0 errors
      Gate 5: flyway verify → clean (no checksum mismatch)

      Part B — Deploy the app properly (not just `dotnet run` against source):
      → Script reference: claire domain read fivepoints operational TEST_ENV_START
      claire fivepoints test-env-start  (or ./scripts/test-env-start.sh)
      → Wait for "✅ Environment ready — API: https://localhost:58337 | UI: http://localhost:5173"
      → Verify the app loads in the browser (http://localhost:5173)
      → Verify Swagger UI responds (https://localhost:58337/swagger)
      ⚠️ The deploy must use the built artifact from Part A, not a live-recompile
         of source. Confirm the API binary was produced by the Gate build, not
         by a `dotnet watch`/hot-reload process.

      Part C — 🚨 Verify the planned feature does NOT yet exist (THIS IS THE MOST IMPORTANT BASELINE):
      Navigate in the UI to the section where the feature will live. Confirm:
        - No menu item for it
        - No route for it (hit the expected URL → 404 or matches the "before" FDS state)
        - No API endpoint for it (Swagger UI does not list it)
      If the feature ALREADY exists → STOP. Either the PBI is misrouted, the
      branch isn't fresh, or someone else shipped it. Trigger Discord Ping
      Protocol. Do NOT proceed to [3/11].

      Part D — Baseline video proof (MANDATORY — proves the "before" state):
      → claire domain read video_proof operational RECORDING_WORKFLOW
      → Record MP4: app loads, Swagger responds, feature does NOT exist — this
         is the "before" proof. [9/11] compares the "after" screenshot against it.

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

- [ ] [5/11] Create GitHub PR + wait for Steven Reviewer + post PR link on issue (MANDATORY — do not wait to be asked):
      gh pr create --base staging --title "feat(five-points): <description>" --body "Closes #<N>"
      # Steven Reviewer (fivepoints-reviewer persona) fires automatically via GitHub Actions runner.
      # Steven's job includes rejecting any PR that contains test artifacts — this is the
      # no-test-pollution enforcement mechanism (replacing the prior isolated-worktree approach).
      Wait for Steven's APPROVE before continuing (arrives via claire wait).
      ❌ Do NOT proceed without Steven's approval.
      ❌ If Steven flags test-pollution → remove the test files from the feature
         branch (keep them in `~/.claire/scratch/tests/<issue-N>/` or similar),
         re-push, re-request review. Tests belong outside the feature branch.
      Post PR link on the issue immediately after creation (do NOT wait to be asked):
      gh issue comment <N> --body "PR created: https://github.com/<repo>/pull/<PR_NUMBER>"
      → TaskUpdate(<task_5_id>, status="completed")

--- SELF-TESTING (in the CURRENT worktree — Steven Reviewer enforces no-test-pollution) ---

- [ ] [6/11] Start test environment in the current worktree:
      ℹ️ Pipeline shape change (issue #42): the isolated-worktree step is gone.
         Test in the same worktree you implemented in. Steven Reviewer rejects
         PRs containing test artifacts, which is the guard against test
         pollution (previously achieved by the isolated-worktree boundary).
      ./scripts/test-env-start.sh
      → Wait for "✅ Environment ready — API: https://localhost:58337 | UI: http://localhost:5173"
      → If script missing: start SQL Server, dotnet run, and npm run dev manually
      ⚠️ Any test code you write (e2e specs, fixtures, Playwright projects)
         must live OUTSIDE the feature branch. Use `~/.claire/scratch/tests/<issue-N>/`
         or a `.gitignored` local path — NEVER commit them to the feature branch.
      → TaskUpdate(<task_6_id>, status="completed")

- [ ] [7/11] Swagger verification (backend gate — run BEFORE Playwright):
      claire domain read fivepoints operational SWAGGER_VERIFICATION
      → Verify all new endpoints appear in swagger.json
      → Verify all endpoints return HTTP 200 with valid Bearer token
      ❌ If any endpoint missing or 4xx:
         Fix in the current worktree (feature branch) → push fix to GitHub → retest from this step
      → TaskUpdate(<task_7_id>, status="completed")

- [ ] [8/11] Verify shared login fixture exists, then run E2E tests + record MP4:
      Check: e2e/global-setup.ts exists in com.tfione.web/
      If missing → create it before writing feature tests (put in scratch path if not yet merged).
      Reference credentials: claire domain read fivepoints operational TESTING
      Run E2E tests (Playwright) — only after Swagger passed.
      Record MP4 proof **scoped to the FDS section you implemented** (not all FDS):
      → Frontend UI proof: claire domain read video_proof technical PLAYWRIGHT_PATTERNS
      → Terminal/API proof: claire domain read video_proof technical BACKEND_RECORDING
      ❌ Do NOT record every FDS feature — only the section named in the
         issue's FDS Section comment (per analyst/author scoping).
      ❌ Do NOT use ffmpeg or screencapture — use Playwright proof recording.
      ❌ If tests fail: fix in current worktree → push fix → retest from step 7.
      Post MP4 URL/path on the issue before continuing.
      → TaskUpdate(<task_8_id>, status="completed")

- [ ] [9/11] 🚨 HARD STOP — Visual verification of EVERY screenshot (MANDATORY):
      For each screenshot produced in [8/11], perform **actual visual inspection**.
      DOM `pageContains` / regex checks do NOT count as verification — they prove
      presence in markup, not correctness of the rendered output.

      Capture screenshots of the **final state** of each implemented view:
      → After the happy-path interaction completes (form submitted, page saved)
      → Before any cleanup / navigation away
      Store the screenshots alongside the MP4 (scratch path, not committed).

      Then, for every screenshot (no skipping, no "I already looked at the similar one"):

        1. **Open the PNG file** with the Read tool on the image path.
        2. **Describe what is rendered** in 2–4 sentences per screenshot:
           - Layout / structure observed
           - Presence and position of each FDS-mandated element
             (labels, buttons, banners, permission states)
           - Any visual anomaly (overlapping text, missing images, wrong
             colors, broken alignment)
        3. **Cross-reference against the FDS** (the section file from [1.5/11] Step 2):
           - Enumerate the FDS obligations that apply to that view
           - For each obligation mark ✅ visible / ❌ missing / ⚠️ present-but-wrong
             (with specifics — location, what's off)
        4. **Post the verification on the issue** in this exact shape:

        gh issue comment <N> --body "**Visual Verification ([9/11])**
        For each screenshot, a rendered-state description and per-obligation pass/fail:

        ### 01-<name>.png
        - Rendered: <2–4 sentences>
        - FDS obligations checked:
          - <obligation A>: ✅ visible at <location>
          - <obligation B>: ❌ missing
          - <obligation C>: ⚠️ present but <issue>
        ### 02-<name>.png
        ... (repeat for every screenshot, no skipping)"

      ⚠️ HARD RULES:
        - **DOM `pageContains` / regex checks do NOT count as verification.**
          They prove presence in markup, not correctness of the rendered
          output. Do not use them as a substitute for reading the image.
        - **You MUST open every screenshot.** A shortcut of "I already looked
          at the similar one" is not acceptable — each screen has its own
          obligations.
        - **Silent pass is a failure.** If you post "✅ all verified" without
          the per-screenshot descriptions above, [10/11] (ADO transition)
          rejects the run.
        - **If the tool cannot read PNGs** (e.g. sandboxed environment without
          image support) — block on Discord Ping Protocol (see persona top),
          do not fabricate.

      ❌ fivepoints ado-push will reject if no MP4 AND no Visual Verification comment is posted.
      → TaskUpdate(<task_9_id>, status="completed")

--- ADO TRANSITION (after scoped MP4 + screenshot verification posted) ---

- [ ] [10/11] PAT gate + push feature branch to ADO:
      claire fivepoints ado-transition --issue <N>
      → [1/3] Verifies branch naming convention
      → [2/3] PAT gate: if AZURE_DEVOPS_WRITE_PAT is not set, posts wait comment
              on the GitHub issue and pauses until user provides the write PAT
      → [3/3] Pushes branch to ADO + creates ADO PR + monitors build
      ❌ FAIL → fix in current worktree → retest → rerun ado-transition
      ✅ PASS → ADO PR created, build passed.
      ℹ️ Pipeline shape change (issue #42): the GitHub issue **stays open**
         after ADO merge — it will be closed by the owner when they're ready,
         not automatically by the ado-push flow. Do NOT close the issue
         yourself from this step.
      → TaskUpdate(<task_10_id>, status="completed")

- [ ] [11/11] Post-session retrospective + stop test environment + execute claire stop:
      ⚠️  Only after step [10/11] is completed and the ADO build passed.
      ℹ️ The GitHub issue stays open (see [10/11]) — you stop the session,
         the owner closes the issue separately.

      Retrospective — pick the correct target repo when filing improvement issues:
      When `claire wait` returns the retrospective prompt, walk the 4-question decision flow:
      `claire domain read claire knowledge ISSUE_REPO_ROUTING`
      Always pass `--github-repo <owner/name>` explicitly to `claire issue create`.
      The pre-flight warning fires if the flag disagrees with the cwd-detected repo —
      heed it; cwd auto-detection has silently mis-routed plugin issues into core before.
      Quick guide for dev-side retrospectives:
        • Dev checklists, gates, FDS handling, ADO transition, fivepoints commands
          → `CLAIRE-Fivepoints/claire-plugin`
        • TFI One application code (endpoints, migrations, web UI) → `CLAIRE-Fivepoints/fivepoints`
        • Claire core (bash/python architecture, generic personas, hooks) → `claire-labs/claire`

      Tear down + stop:
      kill $API_PID $VITE_PID        # PIDs printed by test-env-start.sh
      docker stop tfione-sqlserver
      Execute: claire stop
      → TaskUpdate(<task_11_id>, status="completed")
```
