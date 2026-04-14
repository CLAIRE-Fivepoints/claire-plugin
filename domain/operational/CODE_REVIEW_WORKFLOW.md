---
domain: five_points
category: operational
name: CODE_REVIEW_WORKFLOW
title: "Five Points — Code Review Workflow"
keywords: [five-points, fivepoints, code-review, pr-review, azure-devops, workflow, fivepoints-reviewer]
updated: 2026-03-06
---

# Five Points — Code Review Workflow

> Code reviews for TFI One development happen through the GitHub PR thread, not in terminal or chat.

---

## Trigger

The gatekeeper review fires **automatically** via the GitHub Actions self-hosted runner
when a PR is opened or updated on `fivepoints-test`. No manual step needed.

---

## Developer: How to Request a Review

### 1. After Pushing a PR — Wait for Auto-Review

The runner fires `claire review --pr N` automatically. Wait for the gatekeeper review
to arrive via `claire wait --pr N`.

### 2. Wait

Claire reviews the PR diff and posts the full review as a comment on the PR.
All discussion happens in the PR thread — not in terminal or Azure DevOps chat.

### 3. Discuss and Resolve

Reply to the review comment for each concern. Claire will update the review based on your explanations. Once all concerns are resolved, approve and merge the PR.

> Do not merge until all blocking concerns are resolved.

---

## Claire: Review Behavior

When `claire review --pr N` is run, Claire:

1. **Reads domain docs** before looking at code:
   - `claire domain read fivepoints knowledge CODE_REVIEW_PERSONA` — review checklist and standards
   - `claire domain read fivepoints knowledge REVIEWER_PERSONA` — Steven Franklin persona
   - `claire domain read five_points operational CODING_STANDARDS`

2. **Reads the PR diff** via `gh pr diff N`

3. **Posts the full review** as a comment on the GitHub PR using this format:

   ```markdown
   ## Code Review

   **Decision:** APPROVE / REQUEST CHANGES

   **Issues found:**
   - [file:line] Description of the problem — reference to CODING_STANDARDS rule
   - [file:line] Description of the problem — reference to PATTERNS doc

   **No issues found:**
   - Branch naming follows convention
   - DDL constraints are explicitly named
   ```

4. **Waits for developer responses** (`claire wait --pr <N>`)

5. **Discusses each concern** — never marks something as blocking without letting the developer respond first

6. **Updates the review** if the developer explains the choice is intentional or acceptable

> Claire does NOT merge the PR. The developer merges once all concerns are resolved.

---

## Communication Rules

| Channel | Purpose |
|---------|---------|
| GitHub PR thread | All review discussion, questions, decisions |
| Terminal | Execution status only (no analysis, no questions) |
| Azure DevOps PR | Optional summary link to the GitHub PR |

---

## Migrations

When a PR adds or modifies any file under `com.tfione.db/migration/`, reviewers must enforce the seed data rule below. Block the PR if it fails.

### No seed data

A migration script may only contain:
- DDL: CREATE TABLE, ALTER TABLE, CREATE INDEX
- Reference data required for the application to function (e.g. status types, permission types, system config values)

A migration script must never contain:
- Seed data added to make a local dev grid look populated
- Data tied to a hardcoded OrganizationId or any environment-specific GUID
- Any data whose only purpose is to demonstrate the feature during development

Test: Before approving a migration, ask: "Would this script run cleanly on an empty database (tfi_one_empty) with no pre-existing org/user data?" If no → request changes.

---

## Reference

- Reviewer checklist and standards: `claire domain read fivepoints knowledge CODE_REVIEW_PERSONA`
- Coding rules: `claire domain read five_points operational CODING_STANDARDS`
- Code patterns: `claire domain read five_points technical CODE_PATTERNS`
