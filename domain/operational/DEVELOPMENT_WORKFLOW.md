---
keywords: [workflow, git, branching, cicd, azure-devops, docker, testing, hangfire, stylecop]
---

# TFI One — Development Workflow

---

## Git Branching Strategy

```
master ─── Production
  ├── release/* ─── Release preparation
  ├── hotfix/* ─── Emergency production fixes
  └── dev ─── Integration branch
       ├── feature/[PBI#]-description ─── New features
       └── bugfix/[PBI#]-description ─── Bug fixes
```

**Key Rules**:
- **Always merge, never rebase**
- No force push to any branch
- Feature naming: `feature/[PBINumber]-short-description`
- Daily: pull dev, merge dev into feature, commit frequently
- End of day: push to remote
- Completion: Create PR → review → merge to dev

### Use the Branch Created For You

Azure DevOps creates a branch for each PBI/work item. Always start from that branch — never create your own from `dev` or `master`.

- Branch naming convention: `feature/{PBI-number}-{description}`
- The branch is pre-linked to the work item for traceability
- If you need sub-branches, branch off the PBI branch (not `dev`)

### No Cross-Branch Dev Merges

Parent-child branch hierarchy must be respected. Never merge `dev` directly into a child branch.

```
dev
 └── feature/1234-parent       ← merge dev here first
      └── feature/1234-child   ← then merge parent into child
```

**Correct flow** to get `dev` changes into a child branch:
1. Merge `dev` into the parent branch
2. Merge the parent branch into the child branch

**Never do**: Merge `dev` directly into a child branch. This bypasses the parent and creates merge conflicts and untraceable history.

---

## Daily Development Flow

```
1. Pull latest dev
2. Merge dev into your feature branch
3. Make changes + commit frequently
4. Push to remote at end of day
5. When complete: Run the [Pre-PR Checklist (Steven's Rules)](ADDING_FEATURES.md#pre-pr-checklist-stevens-rules)
6. Create PR to dev
7. Code review → Approval → Merge
```

---

## Build Configurations

| Config | Use | Settings |
|--------|-----|---------|
| Debug | Local development | SuperUser bypass, memory cache, console logging |
| Gate | Pre-production testing | Staging DB, Azure services |
| Release | Production | Azure Key Vault secrets, Couchbase cache |
| DockerBuild | CI/CD container | In-memory DB, no CORS, minimal config |

---

## CI/CD Pipeline (Azure DevOps)

**Repository**: https://dev.azure.com/fivepointstechnology

### Build Steps
1. Restore NuGet packages
2. Build solution (Release configuration)
3. Run unit tests (`com.tfione.service.test`)
4. Publish API artifact
5. Build Docker image (Windows Server Core)
6. Push to container registry

### Docker Image

```dockerfile
FROM mcr.microsoft.com/dotnet/aspnet:8.0-windowsservercore-ltsc2022
EXPOSE 8080
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "com.tfione.api.dll"]
```

**Windows Server Core** — not Linux. Required for Windows-specific dependencies.

---

## Unit Test Policy

- Code **must be structured for testability**: use dependency injection, interfaces, and separation of concerns
- Do **NOT** commit unit test files to the repository
- E2E tests (Playwright) are separate and live in the `tfione-e2e` repo
- The existing `com.tfione.service.test` project contains integration/utility tests only (see below)

> Source: reviewer feedback, Rule #9 — "Make everything unit testable but do not write (or at least don't check in) unit tests."

---

## Unit Tests (`com.tfione.service.test`)

**Framework**: xUnit 2.5.3
**Mocking**: Moq 4.20.70

```csharp
public class TestBase
{
    protected IServiceProvider ServiceProvider { get; }

    public TestBase()
    {
        var services = new ServiceCollection();
        services.AddModelDependencies(config);
        ServiceProvider = services.BuildServiceProvider();
    }
}
```

### Current Test Coverage

| Area | Coverage |
|------|----------|
| Encryption (Encryptor) | Good — 12 tests |
| Password Generation | Basic — 2 tests |
| SendGrid, Twilio, Google, Adobe | Integration tests |
| Repositories | **None** |
| Controllers | **None** |
| Middleware / Authorization | **None** |

**Coverage gap**: Only service-layer utilities are tested. Repository, controller, and authorization code has no tests.

---

## Coding Standards

### Required Field Asterisk

All required form fields MUST use the `required` prop to display an asterisk (`*`) next to the label. MUI automatically renders the asterisk via the `Mui-required` CSS class on `FormLabel`.

```tsx
// Required field — shows asterisk
<TfioTextInput
    name='schoolName'
    required={true}
    labelToken='enrollment.schoolName'
    labelDefault='School Name'
/>

// Optional field — no asterisk
<TfioTextInput
    name='isd'
    required={false}
    labelToken='enrollment.isd'
    labelDefault='ISD'
/>
```

**Frontend ↔ Backend alignment**: The `required` prop MUST match the server-side FluentValidation rule:
- Backend has `RuleFor(x => x.Field).NotEmpty()` → frontend `required={true}`
- Backend has no required rule → frontend `required={false}`

This ensures visual consistency, accessibility compliance, and frontend-backend validation alignment.

---

## Code Style (StyleCop)

**Indentation**: 4 spaces (no tabs)
**Company**: FivePoints Technology Group

### Disabled Rules
| Rule | Why Disabled |
|------|-------------|
| SA1200 | Using directives inside namespace (allowed) |
| SA1633 | No file header copyright required |
| SA1300 | Elements don't need to start with uppercase |
| SA1623 | Properties don't need uppercase description |

### Global Suppressions
- Documentation not required for EF-generated entities (`com.tfione.db.orm`) — SA1600 suppressed
- `this.` prefix not required in ORM namespace — SA1101 suppressed
- **SA1516 is NOT suppressed for ORM entities** — blank line required between every property, even in manually-created ORM entities

---

## Database Migrations (Flyway)

**Tool**: Flyway (not EF Core migrations)
**Location**: `com.tfione.db/migration/`

### Naming Convention
```
V{Major}.{Minor}.{Date}.{Seq}.{SubSeq}__{description}.sql
```

**Example**: `V1.0.20240115.001.001__add_provider_status_column.sql`

### Flyway Commands
```bash
# Apply pending migrations
flyway migrate

# Check status
flyway info

# Validate migration checksums
flyway validate
```

Applied migrations tracked in `FlywaySchemaHistory` table.

---

## Background Jobs (Hangfire)

Jobs run via `com.tfione.chron` (Windows Service):

| Job | Schedule | Purpose |
|-----|----------|---------|
| `AssignProviderDocumentsJob` | Daily at configurable hour | Auto-assign document requirements to providers |
| `AssignClientDocumentsJob` | Daily at configurable hour | Auto-assign document requirements to clients |

Configuration:
```json
{
  "AssignDocumentsFromDefinitionScheduleOptions": {
    "Enabled": true,
    "JobStartHour": 2,
    "JobStartMinute": 0
  }
}
```

---

## Validation

See [Validation Patterns](../technical/VALIDATION_PATTERNS.md) for the complete reference on:
- Frontend/backend rule parity (FluentValidation ↔ fluentvalidation-ts)
- Data-driven rules from `conf.ValidationRule` table
- Cross-field validation (date ranges, conditional required, unique constraints)
- Content token naming conventions
- Input masks and required field indicators

---

## Local Development Setup

### Backend
1. Install .NET 8.0 SDK
2. Set up SQL Server (local or Docker)
3. Run Flyway migrations
4. Configure `appsettings.Development.json` with local connection string
5. Run `com.tfione.api`

### Frontend
1. Install Node.js
2. `npm install` in `com.tfione.web/`
3. Create `.env.local` with `VITE_API_URL`, `VITE_MUI_LICENSE_KEY`, etc.
4. `npm run dev`

### Environment Variables (Frontend)
```
VITE_API_URL=https://localhost:58337
VITE_SSO_CLIENT_ID=<azure-ad-client-id>
VITE_SSO_REDIRECT_URL=https://localhost:5173
VITE_ENV_NAME=local
VITE_MUI_LICENSE_KEY=<mui-pro-key>
VITE_RECAPTCHA_SITE_KEY_V3=<key>
VITE_RECAPTCHA_SITE_KEY_V2=<key>
```
