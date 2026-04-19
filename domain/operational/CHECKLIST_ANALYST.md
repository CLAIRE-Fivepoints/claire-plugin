---
name: CHECKLIST_ANALYST
description: "⚠️ DEPRECATED (issue #42) — Five Points pipeline role:analyst session checklist. Analyst pipeline currently retired; the dev role reads the FDS directly per CHECKLIST_DEV_PIPELINE [1.5/11]. Kept for future reactivation."
type: operational
keywords: [fivepoints, analyst, pipeline, checklist, role, deprecated]
updated: 2026-04-19
---

# ⚠️ DEPRECATED — Analyst Pipeline Retired (issue #42)

This checklist is no longer the live source of truth for any session. The
analyst pipeline is retired — the dev role reads the FDS directly via
`CHECKLIST_DEV_PIPELINE.md [1.5/11]` ("FDS Read + Scope Confirmation").

**Do not run this checklist as live guidance.** It is preserved for two reasons:
1. **Future reactivation.** If the analyst pipeline is brought back, this
   checklist is the starting point.
2. **Historical record.** Past sessions ran on this checklist; preserving it
   keeps the audit trail coherent.

When the pipeline is reactivated, restore the deprecation header to a real
description and remove this banner.

---

## Your Checklist (MANDATORY — follow in order)

```
- [ ] Load domain context:
      claire domain read fivepoints knowledge ANALYST_PERSONA
      claire domain read fivepoints operational PIPELINE_WORKFLOW
      claire domain read fivepoints technical FACE_SHEET_SECTION_PATTERNS
- [ ] Read issue body (PBI reference, requirements)
- [ ] FDS cache pre-flight — check domain cache is in sync with the fresh PBI attachment:
      ```bash
      claire fivepoints ado-fetch-attachments --pbi <parent-pbi> --diff-only
      ```
      - Exit 0 → cache matches → read the existing `FDS_<NAME>_SCREENS_*.md`
      - Exit 1 → cache is stale. **Refresh it yourself** by running the same
        command without `--diff-only`:
        ```bash
        claire fivepoints ado-fetch-attachments --pbi <parent-pbi>
        ```
        That extracts the .docx, splits it into per-section markdown
        (`FDS_<NAME>_SCREENS_*.md`), and builds the image index — into staging
        (`~/TFIOneGit/.fds-cache/<pbi>/`). Read the new section files from
        staging, then commit the fresh cache to the plugin repo so subsequent
        sessions hit a fresh `--diff-only` ✅.
        **Do NOT write specs from stale cache or from the raw ADO docx.**
      Reference: `claire domain read fivepoints operational ADO_ATTACHMENTS`
- [ ] Read ADO work item — ALL fields AND all attachments:
      Read: title, description, acceptance criteria, parent items (PBI → Feature → Epic).
      ⚠️ "Read the work item" means ALL of it — fields AND attachments. Never skip attachments.
      If the description mentions an attached document ("see attached FDS", "latest version attached",
      etc.) → YOU MUST download and read that attachment before continuing.

      Fetch attachments + build the cache (single command, end-to-end):
        ```bash
        claire fivepoints ado-fetch-attachments --pbi <pbi-id>
        ```
        → Downloads the .docx, splits into per-section markdown, builds the
          image index. PAT comes from `~/.config/claire/.env` automatically.
          Reference: `claire domain read fivepoints operational ADO_ATTACHMENTS`
        → If the PBI has no attachment → re-run with the parent Feature/Epic
          ID until you find the FDS. The script handles relations correctly.
        → If after walking PBI → Feature → Epic there is still no FDS attachment
          → trigger the **Discord Ping Protocol** (see persona top), do NOT
          speculate.
      ⚠️ Missing the FDS is the #1 cause of wrong specs. Do not skip this step.

- [ ] Identify the specific target section — NOT the parent document:
      The ADO description often names a broad document ("Client Management FDS Chapter 10").
      Your target is a SPECIFIC sub-section within that document, not the whole document.
      ⚠️ "Chapter N" references may be stale — the current FDS uses section names, not chapter
         numbers. Navigate by section NAME, not by number.

      Steps:
        1. Read the FDS (from attachment or domain doc) — scan the table of contents
        2. Find the named section that matches the task description
        3. Identify the EXACT sub-section you are responsible for
           Example: target = "Client Face Sheet" (not "Client Management" which has 20+ sub-features)
        4. Read that sub-section in full — every word, every sub-section heading
      ⚠️ HARD STOP: Do NOT post any analysis, options, or scope until you have READ the
         target section. The FDS is the answer. Do not speculate.

- [ ] Verify the request is clear enough to proceed:
      After reading the FDS section, confirm you have:
        ✅ The exact section name and its content (not just a chapter reference)
        ✅ Enough detail to describe what the UI should show and what the API should return
        ✅ No contradictions between the ADO description and the current FDS
      If ANY of these are missing or unclear → post ONE focused question on the GitHub issue:
        gh issue comment <N> --repo CLAIRE-Fivepoints/fivepoints \
          --body "**Analyst needs clarification before proceeding:**\n\n<specific question>"
        claire wait --issue <N>
      ⚠️ HARD STOP: Do NOT create a branch or write specs until the request is clear.
         One good question beats three pages of speculation.

- [ ] 🚨 Post FDS Read Receipt on the GitHub issue (MANDATORY — audit trail):
      After reading the target FDS section, post a receipt comment on the issue.
      This is the single piece of evidence the dev role will cross-check against.
      Skipping this step = silent failure chain → wrong specs ship to prod.
      Use a heredoc with a flush-left `EOF` terminator — a multi-line
      double-quoted string preserves the checklist indentation and GitHub
      markdown then renders the body as a code block instead of a list.

gh issue comment <N> --body "$(cat <<'EOF'
**FDS Read Receipt**
- Document: <exact docx filename as attached to the PBI>
- Section: <exact section number + title> (pages X-Y)
- Screens identified: <count>
- Menu items: <count>
- Sub-pages per screen: <exhaustive list, one line per screen>
  Example:
    - Client Face Sheet: Demographics, Emergency Contacts, Household Members
    - Medical File: Allergies, Medications, Diagnoses, Immunizations
- Labels verbatim from FDS: <list — no renaming, no guessing>
EOF
)"

      ⚠️ The dev role's [1.5/12] FDS Cross-Check reads this comment via
         `gh issue view <N> --json comments --jq '.comments[] | select(.body | startswith("**FDS Read Receipt**")) | .body'`
         — the receipt body MUST start with `**FDS Read Receipt**` (no leading
         whitespace, no prefix) for that selector to find it. If the receipt
         is missing or incomplete, the dev will block and ask for it.
      ⚠️ HARD STOP: Do NOT write specs or create the branch until this receipt is posted.

- [ ] Deep dive the assigned task — identify the FDS section to implement:
      - Task ID from the GitHub issue title (use this for branch naming, NOT the parent PBI ID)
      - Confirm the specific sub-section you will implement (from the step above)
      - Scope: implement the specified sub-section entirely — nothing more, nothing less
      ⚠️ HARD STOP: Do not proceed until the FDS sub-section is clearly identified AND read.
- [ ] Search domain context for the section:
      claire domain search "<section name from issue>"
      Find FDS section and any existing section domain docs
- [ ] Identify and post the FDS section for this PBI:
      From the domain search results (or FDS source documents), identify the FDS section
      number, title, AND **the exact source file path** in the cache
      (e.g., `domain/knowledge/FDS_CLIENT_SCREENS_s16.md`).
      Then post it as a comment on the GitHub issue:
      gh issue comment <N> --repo claire-labs/fivepoints-test \
        --body "**FDS Section:** 16.9 — <Title> (\`<exact/cache/path/FDS_NAME_SCREENS_sXX.md>\`)"
      ⚠️ MANDATORY — E2E test checks for this comment before transition.
      ⚠️ The exact file path is mandatory — the dev's [1.5/12] FDS Cross-Check
         opens this file directly to verify your spec. A bare section number
         forces them to grep, which is brittle.
- [ ] Pull latest dev branch into TFIOneGit:
      cd ~/TFIOneGit && git checkout dev && git pull origin dev && git push github dev
      → Both remotes must agree on dev tip before pre-flight `git fetch github` lookups.
      → See: claire domain read fivepoints operational ADO_GITHUB_SYNC
- [ ] Pre-flight: detect existing branch + PR for {ticket-id} (BEFORE creating anything):
      ⚠️ MANDATORY — never `git checkout -b` blindly. A previous analyst session may
         have already created a branch (and possibly an associated PR) for this task.
         Reusing that work preserves context and avoids duplicate branches.

      existing_branch=$(gh api repos/CLAIRE-Fivepoints/fivepoints-test/branches \
        --paginate \
        --jq ".[] | select(.name | startswith(\"feature/{ticket-id}-\")) | .name" \
        | head -1)
      existing_pr=$(gh pr list --repo CLAIRE-Fivepoints/fivepoints-test \
        --search "head:feature/{ticket-id}-" --state all \
        --json number,state,headRefName -q '.[0]')

      ⚠️ Use the SAME {ticket-id} you will use for branch naming (the ADO task ID
         from the GitHub issue title — NOT the parent PBI ID).
         Example: if issue says "Task #10901 (PBI #10847)", search for "feature/10901-".
- [ ] Branch step — REUSE existing branch if found, otherwise CREATE a new one:

      IF existing_branch is non-empty → REUSE PATH (do NOT run `git checkout -b`):
        git fetch github "$existing_branch"
        git checkout "$existing_branch"
        echo "✓ Reusing existing branch: $existing_branch"
        branch_was_reused=yes

        IF existing_pr is non-empty → MANDATORY: read prior context before re-analyzing:
          pr_number=$(echo "$existing_pr" | jq -r .number)
          pr_state=$(echo "$existing_pr" | jq -r .state)
          gh pr view "$pr_number" --repo CLAIRE-Fivepoints/fivepoints-test --comments
          gh pr diff "$pr_number" --repo CLAIRE-Fivepoints/fivepoints-test
          # Post on the GitHub issue so the user knows we are not re-analyzing from scratch:
          gh issue comment <N> --repo claire-labs/fivepoints-test \
            --body "Found existing PR #$pr_number (state: $pr_state) — reusing branch \`$existing_branch\` instead of creating new"
          ⚠️ You MUST read the PR comments and diff before writing any new specs.
             Re-analyzing from scratch destroys the previous analyst's context.

      ELSE (no existing branch) → CREATE PATH (original flow):
        git checkout -b feature/{ticket-id}-{description}
        git push -u github feature/{ticket-id}-{description}
        # Verify push succeeded:
        gh api repos/CLAIRE-Fivepoints/fivepoints-test/branches/feature/{ticket-id}-{description} --jq '.name'
        branch_was_reused=no

      ⚠️ Push to fivepoints-test (GitHub), NOT to ADO
      ⚠️ {ticket-id} = the ADO task ID directly assigned to you (from the GitHub issue title),
         NOT the parent PBI ID.
         Example: if issue says "Task #10901 (PBI #10847)", use 10901 — not 10847.
         ✅ feature/10901-description   ❌ feature/10847-description
- [ ] Post branch name as comment on the GitHub issue (indicate new vs reused):
      branch_name=$(git rev-parse --abbrev-ref HEAD)
      gh issue comment <N> --repo claire-labs/fivepoints-test \
        --body "Branch: \`$branch_name\` (reused: $branch_was_reused)"
      ⚠️ MANDATORY — transition guard requires branch name in issue comments
      ⚠️ The "(reused: yes/no)" suffix tells downstream personas whether prior work exists
- [ ] Run section analysis:
      claire analyze --branch feature/{ticket-id}-{description} --section <N> --fds-note "<spec>"
      ⚠️ Use the PBI feature branch, NOT the dev branch
- [ ] Write all specs to the GitHub issue comment:
      - FDS sections referenced
      - Known constraints or dependencies
      - Implementation notes for the dev
      - Branch name (MUST be included for handoff)
- [ ] Evaluate the PBI tier (1-5) yourself and post the result to the GitHub issue:
      The tier reflects implementation complexity / risk:
        Tier 1 — trivial (label change, copy edit, single-line config)
        Tier 2 — small (new endpoint, single screen, no migration)
        Tier 3 — medium (multi-screen feature, migration, business logic)
        Tier 4 — large (cross-cutting refactor, schema redesign, new module)
        Tier 5 — epic (multi-PBI initiative, architecture shift)
      Decide based on what you read in the FDS and ADO description, then post:
        gh issue comment <N> --body "**Tier N — <Label>**

        <scoring rationale: what makes it this tier, not the next/previous>"
      ⚠️ This step is MANDATORY. The E2E test asserts a Tier [1-5] comment exists before transition.
      Note: there is no `claire tier-score` command — the tier is an analyst
      judgment, not an automated evaluation. If you're unsure between two
      tiers, default to the higher one and explain the trade-off in the
      rationale.
- [ ] Execute: claire fivepoints transition --role analyst --issue <N>
      ↳ Transition complete? → STOP HERE
- [ ] Post-session retrospective — pick the correct target repo when filing improvement issues:
      When `claire wait` returns the retrospective prompt, walk the 4-question decision flow:
      `claire domain read claire knowledge ISSUE_REPO_ROUTING`
      Always pass `--github-repo <owner/name>` explicitly to `claire issue create`.
      The pre-flight warning fires if the flag disagrees with the cwd-detected repo —
      heed it; cwd auto-detection has silently mis-routed plugin issues into core before.
      Quick guide for analyst-side retrospectives:
        • FDS handling, section detection, analyst persona, ADO attachment workflow,
          fivepoints checklist content → `CLAIRE-Fivepoints/claire-plugin`
        • TFI One application bugs (endpoints, UI, migrations) → `CLAIRE-Fivepoints/fivepoints`
        • Claire core (bash/python architecture, generic personas, hooks) → `claire-labs/claire`
- [ ] 🚨 Execute: claire stop   ← MANDATORY. Session ends here.
```
