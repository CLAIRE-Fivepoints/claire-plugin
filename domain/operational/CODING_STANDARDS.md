---
keywords: [five-points, coding-standards, conventions, review, tfi-one]
---

# Five Points – Coding Standards

> These rules apply to **all** Fivepoints / TFI One development.
> For detailed code patterns and templates, see `technical/CODE_PATTERNS.md`.
> For implementation-level design patterns (Repository, DTO, Auth, SQL migrations, Frontend), see `fivepoints/technical/PATTERNS.md`.

---

## Code Review Rules (Azure DevOps PR #228)

### 1. Branch Discipline

Use the branch created for you. Do not branch off a branch you made, and do not merge `dev` into a child branch without going through the parent branch.

```
dev → feature/PBI# (parent) → feature/PBI#-sub (child)
```

- Child branches merge back into their parent, never directly into `dev`.
- If you need updates from `dev`, merge `dev` into the **parent** first, then merge parent into child.
- Always use merge, never rebase.

**Branch naming convention:**

| Type | Format |
|------|--------|
| Feature | `feature/{ticket-id}-short-description` |
| Bug | `bugfix/{ticket-id}-short-description` |

Examples: `feature/10856-client-export`, `bugfix/10901-fix-null-reference`

**PR title convention:** `{ticket-id}-short-description`

Example: `10856-client-export`

### 2. Explicit Constraint Names

Every constraint in every DDL statement needs an explicit name — foreign keys, primary keys, indexes, unique constraints, defaults, etc.

FK naming convention: `FK_{ChildTable}_{ParentTable}`

```sql
-- Good
ALTER TABLE [client].[ClientEducation]
    ADD CONSTRAINT [FK_ClientEducation_Client]
    FOREIGN KEY ([ClientId]) REFERENCES [client].[Client]([ClientId]);

-- Bad (implicit name)
ALTER TABLE [client].[ClientEducation]
    ADD FOREIGN KEY ([ClientId]) REFERENCES [client].[Client]([ClientId]);
```

### 3. Permission Error Handling

Repositories must communicate permission errors back to the client via `model.Messages` — never throw exceptions for business/permission errors.

```csharp
// Pattern: access-denied via model message
if (!hasAccess)
{
    model.Messages.Add(new ModelMessageModel("access-denied",
        content.GetContent("access-denied", "You do not have permission")));
    return model;
}
```

### 4. Dual Validation

All validations must exist on **both** the client and the server. Never rely on client-side validation alone; never skip client-side validation because the server validates.

- **Server**: FluentValidation with `BaseValidator<T>` (rules can be data-driven from DB)
- **Client**: `fluentValidationResolver` fetches rules from API, React Hook Form enforces them

### 5. Content Hook for All Strings

All string literals must run through the content hook, on both server and client side. No hardcoded user-facing strings.

```tsx
// Frontend — Good
content("education.title", "Education")
<TfioTextInput labelToken="education.schoolName" labelDefault="School Name" />

// Frontend — Bad
<h2>Education</h2>
<TextField label="School Name" />
```

```csharp
// Backend — Good
content.GetContent("access-denied", "You do not have permission")
```

### 6. Use Wrapped Components

Always use the TFI One wrapped components where they exist. Do not use raw HTML elements or MUI base components when a wrapper is available.

| Wrapper | Replaces |
|---------|----------|
| `TfioTextInput` | `TextField` |
| `TfioDateInput` | `DatePicker` |
| `TfioSelectInput` | `Select` |
| `TfioCheckboxInput` | `Checkbox` |
| `TfioButton` | `Button` |
| `TfioDataGrid` | `DataGrid` |
| `TfioDialog` | `Dialog` |

All Tfio* inputs accept `labelToken` / `labelDefault` props for content hook integration.

### 7. One Class / Component per File

No file should contain more than one class or component. Each class, React component, or interface gets its own file.

### 8. Unit Tests

**Do not create tests for business logic.** Tests for TFI One application domain (clients, providers, organizations, FDS sections) are not part of the workflow.

> **Source:** Steven Franklin

**What belongs in `com.tfione.service.test`:**
- Infrastructure service tests — stateless utilities (encryption, password generation, URL builders)
- External API adapter tests — verify third-party integrations (email, SMS, address validation, signing)

**Examples from `main`:**
```
encryption/EncryptorTests            — Encryptor service (pure, no DB)
password/PasswordGeneratorTests      — PasswordGenerator (pure, no DB)
signing/AdobeEndpointGeneratorTests  — Adobe URL builder (pure, no DB)
mapping/GoogleAddressValidationTests — Google Maps API adapter (external API)
email/SendGridTests                  — SendGrid adapter (external API)
messaging/TwilioTests                — Twilio adapter (external API)
```

**What does NOT belong in `com.tfione.service.test`:**
- Business logic tests — any test for TFI One domain behavior (clients, providers, FDS, organizations)
- Tests that mock the database layer for domain validation

### 9. SQL Migrations: No 3-Part Database Name

Flyway migrations must **never** use the 3-part `[database].[schema].[table]` syntax. Flyway connects to the correct database via the connection string — hardcoding the database name will cause the migration to fail on any environment where the database has a different name (CI, staging, prod).

```sql
-- Bad: SSMS auto-generates this — never copy into a migration
ALTER TABLE [tfi_one].[file].[FileMetaData]
    ALTER COLUMN [MimeType] nvarchar(255) not null

-- Good
ALTER TABLE [file].[FileMetaData]
    ALTER COLUMN [MimeType] nvarchar(255) not null
```

> Root cause: SSMS "Script Table As" generates 3-part names automatically. Always strip the database prefix before adding SQL to a migration file.

### 10. SQL Migrations: No Role Permissions

**Do not create role permissions in migrations.** Roles are managed via the UI by users — not via SQL migrations.

❌ Never add `GRANT`, `DENY`, or role assignment SQL to a migration file.
✅ Role setup is handled manually by users through the application UI.

### 11. Source Control — Excluded Files

**`com.tfione.api.d.ts` must never be committed to source control.**

This file is generated and is part of `.gitignore`. If it appears in your `git status`, do not stage or commit it.

```bash
# If accidentally staged:
git restore --staged com.tfione.api.d.ts
```

> If this file is already tracked in git history, it must be removed with `git rm --cached`.

### 12. PermissionCode Enum Values Must Be Wired in the Same PR

Every new value added to `com.tfione.model/enumeration/auth/PermissionCode.cs` must ship in the same PR with at least one `[PermissionAuthorize(PermissionCode.<NewValue>)]` usage in `com.tfione.api/`.

**An orphan enum value** (added to the enum with no corresponding controller authorization) causes two distinct failure modes:

1. **CS0102 duplicate definition errors** — If a parallel feature branch later adds the same enum value to implement the actual feature, both branches define the same identifier in `PermissionCode`. The cherry-pick or merge breaks the build immediately at Gate 1.
2. **Silently broken authorization** — An admin can toggle the permission in the UI, but no route honors it. The permission exists in name only.

**Rule:** A PR that adds enum values to `PermissionCode` without any `[PermissionAuthorize]` usage in `com.tfione.api/` must not be merged.

> **Source:** fivepoints-test#146 — `dev` branch contained `AccessClientAdoptionPlacements`, `ViewClientAdoptionPlacement`, `ManageClientAdoptionPlacement` as orphans, causing CS0102 build failures when the FDS 16.9 implementation was cherry-picked.

---

## Build & Quality Standards

### StyleCop (Backend)

Gate build treats ALL warnings as errors. Key rules:

| Rule | Scope | Description |
|------|-------|-------------|
| SA1516 | All namespaces (including `com.tfione.db.orm`) | Blank line between every element |
| SA1600 | `com.tfione.model`, `com.tfione.api` | XML doc on every public element |
| SA1101 | Most namespaces | `this.` prefix required |

**Suppressions** (in `com.tfione.db/GlobalSuppressions.cs`):
- SA1600 suppressed for `com.tfione.db.orm` — no XML docs on ORM entities
- SA1101 suppressed for `com.tfione.db.orm` — no `this.` prefix in ORM entities
- SA1516 is **NOT** suppressed anywhere — blank lines required everywhere

### TypeScript Strict Mode (Frontend)

- `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`, `noUncheckedIndexedAccess`
- ESLint v9 (flat config)
- Vite production build must compile clean

### TypeScript Equality

Always use **strict equality** (`===`, `!==`). Never use loose equality (`==`, `!=`).

```typescript
// CORRECT
if (value === null) { ... }
if (status !== 'active') { ... }

// WRONG — type coercion, implicit conversions
if (value == null) { ... }
if (status != 'active') { ... }
```

TypeScript's strict mode does not enforce this automatically — it must be followed manually. ESLint rule `eqeqeq` enforces this.

### CI Gate Build

10-step quality gate (all must pass):
1. StyleCop analysis (warnings = errors)
2. .NET build
3. xUnit tests
4. Flyway migration — empty DB
5. Flyway migration — incremental from QA bacpac
6. TypeScript strict compile
7. Vite production build
8. ESLint
9. Bundle size check
10. Deployment validation

---

## Database Standards

### Flyway Migration Naming

```
V{major}.{minor}.{YYYYMMDD}.{ticket}.{seq}__{description}.sql
```

Example: `V1.0.20260227.14.1__client_education_tables.sql`

**Schema prefixes**: `[ref]`, `[client]`, `[provider]`, `[sec]`, `[org]`

**CRITICAL**: Never modify an already-applied migration. Flyway stores CRC32 checksums in `flyway_schema_history`; changing a file breaks CI with:
```
Validate failed: Migrations have failed validation
Migration checksum mismatch for V1.0.XXXXXXXX.XXXX.X__description.sql
```
Create a **new** migration with corrective SQL instead.

### Local Verification

Before pushing, verify migrations haven't been accidentally modified:
```bash
claire flyway verify              # compare against origin/dev
claire flyway verify --base main  # compare against main
```

### No 3-Part Database Name in Migrations

See **Code Review Rule #9** above. Never use `[database].[schema].[table]` — use `[schema].[table]` only.

### Boolean Fields

Always use `bool`, never `bool?`. Booleans represent Yes/No, not Yes/No/Unknown.

### 7 Audit Fields on Every Table

`Deleted`, `CreatedDate`, `CreatedBy`, `UpdatedDate`, `UpdatedBy`, `DeletedDate`, `DeletedBy`

### Soft Delete Only

Never physically delete records. Set `Deleted = true`. The `MetadataInterceptor` auto-stamps audit fields.

---

## Further Reference

Detailed code templates and architecture patterns in this domain:
- `technical/PATTERNS.md` — Architecture overview and naming conventions
- `technical/TECHNICAL_STANDARDS.md` — 16 technical standards from the Technical Design Document
- `technical/ARCHITECTURE_PATTERNS.md` — 11-layer request flow with full code templates
- `technical/CODE_QUALITY_TOOLS.md` — CI/CD pipeline and quality tooling inventory
- `technical/CODE_PATTERNS.md` — Definitive code pattern reference (16 sections)
