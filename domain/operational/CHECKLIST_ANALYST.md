---
name: CHECKLIST_ANALYST
description: "Five Points — Pipeline role:analyst session checklist"
type: operational
keywords: [fivepoints, analyst, pipeline, checklist, role]
updated: 2026-04-14
---

## Your Checklist (MANDATORY — follow in order)

```
- [ ] Load domain context:
      claire domain read fivepoints knowledge ANALYST_PERSONA
      claire domain read fivepoints operational PIPELINE_WORKFLOW
      claire domain read fivepoints technical FACE_SHEET_SECTION_PATTERNS
- [ ] Read issue body (PBI reference, requirements)
- [ ] Read ADO work item (read-only) — title, description, acceptance criteria, parent items
- [ ] Deep dive the assigned task — identify the FDS section to implement:
      - Task ID from the GitHub issue title (use this for branch naming, NOT the parent PBI ID)
      - Read the ADO task description to identify which FDS section/subsection is assigned
      - If the section is not explicitly named in the task → read the parent PBI/Feature
        to find which FDS section this task belongs to
      - Scope: implement the specified FDS section entirely
      ⚠️ HARD STOP: Do not proceed until the FDS section is clearly identified.
- [ ] Search domain context for the section:
      claire domain search "<section name from issue>"
      Find FDS section and any existing section domain docs
- [ ] Identify and post the FDS section for this PBI:
      From the domain search results (or FDS source documents), identify the FDS section
      number and title that covers this task (e.g., "16.9 — Client Agreements").
      Then post it as a comment on the GitHub issue:
      gh issue comment <N> --repo claire-labs/fivepoints-test \
        --body "**FDS Section:** 16.9 — <Title>"
      ⚠️ MANDATORY — E2E test checks for this comment before transition
- [ ] Pull latest dev branch into TFIOneGit:
      cd ~/TFIOneGit && git checkout dev && git pull origin dev
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
- [ ] Run claire tier-score and post result to GitHub issue:
      claire tier-score
      Then post to issue:
        gh issue comment <N> --body "**Tier N — <Label>**\n<scoring rationale>"
      ⚠️ This step is MANDATORY. The E2E test asserts a Tier [1-5] comment exists before transition.
- [ ] Execute: claire fivepoints transition --role analyst --issue <N>
      ↳ Transition complete? → STOP HERE
- [ ] 🚨 Execute: claire stop   ← MANDATORY. Session ends here.
```
