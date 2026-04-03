---
keywords: [database, efcore, tfionecontext, sql-server, flyway, migrations, schemas, soft-delete, global-query-filter, entities, orm]
---

# TFI One — Database Layer (`com.tfione.db`)

**ORM**: Entity Framework Core 8.0
**Database**: SQL Server
**Migrations**: Flyway (external, SQL-based — not EF migrations)
**Entities**: 179+ ORM classes

---

## DbContext

### TfiOneContext (Main Context)

```csharp
public class TfiOneContext : DbContext
{
    // 179+ DbSet<T> properties
    // Interceptors: AuditInterceptor, MetadataInterceptor
    // Global query filter: IDeletable → WHERE Deleted = false
}
```

```csharp
AddDbContextPool<TfiOneContext>(options =>
{
    options.UseSqlServer(connectionString);
    options.AddInterceptors(auditInterceptor, metadataInterceptor);
});
```

**Development mode**: `UseInMemoryDatabase("tfione")` when `ASPNETCORE_ENVIRONMENT = "DockerBuild"`.

### DataProtectionKeyContext
Separate context for ASP.NET Core Data Protection encryption keys.

---

## Global Query Filter (Auto Soft Delete)

```csharp
foreach (var entityType in modelBuilder.Model.GetEntityTypes())
{
    if (typeof(IDeletable).IsAssignableFrom(entityType.ClrType))
    {
        // Applies: WHERE Deleted = false
        modelBuilder.Entity(entityType.ClrType)
            .HasQueryFilter(e => !((IDeletable)e).Deleted);
    }
}
```

**Effect**: All queries on `IDeletable` entities automatically filter deleted records. No manual `Where(!x.Deleted)` needed in repos.

---

## 10 SQL Schemas

| Schema | Domain | Key Tables |
|--------|--------|-----------|
| `org` | Organization | Organization, Tenant, IncidentReport |
| `sec` | Security & Auth | AppUser, Role, Permission, DataPermission, RefreshToken, OtpChallenge |
| `ref` | Reference/Lookup | 50+ type tables (StateType, GenderType, etc.) |
| `conf` | Configuration | Menu, Content, ValidationRule, FormSchema |
| `com` | Common | FileMetaDatum, EmailQueue |
| `case` | Case Management | Case, CaseAddress, CaseParticipant, Intake |
| `client` | Client Management | Client, ClientAddress, IntakeClient |
| `agency` | Agency | Agency, AgencyAddress, AgencyAlert |
| `provider` | Provider | Provider, ProviderAddress, HouseholdMember, PhaseHistory |
| `doc` | Documents | DocumentCategory, DocumentDefinition, DocumentSubmission |
| `sp` | Service Provider | ServiceProvider, ServiceProviderContract |

---

## Universal Audit Columns (every table)

```sql
[EntityNameId]  [UNIQUEIDENTIFIER] NOT NULL PRIMARY KEY CLUSTERED DEFAULT NEWSEQUENTIALID(),
[Deleted]       [bit]              NOT NULL,
[CreatedDate]   [datetime]         NOT NULL,
[CreatedBy]     [UNIQUEIDENTIFIER] NOT NULL,
[UpdatedDate]   [datetime]         NOT NULL,
[UpdatedBy]     [UNIQUEIDENTIFIER] NOT NULL,
[DeletedDate]   [datetime]         NULL,
[DeletedBy]     [UNIQUEIDENTIFIER] NULL,
```

- Present on **every single table** (179+)
- `DeletedDate` / `DeletedBy` nullable (only set on soft delete)
- `CreatedBy` / `UpdatedBy` are GUIDs referencing AppUser (not FK — just value copy)

---

## Primary Key Pattern

```sql
[EntityNameId] [UNIQUEIDENTIFIER] NOT NULL PRIMARY KEY CLUSTERED DEFAULT NEWSEQUENTIALID()
```

- Always `UNIQUEIDENTIFIER` (never `int IDENTITY`)
- Always `PRIMARY KEY CLUSTERED`
- Always `NEWSEQUENTIALID()` (sequential GUIDs for index performance)
- Named `{EntityName}Id` in singular form

---

## Foreign Key Naming

Every FK, PK, UQ, and CHECK constraint MUST have an explicit name. Never rely on auto-generated constraint names.

```sql
-- WRONG (no explicit name):
FOREIGN KEY ([OrganizationId]) REFERENCES [org].[Organization]([OrganizationID])

-- CORRECT (explicit name):
CONSTRAINT [FK_TypeName_Organization] FOREIGN KEY ([OrganizationId])
    REFERENCES [org].[Organization] ([OrganizationID])
```

Naming conventions:
- `FK_{ChildTable}_{ParentTable}` — standard FK
- `FK_{ChildTable}_{ParentTable}_{Column}` — when multiple FKs to the same table

Examples:
- `FK_Provider_Organization`
- `FK_Agency_FinancialAccountType`
- `FK_DocumentDefinition_DocumentCategory`
- `FK_ClientEducation_YesNoType_IEP` — disambiguated by column

---

## Reference Table Pattern

All in `ref` schema. Every `ref.*` table MUST follow this exact template:

```sql
CREATE TABLE [ref].[TypeName](
    [TypeNameId]      [uniqueidentifier] NOT NULL PRIMARY KEY CLUSTERED DEFAULT NEWSEQUENTIALID(),
    [Deleted]         [bit]              NOT NULL,
    [CreatedDate]     [datetime]         NOT NULL,
    [CreatedBy]       [uniqueidentifier] NOT NULL,
    [UpdatedDate]     [datetime]         NOT NULL,
    [UpdatedBy]       [uniqueidentifier] NOT NULL,
    [DeletedDate]     [datetime]         NULL,
    [DeletedBy]       [uniqueidentifier] NULL,
    [OrganizationId]  [uniqueidentifier] NULL,
    [Code]            [nvarchar](10)     NOT NULL,
    [Description]     [nvarchar](100)    NOT NULL,
    CONSTRAINT [FK_TypeName_Organization] FOREIGN KEY ([OrganizationId])
        REFERENCES [org].[Organization] ([OrganizationID])
);
```

**Mandatory rules:**
- All 8 audit columns are required (Deleted, CreatedDate/By, UpdatedDate/By, DeletedDate/By)
- Use `Deleted bit` for soft delete — NEVER `Active bit`
- No `SortOrder` column (not part of the pattern)
- `Code` is `nvarchar(10)`, `Description` is `nvarchar(100)`
- `OrganizationId` MUST be `NULL` (nullable) — see below

### OrganizationId Nullability in Ref Tables

`OrganizationId` in reference tables MUST be nullable (`NULL`):
- `NULL` = shared across all organizations (default seed data)
- Has a value = organization-specific override
- NEVER `NOT NULL` — this would force duplicating ref data per org

### YesNo / YesNoUnknown FK Pattern

**NEVER use `bit` columns for user-selectable boolean values.** Instead, use FKs to reference tables:

- `ref.YesNoType` — for Yes/No choices
- `ref.YesNoUnknownType` — for Yes/No/Unknown choices

```sql
-- WRONG:
[IEP] [bit] NULL,

-- CORRECT:
[IEPTypeId] [uniqueidentifier] NULL,
CONSTRAINT [FK_ClientEducation_YesNoType_IEP] FOREIGN KEY ([IEPTypeId])
    REFERENCES [ref].[YesNoType] ([YesNoTypeID])
```

**Why:** Reference data is consistent, translatable, auditable, and doesn't require GUID-to-bool translation in the application layer.

### Summary

C# interface: `IReference { Guid Id; string Code; string Description; bool Deleted; }`
Table name suffix: always `Type` (GenderType, StateType, ProviderStatusType)

**50+ reference tables**: StateType, CountyType, GenderType, EthnicityType, RaceType, AddressType, ProviderStatusType, ClientStatusType, CaseRoleType, HouseholdMemberRoleType, BackgroundCheckType, TrainingType, PlacementRateType, YesNoType, YesNoUnknownType, etc.

---

## Address Sub-Table Pattern

Every addressable entity has a `{Entity}Address` table:

```sql
[StreetLine1]  [nvarchar](100) NOT NULL,
[StreetLine2]  [nvarchar](100) NULL,
[City]         [nvarchar](50)  NOT NULL,
[StateTypeId]  [UNIQUEIDENTIFIER] NOT NULL,   -- FK → ref.StateType
[CountyTypeId] [UNIQUEIDENTIFIER] NULL,       -- FK → ref.CountyType
[ZipCode]      [nvarchar](10)  NOT NULL,      -- ZIP+4 format
[IsDefault]    [bit]           NOT NULL,      -- Primary address flag
[StartDate]    [datetime]      NOT NULL,
[EndDate]      [datetime]      NULL,          -- null = current
```

Address tables: AgencyAddress, ProviderAddress, CaseAddress, ClientAddress, CaseParticipantAddress, ServiceProviderAddress.

---

## String Length Standards

| Field Type | Length | Examples |
|-----------|--------|---------|
| Names | `nvarchar(50)` | FirstName, LastName, City |
| Entity Names | `nvarchar(100-150)` | AgencyName(100), ProviderName(150) |
| Email | `nvarchar(100)` | EmailAddress |
| Phone | `nvarchar(50)` | PhonePrimary, PhoneSecondary |
| Street | `nvarchar(100)` | StreetLine1, StreetLine2 |
| Zip | `nvarchar(10)` | ZipCode |
| SSN | `nvarchar(50)` | Ssn (encrypted, so larger) |
| Code (ref) | `nvarchar(10)` | Code |
| Description (ref) | `nvarchar(100)` | Description |
| Document name | `nvarchar(254)` | DocumentName, FormName |
| Comments | `nvarchar(2000)` | Comment |
| Notes | `nvarchar(4000)` | Notes |
| Long text | `nvarchar(max)` | Message, JSON data |

---

## DB Interfaces

| Interface | Purpose |
|-----------|---------|
| `IDeletable` | Soft delete (`Deleted` bit, `DeletedDate`, `DeletedBy`) |
| `IReference` | Lookup tables (Code, Description, Deleted) |
| `IOrganizationalReference` | Multi-tenant (OrganizationId nullable) |
| `IOrganizationalEntity` | Org-scoped business entities |
| `IChildReference` | Parent-child lookups (ParentId) |
| `IRestrictedQuery` | Row-level security (RestrictedId, OrganizationId) |
| `IAuditable` | Marker for AuditInterceptor tracking |

---

## Complex Entity Relationships

### Provider (richest entity)
```
Provider
├── ProviderAddress (N)
├── ProviderAlert (N)
├── ProviderAgencyHistory (N)
├── ProviderWorker (N)
├── HouseholdMember (N)
│   ├── HouseholdMemberRace (N)
│   ├── HouseholdMemberBackgroundCheck (N)
│   ├── HouseholdMemberTraining (N)
│   └── ProviderPet (N) → ProviderPetVaccination (N)
├── PhaseHistory (N) → PhaseWithdrawal (N)
└── PlacementAdjustment (1)
```

### Client (intake-driven)
```
Client
├── ClientAddress (N)
├── ClientDocumentRequirement (N) → Submission (N)
├── ClientProgramEnrollment (N)
└── IntakeClient → Intake
    ├── IntakeCaseParticipant (N)
    └── Case → CaseAddress, CaseParticipant, CaseRole
```

---

## Migration Strategy

**Tool**: Flyway (not EF Core migrations)
**Location**: `com.tfione.db/migration/`
**Naming**: `V{Major}.{Minor}.{Date}.{Seq}.{SubSeq}__{description}.sql`

Flyway tracks applied migrations in `FlywaySchemaHistory` table.

---

## Data Seeding Pattern

```sql
DECLARE @PrimeUserId UNIQUEIDENTIFIER = '892e261f-f2a1-4217-8f3c-027a6a4519cc';

INSERT INTO [ref].[StateType] (
    [Deleted], [CreatedDate], [CreatedBy], [UpdatedDate], [UpdatedBy],
    [Code], [Description]
) VALUES (
    0, GETDATE(), @PrimeUserId, GETDATE(), @PrimeUserId,
    'AK', 'Alaska'
);
```

- No explicit IDs — `NEWSEQUENTIALID()` generates them
- `Deleted = 0` always in seed data
- `CreatedDate = UpdatedDate = GETDATE()`

---

## Adding ORM Entities Manually

Most entities are scaffolded via `dotnet ef dbcontext scaffold`. When adding new entities manually:

### StyleCop Rules for `com.tfione.db.orm`

`GlobalSuppressions.cs` suppresses `SA1600` (XML docs) and `SA1101` (`this.` prefix) for the whole `com.tfione.db.orm` namespace. **SA1516 (blank line between elements) is NOT suppressed** — it must be satisfied manually.

```csharp
// Every property must have a blank line before it
public partial class ClientEducation : IDeletable
{
    public ClientEducation()
    {
        // init collections
    }

    public Guid ClientEducationId { get; set; }

    public bool Deleted { get; set; }

    public DateTime CreatedDate { get; set; }

    // ... every property separated by blank line

    public virtual Client Client { get; set; } = null!;
}
```

### TfiOneContext Registration

1. Add `DbSet<T>` property (blank-line separated, alphabetical)
2. Add entity configuration in `OnModelCreatingPartial`:

```csharp
modelBuilder.Entity<ClientEducation>(entity =>
{
    entity.ToTable("ClientEducation");
    entity.HasKey(e => e.ClientEducationId);
    entity.Property(e => e.ClientEducationId).HasDefaultValueSql("newsequentialid()");
    entity.HasOne(d => d.Client)
        .WithMany(p => p.ClientEducations)
        .HasForeignKey(d => d.ClientId)
        .OnDelete(DeleteBehavior.ClientSetNull);
});
```

3. Add back-reference collection on the parent entity.
