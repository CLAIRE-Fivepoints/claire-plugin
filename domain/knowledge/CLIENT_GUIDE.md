---
keywords: [five-points, fiveptg, client-guide, poc, react, dotnet, brian-cliburn, steve-franklin, engagement]
---

# Five Points Group – Client Guide

## Overview

Five Points Group is evaluating an AI-assisted development engagement with C.L.A.I.R.E.
The goal: validate that AI code generation can match their architectural patterns and deliver
production-quality React / .NET code at scale.

---

## Contacts

| Role | Name | Email |
|------|------|-------|
| Decision maker | Brian Cliburn | brian.cliburn@fiveptg.com |
| Lead Engineer | Steve Franklin | — |

**Communication rule:** Technical questions → Steve Franklin. Commercial/strategic → Brian Cliburn.

---

## Their Stack

- **Frontend:** React (version TBD — confirm with Steve)
- **Backend:** .NET (version TBD — confirm with Steve)
- **Architectural patterns:** TBD — must confirm before calibration

> Key question to ask Steve: Clean Architecture? Vertical Slice? CQRS with MediatR?

---

## Current Code-Gen Baseline

Five Points already runs an AI code-gen process internally.
**Benchmark:** a few hours per PBI.
Our engagement must match or beat this while delivering higher architectural fidelity.

---

## Proof of Concept Options

### Option 1 — Client Management / Education *(recommended start)*

| Attribute | Detail |
|-----------|--------|
| Scope | ~7 PBIs |
| Infrastructure | Existing — standalone verticals within existing infra |
| Risk | Low |
| Status | Already slated for AI code-gen in their current process |

**Why start here:** Lower risk, existing infrastructure means we can validate pattern-matching
without having to infer the full architecture from scratch.

---

### Option 2 — Service Requests *(more ambitious)*

| Attribute | Detail |
|-----------|--------|
| Scope | Full functional area |
| Infrastructure | None — build from scratch |
| Risk | Higher |
| Validation | Must match existing architectural patterns and stand up the full area |

**Why this is interesting:** Full-stack validation. If we can build a new functional area that
looks indistinguishable from their hand-written code, the commercial case is clear.

**Recommendation:** Only start Option 2 after Option 1 is validated.

---

## What We Need From Five Points

### Critical (blocks work from starting)

- [ ] **Reference code** — 1–2 complete feature verticals (frontend + API + data layer)
  - This is the single most important input
  - Used to calibrate naming, structure, patterns, style
  - Without this, generated code will miss their conventions

### Required Before First PBI

- [ ] Architecture documentation (diagram, stack versions, pattern choices)
- [ ] Development standards (linting config, naming conventions, testing standards)
- [ ] Design assets (Figma or equivalent for target area)
- [ ] Data model / DB schema for the target area

### Option-Specific

**Option 1:**
- [ ] PBI descriptions with acceptance criteria for all 7 items
- [ ] Integration context with existing infrastructure

**Option 2:**
- [ ] Service request domain requirements (lifecycle states, roles, triggers)
- [ ] Integration points with existing modules
- [ ] Any prior design or requirements documentation

---

## Onboarding Protocol

1. **Receive materials** — request everything in the checklist above
2. **Calibration session** — 30–45 min with Steve Franklin to walk through the codebase
   - More efficient than 2–3 rounds of misaligned output
3. **Document patterns** — update `five_points/technical/PATTERNS.md` after the session
4. **First PBI** — generate, submit for review, calibrate based on feedback
5. **Iterate** — the first 1–2 PBIs are calibration; speed increases after that

---

## Commercial Model (pending PoC outcome)

Brian's stated intent if PoC succeeds:
- Move quickly into commercial arrangement
- Options discussed: per-module pricing OR subscription
- Decision will be based on PoC outcomes

**Do not discuss pricing until PoC is validated.**

---

## Engagement Timeline

| Date | Event |
|------|-------|
| 2026-02-24 | Initial email from Brian Cliburn |
| 2026-02-24 | Response sent (GitHub issue #1123) |
| TBD | Receive reference materials from Five Points |
| TBD | Calibration session with Steve Franklin |
| TBD | First PBI delivered |
| TBD | PoC evaluation |
| TBD | Commercial discussion |

---

## Open Questions

1. Which .NET version? Which React version?
2. What architectural pattern do they use (.NET side)?
3. Do they have a design system / component library?
4. What is their test coverage expectation?
5. How do they handle authentication in existing modules?
6. What CI/CD pipeline do they use?
