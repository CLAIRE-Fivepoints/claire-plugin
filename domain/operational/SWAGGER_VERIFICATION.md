---
domain: five_points
category: operational
name: SWAGGER_VERIFICATION
title: "FivePoints — Swagger Endpoint Verification (Code Gen tasks)"
keywords: [five-points, fivepoints, tfi-one, swagger, endpoint, verification, code-gen, macos, jwt, bearer, playwright, curl, docker, sqlserver, appsettings]
updated: 2026-03-30
pr: "#2291"
---

# FivePoints — Swagger Endpoint Verification (Code Gen tasks)

> This document describes how to verify that newly generated Swagger endpoints are correctly
> registered and return 200 OK on macOS. Applies to Code Gen PBI tasks on TFI One.

---

## Context

During Code Gen PBI tasks, the tester role must verify that all new endpoints are:
1. Registered in the Swagger JSON
2. Returning HTTP 200 with a valid Bearer token

Several blockers exist on macOS that are not obvious. This document prevents 30–60 min of rediscovery.

---

## Key Credentials (Local Dev)

| What | Value |
|------|-------|
| SQL Server container | `tfione-sqlserver` |
| SA password | `TFIOne_Dev2024!` |
| App login | `prime.user` / `Admin123!` |
| API HTTPS | `https://localhost:58337` |
| Swagger JSON | `https://localhost:58337/swagger/v1/swagger.json` |

> **Note:** `prime.user` password (`Admin123!`) is NOT the SA password (`TFIOne_Dev2024!`).

---

## Prerequisites

- Build must pass: `dotnet build com.tfione.sln --no-restore` → 0 errors
- Docker container `tfione-sqlserver` must be running (see Step 1)

---

## Step-by-Step Verification

### Step 1 — Start SQL Server container

```bash
docker start tfione-sqlserver
# Wait ~10 seconds before proceeding
sleep 10
```

If the container doesn't exist, it must be created first (outside scope of this doc — see `DEVELOPER_GATES.md`).

---

### Step 2 — Override connection string on macOS

Edit `appsettings.Development.json` in the API project root:

```json
{
  "ConnectionStrings": {
    "tfione": "Data Source=localhost,1433;Initial Catalog=tfi_one;User Id=sa;Password=TFIOne_Dev2024!;TrustServerCertificate=True"
  }
}
```

> **Why:** `Integrated Security=True` uses Windows Authentication (GSSAPI), which is not available on macOS.
> The SA credentials bypass this and connect directly via TCP.

> **Important:** Do NOT commit `appsettings.Development.json` — it contains local credentials.

---

### Step 3 — Start the API

```bash
# Kill any existing API process
pkill -f "com.tfione.api" 2>/dev/null; sleep 2

# Start API in background
cd ~/TFIOneGit
dotnet run --project com.tfione.api --no-build > /tmp/tfiapi.log 2>&1 &
sleep 10

# Verify it's listening
grep "Now listening" /tmp/tfiapi.log
# Expected: Now listening on: https://localhost:58337
```

---

### Step 4 — Get JWT token

> **Critical:** The JWT token MUST be generated AFTER the final API restart.
> JWT signing keys change on every restart — a token from a previous session will be rejected.

```bash
TOKEN=$(curl -sk -X POST "https://localhost:58337/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "prime.user", "password": "Admin123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))")

# Verify token is non-empty
echo "Token length: ${#TOKEN}"
# Expected: Token length: 400+ (non-zero)
```

If `TOKEN` is empty, check:
- API is running (`grep "Now listening" /tmp/tfiapi.log`)
- Credentials are correct (`prime.user` / `Admin123!`)

---

### Step 5 — Verify all endpoints return 200

Replace `CID` and `IID` with realistic test GUIDs, and adapt the endpoint path to the Code Gen task:

```bash
BASE="https://localhost:58337"
CID="00000000-0000-0000-0000-000000000001"
IID="00000000-0000-0000-0000-000000000002"
AUTH="Authorization: Bearer $TOKEN"

# Example: AdoptivePlacement endpoints
curl -sk -o /dev/null -w "GET list    → %{http_code}\n" \
  "$BASE/client/$CID/adoption/adoptiveplacement" -H "$AUTH"

curl -sk -o /dev/null -w "POST        → %{http_code}\n" -X POST \
  "$BASE/client/$CID/adoption/adoptiveplacement" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"familyName":"Test","placementDate":"2026-01-01T00:00:00","selectedClientIds":[]}'

curl -sk -o /dev/null -w "GET by id   → %{http_code}\n" \
  "$BASE/client/$CID/adoption/adoptiveplacement/$IID" -H "$AUTH"

curl -sk -o /dev/null -w "PUT         → %{http_code}\n" -X PUT \
  "$BASE/client/$CID/adoption/adoptiveplacement/$IID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"familyName":"Updated","placementDate":"2026-01-01T00:00:00","selectedClientIds":[]}'

curl -sk -o /dev/null -w "DELETE      → %{http_code}\n" -X DELETE \
  "$BASE/client/$CID/adoption/adoptiveplacement/$IID" -H "$AUTH"

curl -sk -o /dev/null -w "GET view    → %{http_code}\n" \
  "$BASE/client/$CID/adoption/adoptiveplacement/$IID/view" -H "$AUTH"
```

All lines must output HTTP `200`. A `401` means the token is expired or invalid (re-run Step 4).

---

### Step 6 — Record Swagger proof video with Playwright

The Swagger UI Authorize dialog does NOT reliably inject the Bearer token via UI interaction.
Use Playwright route interception instead:

```python
from playwright.sync_api import sync_playwright

TOKEN = "<paste token here>"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    # Inject Bearer token on every API request
    def handle_route(route):
        headers = {**route.request.headers, "Authorization": f"Bearer {TOKEN}"}
        route.continue_(headers=headers)

    page.route("https://localhost:58337/**", handle_route)
    page.goto("https://localhost:58337/swagger")

    # Navigate and demonstrate each endpoint returning 200
    # Record screen during this session (use proof record or OBS)
    input("Press Enter when done recording...")
    browser.close()
```

> **Why route interception:** The Swagger UI "Authorize" button injects the token into the UI state,
> but this can fail silently when the browser has cert warnings or when using `https` with self-signed certs.
> Route interception guarantees the header is present on every request.

---

### Step 7 — Prove endpoints are new (not pre-existing)

```bash
cd ~/TFIOneGit

# Show only [Http*] attributes added by Code Gen commits (not pre-existing)
git diff main -- com.tfione.api/client/AdoptionController.cs | grep '^\+.*\[Http'
```

Expected output: only the new `[HttpGet]`, `[HttpPost]`, `[HttpPut]`, `[HttpDelete]` lines added by
the Code Gen commits. No pre-existing endpoints should appear.

This diff output is included as proof in the PR description or validation comment.

---

## Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `curl` returns 401 | Token expired or generated before API restart | Re-run Step 4 after final restart |
| `curl` returns 500 | DB not connected | Verify `tfione-sqlserver` is running (Step 1) |
| `curl` returns 500 (connection string) | `Integrated Security=True` on macOS | Apply Step 2 override |
| `TOKEN` is empty | Wrong credentials | Use `prime.user` / `Admin123!` (not SA password) |
| Swagger UI shows no auth | Authorize dialog unreliable | Use Playwright route interception (Step 6) |
| API won't start | Previous instance still running | `pkill -f "com.tfione.api"` then restart |

---

## Integration with `fivepoints validation-proof`

The `claire fivepoints validation-proof` command automates part of this flow:
- Records frontend UI validation errors (400 responses)
- Records Swagger API 400 responses via Playwright

For Code Gen endpoint verification (200 responses), use the manual `curl` steps above,
then record the Swagger UI proof separately.
