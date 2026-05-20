---
name: VERIFY_TEMPLATES
title: "fivepoints verify-templates — single-source-of-truth guard for the dev pipeline checklist"
description: "Checks that fivepoints-dev.md has no embedded checklist step definitions and CHECKLIST_DEV_PIPELINE.md is the single source of truth"
domain: fivepoints
category: knowledge
keywords: [verify-templates, checklist, duplication, dry, single-source, fivepoints-dev, CHECKLIST_DEV_PIPELINE, persona, guard]
updated: 2026-05-20
---

# fivepoints verify-templates

Single-source-of-truth guard for the dev pipeline checklist. Asserts that
`domain/persona/fivepoints-dev.md` contains **no embedded step definitions**
(`- [ ] [N/11]` or `- [x] [N/11]` line-starters) and that
`domain/operational/CHECKLIST_DEV_PIPELINE.md` is the canonical file with
all 11 steps.

---

## Usage

```bash
claire fivepoints verify-templates          # summary line only
claire fivepoints verify-templates --verbose # per-check detail
claire fivepoints verify-templates --help
claire fivepoints verify-templates --agent-help
```

---

## What it checks

| Check | Pass condition |
|-------|----------------|
| 1 | `domain/persona/fivepoints-dev.md` exists |
| 2 | `domain/operational/CHECKLIST_DEV_PIPELINE.md` exists |
| 3 | Persona has **no** lines matching `^- \[[ x]\] \[N/11\]` (N = 1–11) |
| 4 | Checklist has **all** lines matching `^- \[[ x]\] \[N/11\]` (N = 1–11) |

Inline cross-references in the persona — e.g. `"never skip [8/11]"` or
`` "see `[10/11]`" `` — are **not** flagged. Only actual step-definition lines
(markdown checkbox + step marker at line start) trigger a failure.

---

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | No duplication; checklist is the single source of truth |
| 1 | Duplication detected, step missing from checklist, or a required file is absent |

---

## Context

Issue #80 (CLAIRE-Fivepoints/claire-plugin): the lean-v3 persona rewrite
(`6c03ec3`) removed the full `[1/11]`–`[11/11]` block that was hand-copied
from `CHECKLIST_DEV_PIPELINE.md` into `fivepoints-dev.md`. This command
formalises that invariant so future edits to either file are immediately
caught if the duplication is re-introduced.

---

## Implementation

| File | Purpose |
|------|---------|
| `domain/commands/verify-templates.sh` | Command implementation |
| `tests/scripts/test_verify_templates.bats` | 9 bats tests |

---

## See also

- `claire domain read fivepoints operational CHECKLIST_DEV_PIPELINE` — the single source of truth
- `claire domain read fivepoints persona fivepoints-dev` — the persona that must not embed the checklist
