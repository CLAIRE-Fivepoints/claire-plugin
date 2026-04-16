---
domain: fivepoints
category: operational
name: TEST_ENV_START
title: "FivePoints — Test Environment Start (fivepoints test-env-start)"
keywords: [five-points, fivepoints, tfi-one, test-env-start, test-environment, tfi-one-stack, sql-server, sqlserver, dotnet, vite, local-testing, dev, tester]
updated: 2026-04-08
pr: "#2346"
---

# FivePoints — Test Environment Start

> Starts the full TFI One local stack: SQL Server (Docker) + .NET API + Vite frontend.
> Used by both the dev and tester roles before running Swagger verification or Playwright tests.

## Command

```bash
claire fivepoints test-env-start [--path /path/to/TFIOneGit]
```

## When to Use

- **Dev role** — step [6/12]: copy feature branch to isolated worktree, then run this
- **Tester role** — step [1/8]: copy branch to isolated worktree, then run this
- Any time you need the full stack running locally for manual testing

## What It Does

| Step | Action |
|------|--------|
| [1/4] | Start `tfione-sqlserver` Docker container (creates if missing) |
| [2/4] | Start .NET API: `dotnet run --urls "https://localhost:58337"` (background) |
| [3/4] | Start Vite frontend: `npm run dev` (background) |
| [4/4] | Wait for health checks on both services |

On success, prints:
```
✅ Environment ready
   API:      https://localhost:58337
   Swagger:  https://localhost:58337/swagger
   UI:       http://localhost:5173
   API PID:  XXXX | Vite PID: XXXX
```

## Default Path

Looks for `com.tfione.sln` in the current directory. Override with `--path`:

```bash
claire fivepoints test-env-start --path /Users/andreperez/TFIOneGit
```

## Teardown (at end of session)

After all tests complete, stop the environment using the PIDs printed at startup:

```bash
kill $API_PID $VITE_PID        # PIDs printed by test-env-start
docker stop tfione-sqlserver
```

## Prerequisites

- Docker running (for SQL Server)
- `com.tfione.sln` present in the target directory
- .NET SDK installed
- Node.js + npm installed (for Vite frontend)

## Manual Fallback (if script missing)

```bash
# SQL Server
docker start tfione-sqlserver

# .NET API
dotnet run --project com.tfione.api/com.tfione.api.csproj --urls "https://localhost:58337" &
API_PID=$!

# Vite frontend
npm --prefix com.tfione.web run dev &
VITE_PID=$!
```

## macOS and Environment Fixes (L1/L2/L3/L8)

These fixes were added after issue #146 (2026-04-08) burned ~15 min each on silent failures.

### L1 — ASPNETCORE_ENVIRONMENT=Development (set automatically)

`test-env-start` now exports `ASPNETCORE_ENVIRONMENT=Development` before `dotnet run`.

**Why:** Without this, the API runs in `Production` mode. In Production,
`RecaptchaSettings.RecaptchaOn` defaults to `true`, which silently rejects all
programmatic logins — the response is HTTP 200 with `userName: null` and `token: null`.
No error message. ~15 min lost debugging before root cause identified.

### L2 — macOS SQL auth override (injected automatically on macOS)

On macOS, `test-env-start` exports `ConnectionStrings__tfione` with a SQL auth
connection string: `Server=localhost,1433;Database=tfi_one;User Id=sa;Password=<detected>;TrustServerCertificate=True;Encrypt=False`

**Why:** The default `appsettings.json` uses `Integrated Security=True` (Kerberos/Windows
auth). On macOS + Docker SQL Server, Kerberos is not configured, and the API fails
immediately at startup with:
```
GSSAPI operation failed: The context has expired and can no longer be used.
```

This override avoids editing `appsettings.Development.json` manually each session.

### L3 — SA password auto-detected from existing container

If `tfione-sqlserver` already exists, `test-env-start` reads its `MSSQL_SA_PASSWORD`
via `docker inspect` and uses that value for both the connection string (L2) and
any new container creation.

**Why:** The container in the original `test-env-start.sh` defaulted to `YourStrong!Passw0rd`,
but existing containers may have been created with a different password
(e.g. `TFIOne_Dev2024!`). The mismatch caused silent connection failures.

### L8 — --help and -h flags

`test-env-start` now accepts `--help` and `-h`. Previously, these returned
`Unknown argument: --help`, inconsistent with all other `claire fivepoints` subcommands.

---

## Relation to the Pre-Gate Routine

`claire fivepoints test-env-start` handles **steps 1–4** of the "Routine — Before Any Local Gate Run" defined in `DEVELOPER_GATES.md`:

| Routine step | What `test-env-start` does |
|---|---|
| 1. Kill existing API | Runs `pkill -f "com.tfione.api"` before starting |
| 2. Start SQL Server | Starts `tfione-sqlserver` Docker container |
| 3. Start fresh .NET API | `dotnet run --urls "https://localhost:58337"` |
| 4. Wait for swagger | Health-checks both API and Vite before printing ready |

After `test-env-start` completes, continue from **step 5** (regenerate TS types):
```bash
cd com.tfione.web
GENERATE_ENV=local \
GENERATE_API="https://localhost:58337/swagger/v1/swagger.json" \
NODE_TLS_REJECT_UNAUTHORIZED=0 \
  npx tsx src/types/com.tfione.api.generate.ts
```

Then run your gate (`npm run build-gate`, `npm run lint`, etc.).

---

## Related

- `claire domain read fivepoints operational SWAGGER_VERIFICATION` — next step after env is ready
- `claire domain read fivepoints operational TESTING` — login credentials and test patterns
- `claire domain read fivepoints operational PIPELINE_WORKFLOW` — full dev/tester checklist
