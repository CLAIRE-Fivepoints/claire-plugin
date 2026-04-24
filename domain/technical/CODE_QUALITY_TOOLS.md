---
keywords: [five-points, tfi-one, code-quality, devops, ci-cd, stylecop, eslint, flyway]
---

# TFI One - Code Quality & DevOps Tools

> Source: `azure/feature/10399-client-mgmt-education` branch (Azure DevOps)
> Generated: 2026-02-27

---

## Backend (.NET)

### StyleCop.Analyzers (v1.1.118)
- Installed in **all 6 .NET projects**
- Configuration: `stylecop.json` (linked in every project)
  - No XML header required
  - 4-space indentation, no tabs
  - System usings first, usings inside namespace
  - Newline at end of file
- Ruleset: `com.tfione.ruleset` — suppresses SA1010, SA1200, SA1208, SA1300, SA1623, SA1627, SA1629, SA1633
- Global suppressions: `GlobalSuppressions.cs` — SA1600/SA1601/SA1101 suppressed for `com.tfione.db.orm` namespace (EF-generated)

### Build Configurations & Warnings-as-Errors

| Config | Analyzers | Warnings as Errors |
|--------|-----------|-------------------|
| **Debug** | Run during build + live analysis | No |
| **Gate** | Run during build + live analysis | **Yes** — all warnings are build-breaking |
| **Release** | Run during build + live analysis | **Yes** — all warnings are build-breaking |

### Nullable Reference Types
- `<Nullable>enable</Nullable>` in every project
- Compiler-level null safety enforcement

### XML Documentation
- All projects generate XML documentation files
- Combined with StyleCop for public API documentation standards

### FluentValidation.AspNetCore (v11.3.0)
- Server-side model validation
- Data-driven rules from DB + hard-coded validators

---

## Frontend (React/TypeScript)

### ESLint (v9.32.0 — Flat Config)
- `@eslint/js` recommended + `typescript-eslint` recommended
- Plugins: `react-hooks` (v5.2.0), `react-refresh` (v0.4.20)
- Script: `npm run lint`

### TypeScript (v5.9.2 — Strict Mode)
- `"strict": true`
- `"noUnusedLocals": true`
- `"noUnusedParameters": true`
- `"noFallthroughCasesInSwitch": true`
- `"noUncheckedSideEffectImports": true`
- `"noUncheckedIndexedAccess": true`
- `tsc -b` runs before Vite build — type errors are build-breaking

### Vite (v7.0.6)
- `@vitejs/plugin-react-swc` — SWC for fast React transforms
- `@vitejs/plugin-basic-ssl` — Local HTTPS
- `@sentry/vite-plugin` — Source map upload to Sentry
- Source maps enabled in production build

---

## Testing

### Backend: xUnit (v2.5.3)
- Project: `com.tfione.service.test`
- Mocking: `Moq` (v4.20.70)
- Coverage: `coverlet.collector` (v6.0.0)
- Tests: SendGrid, Encryptor, Google Address, Twilio, Password, Adobe endpoints
- StyleCop + TreatWarningsAsErrors apply to test project too

### Frontend: None
- No test runner configured (no Jest, Vitest, Playwright, or Cypress)

---

## CI/CD (Azure Pipelines)

### Pipeline Overview

| Pipeline | Trigger | Config | Purpose |
|----------|---------|--------|---------|
| `azure_gated_build.yml` | PRs to `dev`/`master`, `feature/*`, `bugfix/*` | Gate | Quality gate for PRs |
| `azure_master_build.yml` | `master` | Release | QA deploy |
| `azure_master_build_conv.yml` | `master` | Release | Convergence deploy |
| `azure_release_build.yml` | `release/*` | Release | UAT deploy |
| `azure_master_merge.yml` | Cron (11 PM CT) | — | Auto-PR from dev → master |

### Gated Build Steps
1. Start SQL Server 2022 container
2. Install .NET 8 SDK
3. NuGet restore
4. **API build** (`dotnet publish` with `-WarnAsError` + Gate config)
5. **xUnit tests** (`dotnet test`)
6. **Empty Flyway migration** (from scratch)
7. **Incremental Flyway migration** (restore QA bacpac + migrate with `-outOfOrder`)
8. **Generate frontend types** (start API → Swagger → TypeScript auto-gen)
9. **Frontend build** (`tsc -b && vite build`)
10. Cleanup

### Quality Gates Enforced
- StyleCop + compiler warnings = build-breaking errors (Gate/Release)
- xUnit tests must pass
- TypeScript strict-mode compilation must succeed
- Vite production build must succeed
- Flyway migrations must apply cleanly (empty + incremental)

---

## Database Migration

### Flyway (Redgate) — Docker
- Migrations: `com.tfione.db/migration/` (170+ scripts)
- Naming: `V{major}.{minor}.{date}.{workitem}.{sequence}__{description}.sql`
- Out-of-order: Enabled (`-outOfOrder="true"`)
- Environment configs: `com.tfione.db/container/{env}.yml` (dev, local, qa, conv, uat, prd)
- CI validation: Both empty-DB and incremental-migration tests
- Checksums stored in `flyway_schema_history` table

### Frontend Environment Variables

`VITE_TOKEN_EXPIRY_WARNING_SECONDS` in `.env.local` — configures token expiry warning timing.

---

## Error Monitoring & Observability

### Sentry
- **Backend**: `Sentry.Serilog` (v5.10.0)
- **Frontend**: `@sentry/react` (v10.1.0) + `@sentry/vite-plugin` (v4.0.2)
- Org: `five-points-technology-group`
- Source maps uploaded during build

### Serilog (Structured Logging)
- `Serilog` v4.2.0 + `Serilog.AspNetCore` v9.0.0
- Sinks: Azure Table Storage
- Enrichers: Environment

---

## Infrastructure

| Component | Technology |
|-----------|-----------|
| Source Control | Azure DevOps Git |
| CI/CD | Azure Pipelines (YAML) |
| Cloud | Azure (Storage, Key Vault, SQL) |
| Web Server | IIS (Windows Server) |
| Database | SQL Server (Azure SQL) |
| Secrets | Azure DevOps variable groups + Azure Key Vault |
| Notifications | Microsoft Teams webhooks |
| Blob Storage | Azure Blob Storage (bacpacs, documents) |

---

## Not Present (Gaps)

| Category | Missing |
|----------|---------|
| Backend | No `.editorconfig`, no `Directory.Build.props`, no SonarQube |
| Frontend | No Prettier, no Stylelint, no Husky / lint-staged, no commitlint (see note ¹) |
| Frontend Testing | No Jest, Vitest, Playwright, or Cypress |
| Security | No OWASP dependency scanning, no SAST (beyond StyleCop) |
| Code Coverage | `coverlet` present but no thresholds or CI reporting |
| API Contracts | No OpenAPI linting (Spectral, etc.) |
| CI lint gate | `azure_gated_build.yml` does **not** run `npm run lint` (see note ¹) |

¹ **ESLint is enforced client-side via plugin hooks, not Husky.** Issue #119
decided against adding Husky / lint-staged or an `npm run lint` step to
`azure_gated_build.yml`, because both options require committing to
ADO-tracked files in TFIOneGit. Instead, the plugin ships:

- A `pre-commit` Check 6 that runs ESLint on every staged
  `com.tfione.web/**/*.{ts,tsx}`, installed via `claire fivepoints install-hooks`.
- A `pre-push` Check 3 that runs `npm run lint` when pushed commits touch
  the web package.

Both hooks live in the plugin (`domain/hooks/pre-commit`, `pre-push`) and
reach a dev's clone via the installer — no ADO-origin change. Residual-risk
and rationale: `claire domain read fivepoints operational GIT_HOOKS`
→ **Residual risk** and **Why plain hooks and not Husky / lint-staged**.

---

## Complete Tool Inventory

| Tool | Version | Scope |
|------|---------|-------|
| StyleCop.Analyzers | 1.1.118 | All .NET projects |
| C# Nullable Reference Types | (compiler) | All .NET projects |
| FluentValidation | 11.3.0 | Backend validation |
| ESLint | 9.32.0 | Frontend TS/TSX |
| typescript-eslint | 8.39.0 | Frontend TS/TSX |
| eslint-plugin-react-hooks | 5.2.0 | Frontend React |
| TypeScript (strict) | 5.9.2 | Frontend |
| Vite | 7.0.6 | Frontend build |
| xUnit | 2.5.3 | Backend tests |
| Moq | 4.20.70 | Backend mocking |
| Coverlet | 6.0.0 | Backend coverage |
| Flyway | latest (Docker) | DB migrations |
| Sentry | 10.1.0 / 5.10.0 | Error monitoring |
| Serilog | 4.2.0 | Structured logging |
| Swashbuckle | 7.2.0 | API documentation |
| Azure Pipelines | YAML | CI/CD |
