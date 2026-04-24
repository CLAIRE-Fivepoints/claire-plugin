---
name: CHECKLIST_ADO_REVIEW
description: "Five Points — Pipeline role:ado-review session checklist"
type: operational
version: 1.0.0
keywords: [fivepoints, ado-review, pipeline, checklist, role, ado, "persona:fivepoints-ado-review"]
updated: 2026-04-24
---

## Your Checklist (MANDATORY — follow in order)

> **About this role:** The ADO review phase monitors the pull request in Azure DevOps
> after the tester has validated and pushed the branch via `fivepoints ado-push`.
> The checklist is minimal because the actual review and merge happen in ADO,
> governed by Azure DevOps policies and the client team's review process.

### SESSION START — Create All Tasks First (MANDATORY)

Before doing ANY work, create all 3 checklist tasks so each step is auditable:

```
TaskCreate(title="[1/3] Load context + read issue + verify branch pushed to ADO")
TaskCreate(title="[2/3] Monitor ADO PR — watch for merge or changes requested")
TaskCreate(title="[3/3] Close session when ADO PR merges or loops back to dev")
```

---

## Checklist

```
- [ ] [1/3] Load domain context, read issue, verify ADO PR link
      Read the GitHub issue + the tester's proof comment (MP4 URLs).
      Verify branch has been pushed to ADO:
        fivepoints pr-status --pr <ADO_PR_NUMBER>
      Note the build status and any pending reviewer votes.
      → TaskUpdate(<task_1_id>, status="completed")

- [ ] [2/3] Monitor ADO PR for merge or changes requested:
      The ADO PR is now in the client team's hands. Your role is to monitor
      for completion or loopback:
      
      ✅ MERGE PATH:
         - Client reviewers approve and merge the PR into the ADO main branch
         - `fivepoints ado-watch` (started by ado-push) detects the merge
         - ADO automatically closes the GitHub issue (bridge automation)
         - Session ends
      
      🔄 LOOPBACK PATH (changes requested):
         - Client reviewers request changes on the ADO PR
         - Post a comment on the GitHub issue:
           "Changes requested in ADO PR — looping back to dev for revision."
         - Execute: fivepoints transition --role ado-review --next dev --issue <N>
         - claire stop (the dev session resumes the work)
      
      ⚠️ Do NOT manually merge or approve — only the client team can merge in ADO.
         Your job is to monitor and respond to the outcome.
      → TaskUpdate(<task_2_id>, status="completed")

- [ ] [3/3] Confirm final state + claire stop:
      When the ADO PR is merged:
        Verify: gh issue view <N> --json state
        Expected output: state = CLOSED
      If the issue was auto-closed by the bridge → session is done
      Execute: claire stop
      
      If looping back to dev:
        After transition completes → claire stop
        (The dev session resumes; do not continue here)
      → TaskUpdate(<task_3_id>, status="completed")
```

---

## What the ADO-Review role does NOT do
- Does NOT merge the PR manually — only the client team can
- Does NOT approve or request changes — those are client prerogatives
- Does NOT commit code — the branch was finalized by dev and tester
- Does NOT push to ADO — `fivepoints ado-push` already did that

---

## Related
- [PIPELINE_WORKFLOW](PIPELINE_WORKFLOW.md) — Complete pipeline overview
- [ADO_WATCH](ADO_WATCH.md) — Continuous monitoring of ADO PR status
