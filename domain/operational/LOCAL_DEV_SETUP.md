---
domain: fivepoints
category: operational
name: LOCAL_DEV_SETUP
title: "TFI One — Local Development Setup"
keywords: [local, dev, setup, start, run, dotnet, vite, frontend, backend, login, database, sql-server, smoke-test, seed-test-data]
updated: 2026-04-23
---

# TFI One — Local Development Setup

How to start the full application stack locally for development and testing.

---

## TL;DR — From zero to validated multi-user stack

```bash
# 1. Bring the stack up (Docker SQL Server + .NET API + Vite)
claire fivepoints test-env-start

# 2. Confirm the stack is healthy (6 checks, ~5 seconds)
claire fivepoints smoke-test

# 3. Seed multi-user test data (idempotent — safe to re-run)
claire fivepoints seed-test-data
```

After step 3 you have 7 users (`prime.user` + 6 seeded), 4 test clients across
2 organizations, and per-module face-sheet records — enough to exercise
permission scoping, dashboard filtering, and per-org isolation.

See [Smoke test + seed](#smoke-test--seed-data-issue-118) below for details.

---

## Prerequisites

- .NET 8 SDK
- Node.js 20+
- SQL Server running on `localhost:1433`
  - Database: `tfi_one`
  - Credentials: `sa` / `TFIOne_Dev2024!`

---

## Start the Backend

```bash
cd dev/com.tfione.api
dotnet run
```

**URLs:**
| | |
|---|---|
| API | `https://localhost:58337` |
| Swagger UI | `https://localhost:58337/swagger` |
| HTTP (non-SSL) | `http://localhost:58338` |

The backend reads from `appsettings.Development.json` automatically when `ASPNETCORE_ENVIRONMENT=Development` (set in `Properties/launchSettings.json`).

**First run:** dotnet restore runs automatically. Takes ~20s on cold start.

---

## Start the Frontend

```bash
cd dev/com.tfione.web
npm run dev
```

**URL:** `https://localhost:5173`

The `npm run dev` script uses `env-cmd -f ./env/.env.local vite` — it reads env vars from `env/.env.local`. This file is committed and pre-configured for local development.

**Note:** The frontend uses a self-signed SSL certificate (`@vitejs/plugin-basic-ssl`). Browser will show a certificate warning on first visit — click "Advanced → Proceed" to continue.

---

## Login

Navigate to `https://localhost:5173`.

1. Click **"Non TFI Employees Click Here to Login"**
2. Enter credentials:

| Field | Value |
|-------|-------|
| Username | `prime.user` |
| Password | `Test1234!` |

3. Click **Login**

> `SuperUserPermissionBypass: true` is set in `appsettings.Development.json` — the prime user bypasses all permission checks in Development mode.

> **Note:** prior versions of this doc (and `SWAGGER_VERIFICATION.md`) listed
> `Admin123!`. That was stale — the live API rejects it with 401. The actual
> seeded password is `Test1234!` (see `sec.AppUser` row for `prime.user`).

---

## Port Conflicts Between Worktrees

When running multiple Claire worktrees simultaneously, Vite port `5173` may already be in use. Vite will auto-increment to `5174`.

**Two different startup modes result in different API call behavior:**

| Mode | How started | `VITE_API_URL` | API calls |
|------|-------------|----------------|-----------|
| env-cmd mode | `env-cmd -f ./env/.env.local vite` | `/api` | Requires Vite proxy config |
| Direct mode | `vite --port 5174` | `https://localhost:58337` | Direct CORS calls |

**Recommended for direct mode (no proxy):** Start Vite without env-cmd so it reads root `.env.local`:
```bash
cd dev/com.tfione.web
vite --port 5174
```
This uses `VITE_API_URL=https://localhost:58337` (direct API calls). Ensure the API allows the Vite port in CORS config.

**CORS configuration:** `appsettings.Development.json` must allow the Vite port. `WithOrigins()` does NOT accept comma-separated strings — use one value per call:
```json
"CorsSettings": {
  "ValidOrigins": "https://localhost:5174"
}
```

---

## SQL Server (Azure SQL Edge Docker)

The dev database runs in Docker (`tfione-sqlserver`), not native SQL Server. This matters for scripting:

- **sqlcmd is NOT available** inside the Azure SQL Edge container
- **Connection from macOS:** Use `pymssql` with `tds_version='7.3'`
- **Connection string:** `localhost:1433`, database `tfi_one`, user `sa`, password `TFIOne_Dev2024!`

```python
import pymssql
conn = pymssql.connect(
    server='localhost', port=1433, database='tfi_one',
    user='sa', password='TFIOne_Dev2024!',
    tds_version='7.3'  # Required for Azure SQL Edge
)
```

---

## Test Client

For E2E tests and manual testing, a seeded test client exists:

| | |
|---|---|
| **Client ID** | `10000000-0000-0000-0000-000000000001` |
| **Name** | `Student, Test - E2E-001` |
| **DOB** | `2010-05-15` |
| **Face sheet URL** | `https://localhost:5174/client/face_sheet/10000000-0000-0000-0000-000000000001` |
| **Enrollment with address** | `9cf4433e-f36b-1410-8662-0056d94c4b2e` (Austin High School, 1234 Congress Ave, Austin TX 78701) |

**Finding existing clients:** The client search API requires at least one search parameter — searching with no params returns empty `list: []` even if `recordCount > 0`. Always check `recordCount` before assuming no results.

---

## Run E2E Tests

```bash
cd /path/to/tfione-e2e
npm install
npx playwright test                          # all tests
npx playwright test education-bug-fixes.spec.ts --video on   # with video recording
```

Video saved to `test-results/`.

---

## Smoke Test + Seed Data (issue #118)

Manual testing on issue #14 burned ~1h on stack-state debugging (wrong SA
password, port conflicts, empty dropdowns) because nothing automated checked
the stack was healthy and only `prime.user` shipped with the migrations.
Two new commands solve both:

### `claire fivepoints smoke-test`

Six-check health probe of the local stack, ~5 seconds, no DB writes.

| # | Check | Failure means |
|---|-------|---------------|
| 1 | `tfione-sqlserver` container running | Container stopped → `docker start tfione-sqlserver` |
| 2 | Swagger reachable at `https://localhost:58337/swagger/v1/swagger.json` | API not started → `claire fivepoints test-env-start` |
| 3 | Login as `prime.user` returns non-empty token | Wrong password OR API in Production mode (RecaptchaOn=true silently rejects) |
| 4 | `GET /references/StateType` returns non-empty list | Token rejected OR DB empty |
| 5 | `GET /references/CountyType` returns non-empty list | Same as 4 |
| 6 | `GET /users/organization` returns 200 | Token scope wrong |

Exit code 0 = all passed. Exit code 1 = any failed (failed checks listed).
Run before manual testing.

### `claire fivepoints seed-test-data`

Idempotent SQL seed for multi-user testing. Always safe to re-run — every
INSERT is guarded by `IF NOT EXISTS (... WHERE ClientId = c.ClientId)`.

| Section | What it inserts |
|---------|-----------------|
| `users` | 6 `sec.AppUser` (3 roles × 2 orgs); password = `Test1234!` (hash copied from `prime.user` so the same one works) |
| `clients` | 4 `client.Client` rows (2 per org) + `client.ClientAlias` per client |
| `alerts` | 1 `client.ClientAlert` (HOSP) per seeded client |
| `allergies` | 1 `client.Allergy` (Peanuts) per seeded client |
| `education` | 1 `client.ClientEducation` per seeded client |
| `legal` | 1 `client.LegalStatus` + 1 `client.LegalAction` per seeded client |
| `medical` | 1 `client.MedicalFileDiagnosis` per seeded client |

**Seeded users** (all → password `Test1234!`):

| UserName | Org | Role |
|----------|-----|------|
| `2ingage.admin` | 2Ingage | Super User |
| `2ingage.supervisor` | 2Ingage | Case Manager User |
| `2ingage.caseworker` | 2Ingage | CPA Case Manager User |
| `empower.admin` | Empower | Super User |
| `empower.supervisor` | Empower | Case Manager User |
| `empower.caseworker` | Empower | CPA Case Manager User |

**Out of scope** (intentional — file a follow-up issue if you need them):
`Intake`, `HomeStudy`, `Placement` — each has a deep `Case`/`CaseWorker` FK
chain that warrants its own scoped seed.

**Why not a Flyway migration?** `CODING_STANDARDS §10` + `DEV_RULES §1`
forbid seed/role data in migrations: migrations must run cleanly on
`tfi_one_empty`. This script is local-dev only and re-seedable on demand.

```bash
claire fivepoints seed-test-data                    # all sections
claire fivepoints seed-test-data --section users    # one section
claire fivepoints seed-test-data --dry-run          # print SQL, don't run
claire fivepoints seed-test-data --help             # full usage
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ERR_CONNECTION_REFUSED` on login | Backend not running | Run `dotnet run` in `com.tfione.api` |
| SSL certificate warning in browser | Self-signed cert | Click "Advanced → Proceed" |
| `npm run dev` fails | Missing `env/.env.local` | File should exist in repo — check `git status` |
| Login returns 401 with valid-looking creds | Doc lists wrong password (e.g. `Admin123!` — stale) | Use `Test1234!` for `prime.user` (and seeded users) |
| Login returns 200 but `token: null`, `userName: null` | API running in Production mode → `RecaptchaOn=true` silently rejects | Set `ASPNETCORE_ENVIRONMENT=Development` (auto-set by `test-env-start`) |
| Login fails with valid credentials | DB not running or migrations not applied | Start SQL Server and run `flyway migrate` |
| Reference dropdowns appear empty in the UI | API returned 401 (token issue) or 200 + `[]` (DB not seeded) | `claire fivepoints smoke-test` distinguishes the two cases in <5s |
| Build errors on `dotnet run` | NuGet restore failed | Run `dotnet restore` manually first |
| Face sheet cards stuck as spinners, no API calls | `VITE_API_URL=/api` but no proxy configured | Restart Vite in direct mode (`vite --port 5174`) |
| API calls blocked by CORS | Port mismatch between CORS config and running Vite port | Add Vite port to `CorsSettings.ValidOrigins` in `appsettings.Development.json` |
| Old API routes returning 404 | Old API binary still running from before branch switch | Kill old `dotnet run` process, restart from correct branch |
| Port `5173` / `58337` already in use | Stale process from prior session | `lsof -iTCP:5173 -sTCP:LISTEN` then `kill <pid>`; `pkill -f com.tfione.api` for the API |
| Wrong SA password connecting to SQL Server | Container created with a non-default password | `docker inspect tfione-sqlserver --format '{{range .Config.Env}}{{println .}}{{end}}' \| grep MSSQL_SA_PASSWORD` (this is what `seed-test-data` does) |
| `pymssql` connection fails against Azure SQL Edge | Default TDS version incompatible | Add `tds_version='7.3'` to `pymssql.connect()` |
| Client search returns `list: []` but data exists | Search requires at least one param | Always verify with `recordCount` field, not `list.length` |
