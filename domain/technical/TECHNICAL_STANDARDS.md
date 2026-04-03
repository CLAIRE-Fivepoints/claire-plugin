---
keywords: [five-points, tfi-one, technical-standards, constraints, infrastructure, security, vite, swc, typescript, react-router, azure-key-vault, blob-storage, table-storage]
---

# TFI One - Technical Standards & Constraints

**Source**: `TFI One Technical Design Document 20250709.docx`
**Date**: 2026-02-27

---

## Key Technical Differences (vs. Generic Assumptions)

These items are **specific to TFI One** and override general assumptions:

| # | Standard | Detail |
|---|----------|--------|
| 1 | **EF Core: Database First** | Schemas designed in SQL first, then scaffolded. NO code-first migrations. |
| 2 | **FluentValidation from DB** | Rules stored in database, fetched dynamically by frontend. Matched by type name. Org-scoped. |
| 3 | **Hangfire: Separate App** | Runs as standalone console application, NOT embedded in API. Dedicated SQL database. |
| 4 | **Couchbase (not Redis)** | Caching layer. Cluster in app subnet. Handles JWT refresh, validation rules, UI config. |
| 5 | **TFVC (not Git)** | Team Foundation Version Control via Azure DevOps. Centralized model. |
| 6 | **Dual Authentication** | Entra ID SSO (internal TFI) + local username/password (external). Both require MFA. |
| 7 | **Password: HMAC SHA512** | Not bcrypt/Argon2. 16-char min, 180-day max age, no reuse of last 13. |
| 8 | **IIS Hosting** | .NET app hosted on IIS (not Kestrel-only or containerized). |
| 9 | **Dual Logging Sinks** | Serilog → Azure Table Storage + Sentry.io simultaneously. Table naming: `Serilog{Env}{Year}`. |
| 10 | **SurveyJS** | Used for dynamic form digitization (assessments, checklists, notes). |
| 11 | **.NET 10 migration** | Skip .NET 9, move directly to .NET 10 when released. |
| 12 | **SOC 2 Type 2 + TX-RAMP** | Compliance requirements drive all security decisions. |
| 13 | **Immutable Audit Data** | CDC captured at ORM level → Azure Table Storage. Cannot be modified after logging. |
| 14 | **AES-256 at rest** | All Azure-managed data repositories. TLS with SHA-256+RSA in transit. |
| 15 | **API Methods: 2-3 Lines** | Controller methods: receive request → delegate to injected repo → return result. |
| 16 | **Primary: East US 2** | DR region: Central US. Azure Site Recovery for VM replication. |
| 17 | **Vite + SWC** | Vite as build tool, SWC (Rust) as compiler. No webpack, no Babel. |
| 18 | **TypeScript strict mode** | `"strict": true` in tsconfig. No implicit `any`. |
| 19 | **React Router** | Client-side routing. Declarative `<Routes>`, `useNavigate()` for programmatic nav. |
| 20 | **Azure Key Vault** | All secrets in Key Vault. `appsettings.json` = non-sensitive config only. |
| 21 | **Blob Storage** | Unstructured data (documents, files). Separate from Table Storage (audit logs). |

---

## Authentication & Authorization

### Dual Auth Flow
```
Internal TFI Users → Microsoft Entra ID (SSO) → MFA enforced by Entra
External Users → Local username/password → Local MFA (email/SMS/Authenticator)
```

### Password Policy (Local Auth)
- Min 16 characters
- Min 1 uppercase, 1 digit
- Username not in password
- Digit cannot be last character
- No 3 consecutive identical characters
- No reuse of last 13 passwords
- Max age: 180 days
- Lockout after 5 failed attempts
- Expiry notification: 3 days before

### JWT Authorization
- Short-lived tokens (configurable, e.g. 30 minutes)
- JWT refresh managed through Couchbase cache
- Claims contain user permissions for `[PermissionAuthorize]` checks
- Auth attempts logged: username, timestamp, result, IP address

---

## API Design Standards

```csharp
// CORRECT: 2-3 lines, delegate to injected repo
[HttpGet]
[PermissionAuthorize(PermissionCode.ClientView)]
public async Task<ActionResult<List<ClientListModel>>> Search([FromQuery] ClientSearchModel model)
    => Ok(await _repo.Search(model));

// WRONG: Business logic in controller
[HttpGet]
public async Task<ActionResult<List<ClientListModel>>> Search([FromQuery] ClientSearchModel model)
{
    var clients = await _context.Clients.Where(...).ToListAsync(); // NO
    // ... processing logic ... // NO
}
```

### Conventions
- Route: lowercase plural noun `[Route("clients")]`
- All endpoints: JWT Bearer auth (except `[AllowAnonymous]`)
- Permission: `[PermissionAuthorize(PermissionCode.XxxYyy)]`
- Return: `ActionResult<T>`
- HTTPS enforced, CSRF/XSRF protection, CORS configured

---

## Database Patterns

### Database First Workflow
```
1. Design schema in SQL Server → write Flyway migration
2. Apply migration to database
3. Scaffold ORM entities from database
4. Map entities to DTOs in repository layer
```

> **Critical:** Files in `com.tfione.db/orm/` MUST be generated via `dotnet ef dbcontext scaffold`, never hand-written.
> Hand-coding ORM entities risks mismatches with the actual DB schema and breaks other developers' builds.
> Exception: `com.tfione.db/partial/TfiOneContext.cs` (adding `DbSet` properties and partial class extensions) is hand-coded.

### Migration Naming
```
V1.0.YYYYMMDD.TICKET.N__description.sql
```

### Environments
| Environment | Database |
|-------------|----------|
| Development | Local SQL Server Developer Edition |
| QA | Azure SQL Database |
| UAT | Azure SQL Database |
| Production | Azure SQL Database (with geo-replication) |

### Data Audit (CDC)
- Captured at ORM level via `AuditInterceptor`
- Stored in Azure Table Storage (immutable)
- Partition schemes: by date, by user
- Forensic-level tracking

---

## Frontend Patterns

### Build Toolchain
```
Vite (build tool — fast, lean, HMR)
├── SWC compiler (Rust-based, replaces Babel — faster transforms)
├── TypeScript 5.x (strict mode enabled)
└── Output: optimized ES modules for production
```

- **Vite**: replaces webpack/CRA; native ESM, instant HMR
- **SWC**: Rust-based transpiler; used instead of Babel for speed
- **TypeScript strict mode**: `"strict": true` in tsconfig — no implicit `any`, no loose null checks
- No Babel config files should exist in the project

### Routing
- **React Router** for all client-side navigation
- Declarative route definitions (JSX-based `<Routes>`)
- Dynamic route params for record-specific pages (e.g., `/clients/:id`)
- Navigation handled programmatically via `useNavigate()` hook

### State Management
```
Redux Toolkit
├── Redux Thunk (async logic/side effects)
└── RTK Query (data fetching, caching, API integration)
```

### Form Validation (Frontend-Backend)
```
DB (ValidationRule table)
  → Backend (FluentValidation, DynamicValidator<T>)
    → Frontend (fetches rules, applies by type name)
      → If validation fails → controller never hit → errors to client
```

### Component Library: MUI
- Pre-built accessible components
- MUI X Data Grid Pro for all data grids
- MUI X Date Pickers Pro for dates
- Consistent theming

---

## Infrastructure

### Caching (Couchbase)
```
Couchbase Cluster (3-node, app subnet)
├── JWT token refresh management
├── Validation business rules cache
├── UI configuration parameters
└── Reference data cache
```
- Sub-millisecond latency
- JSON document model
- Horizontal scaling
- Automatic data replication

### Background Jobs (Hangfire)
```
Standalone Console Application (separate from API)
├── Dedicated SQL Server database
├── 20 worker threads
├── Dashboard UI for monitoring
└── Job types: Recurring, Fire-and-forget, Delayed, Continuation
```

### Configuration Management (Azure Key Vault)
- **All secrets stored in Azure Key Vault** — never in `appsettings.json` or source control
- Secrets: connection strings, API keys, encryption keys, client secrets
- JSON config files per functional component (e.g., `hangfire.json`, `couchbase.json`) loaded at app startup
- Config files reference Key Vault references via managed identity — no secrets in plain text
- **Rule**: if it's a secret, it goes to Key Vault. `appsettings.json` = non-sensitive config only.

### Azure Storage

#### Blob Storage
- **Purpose**: unstructured data — documents, uploaded files, binary assets
- Organized by container per data type (e.g., `client-documents`, `assessments`)
- Access via Azure SDK; never direct HTTP unless SAS token issued

#### Table Storage
- **Purpose**: audit logs and immutable records (CDC output)
- Table naming convention: `Serilog{Env}{Year}` (e.g., `SerilogProduction2025`)
- Records are written once, never updated or deleted
- Partition key: date or user for forensic query patterns

### Backup & Recovery
| Resource | Frequency | Retention |
|----------|-----------|-----------|
| VM (production) | Every 4 hours | 14 days (7-day instant restore) |
| DB Full | Weekly | Per policy |
| DB Differential | Every 12-24 hours | Per policy |
| DB Transaction Log | ~Every 10 minutes | Per policy |

### Disaster Recovery
- Primary: **Eastern US 2**
- Secondary: **Central US**
- Azure Site Recovery for VMs
- Azure SQL geo-replication
- Tested annually

---

## Security Stack

| Layer | Technology |
|-------|-----------|
| Compliance | SOC 2 Type 2 + TX-RAMP |
| Transit Encryption | TLS (SHA-256 with RSA) |
| At-Rest Encryption | AES-256 |
| Vulnerability Scan | Qualys Threat Protection + WAS |
| Antivirus | Sophos Endpoint Protection |
| Monitoring | Pulseway + Netwrix |
| Firewall | Azure Premium Firewall |
| Network | Hub-and-spoke, VNet Peering, NSGs |
| Logging | Serilog → Azure Table Storage + Sentry.io |
| PII Protection | Sentry.io HIPAA-compliant PII scrubbing |

---

## CI/CD Pipeline

```
TFVC (Azure DevOps)
  → Pull Request (peer review, inline comments)
    → CI Pipeline (auto-trigger on check-in/PR merge)
      → Build + StyleCop + Unit Tests + Static Analysis
        → CD Pipeline (deployment gates + approvals)
          → Security scanning + vulnerability assessment
            → Deploy (front-end + back-end + DB schema)
```

### Deployment Targets
```
CI: auto-triggered on check-in or PR merge
  → Build + StyleCop + Unit Tests + Static Analysis
CD: automated deployment with approval gates
  → QA (automatic after CI pass)
  → UAT (manual approval gate)
  → Production (manual approval gate)
```
- Infrastructure-as-code for repeatable provisioning
- Three change categories: frontend, backend, database schema
- Each deployment includes: security scanning + vulnerability assessment
