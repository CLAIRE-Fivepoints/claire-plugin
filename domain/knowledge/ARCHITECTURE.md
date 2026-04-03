---
keywords: [architecture, clean-architecture, dotnet, projects, layers, dependency-injection, multi-tenant, solution]
---

# TFI One — Architecture

**Solution**: `com.tfione.sln`
**Pattern**: Clean Architecture / N-Tier Layered
**Framework**: .NET 8.0 / ASP.NET Core 8.0

---

## 8-Project Structure

```
com.tfione.sln
├── com.tfione.api          # REST API (ASP.NET Core 8.0)
├── com.tfione.web          # Frontend SPA (React 19 + TypeScript + Vite)
├── com.tfione.service      # Business Logic Layer
├── com.tfione.repo         # Data Access Layer (Repository Pattern)
├── com.tfione.db           # EF Core Context + 179 ORM Entities
├── com.tfione.model        # DTOs, ViewModels, Enums, Constants
├── com.tfione.chron        # Background Jobs (Hangfire)
└── com.tfione.service.test # Unit Tests
```

---

## Dependency Flow

```
                    ┌──────────────┐
                    │  com.tfione  │
                    │     .web     │  React 19 + MUI + Redux
                    │   (SPA UI)   │
                    └──────┬───────┘
                           │ HTTP/REST
                    ┌──────▼───────┐
                    │  com.tfione  │
                    │     .api     │  Controllers, Middleware, Auth
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──────┐    │     ┌──────▼───────┐
       │  com.tfione  │    │     │  com.tfione  │
       │   .model     │    │     │    .chron    │
       │  (DTOs/VMs)  │    │     │  (Scheduler) │
       └──────────────┘    │     └──────┬───────┘
                           │            │
                    ┌──────▼───────┐    │
                    │  com.tfione  │    │
                    │   .service   │◄───┘
                    │ (Biz Logic)  │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  com.tfione  │
                    │    .repo     │  38 Repositories
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  com.tfione  │
                    │     .db      │  EF Core 8 + SQL Server
                    └──────────────┘
```

---

## Layer Responsibilities

### `com.tfione.api` — Presentation
- 20 REST controllers inheriting `BaseController`
- JWT Bearer authentication on all endpoints
- `[PermissionAuthorize]` for fine-grained RBAC
- FluentValidation filter on all POST/PUT/PATCH requests
- Swagger/OpenAPI at `/swagger`
- Global error handling middleware
- CORS, CSRF, Anti-Forgery token configuration

### `com.tfione.service` — Application / Business Logic
- Interface-based DI services
- Cross-cutting: encryption, caching, messaging, validation
- External integrations: Adobe Sign, Twilio, SendGrid, Azure Blob
- Audit trail generation (Azure Table Storage)
- Dynamic validation engine (database-driven rules)

### `com.tfione.repo` — Data Access
- 38 repositories inheriting `BaseRepo`
- Interface-based design (`IXxxRepo` / `XxxRepo`)
- LINQ-to-Entities — no raw SQL or Dapper
- Soft-delete filtering, multi-tenant scoping, row-level security

### `com.tfione.db` — Database
- `TfiOneContext` with 179+ DbSet properties
- EF Core interceptors: `AuditInterceptor`, `MetadataInterceptor`
- Flyway-based migration management (SQL files, not EF migrations)
- `DataProtectionKeyContext` for ASP.NET Data Protection keys

### `com.tfione.model` — Shared Models
- DTOs, ViewModels, Search Models, Edit Models
- Enums: PermissionCode, AuditAction, ErrorCode
- Constants: AuthorizationConstants, CustomClaimTypes
- Settings classes bound via `IOptions<T>`
- `BaseModel` and `BaseSearchModel` base classes

### `com.tfione.chron` — Background Jobs
- Hangfire 1.8.18 with SQL Server backend
- 20 worker threads
- Windows Service host via `IHostedService`
- Runs: `AssignProviderDocumentsJob`, `AssignClientDocumentsJob` (daily)

---

## DI Registration Pattern

```csharp
// Composition Root: Program.cs
builder.Services
    .AddDbServices(config)      // EF Core + SQL Server
    .AddRepoServices()          // 38 Repository registrations (Transient)
    .AddServiceServices(config) // Business services + externals
    .AddApiServices(config);    // Auth, validation, Swagger

// Lifetime convention:
// - Transient: Repos, Validators, Interceptors, most services
// - Scoped:    EncryptionProvider, StorageProvider
// - Singleton: Encryptors, JWT authenticators, CacheProvider
```

---

## Multi-Tenancy

- **Organization-based** isolation via `OrganizationId` FK on every entity
- `IOrganizationalReference` interface enforces tenant context
- User-Organization N:N via `AppUserOrganization`
- Organization switch via `POST /auth/change-organization/{orgId}`
- `DataPermission` table for row-level security (per-user access)
- JWT carries `current-org-id` and `orgs` claims

---

## Configuration

- `appsettings.json` / `appsettings.Development.json`
- Typed `IOptions<T>` pattern for all settings classes
- Azure Key Vault (production) — all secrets stored there
- Environment variable overrides (highest priority)
- `DockerBuild` environment uses in-memory database
