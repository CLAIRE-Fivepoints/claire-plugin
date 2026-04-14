---
domain: fivepoints
category: knowledge
name: FINISH_EXISTING_PR_PERSONA
title: "FivePoints — Finish Existing PR Persona"
keywords: [five-points, finish-existing-pr, stale-pr, rebase, rescue-dev, persona, checklist, ado-pr, no-force-push, land, fivepoints-land, rebase-no-force]
updated: 2026-04-08
pr: "#18"
---

# FivePoints — Finish Existing PR Persona

> Use this persona when an issue says "finish work on this branch" or "the PR is stale,
> needs rebasing". This is a fundamentally different flow from the standard analyst→dev→tester
> pipeline.

**Key difference from the dev persona:** There is no FDS section to analyze, no new branch
to create, no analysis to write. The work is: rebase, gates, e2e, push, proof post.

**Source:** Discovered and documented during issue #146 (session 2026-04-08, PBI #10847).

---

## 9-Step Checklist

### Step 1 — Identify the ADO PR

```bash
# Find the PR number from the issue or context
gh issue view <N> --repo CLAIRE-Fivepoints/fivepoints-test
# Look for: "ADO PR: https://dev.azure.com/.../pullrequest/NNN"

# Verify PR state
claire fivepoints pr-status --pr <ADO_PR_NUMBER>
```

Read ALL comments on the PR chronologically — understand why it was rejected/stalled
before touching any code. Quote the specific feedback.

---

### Step 2 — Read diff, not the whole FDS

```bash
cd ~/TFIOneGit

# What files does this PR change?
git diff ado/dev...feature/XXXXX-your-branch --name-only

# How far is it behind dev?
git rev-list --count feature/XXXXX-your-branch..ado/dev
```

**Do NOT re-analyze the FDS section from scratch.** The analysis was done in a previous
session. Read the PR comments to understand what was already built and what failed.

---

### Step 3 — Confirm desired end state with the user

Post in the GitHub issue:
1. What the PR currently does (from reading diff + comments)
2. What feedback was given (exact quotes)
3. Your proposed approach: rebase onto dev? Drop certain commits? New commits?

Wait for user confirmation before writing any code.

---

### Step 4 — Rebase / catch-up branch

```bash
cd ~/TFIOneGit

# Safety backup tag (always do this before destructive git operations)
git tag "backup-pre-rebase-$(date +%Y-%m-%d)-${BRANCH_SHORT}" HEAD

# Fetch latest dev
git fetch ado dev

# Rebase current branch onto ado/dev
git rebase ado/dev
# → resolve conflicts if any
# → drop ci/empty commits: git rebase -i ado/dev
```

**If the rebase history is complex:**
```bash
# Alternative: cherry-pick only the feature commits (skip ci/merge commits)
git checkout -b feature/XXXXX-fresh ado/dev
git cherry-pick <commit1> <commit2> ...
```

---

### Step 5 — Run 4 gates

From `~/TFIOneGit`:
```bash
# Build
dotnet build com.tfione.sln --no-incremental 2>&1 | tail -5

# Unit tests (controller + repo tests only — no biz logic)
dotnet test com.tfione.service.test/com.tfione.service.test.csproj --no-build 2>&1 | tail -10

# Build gate (no GRANT/DENY in migrations, no d.ts staged)
claire fivepoints install-hooks  # ensure hook is installed
git diff ado/dev --name-only | grep migration/ | xargs -I{} grep -l "GRANT\|DENY" {} 2>/dev/null && echo "FAIL: GRANT/DENY found" || echo "OK"

# Lint
dotnet format com.tfione.sln --verify-no-changes 2>&1 | tail -5
```

All 4 must be green before proceeding.

---

### Step 6 — Run e2e proof

```bash
# Start test environment (fixes for L1/L2/L3 are baked in)
claire fivepoints test-env-start --path ~/TFIOneGit

# Run e2e for the section being worked on
cd ~/TFIOneGit
python3 ~/.config/claire/plugins/fivepoints/domain/scripts/<section>_e2e.py \
    --base-url https://localhost:58337 \
    --client-id <TEST_CLIENT_ID>
```

Record video proof. Convert webm → mp4 if needed:
```bash
for f in /tmp/<section>_proof/*.webm; do
    ffmpeg -i "$f" "${f%.webm}.mp4" -y
done
```

---

### Step 7 — Push (with no-force-push strategy if needed)

```bash
# Try normal push first
git push ado feature/XXXXX-your-branch --force-with-lease

# If denied (TF401027: You need the Git 'ForcePush' permission):
claire fivepoints rebase-no-force \
    --branch feature/XXXXX-your-branch \
    --target dev \
    --pr <ADO_PR_NUMBER>
```

See `claire domain read fivepoints operational NO_FORCE_PUSH_STRATEGY` for details.

---

### Step 8 — Post proof on ADO PR

```bash
# Post recap comment on ADO PR
claire fivepoints reply --pr <ADO_PR_NUMBER> --message "$(cat <<'MSG'
## Proof — $(date +%Y-%m-%d)

**Gates (all green):**
- ✅ Build: `dotnet build` — 0 errors
- ✅ Tests: `dotnet test` — XX passed
- ✅ Build gate: no GRANT/DENY, no d.ts
- ✅ Lint: `dotnet format --verify-no-changes`

**E2E (6/6 scenarios PASS):**
- ✅ Scenario 1: ...
...

**Video:** [proof.mp4](...)
MSG
)"

# Upload video attachments to the PR thread
# (use ADO Attachments API or paste link to /tmp/<section>_proof/*.mp4)
```

---

### Step 9 — Wait for merge

```bash
claire fivepoints ado-watch --pr <ADO_PR_NUMBER>
# OR (for integrated GitHub tracking):
claire fivepoints land --pr <ADO_PR_NUMBER> --skip-to post-proof
```

Do NOT merge the PR yourself. Wait for Steven's approval.

---

## One-Command Shortcut

The `land` command automates steps 4–9:

```bash
claire fivepoints land --pr <ADO_PR_NUMBER> --branch feature/XXXXX-your-branch
```

Use the manual checklist above when you need fine-grained control (e.g. cherry-pick
strategy, manual conflict resolution, or partial runs).

---

## Critical Differences from Dev Persona

| Dev persona | Finish-existing-PR persona |
|-------------|---------------------------|
| Start from `~/TFIOneGit main` | Start from the existing feature branch |
| Create new branch | Rebase existing branch |
| Analyze FDS section | Read PR comments (already analyzed) |
| Standard `git push ado` | May need no-force-push strategy |
| `ado-push` command | `rebase-no-force` + manual proof post |

---

## Related

- `claire fivepoints land --agent-help` — automated end-to-end command
- `claire domain read fivepoints operational NO_FORCE_PUSH_STRATEGY` — push strategy details
- `claire domain read fivepoints operational DEVELOPER_GATES` — gate definitions
- `claire domain read fivepoints operational TESTING` — e2e credentials and test patterns
- Issue #146 — original session this persona was derived from
