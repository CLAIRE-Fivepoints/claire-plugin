---
domain: fivepoints
category: operational
name: TEST_DATA_STAGING
title: "FivePoints — Staging Test Data for FDS Screenshot Verification"
keywords: [test-data, seed, staging, fds-verification, restricted-query-provider, organization-id, prime-user, client-face-sheet, env-blocked, sql-only]
updated: 2026-04-20
related-pr: "CLAIRE-Fivepoints/fivepoints#76"
---

# FivePoints — Staging Test Data for FDS Screenshot Verification

> Use this when step **[9/11]** of the dev pipeline (Screenshot + FDS
> verification) produces **env-blocked** labels — i.e. the code path is
> correct but the page renders empty because the DB has no matching row.
> Example: label 3 "[Client Name - Client ID]" renders as `", -"` and
> label 6 "pending documents alert" never fires.
>
> Historically this has been treated as "code correct, out of scope" and
> shipped with partial FDS proof. That is no longer acceptable — the
> pattern below makes it a **5-minute SQL-only task**, not an agency-chain
> seed project.

---

## When This Applies

- Step **[9/11]** screenshot shows an expected FDS label rendering blank,
  with the API returning `null` / `0 rows` on a route whose code path you
  just wrote.
- The component code is correct (you can see the JSX rendering
  `{client?.lastName}` etc. verbatim per FDS).
- The shape is "the request returns, but the payload is empty" — NOT a
  500, NOT a permission-denied alert.

If the symptom is a 500 or a permission-denied alert, staging test data
will **not** fix it — investigate the endpoint first.

---

## Why `SuperUserPermissionBypass=true` Is Not Enough

The bypass flag skips the permission check. It does **not** skip the
**organization filter** applied on every read by the
`RestrictedQueryProvider`:

```csharp
// com.tfione.service/security/RestrictedQueryProvider.cs:43-46
query = query.Where(x =>
    x.OrganizationId == GetCurrentOrganizationId()
    && x.Deleted == false);
```

If a seeded row's `OrganizationId` does not match the **current
organization** of the authenticated user, the query returns zero rows —
regardless of any bypass flag. This is the single most common reason
test data "does not show up".

---

## The Prime User's Current Organization — How to Find It

⚠️ Do **not** use "the first org in the list" from `dbo.Organization`.
Prime user's current org is chosen at login and is the one used by
`GetCurrentOrganizationId()`.

Get it from the live `/auth/login` response:

```bash
curl -sk -X POST https://localhost:58337/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"userName":"prime.user","password":"Test1234!"}' \
  | jq -r '.currentOrganizationId'
```

As of PR CLAIRE-Fivepoints/fivepoints#76 (2026-04-20) this value is:

```
adfd423e-f36b-1410-8ead-0015e3941933
```

If the dev DB is reset / re-seeded, re-run the `curl` — do not hardcode.

---

## Minimum Seed Set — Client Face Sheet

For the Client Face Sheet page (`/client/face_sheet/:clientId`) to
render all 10 FDS labels, seed in this order:

| Order | Table | Purpose |
|---|---|---|
| 1 | `client.Client` | The client row itself — `OrganizationId` = prime.user's current org |
| 2 | `client.ClientAddress` | Required by dashboard projection `c.ClientAddresses.First().CountyTypeId` — missing row throws |
| 3 | `doc.DocumentDefinition` | Join target for `GetClientDashboardRequirements` |
| 4 | `client.ClientDocumentRequirement` | Must have a past `DueDate` → triggers the pending-docs alert (FDS label 6) |

Different sections of TFI One may need different seed sets — when you
hit a new env-blocked label, trace the failing query, find the missing
join row, and add it to the doc for the next session.

---

## SQL Skeleton (test-env only, never committed)

```sql
-- STEP 0 — capture the target org from /auth/login first (see section above).
-- Replace @orgId with the value you captured; do not hardcode across sessions.
DECLARE @orgId uniqueidentifier = 'adfd423e-f36b-1410-8ead-0015e3941933';

-- STEP 1 — disable FK checks for the session.
-- The Restricted / Agency FK chain has no seed data in the dev DB;
-- enforcing it here would cascade-fail every insert.
EXEC sp_MSforeachtable 'ALTER TABLE ? NOCHECK CONSTRAINT ALL';

-- STEP 2 — seed Client under prime.user's org.
INSERT INTO client.Client (Id, OrganizationId, FirstName, LastName, PersonNumber, Deleted)
VALUES ('11111111-1111-1111-1111-111111111111', @orgId,
        'Jane', 'TestClient', 'TEST-18839', 0);

-- STEP 3 — seed ClientAddress (dashboard projection calls .First() on this collection).
INSERT INTO client.ClientAddress (Id, ClientId, CountyTypeId, Deleted)
VALUES ('AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA',
        '11111111-1111-1111-1111-111111111111',
        (SELECT TOP 1 Id FROM ref.CountyType), 0);

-- STEP 4 — seed DocumentDefinition so the requirements join resolves.
INSERT INTO doc.DocumentDefinition (Id, OrganizationId, Name, Deleted)
VALUES ('55555555-5555-5555-5555-555555555555', @orgId,
        'Test Document — Release of Information', 0);

-- STEP 5 — seed a past-due requirement to trigger the pending-docs alert.
INSERT INTO client.ClientDocumentRequirement
  (Id, ClientId, DocumentDefinitionId, DueDate, Deleted)
VALUES ('44444444-4444-4444-4444-444444444444',
        '11111111-1111-1111-1111-111111111111',
        '55555555-5555-5555-5555-555555555555',
        DATEADD(day, -7, GETUTCDATE()), 0);

-- STEP 6 — re-enable FK checks.
EXEC sp_MSforeachtable 'ALTER TABLE ? WITH CHECK CHECK CONSTRAINT ALL';
```

---

## Hard Rules

- ⚠️ **Never commit the SQL file to the feature branch.** Keep it in
  `~/.claire/scratch/tests/issue-<N>/seed.sql` (per Steven Reviewer's
  no-test-pollution rule). The PR diff must contain zero seed SQL.
- ⚠️ **Seeded rows disappear on DB rebuild** — that is intentional.
  Every Claire session starts from a clean DB; staging is re-applied
  per session.
- ⚠️ **FK-check toggle is test-env only.** Do **not** ship production
  migrations that use `NOCHECK`.
- ⚠️ **Use prime.user's live `currentOrganizationId`.** Do not hardcode
  it across sessions — it can change on DB rebuild.

---

## Re-Screenshot After Staging

After the seed completes:

1. Hard-refresh the browser tab (`Cmd+Shift+R`) — the RTK cache may
   still hold a `null` response.
2. Re-capture the screenshot.
3. Update step **[9/11]** FDS verification comment with the new
   screenshot and flip the label from `⚠️ env-blocked` to `✅ visible`.

---

## Reference

- PR that discovered the pattern: **CLAIRE-Fivepoints/fivepoints#76**
- Comment with the full root cause:
  https://github.com/CLAIRE-Fivepoints/fivepoints/pull/76#issuecomment-4282200207
- Related:
  - `claire domain read fivepoints operational TESTING` — test users, creds, DB config
  - `claire domain read fivepoints operational CHECKLIST_DEV_PIPELINE` — step [9/11]
  - `claire domain read fivepoints technical BACKEND_DATABASE` — schema overview
