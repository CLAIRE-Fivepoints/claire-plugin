---
name: E2E_BLIND_BENCHMARK
title: E2E Blind Benchmark — Section 24 Education
description: Step-by-step plan for the true E2E blind benchmark (spec → domain → implementation → verification)
domain: fivepoints
category: technical
keywords: benchmark, education, section-24, e2e, blind-test, domain-creation, playwright, backend-tests
updated: 2026-03-19
---

# E2E Blind Benchmark — Section 24 Education

## Overview

A **true end-to-end blind benchmark**: Claire receives only the raw spec documents,
creates a domain document from scratch, then uses that domain to implement Section 24.

**Goal:** Determine whether automated domain extraction from a spec alone produces
sufficient context for a correct implementation — in one loop.

---

## Repository Setup

| Resource | Location |
|----------|----------|
| TFI One repo | `/Users/andreperez/TFIOneGit` |
| Blank slate branch | `feature/10399-client-mgmt-education-impl` |
| Ground truth branch | `feature/10399-education-gaps` |
| Claire domain output | `30_universe/domains/<fictional-client>/technical/EDUCATION.md` (**NOT** fivepoints) |
| This benchmark plan | `30_universe/domains/fivepoints/technical/E2E_BLIND_BENCHMARK.md` |
| Spec — Client Mgmt | `30_universe/domains/fivepoints/knowledge/CLIENT_MANAGEMENT_REQUIREMENTS.md` (Section "Education") |
| Spec — Technical Design | `30_universe/domains/fivepoints/knowledge/TECHNICAL_DESIGN_DOCUMENT.md` + uploaded `TFI One Technical Design Document 20250709.docx` |

> **Important:** The domain document created during Phase A MUST NOT be placed in the `fivepoints` domain.
> It goes into a **new fictional-client domain** to simulate discovering a new client from scratch.
> The existing fivepoints domain is preserved and used only for ground truth comparison (Phase C/D).

---

## Benchmark Branches

```
origin/dev
    └── feature/10399-client-mgmt-education-impl  ← blank slate (start here)
    └── feature/10399-education-gaps              ← ground truth (score against this)
```

**Starting point for each round:**
Each round starts from the current tip of `feature/10399-client-mgmt-education-impl`.
Claire creates a fresh `benchmark/round-N` branch from that tip.

---

## Benchmark Prompt (Round 1)

This is the exact prompt given to Claire at the start of each round.
The spec is presented as a **fictional new client** — no TFI One / fivepoints context provided.

```
You are onboarding a new client: a child welfare case management software company.

They have provided you three inputs:
1. Their functional spec for the "Education" module (Section 24)
2. Their technical design document describing their stack and conventions
3. Their existing codebase (for reference on patterns and conventions)

PHASE A — Before writing any code, read these inputs and create a domain document at:
  30_universe/domains/benchmark-client/technical/EDUCATION.md

This document must capture:
- DDL patterns: table names, column types, FK constraints, nullable rules
- Entity names: class names, namespace conventions
- Endpoint conventions: route patterns, HTTP verbs, controller naming
- Frontend structure: component naming, state management pattern, UI component library
- Business rules: conditional field visibility, date constraints, aggregation logic
- Permission model: authorization attribute patterns per endpoint
- Reference entities: which fields use lookup tables vs enums vs booleans

Ask questions if you need clarification before proceeding to Phase B.

PHASE B — Using ONLY the domain document you just created (no re-reading the codebase),
implement the Education module on branch benchmark/round-1.

Prove your work: all backend tests pass + Playwright scenarios pass.
```

**Key constraint:** Claire must not reference the `fivepoints` domain during the session.
The domain she creates goes to `30_universe/domains/benchmark-client/` — a new domain.

**What "blind" means here:** Claire derives her own domain from spec + code, without
consulting the existing curated fivepoints domain. The test is whether she can extract
the right patterns herself, not whether she can work from spec alone.

---

## Phase A — Domain Creation

**Input:** Spec documents only (no existing code reference allowed)
**Output:** `30_universe/domains/benchmark-client/technical/EDUCATION.md` (**NOT fivepoints**)

### A.1 Spec documents to read
1. `30_universe/domains/fivepoints/knowledge/CLIENT_MANAGEMENT_REQUIREMENTS.md` — Section "Education" (lines ~650–733)
2. `30_universe/domains/fivepoints/knowledge/TECHNICAL_DESIGN_DOCUMENT.md` + uploaded `TFI One Technical Design Document 20250709.docx`

### A.2 Domain document must capture

| Section | Content |
|---------|---------|
| **DDL Patterns** | Table names, column types (`BIT NOT NULL`, `uniqueidentifier`), FK constraints, nullable rules |
| **Entity Names** | C# class names, namespace conventions, ORM mappings |
| **Endpoint Conventions** | Route patterns (`/client/{id}/education`), HTTP verbs, controller naming |
| **Frontend Structure** | Component file names, RTK Query slice pattern, MUI primitives |
| **Business Rules** | IEP date visibility, GED future-date lock, most-recent aggregation for Overview card |
| **Permission Codes** | `[Authorize]` attribute values per endpoint |
| **Reference Entities** | Which dropdowns use GUID references vs enums |

### A.3 Acceptance criterion
Domain document is complete when it could be given to a developer with zero prior
TFI One knowledge and they could implement Section 24 correctly.

---

## Phase B — Implementation

**Input:** Domain document from Phase A only (no peeking at ground truth branch)
**Branch:** `benchmark/round-N` branched from `feature/10399-client-mgmt-education-impl`

### B.1 Sub-modules to implement (6 total)

| # | Sub-module | Key files |
|---|------------|-----------|
| 1 | Education Overview card | `education_overview_card.tsx`, `EducationController.cs` (GetOverview) |
| 2 | Edit Education Info | `education_edit.tsx`, `EducationController.cs` (GetEdit, SaveEdit) |
| 3 | Grade Achieved History | `grade_achieved_*.tsx`, `EducationController.cs` (Search/Get/Create/Update/Delete) |
| 4 | GED History | `ged_test_*.tsx`, `EducationController.cs` (Search/Get/Create/Update/Delete) |
| 5 | Enrollment History | `enrollment_*.tsx`, `EducationController.cs` (Search/Get/Create/Update/Delete) |
| 6 | Report Card History | `report_card_*.tsx`, `EducationController.cs` (Search/Get/Create/Update/Delete) |

### B.2 Backend layers (per sub-module)
1. **DDL** — `com.tfione.db/migrations/` — migration SQL file
2. **ORM** — `com.tfione.db/orm/` — entity class + `TfiOneContext.cs` DbSet
3. **Model** — `com.tfione.model/client/` — view/edit/list model classes
4. **Repo** — `com.tfione.repo/client/EducationRepo.cs` — data access
5. **Controller** — `com.tfione.api/client/EducationController.cs` — endpoints
6. **Validator** — `com.tfione.service/client/` — FluentValidation rules

### B.3 Frontend layers (per sub-module)
1. **RTK Query slice** — `com.tfione.web/src/redux/services/com.tfione.api/education.ts`
2. **Components** — `com.tfione.web/src/components/client/face_sheet/education/`
3. **Face sheet registration** — add to client face sheet navigation
4. **Context menu** — register education route in face sheet menu

---

## Phase C — Verification

### C.1 Backend tests (25 xUnit tests)

**File:** `com.tfione.service.test/client/EducationControllerTests.cs`

**Run command:**
```bash
cd /Users/andreperez/TFIOneGit
dotnet test com.tfione.service.test --filter "FullyQualifiedName~EducationControllerTests" --verbosity normal
```

**Expected:** 25/25 passing

### C.2 Playwright E2E tests (6 scenarios)

**File:** `com.tfione.web/e2e/education.spec.ts`

**Run command:**
```bash
cd /Users/andreperez/TFIOneGit/com.tfione.web
npx playwright test education.spec.ts --reporter=list
```

**Expected:** 6/6 passing

**Note:** Current Playwright coverage is limited to Edit Education Info sub-module.
Other 5 sub-modules (Overview, Grade Achieved, GED, Enrollment, Report Card) require
manual verification via the reviewer checklist.

### C.3 Structural diff against ground truth

```bash
git -C /Users/andreperez/TFIOneGit diff feature/10399-education-gaps..benchmark/round-N --stat
```

**Expected:** Zero diff on education-specific files.

### C.4 Build gate

```bash
cd /Users/andreperez/TFIOneGit
dotnet build com.tfione.sln
```

**Expected:** 0 errors, 0 warnings (StyleCop must pass).

---

## Phase D — Gap Analysis

After each round, compare:

| Failure Category | Likely Source |
|-----------------|---------------|
| FK constraint errors | Domain missing DDL relationships |
| `BIT NOT NULL` issues | Domain missing column constraint rules |
| GUID vs boolean confusion | Domain missing reference entity types |
| Wrong MUI primitives | Domain missing frontend component patterns |
| Missing permission codes | Domain missing authorization table |
| Wrong validation rules | Domain missing server-side validator patterns |

**Gap document location:** `30_universe/domains/fivepoints/technical/SECTION_24_EDUCATION_GAPS_RN.md`
(where N = round number)

---

## Scoring Rubric

| Metric | Weight | Measurement |
|--------|--------|-------------|
| Backend tests pass rate | 40% | `X/25` xUnit tests |
| Playwright pass rate | 30% | `X/6` E2E scenarios |
| Structural diff count | 20% | Files different from ground truth |
| StyleCop/build clean | 10% | 0 errors = full score |

**Score formula:**
```
Score = (backend_pass/25 * 0.40) + (playwright_pass/6 * 0.30) +
        (1 - diff_files/total_education_files * 0.20) + (build_clean * 0.10)
```

**Target:** Score ≥ 0.85 to consider domain auto-generation viable.

---

## Round Tracking

| Round | Branch | Domain SHA | Score | Key Gaps |
|-------|--------|------------|-------|----------|
| Pre-benchmark #42 | `feature/10399-client-mgmt-education-impl` | N/A | ~0.4 | FK, BIT NOT NULL, MUI primitives |
| Pre-benchmark #47 | `feature/10399-client-mgmt-education-impl` | N/A | ~0.6 | GUID/bool, reference entities, validators |
| Round 1 | `benchmark/round-1` | TBD | TBD | TBD |

---

## Known Failure Modes (from #42 and #47)

These must be explicitly covered in the domain document to avoid repeat failures:

1. **GUID vs boolean** — IEP, ARD, OnGradeLevel are stored as `BIT NOT NULL` in SQL but
   the Yes/No dropdowns reference GUID lookup entities, not booleans. Both the SQL column
   and the C# model must handle this correctly.

2. **FK constraints** — Each sub-module table has an FK to `client_master`. The domain
   must specify the exact constraint syntax used in TFI One migrations.

3. **BIT NOT NULL defaults** — All boolean-like columns require `BIT NOT NULL DEFAULT 0`
   in the DDL, not nullable bits.

4. **MUI primitives** — Use `TfioSelect` not `Select`, `TfioDatePicker` not `DatePicker`.
   The domain must list the exact MUI wrapper components used in TFI One.

5. **Permission codes** — Each controller action requires a specific `[Authorize(Policy=...)]`
   attribute. The domain must document the permission code per endpoint.

6. **Split component rule** — Add/Edit components must be split into separate files
   (`education_add.tsx` and `education_edit.tsx`), not combined. StyleCop enforces this.
