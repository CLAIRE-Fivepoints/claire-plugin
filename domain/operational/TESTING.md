---
keywords: [testing, local-setup, credentials, cors, login, vite, dotnet, prime-user, password, azure-devops, pat]
---

# TFI One — Local Testing Guide

---

## Test Users & Credentials

| User | Password | Role | Notes |
|------|----------|------|-------|
| `prime.user` | `Test1234!` | SU (Super User) | Full permissions, bypass enabled |

- Prime user ID: `892e261f-f2a1-4217-8f3c-027a6a4519cc`
- Password hashing: HMACSHA512 with key from `appsettings.json`
- Password stored in `sec.AppUser` table

---

## Local Server Setup

```bash
# Backend (.NET API)
cd /Users/andreperez/projects/fivepoints/dev
dotnet run --project com.tfione.api/com.tfione.api.csproj --urls="https://localhost:58337"

# Frontend (Vite)
cd /Users/andreperez/projects/fivepoints/dev/com.tfione.web
nvm use 22
npm run dev
# Default port: 5173
```

---

## CORS Configuration

File: `com.tfione.api/appsettings.json`

```json
"CorsSettings": {
    "ValidOrigins": "https://localhost:5173"
}
```

**Critical:** Frontend port MUST match `ValidOrigins`.

If login silently fails (`net::ERR_FAILED`), CORS mismatch is the likely cause:
1. Check which port Vite is actually using (5173, 5174, 5175...)
2. Update `ValidOrigins` in `appsettings.json` to match
3. Restart the .NET API

---

## Login Flow

1. Open `https://localhost:5173`
2. Click **"Non TFI Employees Click Here to Login"** (standard login, not SSO)
3. Enter `prime.user` / `Test1234!`
4. Click **Login**

---

## Database

- SQL Server on `localhost` (Integrated Security / Windows Auth)
- Database: `tfi_one`
- Connection string: `appsettings.json` → `ConnectionStrings:tfione`
- Migrations: Flyway in `com.tfione.db/migration/`

### macOS — Use SQL Auth (avoid Kerberos)

On macOS, `Integrated Security=True` uses Kerberos which requires `/etc/krb5.conf` and
`kinit`. Simpler to use SQL Server Authentication instead.

**Override in `appsettings.Development.json`:**

```json
"ConnectionStrings": {
  "tfione": "Data Source=localhost,1433;Initial Catalog=tfi_one;User ID=sa;Password=TFIOne_Dev2024!;TrustServerCertificate=True"
}
```

| Field    | Value            |
|----------|------------------|
| Server   | `localhost,1433` |
| User     | `sa`             |
| Password | `TFIOne_Dev2024!` |
| DB (API) | `tfi_one`        |
| DB (Hangfire) | `hangfire_tfi_one` |

---

## Azure DevOps PAT

Commands like `fivepoints wait`, `fivepoints pr-status`, `fivepoints build-log` require `AZURE_DEVOPS_PAT`.

PAT extraction logic: `30_universe/plugins/fivepoints/domain/scripts/ado_common.sh` — function `ado_init`

**Resolution priority (first found wins):**

1. **Git remote URL (already configured for `andre.perez`)** — auto-detected, no setup needed:
   ```
   https://user:PAT@dev.azure.com/FivePointsTechnology/TFIOne/_git/TFIOneGit
   ```

2. **Claire config (persistent):**
   ```bash
   claire config set azure_devops.pat <your-pat>
   ```

3. **Environment variable:**
   ```bash
   export AZURE_DEVOPS_PAT='your-pat'
   ```

If none found: `ERROR: AZURE_DEVOPS_PAT not set`

---

## Common Test Data

| Resource | ID |
|----------|----|
| Test Client ID | `10000000-0000-0000-0000-000000000001` |
| Test Organization | `07e2433e-f36b-1410-8662-0056d94c4b2e` |

---

## Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Login silently fails (`net::ERR_FAILED`) | CORS mismatch | Update `ValidOrigins` to match Vite port, restart API |
| 401 Unauthorized | Wrong credentials or SSO flow used | Use standard login button, not SSO |
| DB connection error | SQL Server not running | Start SQL Server service |
| `Cannot authenticate using Kerberos` (macOS) | No active Kerberos ticket | Run `kinit user@FIVEPTG.LOCAL` before starting backend |
