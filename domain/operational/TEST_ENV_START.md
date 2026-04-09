---
domain: five_points
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

- **Dev role** — step [6/11]: copy feature branch to isolated worktree, then run this
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

- `claire domain read five_points operational SWAGGER_VERIFICATION` — next step after env is ready
- `claire domain read five_points operational TESTING` — login credentials and test patterns
- `claire domain read five_points operational PIPELINE_WORKFLOW` — full dev/tester checklist
