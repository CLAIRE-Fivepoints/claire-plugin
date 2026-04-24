---
domain: fivepoints
category: knowledge
name: DEV_RULES
title: "Five Points — Development Rules (Overrides Core)"
keywords: [five-points, tfi-one, dev-rules, development, rules, grant, deny, d-ts, ddl, dba, ef-core, scaffolding, subprocess, angular, flyway, migration, business-logic-tests, role-dev, fivepoints-dev, pbi, git-push-github, "persona:fivepoints-dev"]
updated: 2026-03-29
---

# Five Points — Development Rules

> These rules apply to the **Five Points / TFI One repository**.
> They inherit from [Core DEV_RULES](../../core/knowledge/DEV_RULES.md) and override where noted.
> **Conflict resolution: most specific level wins** — these rules take precedence over core within Five Points.

---

## Inherited from Core

All rules in `core/knowledge/DEV_RULES` apply here unless explicitly overridden below.
See: `claire domain read core knowledge DEV_RULES`

---

## Five Points-Specific Rules

### 1. No GRANT/DENY in Migration Files

**Rule:** Flyway migration files must never contain `GRANT`, `DENY`, or `EXEC sp_addrolemember`. Role permissions are managed via the application UI.

**Why:** Database role permissions are tenant-configurable through the UI. Embedding them in migrations creates conflicts between environments and removes the admin's ability to customize access.

**Violation:**
```sql
-- ❌ In a Flyway migration
GRANT SELECT ON dbo.ClientTable TO app_role;
```

---

### 2. No `.d.ts` Files Committed

**Rule:** `com.tfione.api.d.ts` is a generated file and must never appear in source control.

**Why:** It is auto-generated and listed in `.gitignore`. Committing it causes merge conflicts on every build and bloats the repository.

**Fix if accidentally tracked:**
```bash
git rm --cached com.tfione.api.d.ts
git commit -m "chore: remove generated file from tracking"
```

---

### 3. DDL Changes Require Scaffolding

**Rule:** Files in `com.tfione.db/orm/` must be generated via `dotnet ef dbcontext scaffold`, never hand-coded. Only `com.tfione.db/partial/TfiOneContext.cs` is hand-coded.

**Why:** Hand-coded ORM entities drift from the actual database schema. Scaffolding guarantees the C# model matches the database after migrations run.

**Workflow:**
1. Write/apply Flyway migration
2. Run `dotnet ef dbcontext scaffold`
3. Commit the scaffolded output

---

### 4. Business Logic Tests Not Committed

**Rule:** Tests for TFI One business domain (clients, providers, organizations, FDS sections) must not be committed. `com.tfione.service.test` is only for infrastructure/utility services and external API adapters.

**Allowed test scopes:**
- `encryption/` — Encryptor, hashing, cipher utilities
- `password/` — PasswordGenerator
- `signing/` — Adobe endpoint URL builders
- `mapping/` — Google/address API adapters
- `email/` — SendGrid adapter
- `messaging/` — Twilio adapter

**Why:** Business logic tests that mock repositories or DbContext create false confidence — they pass in CI but fail against the real database. Infrastructure tests are safe to unit-test because they have stable, well-defined contracts.

---

### 5. Branch Naming Convention

**Rule:** All branches must follow `feature/{ticket-id}-short-description` or `bugfix/{ticket-id}-short-description`. PR title must be `{ticket-id}-short-description`.

**Why:** The CI pipeline and ADO integration parse branch names to link work items. Non-conforming branches break traceability.

---

### 6. subprocess in Python is OK (ADO Wrapper)

**Rule (overrides Claire rule #2):** In the Five Points context, `subprocess` usage in Python is permitted for Azure DevOps CLI wrappers and automation scripts.

**Why:** Five Points automation wraps `az devops` CLI commands. The Python scripts are orchestration tools for ADO, not logic modules — the architecture boundary is different from Claire.

**Scope:** This override applies only to Five Points ADO automation scripts, not to general Python modules.

---

### 7. Flyway Migration Naming

**Rule:** Migration files follow the pattern `V{version}__{description}.sql` with double underscores and use `[schema].[table]` — no 3-part database names.

**Why:** 3-part names (`database.schema.table`) break in multi-database environments. Flyway requires the `V{n}__` prefix for ordering.

---

### 8. XML Docs on All Public Elements

**Rule:** All public classes, methods, and properties in `com.tfione.api` and `com.tfione.model` must have XML documentation comments.

**Why:** The build treats SA1516 warnings as errors. Missing XML docs will fail the build.

---

## How This Interacts with Core

| Core Rule | Five Points Override | Result |
|-----------|---------------------|--------|
| No silent exception swallowing | — (no override) | Core rule applies |
| No secrets in logs | — (no override) | Core rule applies |
| Tests before merge | Business logic tests excluded (rule #4) | FP rule applies |
| Documentation for features | — (no override) | Core rule applies |
| Errors include context | — (no override) | Core rule applies |

| Claire Rule | Five Points Override | Result |
|-------------|---------------------|--------|
| No subprocess in Python | subprocess OK for ADO wrappers (rule #6) | FP rule applies |

---

## See Also

- [Core DEV_RULES](../../core/knowledge/DEV_RULES.md) — universal baseline (inherited)
- [Five Points Code Review Persona](./CODE_REVIEW_PERSONA.md) — reviewer enforcement
- [Five Points Analyst Persona](./ANALYST_PERSONA.md) — pre-implementation analysis
