#!/usr/bin/env bash
# fivepoints seed-test-data
# Idempotent test-data seeder for local TFI One stack.
#
# Issue #118 — only one user (prime.user) ships with the migrations,
# blocking multi-user testing. This seeds 6 users (3 roles × 2 orgs),
# 4 clients (2 per org), and per-module face-sheet data so the local
# stack mirrors a realistic multi-tenant scenario.
#
# Why a script (not a Flyway migration):
#   - CODING_STANDARDS §10 + DEV_RULES §1 forbid seed data and GRANT/DENY
#     in migrations. Migrations must run cleanly on tfi_one_empty.
#   - This data is for local dev only and must be re-seedable on demand
#     (idempotent INSERTs guarded by IF NOT EXISTS).
#
# Exit codes:
#   0 — all requested sections succeeded
#   1 — at least one section failed
#   2 — invalid argument

set -uo pipefail

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Usage: claire fivepoints seed-test-data [OPTIONS]

Seed local TFI One DB with multi-user test data. Idempotent.

Sections (run in dependency order):
  users      6 AppUsers (3 roles × 2 orgs) — share prime.user's password (Test1234!)
  clients    4 Clients (2 per org), with addresses + aliases
  alerts     1 ClientAlert per client (HOSP)
  allergies  1 Allergy per client (Peanuts)
  education  1 ClientEducation row per client
  legal      1 LegalStatus + 1 LegalAction per client
  medical    1 MedicalFileDiagnosis per client

Options:
  --section <name>      Run a single section. Default: all sections in order.
                        Repeat the flag to run several specific ones.
  --container <name>    Docker container name (default: tfione-sqlserver)
  --database <name>     Target database name (default: tfi_one)
  --dry-run             Print the SQL that would run; do not execute
  --agent-help          Show LLM-optimized help
  -h, --help            Show this help

Test users (all use password 'Test1234!' — same hash as prime.user):
  Org "2Ingage"  →  2ingage.admin (SU), 2ingage.supervisor (CM), 2ingage.caseworker (CPA)
  Org "Empower"  →  empower.admin (SU), empower.supervisor (CM), empower.caseworker (CPA)

Out of scope (intentional — these need Case + CaseWorker chains, larger
follow-up): Intake, HomeStudy, Placement. File a follow-up issue if needed.
EOF
    exit 0
fi

if [[ "${1:-}" == "--agent-help" ]]; then
    cat <<'HELP'
# fivepoints seed-test-data — LLM Agent Guide

## Purpose
Populate the local TFI One DB with multi-user, multi-org test data so manual
QA covers permission-scoping, dashboard filtering, and per-org isolation.
The migrations only ship `prime.user`; that's insufficient — issue #118.

## Usage
```bash
claire fivepoints seed-test-data
claire fivepoints seed-test-data --section users --section clients
claire fivepoints seed-test-data --dry-run
```

## What it inserts
- 2 existing organizations are reused (`2Ingage`, `Empower` — already in the seed)
- 6 AppUsers (3 roles × 2 orgs); password = `Test1234!` (hash copied from prime.user)
- 4 Clients (2 per org) with deterministic GUIDs starting `00010000…`, `00020000…`
- Per-client module data: ClientAlert, Allergy, ClientEducation, LegalStatus,
  LegalAction, MedicalFileDiagnosis

## Idempotency
Every INSERT is guarded by `IF NOT EXISTS (SELECT 1 ...)`. Re-running is safe.
Existing rows are left untouched (no UPDATE).

## Run order matters
`users` → `clients` → everything else. The default (no --section) runs them
in order. Single-section runs assume the dependency was already seeded.

## Pair with smoke-test
Run `claire fivepoints smoke-test` first to confirm the stack is healthy,
then run this to seed the data.
HELP
    exit 0
fi

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

CONTAINER="tfione-sqlserver"
DATABASE="tfi_one"
DRY_RUN=0
SECTIONS=()
ALL_SECTIONS=(users clients alerts allergies education legal medical)

while [[ $# -gt 0 ]]; do
    case $1 in
        --section)    SECTIONS+=("$2"); shift 2 ;;
        --container)  CONTAINER="$2"; shift 2 ;;
        --database)   DATABASE="$2"; shift 2 ;;
        --dry-run)    DRY_RUN=1; shift ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Run with --help for usage." >&2
            exit 2
            ;;
    esac
done

if [[ ${#SECTIONS[@]} -eq 0 ]]; then
    SECTIONS=("${ALL_SECTIONS[@]}")
fi

# Validate
for s in "${SECTIONS[@]}"; do
    found=0
    for valid in "${ALL_SECTIONS[@]}"; do
        [[ "$s" == "$valid" ]] && found=1 && break
    done
    if [[ $found -eq 0 ]]; then
        echo "Unknown section: $s" >&2
        echo "Valid sections: ${ALL_SECTIONS[*]}" >&2
        exit 2
    fi
done

# ---------------------------------------------------------------------------
# Container + SA password resolution
# ---------------------------------------------------------------------------

if ! docker ps --filter "name=^${CONTAINER}\$" --filter 'status=running' --format '{{.Names}}' | grep -q "^${CONTAINER}\$"; then
    echo "❌ Container '${CONTAINER}' is not running." >&2
    echo "   Start it: docker start ${CONTAINER}  (or: claire fivepoints test-env-start)" >&2
    exit 1
fi

SA_PASS=$(docker inspect "$CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
    | awk -F= '$1=="MSSQL_SA_PASSWORD"||$1=="SA_PASSWORD"{print $2; exit}')

if [[ -z "$SA_PASS" ]]; then
    echo "❌ Could not detect SA password from container '${CONTAINER}' env." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# SQL exec helper
# ---------------------------------------------------------------------------

# run_sql <label> <sql>
run_sql() {
    local label="$1"
    local sql="$2"
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "----- DRY-RUN: ${label} -----"
        printf '%s\n' "$sql"
        return 0
    fi
    # -b returns non-zero on SQL errors. -I quoted identifiers on. -j prints raw error text.
    if docker exec -i "$CONTAINER" /opt/mssql-tools18/bin/sqlcmd \
        -S localhost -U sa -P "$SA_PASS" -C -b -I \
        -d "$DATABASE" -Q "$sql" 2>&1; then
        return 0
    else
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Section: users
# ---------------------------------------------------------------------------
# 6 users, 3 roles × 2 orgs. Password copied from prime.user so the same
# 'Test1234!' works for every seeded user. AppUserId GUIDs use a stable
# pattern so re-runs are idempotent and easy to recognize in queries.
#
# UUID convention:
#   AppUser:               00000001-0000-0000-USER-000000000001 .. 0006
#   AppUserOrganization:   00000002-0000-0000-USER-000000000001 .. 0006

seed_users() {
    local sql
    sql=$(cat <<'SQL'
DECLARE @PrimeUserId UNIQUEIDENTIFIER;
DECLARE @PrimePassword NVARCHAR(255);
DECLARE @PrimeSalt NVARCHAR(255);

SELECT TOP 1 @PrimeUserId = AppUserId, @PrimePassword = Password, @PrimeSalt = Salt
FROM sec.AppUser WHERE UserName = 'prime.user';

IF @PrimeUserId IS NULL
BEGIN
    RAISERROR('prime.user not found — migrations not applied?', 16, 1);
    RETURN;
END

DECLARE @Org2IngageId UNIQUEIDENTIFIER =
    (SELECT TOP 1 OrganizationId FROM org.Organization WHERE OrganizationName = '2Ingage' AND Deleted = 0);
DECLARE @OrgEmpowerId UNIQUEIDENTIFIER =
    (SELECT TOP 1 OrganizationId FROM org.Organization WHERE OrganizationName = 'Empower' AND Deleted = 0);

IF @Org2IngageId IS NULL OR @OrgEmpowerId IS NULL
BEGIN
    RAISERROR('Required orgs (2Ingage, Empower) missing — check initial seed data.', 16, 1);
    RETURN;
END

DECLARE @SuperUserRoleId UNIQUEIDENTIFIER =
    (SELECT TOP 1 RoleId FROM sec.Role WHERE RoleName = 'Super User' AND Deleted = 0);
DECLARE @CaseManagerRoleId UNIQUEIDENTIFIER =
    (SELECT TOP 1 RoleId FROM sec.Role WHERE RoleName = 'Case Manager User' AND Deleted = 0);
DECLARE @CpaCaseManagerRoleId UNIQUEIDENTIFIER =
    (SELECT TOP 1 RoleId FROM sec.Role WHERE RoleName = 'CPA Case Manager User' AND Deleted = 0);

DECLARE @Now DATETIME = GETUTCDATE();

DECLARE @Users TABLE (
    AppUserId UNIQUEIDENTIFIER, OrgId UNIQUEIDENTIFIER, RoleId UNIQUEIDENTIFIER,
    UserName NVARCHAR(255), FirstName NVARCHAR(255), LastName NVARCHAR(255), Email NVARCHAR(255)
);
INSERT INTO @Users VALUES
    ('00000001-0000-0000-0001-000000000001', @Org2IngageId, @SuperUserRoleId,      '2ingage.admin',      '2ingage', 'Admin',      '2ingage.admin@example.test'),
    ('00000001-0000-0000-0001-000000000002', @Org2IngageId, @CaseManagerRoleId,    '2ingage.supervisor', '2ingage', 'Supervisor', '2ingage.supervisor@example.test'),
    ('00000001-0000-0000-0001-000000000003', @Org2IngageId, @CpaCaseManagerRoleId, '2ingage.caseworker', '2ingage', 'CaseWorker', '2ingage.caseworker@example.test'),
    ('00000001-0000-0000-0001-000000000004', @OrgEmpowerId, @SuperUserRoleId,      'empower.admin',      'Empower', 'Admin',      'empower.admin@example.test'),
    ('00000001-0000-0000-0001-000000000005', @OrgEmpowerId, @CaseManagerRoleId,    'empower.supervisor', 'Empower', 'Supervisor', 'empower.supervisor@example.test'),
    ('00000001-0000-0000-0001-000000000006', @OrgEmpowerId, @CpaCaseManagerRoleId, 'empower.caseworker', 'Empower', 'CaseWorker', 'empower.caseworker@example.test');

INSERT INTO sec.AppUser
    (AppUserId, Deleted, CreatedDate, CreatedBy, UpdatedDate, UpdatedBy,
     FirstName, LastName, EmailAddress, UserName, Password, Salt,
     Locked, ExternalAuthentication, HasAuthenticatedWithTotp)
SELECT u.AppUserId, 0, @Now, @PrimeUserId, @Now, @PrimeUserId,
       u.FirstName, u.LastName, u.Email, u.UserName, @PrimePassword, @PrimeSalt,
       0, 0, 0
FROM @Users u
WHERE NOT EXISTS (SELECT 1 FROM sec.AppUser WHERE UserName = u.UserName);

INSERT INTO sec.AppUserOrganization
    (AppUserOrganizationId, Deleted, CreatedDate, CreatedBy, UpdatedDate, UpdatedBy,
     AppUserId, OrganizationId, RoleId, [Default])
SELECT
    CAST(CONCAT('00000002-0000-0000-0001-', RIGHT('000000000000' + CAST(ROW_NUMBER() OVER (ORDER BY u.UserName) AS VARCHAR(12)), 12)) AS UNIQUEIDENTIFIER),
    0, @Now, @PrimeUserId, @Now, @PrimeUserId,
    u.AppUserId, u.OrgId, u.RoleId, 1
FROM @Users u
WHERE NOT EXISTS (SELECT 1 FROM sec.AppUserOrganization WHERE AppUserId = u.AppUserId);

DECLARE @CntU INT, @CntAuo INT;
SELECT @CntU = COUNT(*) FROM sec.AppUser
    WHERE UserName LIKE '%ingage%' OR UserName LIKE 'empower%';
SELECT @CntAuo = COUNT(*) FROM sec.AppUserOrganization auo
    JOIN sec.AppUser au ON au.AppUserId = auo.AppUserId
    WHERE au.UserName LIKE '%ingage%' OR au.UserName LIKE 'empower%';
PRINT 'users: AppUser=' + CAST(@CntU AS VARCHAR(10)) + ' AppUserOrganization=' + CAST(@CntAuo AS VARCHAR(10));
SQL
)
    run_sql "users" "$sql"
}

# ---------------------------------------------------------------------------
# Section: clients
# ---------------------------------------------------------------------------
# 4 clients (2 per org), with the minimum NOT-NULL fields. RestrictedId
# self-references the ClientId (matches the existing 'Jane TestClient'
# seed pattern in the migrations).

seed_clients() {
    local sql
    sql=$(cat <<'SQL'
DECLARE @PrimeUserId UNIQUEIDENTIFIER =
    (SELECT TOP 1 AppUserId FROM sec.AppUser WHERE UserName = 'prime.user');
DECLARE @Org2IngageId UNIQUEIDENTIFIER =
    (SELECT TOP 1 OrganizationId FROM org.Organization WHERE OrganizationName = '2Ingage' AND Deleted = 0);
DECLARE @OrgEmpowerId UNIQUEIDENTIFIER =
    (SELECT TOP 1 OrganizationId FROM org.Organization WHERE OrganizationName = 'Empower' AND Deleted = 0);
DECLARE @MaleId UNIQUEIDENTIFIER =
    (SELECT TOP 1 GenderTypeId FROM ref.GenderType WHERE Code = 'male');
DECLARE @FemaleId UNIQUEIDENTIFIER =
    (SELECT TOP 1 GenderTypeId FROM ref.GenderType WHERE Code = 'female');
DECLARE @EthnicityId UNIQUEIDENTIFIER =
    (SELECT TOP 1 EthnicityTypeId FROM ref.EthnicityType ORDER BY Code);
DECLARE @ICWAStatusId UNIQUEIDENTIFIER =
    (SELECT TOP 1 ICWAStatusTypeId FROM ref.ICWAStatusType ORDER BY Code);
DECLARE @StateId UNIQUEIDENTIFIER =
    (SELECT TOP 1 StateTypeId FROM ref.StateType WHERE Code = 'TX');
DECLARE @YesId UNIQUEIDENTIFIER =
    (SELECT TOP 1 YesNoUnknownTypeId FROM ref.YesNoUnknownType WHERE Code = 'no');
DECLARE @AgencyId UNIQUEIDENTIFIER = '22222222-2222-2222-2222-222222222222';
DECLARE @Now DATETIME = GETUTCDATE();
DECLARE @BeginDate DATETIME = '2024-01-01';

DECLARE @Clients TABLE (
    ClientId UNIQUEIDENTIFIER, OrgId UNIQUEIDENTIFIER, GenderId UNIQUEIDENTIFIER,
    PersonNumber NVARCHAR(50), FirstName NVARCHAR(255), LastName NVARCHAR(255), DOB DATETIME
);
INSERT INTO @Clients VALUES
    ('00010000-0000-0000-0001-000000000001', @Org2IngageId, @MaleId,   '2I-0001', 'Alpha',  'TestClient', '2015-04-15'),
    ('00010000-0000-0000-0001-000000000002', @Org2IngageId, @FemaleId, '2I-0002', 'Beta',   'TestClient', '2010-08-22'),
    ('00010000-0000-0000-0002-000000000001', @OrgEmpowerId, @FemaleId, 'EMP-001', 'Gamma',  'TestClient', '2017-02-09'),
    ('00010000-0000-0000-0002-000000000002', @OrgEmpowerId, @MaleId,   'EMP-002', 'Delta',  'TestClient', '2012-11-30');

-- RestrictedId is a computed column (cannot be inserted) — omit from column list.
INSERT INTO client.Client
    (ClientId, Deleted, CreatedDate, CreatedBy, UpdatedDate, UpdatedBy,
     OrganizationId, PersonNumber, FirstName, MiddleName, LastName, DateOfBirth,
     BeginDate, GenderTypeId, EthnicityTypeId, AgencyId, ICWAStatusTypeId,
     StateOfCustodyId, PRTFClient)
SELECT c.ClientId, 0, @Now, @PrimeUserId, @Now, @PrimeUserId,
       c.OrgId, c.PersonNumber, c.FirstName, '', c.LastName, c.DOB,
       @BeginDate, c.GenderId, @EthnicityId, @AgencyId, @ICWAStatusId,
       @StateId, @YesId
FROM @Clients c
WHERE NOT EXISTS (SELECT 1 FROM client.Client WHERE ClientId = c.ClientId);

-- One ClientAlias per client (FirstName/MiddleName/LastName/StartDate columns).
INSERT INTO client.ClientAlias
    (ClientAliasId, Deleted, CreatedDate, CreatedBy, UpdatedDate, UpdatedBy,
     ClientId, FirstName, MiddleName, LastName, StartDate)
SELECT
    CAST(CONCAT('00020000-0000-0000-0000-', RIGHT('000000000000' + CAST(ROW_NUMBER() OVER (ORDER BY c.ClientId) AS VARCHAR(12)), 12)) AS UNIQUEIDENTIFIER),
    0, @Now, @PrimeUserId, @Now, @PrimeUserId,
    c.ClientId, CONCAT('A', c.FirstName), '', CONCAT(c.LastName, '-Alias'), @Now
FROM @Clients c
WHERE NOT EXISTS (SELECT 1 FROM client.ClientAlias WHERE ClientId = c.ClientId);

DECLARE @CntC INT;
SELECT @CntC = COUNT(*) FROM client.Client WHERE LastName = 'TestClient';
PRINT 'clients: Client=' + CAST(@CntC AS VARCHAR(10));
SQL
)
    run_sql "clients" "$sql"
}

# ---------------------------------------------------------------------------
# Section: alerts
# ---------------------------------------------------------------------------

seed_alerts() {
    local sql
    sql=$(cat <<'SQL'
DECLARE @PrimeUserId UNIQUEIDENTIFIER =
    (SELECT TOP 1 AppUserId FROM sec.AppUser WHERE UserName = 'prime.user');
DECLARE @AlertTypeId UNIQUEIDENTIFIER =
    (SELECT TOP 1 ClientAlertTypeId FROM ref.ClientAlertType WHERE Code = 'HOSP');
DECLARE @Now DATETIME = GETUTCDATE();

INSERT INTO client.ClientAlert
    (ClientAlertId, Deleted, CreatedDate, CreatedBy, UpdatedDate, UpdatedBy,
     ClientId, ClientAlertTypeId, StartDate, Description)
SELECT
    NEWID(),
    0, @Now, @PrimeUserId, @Now, @PrimeUserId,
    c.ClientId, @AlertTypeId, @Now, 'Test hospital alert (seed)'
FROM client.Client c
WHERE c.LastName = 'TestClient'
  AND NOT EXISTS (SELECT 1 FROM client.ClientAlert WHERE ClientId = c.ClientId AND ClientAlertTypeId = @AlertTypeId);

DECLARE @CntA INT;
SELECT @CntA = COUNT(*) FROM client.ClientAlert ca
    JOIN client.Client c ON c.ClientId = ca.ClientId
    WHERE c.LastName = 'TestClient';
PRINT 'alerts: ClientAlert=' + CAST(@CntA AS VARCHAR(10));
SQL
)
    run_sql "alerts" "$sql"
}

# ---------------------------------------------------------------------------
# Section: allergies
# ---------------------------------------------------------------------------

seed_allergies() {
    local sql
    sql=$(cat <<'SQL'
DECLARE @PrimeUserId UNIQUEIDENTIFIER =
    (SELECT TOP 1 AppUserId FROM sec.AppUser WHERE UserName = 'prime.user');
DECLARE @Now DATETIME = GETUTCDATE();

INSERT INTO client.Allergy
    (AllergyId, Deleted, CreatedDate, CreatedBy, UpdatedDate, UpdatedBy,
     ClientId, AllergyName, StartDate)
SELECT
    NEWID(),
    0, @Now, @PrimeUserId, @Now, @PrimeUserId,
    c.ClientId, 'Peanuts', @Now
FROM client.Client c
WHERE c.LastName = 'TestClient'
  AND NOT EXISTS (SELECT 1 FROM client.Allergy WHERE ClientId = c.ClientId AND AllergyName = 'Peanuts');

DECLARE @CntAl INT;
SELECT @CntAl = COUNT(*) FROM client.Allergy a
    JOIN client.Client c ON c.ClientId = a.ClientId
    WHERE c.LastName = 'TestClient';
PRINT 'allergies: Allergy=' + CAST(@CntAl AS VARCHAR(10));
SQL
)
    run_sql "allergies" "$sql"
}

# ---------------------------------------------------------------------------
# Section: education
# ---------------------------------------------------------------------------

seed_education() {
    local sql
    sql=$(cat <<'SQL'
DECLARE @PrimeUserId UNIQUEIDENTIFIER =
    (SELECT TOP 1 AppUserId FROM sec.AppUser WHERE UserName = 'prime.user');
DECLARE @Now DATETIME = GETUTCDATE();

INSERT INTO client.ClientEducation
    (ClientEducationId, Deleted, CreatedDate, CreatedBy, UpdatedDate, UpdatedBy, ClientId)
SELECT
    NEWID(),
    0, @Now, @PrimeUserId, @Now, @PrimeUserId, c.ClientId
FROM client.Client c
WHERE c.LastName = 'TestClient'
  AND NOT EXISTS (SELECT 1 FROM client.ClientEducation WHERE ClientId = c.ClientId);

DECLARE @CntE INT;
SELECT @CntE = COUNT(*) FROM client.ClientEducation e
    JOIN client.Client c ON c.ClientId = e.ClientId
    WHERE c.LastName = 'TestClient';
PRINT 'education: ClientEducation=' + CAST(@CntE AS VARCHAR(10));
SQL
)
    run_sql "education" "$sql"
}

# ---------------------------------------------------------------------------
# Section: legal
# ---------------------------------------------------------------------------

seed_legal() {
    local sql
    sql=$(cat <<'SQL'
DECLARE @PrimeUserId UNIQUEIDENTIFIER =
    (SELECT TOP 1 AppUserId FROM sec.AppUser WHERE UserName = 'prime.user');
DECLARE @LegalStatusTypeId UNIQUEIDENTIFIER =
    (SELECT TOP 1 LegalStatusTypeId FROM ref.LegalStatusType ORDER BY Code);
DECLARE @ChildAttendanceTypeId UNIQUEIDENTIFIER =
    (SELECT TOP 1 ChildAttendanceTypeId FROM ref.ChildAttendanceType ORDER BY Code);
DECLARE @LegalActionTypeId UNIQUEIDENTIFIER =
    (SELECT TOP 1 LegalActionTypeId FROM ref.LegalActionType ORDER BY Code);
DECLARE @LegalActionSubTypeId UNIQUEIDENTIFIER =
    (SELECT TOP 1 LegalActionSubTypeId FROM ref.LegalActionSubType ORDER BY Code);
DECLARE @LegalOutcomeTypeId UNIQUEIDENTIFIER =
    (SELECT TOP 1 LegalOutcomeTypeId FROM ref.LegalOutcomeType ORDER BY Code);
DECLARE @Now DATETIME = GETUTCDATE();

INSERT INTO client.LegalStatus
    (LegalStatusId, Deleted, CreatedDate, CreatedBy, UpdatedDate, UpdatedBy,
     ClientId, LegalStatusTypeId, EffectiveDate)
SELECT
    NEWID(),
    0, @Now, @PrimeUserId, @Now, @PrimeUserId,
    c.ClientId, @LegalStatusTypeId, @Now
FROM client.Client c
WHERE c.LastName = 'TestClient'
  AND NOT EXISTS (SELECT 1 FROM client.LegalStatus WHERE ClientId = c.ClientId);

INSERT INTO client.LegalAction
    (LegalActionId, Deleted, CreatedDate, CreatedBy, UpdatedDate, UpdatedBy,
     ClientId, ChildAttendanceTypeId, LegalActionTypeId, LegalActionSubTypeId, LegalOutcomeTypeId, CourtDate)
SELECT
    NEWID(),
    0, @Now, @PrimeUserId, @Now, @PrimeUserId,
    c.ClientId, @ChildAttendanceTypeId, @LegalActionTypeId, @LegalActionSubTypeId, @LegalOutcomeTypeId, @Now
FROM client.Client c
WHERE c.LastName = 'TestClient'
  AND NOT EXISTS (SELECT 1 FROM client.LegalAction WHERE ClientId = c.ClientId);

DECLARE @CntLs INT, @CntLa INT;
SELECT @CntLs = COUNT(*) FROM client.LegalStatus ls
    JOIN client.Client c ON c.ClientId = ls.ClientId WHERE c.LastName = 'TestClient';
SELECT @CntLa = COUNT(*) FROM client.LegalAction la
    JOIN client.Client c ON c.ClientId = la.ClientId WHERE c.LastName = 'TestClient';
PRINT 'legal: LegalStatus=' + CAST(@CntLs AS VARCHAR(10)) + ' LegalAction=' + CAST(@CntLa AS VARCHAR(10));
SQL
)
    run_sql "legal" "$sql"
}

# ---------------------------------------------------------------------------
# Section: medical
# ---------------------------------------------------------------------------

seed_medical() {
    local sql
    sql=$(cat <<'SQL'
DECLARE @PrimeUserId UNIQUEIDENTIFIER =
    (SELECT TOP 1 AppUserId FROM sec.AppUser WHERE UserName = 'prime.user');
DECLARE @Now DATETIME = GETUTCDATE();

INSERT INTO client.MedicalFileDiagnosis
    (DiagnosisId, Deleted, CreatedDate, CreatedBy, UpdatedDate, UpdatedBy,
     ClientId, Diagnosis, StartDate)
SELECT
    NEWID(),
    0, @Now, @PrimeUserId, @Now, @PrimeUserId,
    c.ClientId, 'Test diagnosis (seed)', @Now
FROM client.Client c
WHERE c.LastName = 'TestClient'
  AND NOT EXISTS (SELECT 1 FROM client.MedicalFileDiagnosis WHERE ClientId = c.ClientId);

DECLARE @CntM INT;
SELECT @CntM = COUNT(*) FROM client.MedicalFileDiagnosis m
    JOIN client.Client c ON c.ClientId = m.ClientId
    WHERE c.LastName = 'TestClient';
PRINT 'medical: MedicalFileDiagnosis=' + CAST(@CntM AS VARCHAR(10));
SQL
)
    run_sql "medical" "$sql"
}

# ---------------------------------------------------------------------------
# Run sections in order
# ---------------------------------------------------------------------------

FAILED=()
for section in "${SECTIONS[@]}"; do
    echo ""
    echo "▶ Running section: ${section}"
    case "$section" in
        users)      seed_users      || FAILED+=("$section") ;;
        clients)    seed_clients    || FAILED+=("$section") ;;
        alerts)     seed_alerts     || FAILED+=("$section") ;;
        allergies)  seed_allergies  || FAILED+=("$section") ;;
        education)  seed_education  || FAILED+=("$section") ;;
        legal)      seed_legal      || FAILED+=("$section") ;;
        medical)    seed_medical    || FAILED+=("$section") ;;
    esac
done

echo ""
if [[ ${#FAILED[@]} -eq 0 ]]; then
    echo "✅ All sections succeeded."
    exit 0
else
    echo "❌ ${#FAILED[@]} section(s) failed: ${FAILED[*]}"
    exit 1
fi
