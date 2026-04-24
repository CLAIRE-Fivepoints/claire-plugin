---
name: CHECKLIST_DEV_PIPELINE
description: "Five Points — Pipeline role:dev session checklist"
type: operational
keywords: [fivepoints, dev, developer, pipeline, checklist, role, "persona:fivepoints-dev"]
updated: 2026-04-20
---

### Scope — TFI One app only

This checklist drives **TFI One application work** in `~/TFIOneGit` — a
feature in the API / web / migrations that ends with an ADO push. It does
**NOT** apply to PRs that only touch the claire-plugin repo itself (bash
in `domain/commands/`, Python in `domain/scripts/`, persona/checklist
markdown, etc.).

If the worktree path contains
`.claire/plugins/fivepoints/.claire/worktrees/…`, skip this 11-step
pipeline. Neither `./claire test` (no `./claire` wrapper exists in the
plugin repo) nor global `claire test` (wrong suite — runs core
claire-tests) is the right gate. Run the plugin's own tests directly:

```bash
bats tests/scripts/
python3 -m pytest domain/scripts/tests/
```

Then push → open PR against `main` on `CLAIRE-Fivepoints/claire-plugin`
and let Steven Reviewer (GitHub Actions) handle review. The FDS / Swagger
/ Playwright / ADO-transition steps below are skipped entirely for
plugin-local PRs.

### SESSION START — Create All Tasks First (MANDATORY)

Before doing ANY work, create all 12 checklist tasks so each step is auditable:

```
TaskCreate(title="[1/11] Load context + read issue + checkout branch")
TaskCreate(title="[1.1/11] Install plugin hooks in this clone — claire fivepoints install-hooks (issue #119)")
TaskCreate(title="[1.25/11] Directive Interpretation — scan PBI for 'use X as template' / 'mirror Y' and post interpretation (or no-directive line) before FDS fetch")
TaskCreate(title="[1.5/11] FDS Read + Scope Confirmation — read the FDS attached to the parent PBI yourself")
TaskCreate(title="[2/11] [GATE-0] Baseline gates + deploy + verify feature does NOT yet exist")
TaskCreate(title="[3/11] Implement requirements")
TaskCreate(title="[4/11] Run all 5 gates + commit + push to GitHub")
TaskCreate(title="[5/11] GitHub PR + gatekeeper code review (embed pr_body_checklist.md verbatim)")
TaskCreate(title="[6/11] Start test environment in current worktree (Steven Reviewer enforces no-test-pollution)")
TaskCreate(title="[7/11] Swagger verification (backend gate)")
TaskCreate(title="[8/11] Verify login fixture + run E2E tests (Playwright) + record MP4")
TaskCreate(title="[9/11] Take screenshot of final state + AI-verify against FDS obligations")
TaskCreate(title="[10/11] PAT gate + fivepoints ado-transition → push branch to ADO")
TaskCreate(title="[11/11] Stop test environment + claire stop (issue stays open for owner)")
```

❌ Do NOT start any work before all 12 tasks are created.

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
      claire domain read fivepoints operational ADO_GITHUB_SYNC
      claire domain read fivepoints technical FACE_SHEET_SECTION_PATTERNS
      claire domain read claire knowledge DEBUG_METHODOLOGY
      Read the GitHub issue — locate the **FDS Section** comment (the issue
      author or a prior session should have posted one with the exact source
      file path; if missing, you'll fetch the FDS yourself in [1.5/11]).

      🚨 HARD RULE — Branch existence is a 3-location check. Feature branches
         live in ~/TFIOneGit/ local + github mirror + ado origin; each
         location lights up at a different pipeline step (ado = only after
         [10/11]). See the Branch Visibility Matrix in fivepoints-dev persona
         and ADO_GITHUB_SYNC (section: Feature Branch Visibility (3 Locations)).

         ticket_id="<ticket-id>"                    # from the GitHub issue title
         slug="<slug-from-issue>"
         branch="feature/${ticket_id}-${slug}"
         local=$(git -C ~/TFIOneGit branch --list "feature/${ticket_id}-*" | awk '{print $NF}' | head -1)
         github=$(gh api "repos/$CLAIRE_WAIT_REPO/branches/${branch}" --jq .name 2>/dev/null || echo "")
         ado=$(git -C ~/TFIOneGit ls-remote origin "refs/heads/feature/${ticket_id}-*" | awk '{print $2}' | head -1)
         echo "local=${local:-absent} github=${github:-absent} ado=${ado:-absent}"

         - Present on github + local, absent on ado → interrupted prior
           session before [10/11] → reuse the branch. Do not recreate.
         - Present only on github → git fetch github "$branch" && git
           checkout "$branch" → reuse.
         - Present only on local → git push github "$branch" → reuse.
         - Absent everywhere → truly new → create per analyst checklist.

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

- [ ] [1.1/11] 🪝 Install plugin hooks in this clone (MANDATORY — once per session, before any commit):
      Why: the ADO CI pipeline (`azure_gated_build.yml`) does not run
      `npm run lint`, and per issue #119 we will not commit the missing
      step to the ADO-tracked file. The plugin pre-commit / pre-push hooks
      are the compensating gate — they must be installed before any
      `git commit` or `git push github` in this clone. Reruns are idempotent
      (existing hooks are backed up as `.bak.<timestamp>`).

      Command:
      ```bash
      claire fivepoints install-hooks
      ```

      Dry-run (no side effects, prints what would be written):
      ```bash
      claire fivepoints install-hooks --dry-run
      ```

      Reference:
        - `claire domain read fivepoints operational GIT_HOOKS` — full check list + residual-risk note
        - `claire fivepoints install-hooks --agent-help`
      → TaskUpdate(<task_1.1_id>, status="completed")

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
      PR body MUST embed the plugin-rendered PR checklist (issue #119
      substitute for `.azuredevops/pull_request_template.md`). Read the
      template and paste its fenced block verbatim into the body, filling
      each `[ ]` as it passes:

      ```bash
      claire domain read fivepoints templates pr_body_checklist
      # copy the fenced `## PR Checklist (plugin-rendered — issue #119)` block
      # into --body below, after "Closes #<N>"
      gh pr create --base staging \
          --title "feat(five-points): <description>" \
          --body "Closes #<N>

      ## PR Checklist (plugin-rendered — issue #119)

      - [ ] Follows patterns in \`docs/27-FIVEPOINTS-CODE-PATTERNS.md\`
      - [ ] Uses \`rqProvider.GetRestrictedQuery<T>()\` for entity queries
      - [ ] Uses \`labelToken\` / \`labelDefault\` on Tfio* components
      - [ ] Validators connected via the \`fluentValidationResolver\` pipeline
      - [ ] All tests pass (\`dotnet build -c Gate\`, \`dotnet test\`, \`npm run lint\`, \`npm run build-gate\`)
      - [ ] Pre-commit + pre-push hooks installed for this clone (\`claire fivepoints install-hooks\`)"
      ```
      # Steven Reviewer (fivepoints-reviewer persona) fires automatically via GitHub Actions runner.
      # Steven's job includes rejecting any PR that contains test artifacts — this is the
      # no-test-pollution enforcement mechanism (replacing the prior isolated-worktree approach).
      # Steven also rejects PRs missing the `## PR Checklist (plugin-rendered — issue #119)` block.
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
      claire fivepoints test-env-start  (or ./scripts/test-env-start.sh)
      → Heartbeat fires every 15s during boot:
        `[15s] booting: sqlserver=up api=down vite=down`
        Silence for >30s means the script crashed (no heartbeat = no progress).
      → Wait for "✅ Environment ready — API: https://localhost:58337 | UI: http://localhost:5173"
      → If script missing: start SQL Server, dotnet run, and npm run dev manually
      ⚠️ Any test code you write (e2e specs, fixtures, Playwright projects)
         must live OUTSIDE the feature branch. Use `~/.claire/scratch/tests/<issue-N>/`
         or a `.gitignored` local path — NEVER commit them to the feature branch.

      🚨 If test-env fails or times out (heartbeat shows api/vite stuck on `down`,
         or no heartbeat = script crashed): you may NOT skip [8/11] or [9/11] as
         a workaround. Static code analysis is NOT a substitute for a running
         browser screenshot against FDS labels (issue #74). Apply the persona-top
         **Discord Ping Protocol**:
           1. claire discord send "test-env-start failed for #<N>: <symptom>"
           2. gh issue comment <N> with the same symptom
           3. claire wait --issue <N> and block
         Only the user can authorize a fallback — the dev agent cannot self-authorize one.
      → TaskUpdate(<task_6_id>, status="completed")

- [ ] [7/11] Swagger verification (backend gate — run BEFORE Playwright):
      claire domain read fivepoints operational SWAGGER_VERIFICATION
      → Verify all new endpoints appear in swagger.json
      → Verify all endpoints return HTTP 200 with valid Bearer token
      ❌ If any endpoint missing or 4xx:
         Fix in the current worktree (feature branch) → push fix to GitHub → retest from this step
      → TaskUpdate(<task_7_id>, status="completed")

- [ ] [8/11] 🚨 HARD STOP — Verify shared login fixture, run E2E tests, record MP4 (MANDATORY):
      ⚠️ This step is NOT optional and NOT substitutable. Static code analysis,
         grep on the source tree, or "the file exists so the feature works"
         are NOT acceptable substitutes for an MP4 produced by a real browser
         interacting with the running app. Issue #74 (and #71 / PR #76 before
         it) document the failure mode of self-authorizing a static-analysis
         fallback when test-env felt hard — the gate at [10/11] now rejects
         this with a step-named message naming `[8/11] MP4 missing`.

      📖 Read FIRST (before writing the spec — past sessions tâtonnaient 3+
         times on the login dance because they skipped this):
         claire domain read video_proof technical PLAYWRIGHT_PATTERNS

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
      ❌ If test-env cannot be brought up: Discord Ping Protocol (see [6/11]).
         Do NOT fall back to static analysis. Only the user can authorize a fallback.
      Post MP4 URL/path on the issue before continuing.
      → TaskUpdate(<task_8_id>, status="completed")

- [ ] [9/11] 🚨 HARD STOP — Screenshot + visual verification against FDS obligations (MANDATORY):
      ⚠️ This step is NOT optional and NOT substitutable. The screenshot must
         come from a running browser rendering the actual UI — not a `cat` of
         a JSX file, not a structural grep, not "the labels are in the source
         so the screen renders them". DOM `pageContains` / regex checks do
         NOT count as verification — they prove presence in markup, not
         correctness of the rendered output. Issue #74 documents the failure
         mode of skipping this step when test-env was hard to bring up;
         issue #77 documents the failure mode of substituting DOM-regex for
         actual visual inspection on the remaining screenshots once 2 of 9
         were opened. The gate at [10/11] rejects this step-by-name with
         `[9/11] FDS Verification missing` when the sentinel is absent.

      Capture screenshots of the **final state** of each implemented view:
      → After the happy-path interaction completes (form submitted, page saved)
      → Before any cleanup / navigation away
      Store the screenshots alongside the MP4 (scratch path, not committed).

      Then, for every screenshot captured above (no skipping, no "I already
      looked at the similar one" — each screen has its own obligations):

        1. **Open the PNG file** with the Read tool on the image path.
        2. **Describe what is rendered** in 2–4 sentences per screenshot:
           - Layout / structure observed
           - Presence and position of each FDS-mandated element
             (labels, buttons, banners, permission states)
           - Any visual anomaly (overlapping text, missing images, wrong
             colors, broken alignment)
        3. **Cross-reference against the FDS** (the section file from [1.5/11] Step 2):
           - Enumerate **EVERY** FDS obligation that applies to that view —
             no omission, no "I'll check the important ones", no "the
             obvious labels are there". If the FDS section defines N
             obligations for this view, the verification MUST show N
             entries for this screenshot. Coverage is counted.
           - For each obligation mark ✅ visible / ❌ missing / ⚠️ present-but-wrong
             (with specifics — location, what's off).
           - A missing obligation entry IS a silent-pass failure: a reviewer
             following `fivepoints-reviewer.md` counts the enumerated entries
             against the FDS section and rejects the PR if the count does
             not match.
        4. **Post the verification on the issue.** The comment MUST start with
           the exact sentinel `**FDS Verification (screenshot + AI)**` on its
           own first line — this is what `claire fivepoints ado-transition`'s
           [2/4] proof gate (`check_proof_gate` in `domain/scripts/ado_common.sh`)
           greps for via `startswith(...)`. A discussion comment that merely
           mentions the phrase in prose will NOT satisfy the gate. Shape:

        gh issue comment <N> --body "**FDS Verification (screenshot + AI)**
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
        - **Partial coverage is a failure.** The verification MUST enumerate
          EVERY FDS obligation for each view — not a subset, not "the
          important ones". If the FDS section lists N obligations for a
          view, the comment MUST show N checked entries for that
          screenshot. Missing entries are treated identically to a skip.
        - **Silent pass is a failure.** If you post the sentinel without the
          per-screenshot `### NN-<name>.png` / `- Rendered:` / `- FDS
          obligations checked:` blocks above, [10/11] (ADO transition) still
          accepts the sentinel but a reviewer following
          `fivepoints-reviewer.md` will reject the PR for incomplete proof.
        - **If the tool cannot read PNGs** (e.g. sandboxed environment without
          image support) — block on Discord Ping Protocol (see persona top),
          do not fabricate.

      ⚠️ **Env-blocked FDS label? Stage test data first — do not ship a
         partial proof.** Before marking any label `⚠️ env-blocked` /
         "code correct, data missing", read
         `claire domain read fivepoints operational TEST_DATA_STAGING`.
         That doc covers the one-time pattern (prime.user's live
         `currentOrganizationId` from `/auth/login` + a minimum seed set
         under the right Organization + FK-check toggle) that turns most
         env-blocked labels into a 5-minute SQL-only task. Re-screenshot
         after seeding and flip the label from ⚠️ to ✅. Only fall back
         to "env-blocked" commentary if the staging doc does not cover
         your case — and when that happens, file a follow-up issue so the
         doc is extended.
         ⚠️ Keep the seed SQL in `~/.claire/scratch/tests/issue-<N>/` —
         never committed to the feature branch (Steven Reviewer rejects
         seed SQL in the PR diff).

      ❌ `fivepoints ado-transition` rejects if either MP4 or this FDS
         Verification comment is missing. The rejection message names which
         step was skipped.
      ❌ If test-env cannot be brought up: Discord Ping Protocol (see [6/11]).
         Do NOT post a static-analysis-based "verification" — the screenshot
         must be a real browser screenshot AND each PNG must be opened.
      → TaskUpdate(<task_9_id>, status="completed")

--- ADO TRANSITION (after scoped MP4 + screenshot verification posted) ---

- [ ] [10/11] PAT gate + push feature branch to ADO:
      claire fivepoints ado-transition --issue <N>
      → [1/4] Verifies branch naming convention
      → [2/4] Proof gate: rejects if no MP4 ([8/11]) or no FDS Verification ([9/11])
              comment is posted on the issue. Rejection text names the skipped
              step explicitly so you cannot accidentally bypass it.
      → [3/4] PAT gate: if AZURE_DEVOPS_WRITE_PAT is not set, posts wait comment
              on the GitHub issue and pauses until user provides the write PAT
      → [4/4] Pushes branch to ADO + creates ADO PR + monitors build
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

      Retrospective — issue routing rule (MANDATORY):
      **For fivepoints-dev sessions: ALL retrospective issues → `CLAIRE-Fivepoints/claire-plugin` by default.**
      The motif: TFI One dev sessions run from `~/TFIOneGit/`, which auto-detects `CLAIRE-Fivepoints/fivepoints` as the origin repo.
      Without an explicit `--github-repo` flag, cwd auto-detection wins — silent mis-routing to the app repo.
      Rule: Only PBI-linked direct client work lands in `fivepoints`. Everything else (workflow fixes, dev tooling, pipeline bugs, doc gaps) → `claire-plugin`.
      
      When `claire wait` returns the retrospective prompt:
      Always pass `--github-repo CLAIRE-Fivepoints/claire-plugin` explicitly to `claire issue create`.
      (The pre-flight warning fires if the flag disagrees with cwd-detected repo — heed it.)
      
      Optional: Walk the full 4-question decision flow in `claire domain read claire knowledge ISSUE_REPO_ROUTING`
      
      Quick guide for dev-side retrospectives:
        • Dev checklists, gates, FDS handling, ADO transition, fivepoints commands
          → `CLAIRE-Fivepoints/claire-plugin`
        • TFI One application code (endpoints, migrations, web UI) — ONLY if PBI-linked
          → `CLAIRE-Fivepoints/fivepoints`
        • Claire core (bash/python architecture, generic personas, hooks) → `claire-labs/claire`

      Tear down + stop:
      kill $API_PID $VITE_PID        # PIDs printed by test-env-start.sh
      docker stop tfione-sqlserver
      Execute: claire stop
      → TaskUpdate(<task_11_id>, status="completed")
```
