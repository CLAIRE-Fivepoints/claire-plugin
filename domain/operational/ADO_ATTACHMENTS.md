---
domain: fivepoints
category: operational
name: ADO_ATTACHMENTS
title: "FivePoints — ADO Attachment Fetch & FDS Cache Drift Detection"
keywords: [ado, azure-devops, attachment, fds, docx, cache, drift, image-index, claire-plugin, pbi]
updated: 2026-04-16
---

# FivePoints — ADO Attachment Fetch & FDS Cache Drift Detection

> **Why this exists:** Issue #71 (PBI #18839 Client Face Sheet Code Gen) shipped bad specs
> because the FDS attached to the parent PBI was never read. The cached version in
> `fivepoints/domain/knowledge/FDS_CLIENT_MANAGEMENT.docx` was ~2 MB out of date AND did
> not include the target chapter. This tool closes that gap: an agent can check the cache
> against the fresh ADO attachment in one command.

---

## Command

```bash
claire fivepoints ado-fetch-attachments --pbi <id> [--diff-only] [--auto-issue]
```

### Modes

| Mode | Writes | Opens issue | Use when |
|------|--------|-------------|----------|
| `--diff-only` | staging `.docx` only | no | pre-flight cache check (analyst/dev) |
| (neither flag) | staging + images + index + issue body | no | inspect fresh FDS locally |
| `--auto-issue` | staging + images + index + issue body | yes | report drift to the plugin repo |

### Exit codes

| Code | Meaning |
|------|---------|
| `0`  | cache matches (or PBI has no attachments) — no action needed |
| `1`  | drift detected — staging populated, issue body generated |
| `2`  | error: PAT missing, API failure, or `gh issue create` failed |

---

## What it does

1. **Fetch** the work item relations:
   `GET /_apis/wit/workitems/{pbi}?$expand=relations&api-version=7.1`
2. **Filter** `relations[].rel == "AttachedFile"`.
3. **Download** each attachment to `~/TFIOneGit/.fds-cache/{pbi}/`.
4. **Compare** MD5 against `<plugin>/domain/knowledge/FDS_<NAME>.docx`.
   - Match → print `✅ cache up-to-date` and exit `0`.
   - Drift → proceed to extraction (never overwrite the cache).
5. **Extract** images with section anchors:
   - Walk `word/document.xml` in order, tracking the nearest preceding heading.
   - Skip `<w:ins>` runs (unaccepted insertions). Keep `<w:del>` content.
   - Write PNG/JPEG + per-image `.md` sidecar describing section + surrounding text.
6. **Generate** `FDS_<NAME>_IMAGE_INDEX.md` — a table mapping every image to its section.
7. **Section diff** — extract headings from cached + fresh, list added/removed.
8. **Issue body** — assemble `drift_issue_<NAME>.md` (MD5 delta, section delta, image count).
9. **With `--auto-issue`:** bash reads `drift_action_<NAME>.json` and runs `gh issue create`
   against `CLAIRE-Fivepoints/claire-plugin`.

---

## Output layout (staging)

```
~/TFIOneGit/.fds-cache/{pbi}/
├── 4_-_Client_Management_1_.docx       # fresh attachment (as downloaded)
├── FDS_CLIENT_MANAGEMENT_images/
│   ├── image001.png
│   ├── image001.md                     # section + surrounding paragraphs
│   └── ...
├── FDS_CLIENT_MANAGEMENT_IMAGE_INDEX.md
├── drift_issue_CLIENT_MANAGEMENT.md    # issue body
└── drift_action_CLIENT_MANAGEMENT.json # bash reads this for --auto-issue
```

The **domain cache is never written**. Cache updates flow through a human-reviewed PR
against `fivepoints/domain/knowledge/`.

---

## PAT resolution

Read-only PAT is sufficient. Resolved in order (mirrors `ado_common.sh`):

1. `AZURE_DEVOPS_WRITE_PAT` (env)
2. `AZURE_DEVOPS_DEV_PAT` (env)
3. `AZURE_DEVOPS_PAT` (env)
4. Same three keys from `~/.config/claire/.env`

No ADO call is attempted without a PAT.

---

## Integration points

### Analyst (`CHECKLIST_ANALYST.md`)

Mandatory pre-flight before writing specs:

```bash
claire fivepoints ado-fetch-attachments --pbi <parent> --diff-only
```

- Exit 0 → cache is fresh, proceed with `claire domain read fivepoints knowledge FDS_<NAME>_SCREENS_<section>`.
- Exit 1 → cache is stale. Post a comment asking the plugin team to refresh the cache
  (or run with `--auto-issue` to open the drift issue yourself). Do not write specs
  against stale cache.

### Dev (`CHECKLIST_DEV_PIPELINE.md`)

`[1.5/11]` FDS cross-check, added after `[1/11]` context load:

```bash
claire fivepoints ado-fetch-attachments --pbi <parent> --diff-only
```

- Exit 0 → cross-check the analyst's specs against
  `FDS_<NAME>_SCREENS_<section>.md` + `FDS_<NAME>_IMAGE_INDEX.md`.
- Exit 1 → the analyst should have blocked; do not implement on stale specs.

### Gatekeeper review

PR reviewers should confirm the PR description references the specific FDS section
and image number from the IMAGE_INDEX.

---

## Common errors

| Symptom | Fix |
|---------|-----|
| `No Azure DevOps PAT found` | set `AZURE_DEVOPS_PAT` in `~/.config/claire/.env` |
| `gh issue create failed: authentication required` | run `gh auth status` and refresh if needed |
| No cached counterpart matched | attachment name does not map to `FDS_<TOKEN>.docx` — rename, or prime the cache with a first-pass PR |

---

## Related

- `claire domain read fivepoints operational ADO_PAT_GUIDE` — full PAT setup
- `claire domain read fivepoints operational AZURE_DEVOPS_ACCESS` — org/project/repo identifiers
- Issue #71 (CLAIRE-Fivepoints/fivepoints) — incident that motivated this tool
