---
domain: fivepoints
category: operational
name: ADO_ATTACHMENTS
title: "FivePoints — ADO Attachment Fetch & FDS Manifest"
keywords: [ado, azure-devops, attachment, fds, docx, fetch-on-use, manifest, sha256, claire-plugin, pbi, "persona:fivepoints-dev"]
updated: 2026-04-19
---

# FivePoints — ADO Attachment Fetch & FDS Manifest

> **Why this exists:** Issue #71 (PBI #18839 Client Face Sheet Code Gen) shipped bad specs
> because the FDS attached to the parent PBI was never read. The original response was to
> cache the FDS docx in the plugin repo and hard-stop on drift, but that blocked every
> analyst session on unrelated FDS edits and did not prevent a determined agent from
> fabricating a Read Receipt. Issue #51 replaced the cache-in-git model with **fetch-on-use
> + a mechanically-verified manifest**: the analyst's receipt carries hashes that a CI gate
> on the dev PR recomputes from the live FDS. Fabricated receipts cannot pass the gate.

---

## Command

```bash
claire fivepoints ado-fetch-attachments --pbi <id> [--print-manifest]
```

### Modes

| Mode | Stdout | Use when |
|------|--------|----------|
| (no flag)          | (logs only) | you just want the extracted FDS on disk to read locally |
| `--print-manifest` | JSON manifest | analyst posting the FDS Read Receipt, CI gate recomputing hashes |

### Exit codes

| Code | Meaning |
|------|---------|
| `0`  | success (or PBI has no attachments) |
| `2`  | error: PAT missing, ADO API failure, …   |

---

## What it does

1. **Fetch** the work item relations:
   `GET /_apis/wit/workitems/{pbi}?$expand=relations&api-version=7.1`
2. **Filter** `relations[].rel == "AttachedFile"`.
3. **Download** each attachment to `~/TFIOneGit/.fds-cache/{pbi}/`.
4. **Reuse if MD5 matches** — if the staging copy already matches the live attachment,
   skip re-extract (the manifest is still emitted).
5. **Extract** images with section anchors:
   - Walk `word/document.xml` in order, tracking the nearest preceding heading.
   - Skip `<w:ins>` runs (unaccepted insertions). Keep `<w:del>` content.
   - Write PNG/JPEG + per-image `.md` sidecar describing section + surrounding text.
6. **Write section markdown** — a single `FDS_<NAME>.md` with one heading per section,
   each carrying a `<!-- sha256: ... | pages X-Y -->` marker.
7. **Emit the manifest** (with `--print-manifest`) to stdout — one JSON object per
   invocation. See structure below.

---

## Output layout (staging)

```
~/TFIOneGit/.fds-cache/{pbi}/
├── 4_-_Client_Management_1_.docx       # fresh attachment (as downloaded)
├── FDS_CLIENT_MANAGEMENT.md             # full doc, section by section (with sha256 markers)
├── FDS_CLIENT_MANAGEMENT_images/
│   ├── image001.png
│   ├── image001.md                      # section + surrounding paragraphs
│   └── ...
└── FDS_CLIENT_MANAGEMENT_IMAGE_INDEX.md
```

Nothing is written to the plugin repo. The staging dir is gitignored — it's session-local.

---

## Manifest structure (`--print-manifest`)

```json
{
  "pbi": 17113,
  "org": "FivePointsTechnology",
  "project": "TFIOne",
  "fetched_at": "2026-04-19T20:45:00Z",
  "staging_dir": "/Users/you/TFIOneGit/.fds-cache/17113",
  "docs": [
    {
      "docx_filename": "4 - Client Management(1).docx",
      "docx_md5": "f636b255be9f7e3ab3760b7d2b5f312e",
      "docx_bytes": 6459581,
      "doc_name": "CLIENT_MANAGEMENT",
      "reused": false,
      "pages_supported": true,
      "sections": [
        {
          "title": "Client Face Sheet",
          "path": "Client Management > Client Face Sheet",
          "level": 2,
          "sha256": "<64 hex chars of the section paragraphs>",
          "pages": [142, 157],
          "image_refs": ["image010.png", "image011.png"]
        }
      ]
    }
  ]
}
```

### Fields

- `docx_md5` — streaming MD5 of the downloaded docx bytes. Equals the MD5 an independent
  re-fetch would produce.
- `docx_bytes` — size of the downloaded file.
- `reused` — `true` when the staging copy's MD5 still matched the live download, so the
  extract step (docx parse + images + section markdown + IMAGE_INDEX) was skipped. The
  network download always happens — ADO does not give us a cheap "unchanged" signal.
- `pages_supported` — `true` if the docx carries `<w:lastRenderedPageBreak/>` markers.
  Word emits these when rendering for print/save; if the docx was programmatically
  generated and never opened in Word, pages will be `null`.
- `sections` — **list** (not dict), in document order. Titles like "Field Descriptions"
  repeat under many parents; only `path` is unique.
- `sections[].title` — the heading text as it appears in the docx.
- `sections[].path` — ancestor chain joined with ` > ` (e.g. "Client Management > Client
  Face Sheet"). The CI gate keys on this to look up the section from the Read Receipt.
- `sections[].level` — 1 = H1, 2 = H2, …
- `sections[].sha256` — `sha256` over `"\n".join(section.paragraphs)` (UTF-8). Identical
  content → identical hash. Stable across re-fetches.
- `sections[].pages` — `[start, end]` or `null`.
- `sections[].image_refs` — list of extracted image filenames anchored to this section.

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

Run once at session start, save the manifest, quote hashes in the FDS Read Receipt:

```bash
claire fivepoints ado-fetch-attachments --pbi <parent> --print-manifest > /tmp/fds-manifest.json
```

Read the extracted markdown:

```bash
cat ~/TFIOneGit/.fds-cache/<parent>/FDS_<NAME>.md
```

Quote in the receipt:
- `docx_md5` from `docs[].docx_md5`
- `section_path` + `section_sha256` from the target entry in `docs[].sections[]`
  (the path is the unique key; bare titles can collide)
- 5–10 verbatim labels copied from `FDS_<NAME>.md`

### Dev (`CHECKLIST_DEV_PIPELINE.md`)

Same command — but the dev reads the section to confirm scope. The dev does **not**
manually re-verify the analyst's receipt; the `fds-verify.yml` CI gate on the PR does
that mechanically.

### CI gate (`fds-verify.yml`, `CLAIRE-Fivepoints/fivepoints`)

On every push to a dev PR:
1. Parse the analyst's `**FDS Read Receipt**` comment from the linked issue.
2. Re-run `ado-fetch-attachments --pbi <parent-pbi> --print-manifest` using a read-only
   PAT stored as a repo secret.
3. Compare `docx_md5` and `section_sha256` to the receipt.
4. `grep` each verbatim label in the fresh `FDS_<NAME>.md`. Every label must match exactly.
5. On any mismatch → fail the check with a diff of receipt-claimed vs. live.

Without a passing `fds-verify` check, the dev PR cannot merge.

---

## Common errors

| Symptom | Fix |
|---------|-----|
| `No Azure DevOps PAT found` | set `AZURE_DEVOPS_PAT` in `~/.config/claire/.env` |
| Section sha256 mismatch in CI | analyst fabricated or stale receipt — re-read the section and repost |
| Verbatim label not found in fresh markdown | analyst paraphrased — copy the label verbatim from `FDS_<NAME>.md` |

---

## Related

- `claire domain read fivepoints operational ADO_PAT_GUIDE` — full PAT setup
- `claire domain read fivepoints operational AZURE_DEVOPS_ACCESS` — org/project/repo identifiers
- Issue #71 (CLAIRE-Fivepoints/fivepoints) — incident that motivated the original tool
- Issue #51 (CLAIRE-Fivepoints/claire-plugin) — fetch-on-use + manifest redesign
