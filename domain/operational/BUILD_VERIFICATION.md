---
domain: fivepoints
category: operational
name: BUILD_VERIFICATION
title: "Five Points — Gate Build Verification"
keywords: [five-points, azure-devops, build, gate, ci, flyway, verification, pat]
updated: 2026-03-07
---

# Five Points — Gate Build Verification

---

## Overview

The Gate build runs automatically on every push to `feature/*`, `bugfix/*`, and `dev`.
It validates: .NET build, unit tests, Flyway empty migration, Flyway incremental migration (against QA bacpac), and frontend build.

**PAT scope required**: Code (Read) — the build API requires Build (Read) which the current PAT does NOT have.
Use the commit statuses API instead (works with Code scope).

---

## Step 1 — Extract PAT from git remote

```bash
cd /Users/andreperez/TFIOneGit
PAT=$(git remote get-url origin | sed -n 's|https://[^:]*:\([^@]*\)@.*dev\.azure\.com.*|\1|p')
AUTH=$(echo -n ":${PAT}" | base64)
```

---

## Step 2 — Get latest commit on the branch

```bash
BRANCH="feature/14-education-module"
COMMIT=$(git rev-parse $BRANCH)
echo "Commit: $COMMIT"
```

---

## Step 3 — Check build status via commit statuses API

```bash
curl -s \
  -H "Authorization: Basic ${AUTH}" \
  -H "Content-Type: application/json; charset=utf-8" \
  "https://dev.azure.com/FivePointsTechnology/TFIOne/_apis/git/repositories/TFIOneGit/commits/${COMMIT}/statuses?api-version=7.1" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
statuses = d.get('value', [])
if not statuses:
    print('No build queued yet — wait 1-2 minutes after push')
else:
    for s in statuses[:3]:
        print(s.get('state'), '|', s.get('description', ''))
"
```

### Interpreting results

| State | Meaning | Action |
|-------|---------|--------|
| `pending` | Build queued or running | Wait and re-check |
| `succeeded` | Build passed | Apply fixes to branch |
| `failed` | Build failed | Read error from user or check ADO UI |

---

## Step 4 — If build not queued after 3 minutes

The CI YAML only triggers on push. Verify the push succeeded:

```bash
cd /Users/andreperez/TFIOneGit
git log --oneline origin/feature/14-education-module -3
```

If the branch exists on remote, the build was triggered. ADO can take 2-5 minutes to queue.

---

## Step 5 — If build failed — common causes

### Flyway incremental migration error

**Symptom**:
```
ERROR: Detected applied migration not resolved locally: 1.0.YYYYMMDD.XXXXX.X
```

**Cause**: The QA bacpac contains migrations from other branches merged to dev.
They were applied to the DB but don't exist in the current branch's migration folder.

**Fix** — add `-ignoreMigrationPatterns="*:missing"` to the incremental Flyway command in `com.tfione.ci/azure_gated_build.yml`:

```yaml
docker run --rm --network host ... redgate/flyway \
  -url="..." \
  -user="sa" \
  -password="$(sql_sa_password)" \
  -outOfOrder="true" \
  -ignoreMigrationPatterns="*:missing" \    ← add this
  migrate
```

Both flags are REQUIRED together:
- `-outOfOrder="true"` — allows running migrations out of sequence
- `-ignoreMigrationPatterns="*:missing"` — ignores bacpac-applied migrations not in our scripts

---

### Flyway 3-part table name error

**Symptom**:
```
Database 'tfi_one' does not exist or access denied
```

**Cause**: A migration file uses `[tfi_one].[schema].[table]` (3-part name with DB prefix).

**Fix**: Remove the database prefix — use `[schema].[table]` only.

```sql
-- WRONG
ALTER TABLE [tfi_one].[file].[FileMetaData] ...

-- CORRECT
ALTER TABLE [file].[FileMetaData] ...
```

---

### Gate build C# errors (StyleCop / nullable)

**Symptom**: Errors like `SA1642`, `SA1611`, `SA1615`, `SA1503`, `CS8618`

**Cause**: The Gate build uses `-WarnAsError`, so StyleCop warnings become errors.

| Code | Rule | Fix |
|------|------|-----|
| `SA1642` | Constructor summary must be `Initializes a new instance of the <see cref="X"/> class.` | Fix XML doc |
| `SA1611` | Parameter missing `<param>` tag | Add `<param>` to all method params |
| `SA1615` | Return value missing `<returns>` tag | Add `<returns>` to non-void methods |
| `SA1503` | Braces required (no braceless `if`) | Add `{ }` |
| `CS8618` | Non-nullable field not initialized | Add `= new HashSet<X>()` in constructor |

---

### Test compilation error

**Symptom**: `Error CS0117: 'X' does not contain a definition for 'Y'`

**Cause**: Test references a model field that was renamed or removed.

**Fix**: Update the test to use the correct field name.

---

### Case-sensitive filename (appsettings.json)

**Symptom**: `MSB3030: Could not copy the file 'appsettings.json' because it was not found`

**Cause**: macOS is case-insensitive (`AppSettings.json` = `appsettings.json`), Linux CI is not.

**Fix**: Ensure the filename in `.csproj` matches exactly (lowercase `appsettings.json`).

---

## Step 6 — After fix: push and re-verify

```bash
cd /Users/andreperez/TFIOneGit
git add <files>
git commit -m "Fix CI: <description>"
git push origin feature/14-education-module

# Wait 2 minutes, then re-check with Step 3
```

---

## ADO Build URL (manual check)

If the build ID is known (from commit status `targetUrl: vstfs:///Build/Build/<ID>`):

```
https://dev.azure.com/FivePointsTechnology/TFIOne/_build/results?buildId=<ID>
```

Open in browser to see full logs when API access is limited.
