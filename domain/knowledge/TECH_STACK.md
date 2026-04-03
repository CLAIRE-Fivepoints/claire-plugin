---
keywords: [tech-stack, dotnet, react, typescript, vite, mui, redux, sql-server, azure, couchbase, hangfire, efcore]
---

# TFI One — Technology Stack

---

## Backend

| Category | Technology | Version |
|----------|-----------|---------|
| **Runtime** | .NET | 8.0 (LTS) |
| **Web Framework** | ASP.NET Core | 8.0 |
| **ORM** | Entity Framework Core | 8.0 |
| **Database** | SQL Server | latest |
| **Background Jobs** | Hangfire | 1.8.18 |
| **Validation** | FluentValidation | 11.3.0 |
| **Logging** | Serilog | 4.2.0 |
| **Error Tracking** | Sentry | 5.10.0 |
| **PDF Generation** | iText7 | 9.3.0 |
| **API Docs** | Swashbuckle (Swagger) | 7.2.0 |
| **JWT Auth** | Microsoft.AspNetCore.Authentication.JwtBearer | 8.0.13 |
| **MFA/TOTP** | Otp.NET | 1.4.0 |
| **Code Quality** | StyleCop.Analyzers | 1.1.118 |

---

## Frontend

| Category | Technology | Version |
|----------|-----------|---------|
| **UI Framework** | React | 19.1.1 |
| **Language** | TypeScript | ~5.9.2 |
| **Build Tool** | Vite (SWC) | 7.0.6 |
| **Routing** | React Router | 7.7.1 |
| **UI Library** | Material UI (MUI) | 7.3.1 |
| **Data Grid** | MUI X Data Grid Pro | 8.9.2 |
| **Date Pickers** | MUI X Date Pickers Pro | 8.10.1 |
| **State Management** | Redux Toolkit | 2.8.2 |
| **Data Fetching** | RTK Query (bundled with Redux Toolkit) | 2.8.2 |
| **Forms** | React Hook Form | 7.62.0 |
| **HTTP Client** | Axios | 1.11.0 |
| **Surveys** | Survey.js | 2.3.5 |
| **File Upload** | React Dropzone | 14.3.8 |
| **Auth (Azure AD)** | MSAL React | 3.0.17 |
| **Analytics** | Power BI (embedded) | |

---

## Cloud / Infrastructure

| Category | Technology | Purpose |
|----------|-----------|---------|
| **File Storage** | Azure Blob Storage | Document uploads/downloads |
| **Logging Store** | Azure Table Storage | Audit trails, structured logs |
| **Secret Management** | Azure Key Vault | Production secrets |
| **Distributed Cache** | Couchbase (3-node cluster) | Session/reference data cache |
| **Dev Cache** | In-Memory | Local development caching |
| **Container** | Docker (Windows Server Core 2022) | `mcr.microsoft.com/dotnet/aspnet:8.0-windowsservercore-ltsc2022` |

---

## Third-Party Integrations

| Service | Purpose | SDK/Version |
|---------|---------|-------------|
| **Adobe Sign** | E-signature workflows | REST API v6 |
| **Twilio** | SMS notifications (OTP, alerts) | 7.8.5 |
| **SendGrid** | Email delivery | 9.29.3 |
| **Google Maps** | Address validation | Maps API v1 |
| **Google reCAPTCHA** | Bot protection on login | v2 + v3 (threshold 0.5) |

---

## Security Stack

| Layer | Technology |
|-------|-----------|
| **Authentication** | JWT Bearer (HS256, 5-min TTL) |
| **Token Refresh** | Refresh tokens (7-day TTL) |
| **MFA** | TOTP via Otp.NET |
| **SSO** | Azure AD via MSAL |
| **Authorization** | Claims-based RBAC (`[PermissionAuthorize]`) |
| **Column Encryption** | ASP.NET Data Protection (AES-128-CBC / HMAC-SHA256) |
| **Password** | Salted PBKDF2 + history tracking + 90-day expiry |
| **CSRF** | Anti-forgery tokens (XSRF-TOKEN cookie → X-Csrf-Token header) |
| **CORS** | Configurable origin whitelist |
| **Bot Protection** | Google reCAPTCHA v2 + v3 |

---

## Development Tools

| Tool | Purpose |
|------|---------|
| **Visual Studio / VS Code** | IDE (.vscode config present) |
| **StyleCop** | C# code style enforcement (4-space indentation, PascalCase) |
| **ESLint** | TypeScript/React linting |
| **Azure DevOps / TFS** | Version control, CI/CD pipelines |
| **Flyway** | Database migration management (SQL files, not EF migrations) |

---

## Build Configurations

| Config | Use |
|--------|-----|
| Debug | Local development (SuperUser bypass enabled, memory cache) |
| Gate | Pre-production testing/staging |
| Release | Production deployment (Azure Key Vault, Couchbase) |
| DockerBuild | CI/CD container builds (in-memory DB, no CORS) |

---

## Key Version Constraints

- .NET 8.0 LTS — locked until Nov 2026
- React 19 — requires React Router 7 (new data router APIs)
- MUI 7 — breaking changes from v5/v6 (sx prop, Grid v2)
- EF Core 8 — `DateOnly` support, JSON columns support
- Windows Server Core Docker image — **not Linux** (Windows-specific dependencies)
