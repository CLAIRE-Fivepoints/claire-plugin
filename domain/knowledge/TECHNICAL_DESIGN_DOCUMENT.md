---
keywords: [fivepoints, tfi-one, technical-design, architecture, dotnet, react, azure, authentication, jwt, couchbase, hangfire, serilog, sentry, security, infrastructure, disaster-recovery, soc2, tx-ramp, "persona:fivepoints-analyst"]
---

# TFI One — Technical Design Document

**Source:** TFI One Technical Design Document 20250709.docx
**Date:** July 2025
**Author:** FPTG (Five Points Technology Group)
**Version:** Initial draft (06/01/2025)

---

## Purpose

The purpose of this document is to provide a comprehensive technical overview of the TFI One web-based application architecture, components, frameworks, libraries, and supporting infrastructure. It serves as a foundational reference for developers, architects, security analysts, and operational teams involved in the design, implementation, deployment, and ongoing maintenance of the application.

This documentation outlines both the front-end and back-end technologies selected for TFI One, detailing how each component contributes to delivering a performant, scalable, maintainable, and secure solution. By describing the purpose, benefits, and security considerations associated with each framework and library, this document ensures that all stakeholders have a shared understanding of the technical decisions underpinning the system.

Additionally, it establishes consistent terminology and definitions used across modules, provides rationale for technology selections, and articulates how architectural choices align with TFI's business requirements, operational standards, and security compliance obligations.

**Content supports:**
- Technical alignment among project teams and stakeholders
- Efficient onboarding of new team members
- Guidance for secure and maintainable development practices
- Preparation for audits, compliance assessments, and operational reviews

---

## Module Terms and Glossary

| Term | Definition |
|------|------------|
| **API** | RESTful APIs via ASP.NET Core |
| **Azure Key Vault** | Secure storage for secrets, keys, certificates |
| **Azure SQL Database** | Fully managed cloud relational database |
| **Batch Jobs** | Automated tasks via Hangfire |
| **Caching** | Couchbase Server (in-memory NoSQL) |
| **CI/CD** | Azure DevOps pipelines |
| **Couchbase Server** | NoSQL in-memory caching |
| **DOTNET (.NET)** | Server-side framework, targeting .NET 8 |
| **DTO** | Data Transfer Object |
| **Entity Framework Core (EF Core)** | ORM with Database First approach |
| **FluentValidation** | Validation library for .NET and front-end |
| **Hangfire** | Background job processing for .NET |
| **JWT** | Stateless authentication/authorization tokens |
| **Material UI (MUI)** | React component library (Google Material Design) |
| **React.js** | Front-end JavaScript UI library |
| **React Router** | Declarative routing for React |
| **Redux Toolkit** | State management with RTK Query |
| **RTK Query** | Data fetching and caching within Redux Toolkit |
| **Sentry.io** | Application monitoring and error tracking |
| **SurveyJS** | Dynamic forms/surveys library |
| **SWC** | Super-fast JavaScript/TypeScript compiler |
| **TFVC** | Team Foundation Version Control (centralized) |
| **TypeScript** | Statically typed superset of JavaScript |
| **Vite** | Fast front-end build tool |

---

## Application Front-End Components and Libraries

### Framework: React.js
- Component-based architecture
- Virtual DOM for optimized rendering
- XSS mitigation via JSX automatic escaping

### Build: Vite, SWC, TypeScript
- **Vite:** Native ES modules, instant server start, hot module replacement
- **SWC:** High-performance JavaScript/TypeScript compiler
- **TypeScript:** Static typing, early bug detection

### State Management: Redux Toolkit
- Redux Thunk for async logic
- RTK Query for API calls, caching, synchronization
- Centralized application state

### Routing: React Router
- Declarative routing
- Code splitting and lazy loading
- Prevents open redirect vulnerabilities

### Component Library: Material UI (MUI)
- Pre-built accessible components
- Google Material Design principles

### Form Validation: FluentValidation (Front-End)
- Validation rules fetched from back-end dynamically
- Ensures consistency across front-end and back-end layers
- Prevents injection attacks

### Form Digitization: SurveyJS
- Used to digitize required documents and notes as online forms
- Built-in XSS and injection prevention

### Logging: Sentry.io (Front-End)
- JavaScript SDK integrated into React app
- Automatic capturing of exceptions, user actions, HTTP requests
- Custom logging via Sentry API
- Data scrubbing for PII compliance

---

## Application Back-End Components and Libraries

### Server Framework: .NET (C#)
- Targeting .NET 8 (LTS)
- Migration plan to .NET 10 when released; .NET 9 bypassed
- Hosted on Microsoft IIS servers
- Service-based architecture with dependency injection
- Interfaces define service contracts; implementations are swappable

### Authentication and Authorization

**Two authentication mechanisms:**

1. **Internal TFI users** — Microsoft Entra ID (SSO, MFA enforced by organization)
2. **External users (Five Points employees)** — Local username/password with MFA (email, SMS, Microsoft Authenticator)

**Password requirements (local auth):**
- Minimum 16 characters
- Minimum 1 uppercase character
- Minimum 1 digit character
- Disallow username in password
- Disallow digit as last character
- Disallow 3 consecutive identical characters
- No reuse of last 13 passwords
- Maximum password age: 180 days
- Passwords not stored in plain text (HMAC SHA512 or similar)

**Additional security:**
- All authentication attempts logged (username, timestamp, result, IP)
- Account locked after 5 consecutive failed attempts (configurable period)
- Authorized users can reset/unlock accounts
- Users notified 3 days before password expiry

**JWT Authorization:**
- Header (type + algorithm) + Payload (claims: user details, permissions) + Signature
- Short-lived tokens, configurable refresh period (e.g., 30 minutes)
- Stateless session management

### Database ORM: Entity Framework Core (Database First)
- Database schemas designed first in Azure SQL
- ORM entities scaffolded from schema
- Compile-time type checking via generated entities

### Database: Azure SQL Database
- Used across QA, UAT, and Production environments
- Development uses local SQL Server Developer Edition

**Key features:**
- Fully managed (updates, patches, backups)
- Dynamic scaling (vertical and horizontal)
- Built-in high availability and disaster recovery
- Transparent data encryption (TDE), threat detection, RBAC
- Azure SQL replicas for reporting, HA, and business continuity

### API Design: RESTful APIs (ASP.NET Core)
- Lightweight endpoints: receive request → delegate to injected repository → return result
- Typically 2–3 lines of code per endpoint
- Built-in: Authentication/Authorization, HTTPS enforcement, Data Protection APIs, CSRF/XSRF protection, CORS

### Caching: Couchbase Server
- Central caching for: JWT token refresh management, business rule validation, UI configuration parameters
- In-memory NoSQL with persistent storage
- Hosted as cluster within application subnet
- Sub-millisecond latency, horizontal scaling, automatic data replication

### Batch Management: Hangfire
- Runs as standalone console application (separate from main API)
- Communicates with dedicated SQL Server for job metadata
- Job types: Recurring, Fire-and-Forget, Delayed, Continuations
- Dashboard for monitoring job statuses, execution logs, performance metrics

### Form Validation: FluentValidation (Back-End)
- Validation rules stored in database, keyed by type name
- Org-specific rules or global rules
- If validation fails, controller endpoint is never hit; errors relayed to client
- Hard-coded validations can supplement database-driven rules
- Supports async validation (for database/external calls)

### Logging: Serilog and Sentry.io (Back-End)

**Serilog:**
- Core logging framework (already Five Points standard)
- Structured logs: Application Name, Machine Name, Log Level (Error/Warning/Info/Debug)
- Persisted to Azure Table Storage: naming convention `Serilog{Environment}{Year}`

**Sentry.io (back-end):**
- Configured as a Serilog sink
- Groups similar issues, provides timelines, user-friendly log exploration
- HIPAA compliance: PII scrubbing via built-in reducers before storage

---

## Application Configuration Approach

### Configuration Management: Azure Key Vault
- JSON files organized by functional component, injected at startup
- Sensitive values (connection strings, credentials, keys) stored in Azure Key Vault
- At startup, runtime retrieves secrets from Key Vault and merges with JSON config
- Key Vault: RBAC via Azure AD, AES encryption at rest, TLS in transit, secrets rotation/revocation

---

## Development and Change Management

**Tool: Azure DevOps**

### Version Control: TFVC (Team Foundation Version Control)
- Centralized version control (not Git)
- Centralized storage, audit trails, branching/merging, granular permissions

### Code Reviews and Collaboration
- Pull Requests (PRs) for peer reviews before merge
- Inline commenting, threaded discussions, resolution tracking
- Work item traceability (code change ↔ task)

### Continuous Integration (CI)
- Azure DevOps Pipelines
- Auto-triggered on check-ins or PR merges
- Automated unit tests, integration tests, static code analysis
- Immediate feedback reports

### Continuous Deployment (CD)
- Azure DevOps Pipelines
- Covers: front-end, back-end, and database schema changes
- Multi-environment automation (dev, staging, production)
- Deployment gates and approvals
- Embedded security scanning and vulnerability assessment

---

## System Data Management Approach

**Compliance:** SOC 2 Type 2

### Data Storage: Azure Storage
- **Blob Containers** — uploaded files
- **Table Storage** — structured non-relational data (logs, metadata)

### Database Storage: Azure SQL Database
- Transactional, configuration, and operational data
- Indexing, query optimization, transaction consistency

### Backup and Recovery

**VM Backups (Production):**
- Whole VM backups every 4 hours
- Geo-redundant storage recovery vault
- Instant restore: 7 days
- Retention: 14 days

**Azure SQL Database Backups:**
- Full backups: weekly
- Differential backups: every 12 or 24 hours
- Transaction log backups: approximately every 10 minutes
- Geo-redundant backup storage (replicated to paired region)

### Disaster Recovery
- **Azure Site Recovery (ASR)** — VM-level replication from primary (Eastern US 2) to secondary (Central US)
- **Azure SQL replicas** — geo-replication, real-time synchronization
- **Azure Storage** — geo-redundant replication
- **Azure Key Vault** — geo-redundant key/secret replication
- DR testing: annually (failover + SQL replica sync validation)

### Data Audit: Azure Table Storage
- Change Data Capture (CDC) integrated in ORM
- Critical entity changes logged to Azure Table Storage
- Audit data treated as immutable after initial write
- Supports forensic-level data tracking

---

## System Security Approach

**Compliance frameworks:** SOC 2 Level 2 + TX-RAMP

### Authentication & Authorization
- Azure RBAC + Azure Active Directory (AAD)
- Azure AD Connect for Five Points Active Directory sync
- Principle of least privilege enforced throughout
- MFA required for third-party services (Twilio SendGrid, Sentry.io, etc.)

### Encryption
- **In transit:** TLS with SHA-256 / RSA
- **At rest:** AES 256-bit (Azure Storage, Azure SQL, all Azure-managed repositories)

### Vulnerability Management
- **Qualys Threat Protection** — continuous infrastructure monitoring
- **Qualys WAS (Web Application Scanning)** — regular application scanning
- Regular patching and remediation cycles

### Antivirus and Malware
- **Sophos Endpoint Protection** on all virtual machines
- Real-time detection, proactive threat hunting, centralized management

### Event Logging and Monitoring
- **Pulseway** — real-time infrastructure health monitoring and alerts
- **Netwrix** — auditing and compliance reporting
- **Azure Premium Firewall** — network traffic logging and analysis

### Infrastructure Security
- **Azure Premium Firewall** — network security
- **Hub-and-spoke network architecture**
- **Azure VNet with VNet Peering** — traffic isolation
- **Network Security Groups (NSGs)** — inbound/outbound traffic control

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                         TFI One Architecture                     │
├────────────────────┬────────────────────────────────────────────┤
│ FRONT-END          │ BACK-END                                    │
│ React.js           │ .NET 8 (C#) / ASP.NET Core                 │
│ TypeScript         │ RESTful APIs                                │
│ Vite + SWC         │ Entity Framework Core (Database First)      │
│ Redux Toolkit      │ FluentValidation                            │
│ RTK Query          │ Hangfire (batch jobs)                       │
│ React Router       │ Serilog + Sentry.io                         │
│ Material UI (MUI)  │ Azure Key Vault (secrets)                   │
│ FluentValidation   │ Couchbase Server (caching)                  │
│ SurveyJS           │                                             │
│ Sentry.io          │                                             │
├────────────────────┴────────────────────────────────────────────┤
│ DATA LAYER                                                        │
│ Azure SQL Database (QA / UAT / Production)                       │
│ Azure Blob Storage (files)                                       │
│ Azure Table Storage (logs, metadata)                             │
├──────────────────────────────────────────────────────────────────┤
│ INFRASTRUCTURE                                                    │
│ Azure DevOps (CI/CD)                                             │
│ TFVC (version control)                                           │
│ Azure Premium Firewall + VNet                                    │
│ Azure Site Recovery (DR)                                         │
│ Qualys (vulnerability scanning)                                  │
│ Sophos (endpoint protection)                                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Front-end framework | React.js | Component-based, virtual DOM, large ecosystem |
| Build tool | Vite + SWC | Fastest dev experience, native ES modules |
| State management | Redux Toolkit + RTK Query | Centralized state + data fetching |
| Back-end framework | .NET 8 (C#) | LTS, service-based, DI-first |
| ORM approach | Database First (EF Core) | Schema-driven, compile-time safety |
| Version control | TFVC (not Git) | Five Points standard, centralized |
| Caching | Couchbase | Sub-millisecond latency, in-memory NoSQL |
| Validation | FluentValidation (DB-driven) | Org-specific rules, consistent across layers |
| Auth (internal) | Microsoft Entra ID | SSO + MFA via organization |
| Auth (external) | Local + MFA | Email/SMS/Authenticator for Five Points staff |
| .NET version strategy | .NET 8 → skip 9 → target 10 | LTS only |
