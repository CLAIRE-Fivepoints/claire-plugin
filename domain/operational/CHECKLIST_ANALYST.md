---
name: CHECKLIST_ANALYST
description: "Five Points — Pipeline role:analyst session checklist"
type: operational
keywords: [fivepoints, analyst, pipeline, checklist, role]
updated: 2026-04-19
---

## Your Checklist (MANDATORY — follow in order)

```
- [ ] Load domain context:
      claire domain read fivepoints knowledge ANALYST_PERSONA
      claire domain read fivepoints operational PIPELINE_WORKFLOW
      claire domain read fivepoints technical FACE_SHEET_SECTION_PATTERNS
- [ ] Read issue body (PBI reference, requirements)
- [ ] FDS fetch-on-use + manifest — download the fresh attachment, extract
      sections, emit the manifest you will quote in your receipt:
      ```bash
      claire fivepoints ado-fetch-attachments --pbi <parent-pbi> --print-manifest > /tmp/fds-manifest.json
      ```
      - No cache-in-git, no drift check. The docx is downloaded fresh into
        `~/TFIOneGit/.fds-cache/<parent-pbi>/` (already gitignored). If the
        local copy already matches the live attachment the extraction is
        skipped, but the manifest is always regenerated.
      - Inspect the extracted sections:
        `cat ~/TFIOneGit/.fds-cache/<parent-pbi>/FDS_<NAME>.md`
      - The manifest contains: `docx_md5`, `docx_bytes`, and per-section
        `{sha256, pages, image_refs}`. You will quote these in the receipt.
      - If the PBI has no attachments → walk the parent Feature/Epic. If after
        PBI → Feature → Epic there is still no FDS attachment → trigger the
        **Discord Ping Protocol** (see persona top), do NOT speculate.
      Reference: `claire domain read fivepoints operational ADO_ATTACHMENTS`
      ⚠️ Missing the FDS is the #1 cause of wrong specs. Do not skip this step.
- [ ] Read ADO work item — ALL fields AND all attachments:
      Read: title, description, acceptance criteria, parent items (PBI → Feature → Epic).
      The attachments are already extracted to staging by the previous step —
      read `FDS_<NAME>.md` there, NOT the raw docx.

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

      The receipt must carry the hashes from the manifest and 5-10 verbatim
      labels copied from the extracted section markdown. A CI gate on the dev
      PR re-runs `ado-fetch-attachments --print-manifest` and compares — any
      mismatch fails the merge. Fabricated receipts cannot pass the gate.

gh issue comment <N> --body "$(cat <<'EOF'
**FDS Read Receipt**
- Document: <exact docx filename as attached to the PBI>
- docx_md5: `<md5 from manifest.docs[].docx_md5>`
- Section title: <exact section title as it appears in the FDS> (pages X-Y)
- section_path: `<path from manifest.docs[].sections[i].path — e.g. "Client Management > Client Face Sheet">`
- section_sha256: `<sha256 from the same section entry>`
- Image refs: <comma-separated list from the same section entry's image_refs>
- Verbatim labels (5-10, copied verbatim from the extracted section markdown —
  field names, button text, screen titles, error copy):
    - "<label 1>"
    - "<label 2>"
    - "<label 3>"
    - ... (5 minimum, 10 max)
- Screens identified: <count>
- Sub-pages per screen: <exhaustive list, one line per screen>
  Example:
    - Client Face Sheet: Demographics, Emergency Contacts, Household Members
EOF
)"

      ⚠️ `section_path` is mandatory — sub-section titles like "Field
         Descriptions" repeat dozens of times in a large FDS. The path
         ("Parent > Child > title") is the unique key the CI gate uses to
         look up the section. A bare title can collide; only the path is
         guaranteed to resolve correctly.

      ⚠️ The dev role's [1.5/12] FDS Cross-Check reads this comment via
         `gh issue view <N> --json comments --jq '.comments[] | select(.body | startswith("**FDS Read Receipt**")) | .body'`
         — the receipt body MUST start with `**FDS Read Receipt**` (no leading
         whitespace, no prefix) for that selector to find it. If the receipt
         is missing or incomplete, the dev will block and ask for it.
      ⚠️ The CI gate (`fds-verify.yml` in the app repo) re-runs the manifest
         and greps every verbatim label in the fresh section markdown. A
         hallucinated label → failed check → blocked merge.
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
      From the extracted `FDS_<NAME>.md` in staging (not a committed cache —
      it is regenerated every fetch), identify the section title + page range
      + its sha256 from the manifest. Post it as a comment on the GitHub issue:
      gh issue comment <N> --repo claire-labs/fivepoints-test \
        --body "**FDS Section:** <section title> (pages X-Y, sha256 \`<short>\`)"
      ⚠️ MANDATORY — E2E test checks for this comment before transition.
      ⚠️ The section title must match the one quoted in the Read Receipt — the
         CI gate keys on the receipt's title to look up the section in the
         fresh manifest.
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
