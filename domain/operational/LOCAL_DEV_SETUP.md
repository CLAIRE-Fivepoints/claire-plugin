---
domain: fivepoints
category: operational
name: LOCAL_DEV_SETUP
title: "TFI One — Local Development Setup"
keywords: [local, dev, setup, start, run, dotnet, vite, frontend, backend, login, database, sql-server]
updated: 2026-03-25
---

# TFI One — Local Development Setup

How to start the full application stack locally for development and testing.

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
| Password | `Admin123!` |

3. Click **Login**

> `SuperUserPermissionBypass: true` is set in `appsettings.Development.json` — the prime user bypasses all permission checks in Development mode.

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

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ERR_CONNECTION_REFUSED` on login | Backend not running | Run `dotnet run` in `com.tfione.api` |
| SSL certificate warning in browser | Self-signed cert | Click "Advanced → Proceed" |
| `npm run dev` fails | Missing `env/.env.local` | File should exist in repo — check `git status` |
| Login fails with valid credentials | DB not running or migrations not applied | Start SQL Server and run `flyway migrate` |
| Build errors on dotnet run | NuGet restore failed | Run `dotnet restore` manually first |
| Face sheet cards stuck as spinners, no API calls | `VITE_API_URL=/api` but no proxy configured | Restart Vite in direct mode (`vite --port 5174`) |
| API calls blocked by CORS | Port mismatch between CORS config and running Vite port | Add Vite port to `CorsSettings.ValidOrigins` in `appsettings.Development.json` |
| Old API routes returning 404 | Old API binary still running from before branch switch | Kill old `dotnet run` process, restart from correct branch |
| `pymssql` connection fails against Azure SQL Edge | Default TDS version incompatible | Add `tds_version='7.3'` to `pymssql.connect()` |
| Client search returns `list: []` but data exists | Search requires at least one param | Always verify with `recordCount` field, not `list.length` |
