---
keywords: [five-points, tfi-one, code-patterns, templates, crud, controllers, models, frontend]
---

# Fivepoints Code Patterns — Definitive Reference

**Date:** 2026-02-28
**Branch:** `feature/14-education-module`
**Purpose:** Canonical reference for all code patterns. Any new module MUST follow these conventions.

---

## Table of Contents

1. [Backend — Controller](#1-backend--controller)
2. [Backend — ORM Entities](#2-backend--orm-entities)
3. [Backend — Models (The Quartet)](#3-backend--models-the-quartet)
4. [Backend — Repository](#4-backend--repository)
5. [Backend — Mappings](#5-backend--mappings)
6. [Backend — Permissions](#6-backend--permissions)
7. [Backend — Validation](#7-backend--validation)
8. [Database — Migrations](#8-database--migrations)
9. [Frontend — Components](#9-frontend--components)
10. [Frontend — RTK Query Services](#10-frontend--rtk-query-services)
11. [Frontend — Routing](#11-frontend--routing)
12. [Frontend — Forms & Validation](#12-frontend--forms--validation)
13. [Frontend — Shared Components (Tfio*)](#13-frontend--shared-components-tfio)
14. [Frontend — State Management](#14-frontend--state-management)
15. [Frontend — Hooks](#15-frontend--hooks)
16. [Quick Checklist — New Module](#quick-checklist--new-module)

---

## 1. Backend — Controller

**Location:** `com.tfione.api/{module}/`

### 1.1 Class Declaration

Every controller inherits from `BaseController` which provides `[ApiController]` + `[Authorize]`.

```csharp
[Route("providers")]
public class ProviderController : BaseController
{
    private readonly ILogger<ProviderController> logger;
    private readonly IProviderRepo repo;

    public ProviderController(ILogger<ProviderController> logger, IProviderRepo repo)
    {
        _ = logger ?? throw new ArgumentNullException(nameof(logger));
        _ = repo ?? throw new ArgumentNullException(nameof(repo));
        this.logger = logger;
        this.repo = repo;
    }
}
```

**Rules:**
- Route: `[Route("lowercase-kebab-case")]` at class level
- Fields: `private readonly`, injected via constructor
- Null guard: `_ = x ?? throw new ArgumentNullException(nameof(x));`
- Always use `this.` prefix

### 1.2 HTTP Verb Convention (CRUD)

| Operation | Verb | Route | Example |
|-----------|------|-------|---------|
| Search | `[HttpGet]` | Root or `"{parentId:guid}/children"` | `SearchProviders([FromQuery] model)` |
| Get single | `[HttpGet]` | `"{id:guid}"` | `GetProvider(Guid id)` |
| View (read-only) | `[HttpGet]` | `"{id:guid}/view"` | `ViewProvider(Guid id)` |
| Create | `[HttpPost]` | Root or `"{parentId:guid}/children"` | `CreateProvider(model)` |
| Update | `[HttpPut]` | `"{id:guid}"` | `UpdateProvider(Guid id, model)` |
| Delete | `[HttpDelete]` | `"{id:guid}"` | `DeleteProvider(Guid id)` |

**IMPORTANT:** Create uses POST, Update uses PUT. Never merge both into a single POST.

### 1.3 Nested Resource Routes

Child entities are scoped under the parent ID:

```csharp
[HttpGet("{providerId:guid}/alerts")]
public async Task<ActionResult<ProviderAlertSearchModel>> SearchProviderAlerts(
    Guid providerId, [FromQuery] ProviderAlertSearchModel model)

[HttpGet("{providerId:guid}/alerts/{id:guid}")]
public async Task<ActionResult<ProviderAlertEditModel>> GetProviderAlert(Guid providerId, Guid id)

[HttpPost("{providerId:guid}/alerts")]
public async Task<ActionResult<ProviderAlertEditModel>> CreateProviderAlert(ProviderAlertEditModel model)

[HttpPut("{providerId:guid}/alerts/{id:guid}")]
public async Task<ActionResult<ProviderAlertEditModel>> UpdateProviderAlert(
    Guid providerId, Guid id, ProviderAlertEditModel model)

[HttpDelete("{providerId:guid}/alerts/{id:guid}")]
public async Task<ActionResult<bool>> DeleteProviderAlert(Guid providerId, Guid id)
```

### 1.4 XML Doc Comments

Every endpoint must have full XML documentation:

```csharp
/// <summary>
/// Searches for providers with given search terms.
/// </summary>
/// <param name="model">Model containing search terms.</param>
/// <returns>Results of providers that match given terms.</returns>
[HttpGet]
public async Task<ActionResult<ProviderSearchModel>> SearchProviders(...)
```

### 1.5 Response Pattern

No custom wrapper. All endpoints return `ActionResult<T>` with `this.Ok(model)`. Business errors are communicated via `model.Messages` (see [4.5 Access-Denied Pattern](#45-access-denied-pattern)).

---

## 2. Backend — ORM Entities

**Location:** `com.tfione.db/orm/`

### 2.1 Three Entity Archetypes

| Type | Interfaces | When |
|------|-----------|------|
| **Core entity** (Client, Provider) | `IDeletable, IOrganizationalReference, IRestrictedQuery` | Top-level domain entities needing row-level security |
| **Child entity** (ProviderAlert, ClientEnrollment) | `IDeletable` | Sub-records of a core entity |
| **Reference/Lookup** (GenderType, StateType) | `IDeletable, IOrganizationalReference, IReference` | Dropdown/lookup tables |

### 2.2 Interface Definitions

```csharp
// Every entity
public interface IDeletable {
    bool Deleted { get; set; }
}

// Entities with org-scoping
public interface IOrganizationalReference {
    public Guid? OrganizationId { get; }
}

// Entities needing row-level security queries
public interface IRestrictedQuery {
    public Guid RestrictedId { get; }
    public Guid OrganizationId { get; }
    public bool Deleted { get; set; }
}

// Lookup/reference tables
public interface IReference {
    public Guid Id { get; }
    public string Code { get; }
    public string Description { get; }
    public bool Deleted { get; set; }
}
```

### 2.3 Standard Audit Fields (7 columns, every table)

```csharp
public bool Deleted { get; set; }
public DateTime CreatedDate { get; set; }
public Guid CreatedBy { get; set; }
public DateTime UpdatedDate { get; set; }
public Guid UpdatedBy { get; set; }
public DateTime? DeletedDate { get; set; }
public Guid? DeletedBy { get; set; }
```

### 2.4 Entity Class Template

```csharp
public partial class ProviderAlert : IDeletable
{
    // PK: always {EntityName}Id
    public Guid ProviderAlertId { get; set; }

    // Audit fields (always in this order)
    public bool Deleted { get; set; }
    public DateTime CreatedDate { get; set; }
    public Guid CreatedBy { get; set; }
    public DateTime UpdatedDate { get; set; }
    public Guid UpdatedBy { get; set; }
    public DateTime? DeletedDate { get; set; }
    public Guid? DeletedBy { get; set; }

    // FK + business fields
    public Guid ProviderId { get; set; }
    public string Description { get; set; } = null!;

    // Navigation properties
    public virtual Provider Provider { get; set; } = null!;         // Required FK
    public virtual AppUser? CreatedByUser { get; set; }              // Optional FK
}
```

### 2.5 Constructor (Collection Initialization)

```csharp
public Client()
{
    ClientAddresses = new HashSet<ClientAddress>();
    ClientDocumentRequirements = new HashSet<ClientDocumentRequirement>();
    IncidentReports = new HashSet<IncidentReport>();
}
```

Collections use `HashSet<T>`. Navigation collections are `virtual ICollection<T>`.

### 2.6 Boolean Fields

Rule: Always `bool` (NOT NULL), never `bool?` (nullable). Booleans represent Yes/No, not Yes/No/Unknown.

---

## 3. Backend — Models (The Quartet)

**Location:** `com.tfione.model/{module}/`

### 3.1 Four Model Types per Entity

| Model | Inherits | Purpose |
|-------|----------|---------|
| `{Entity}SearchModel` | `BaseSearchModel` | Search filters + paginated results + dropdown lookups |
| `{Entity}ListModel` | _(none)_ | Single grid row data |
| `{Entity}EditModel` | `BaseModel` | Form data for create/update + dropdown lookups |
| `{Entity}ViewModel` | _(none or BaseModel)_ | Read-only display with resolved FK descriptions |

### 3.2 BaseModel

```csharp
public class BaseModel
{
    public BaseModel() { this.Messages = []; }
    public List<ModelMessageModel> Messages { get; set; }
}
```

`Messages` carries business errors, access-denied messages, and info to the frontend.

### 3.3 BaseSearchModel

```csharp
public class BaseSearchModel : BaseModel
{
    public BaseSearchModel()
    {
        this.Length = 20;
        this.Start = 0;
        this.RecordCount = 20;
    }
    public string? Search { get; set; }
    public string? Sort { get; set; }
    public string? SortDirection { get; set; }
    public int Start { get; set; }
    public int Length { get; set; }
    public int RecordCount { get; set; }
}
```

### 3.4 SearchModel Template

```csharp
/// <summary>
/// Search model for provider alerts.
/// </summary>
public class ProviderAlertSearchModel : BaseSearchModel
{
    public ProviderAlertSearchModel()
    {
        this.List = new List<ProviderAlertListModel>();
    }

    /// <summary>Provider FK for scoping.</summary>
    public Guid ProviderId { get; set; }

    /// <summary>Search results.</summary>
    public List<ProviderAlertListModel> List { get; set; }
}
```

### 3.5 EditModel Template

```csharp
/// <summary>
/// Edit model for provider alerts.
/// </summary>
public class ProviderAlertEditModel : BaseModel
{
    public ProviderAlertEditModel()
    {
        this.Description = string.Empty;
        this.ProviderAlertTypes = new List<LookupOptionModel>();
    }

    /// <summary>Unique identifier.</summary>
    public Guid ProviderAlertId { get; set; }
    public Guid ProviderId { get; set; }
    public string Description { get; set; }
    public DateTime BeginDate { get; set; }

    // Dropdown options populated by repo
    public List<LookupOptionModel> ProviderAlertTypes { get; set; }
}
```

**Rules:**
- Constructor initializes `List<>` collections and default strings
- Required DB fields map to non-nullable model properties
- Dropdown options are `List<LookupOptionModel>`
- Every class and property has XML doc comments
- Never use `[NotMapped]` on Model, ViewModel, EditModel, or SearchModel classes. `[NotMapped]` is an EF Core attribute for ORM entity classes only (`com.tfione.db/orm/`). Using it on DTO classes is meaningless and misleading.

### 3.6 LookupOptionModel

```csharp
public class LookupOptionModel
{
    public Guid Id { get; set; }
    public string? Code { get; set; }
    public string? Value { get; set; }
    public string? Text { get; set; }
}
```

Used everywhere for dropdown data.

---

## 4. Backend — Repository

**Location:** `com.tfione.repo/{module}/`

### 4.1 Constructor (Standard DI)

```csharp
public class ProviderRepo : IProviderRepo
{
    private readonly TfiOneContext tfiOneContext;
    private readonly IRestrictedQueryProvider rqProvider;
    private readonly IUserAccessor userAccessor;
    private readonly IContentProvider contentProvider;
    private readonly IReferenceProvider referenceProvider;

    public ProviderRepo(
        TfiOneContext tfiOneContext,
        IRestrictedQueryProvider rqProvider,
        IUserAccessor userAccessor,
        IContentProvider contentProvider,
        IReferenceProvider referenceProvider)
    {
        _ = tfiOneContext ?? throw new ArgumentNullException(nameof(tfiOneContext));
        _ = rqProvider ?? throw new ArgumentNullException(nameof(rqProvider));
        // ...
        this.tfiOneContext = tfiOneContext;
        this.rqProvider = rqProvider;
        // ...
    }
}
```

### 4.2 RestrictedQuery Pattern (MANDATORY)

**Every data access MUST start with:**

```csharp
var basequery = this.rqProvider.GetRestrictedQuery<Client>();
```

This returns an `IQueryable<T>` pre-filtered by the current user's organizational permissions. Accessing `this.tfiOneContext.SomeEntity` directly bypasses row-level security.

### 4.3 Search Pattern

```csharp
public async Task<ProviderAlertSearchModel> SearchProviderAlerts(
    Guid providerId, ProviderAlertSearchModel model)
{
    // 1. Restricted query
    var basequery = this.rqProvider.GetRestrictedQuery<Provider>();

    // 2. Project into ListModel
    var modelList = from p in basequery
                    where p.ProviderId == providerId
                    select p.ProviderAlerts.Where(a => !a.Deleted)
                    // ... project into ProviderAlertListModel

    // 3. Apply optional filters
    if (!string.IsNullOrEmpty(model.Search))
    {
        modelList = modelList.Where(m =>
            m.Description.ToLower().Contains(model.Search.Trim().ToLower()));
    }

    // 4. Apply paging
    model.RecordCount = await modelList.CountAsync();
    model.List = await modelList
        .Skip(model.Start)
        .Take(model.Length)
        .ToListAsync();

    return model;
}
```

**Rules:**
- Always use `rqProvider.GetRestrictedQuery<>()`
- Apply `.Skip()` / `.Take()` from `BaseSearchModel` properties
- Set `model.RecordCount` before paging
- Filter checks: `!string.IsNullOrEmpty()`, `.Trim().ToLower().Contains()`

### 4.4 Get Single Pattern

```csharp
public async Task<ProviderAlertEditModel> GetProviderAlert(Guid providerId, Guid id)
{
    var basequery = this.rqProvider.GetRestrictedQuery<Provider>();
    var result = await (from p in basequery
                        where p.ProviderId == providerId
                        select p.ProviderAlerts
                            .Where(a => a.ProviderAlertId == id && !a.Deleted)
                            .Select(a => new ProviderAlertEditModel { ... })
                            .FirstOrDefault()
                       ).FirstOrDefaultAsync()
                       ?? new ProviderAlertEditModel();

    // Populate dropdown lookups
    result.ProviderAlertTypes = await this.referenceProvider
        .GetOrgReferences<ProviderAlertType>();

    return result;
}
```

**Rules:**
- `.FirstOrDefaultAsync() ?? new DefaultModel()` — always return a model, never null
- Populate dropdown `List<LookupOptionModel>` via `referenceProvider`

### 4.5 Access-Denied Pattern

```csharp
var basequery = this.rqProvider.GetRestrictedQuery<Provider>();
var hasAccess = await basequery.AnyAsync(p => p.ProviderId == model.ProviderId);
if (!hasAccess)
{
    var content = await this.contentProvider.GetContent(
        "global.access.denied",
        "You do not have permission to access this item.");
    model.Messages.Add(new ModelMessageModel("access-denied", content));
    return model;
}
```

**Rules:**
- No exceptions for business logic — add to `model.Messages` and return
- Content tokens follow `"domain.category.key"` with default fallback
- Use `ModelMessageModel("access-denied", content)` key

### 4.6 Create Pattern

```csharp
public async Task<ProviderAlertEditModel> CreateProviderAlert(ProviderAlertEditModel model)
{
    if (model == null) throw new ArgumentNullException(nameof(model));

    // Access check (see 4.5)
    var basequery = this.rqProvider.GetRestrictedQuery<Provider>();
    var hasAccess = await basequery.AnyAsync(p => p.ProviderId == model.ProviderId);
    if (!hasAccess) { /* add access-denied message, return */ }

    // Create entity and populate
    var dbModel = new ProviderAlert();
    dbModel = this.PopulateProviderAlert(model, dbModel);

    await this.tfiOneContext.ProviderAlerts.AddAsync(dbModel);
    await this.tfiOneContext.SaveChangesAsync();
    return model;
}
```

### 4.7 Update Pattern

```csharp
public async Task<ProviderAlertEditModel> UpdateProviderAlert(
    Guid providerId, Guid id, ProviderAlertEditModel model)
{
    var basequery = this.rqProvider.GetRestrictedQuery<Provider>();
    var dbModel = await (from p in basequery
                         where p.ProviderId == providerId
                         select p.ProviderAlerts.FirstOrDefault(
                             a => a.ProviderAlertId == id && !a.Deleted))
                        .FirstOrDefaultAsync();

    if (dbModel == null)
    {
        // Access-denied pattern (see 4.5)
        return model;
    }

    dbModel = this.PopulateProviderAlert(model, dbModel);
    await this.tfiOneContext.SaveChangesAsync();
    return model;
}
```

### 4.8 Delete Pattern (Soft Delete)

```csharp
public async Task<bool> DeleteProviderAlert(Guid providerId, Guid id)
{
    var basequery = this.rqProvider.GetRestrictedQuery<Provider>();
    var dbModel = await (from p in basequery
                         where p.ProviderId == providerId
                         select p.ProviderAlerts.FirstOrDefault(
                             a => a.ProviderAlertId == id && !a.Deleted))
                        .FirstOrDefaultAsync();

    if (dbModel != null && !dbModel.Deleted)
    {
        dbModel.Deleted = true;
        dbModel.DeletedDate = DateTime.UtcNow;
        dbModel.DeletedBy = this.userAccessor.UserId;
    }

    await this.tfiOneContext.SaveChangesAsync();
    return dbModel != null ? dbModel.Deleted : false;
}
```

**Rules:**
- Never physically delete. Always soft-delete.
- Every soft-delete method MUST set ALL THREE fields explicitly: `Deleted = true`, `DeletedDate = DateTime.UtcNow`, `DeletedBy = this.userAccessor.UserId`. Omitting any field is a bug.

### 4.8.1 Deleted Filter in Get and View Queries

Every `Get` and `View` repository method MUST filter out deleted records:

```csharp
// CORRECT — filter applied in Get query
.Where(a => a.ProviderAlertId == id && !a.Deleted)

// WRONG — deleted records are fetchable
.Where(a => a.ProviderAlertId == id)
```

**Rule:** `Search` queries filter `!entity.Deleted` via the restricted query provider. `Get` and `View` queries MUST apply this filter explicitly — they do NOT benefit from the provider's automatic filter.

### 4.9 Interface Method Signatures

```csharp
public interface IProviderRepo
{
    Task<ProviderAlertSearchModel> SearchProviderAlerts(Guid providerId, ProviderAlertSearchModel model);
    Task<ProviderAlertEditModel> GetProviderAlert(Guid providerId, Guid id);
    Task<ProviderAlertViewModel> ViewProviderAlert(Guid providerId, Guid id);
    Task<ProviderAlertEditModel> CreateProviderAlert(ProviderAlertEditModel model);
    Task<ProviderAlertEditModel> UpdateProviderAlert(Guid providerId, Guid id, ProviderAlertEditModel model);
    Task<bool> DeleteProviderAlert(Guid providerId, Guid id);
}
```

### 4.10 Key Services

| Service | Interface | Purpose |
|---------|-----------|---------|
| RestrictedQueryProvider | `IRestrictedQueryProvider` | `IQueryable<T>` pre-filtered by org/permissions |
| UserAccessor | `IUserAccessor` | Current user ID, org ID, role from JWT |
| ContentProvider | `IContentProvider` | Localized strings (error messages, labels) |
| ReferenceProvider | `IReferenceProvider` | Dropdown/lookup data from reference tables |

---

## 5. Backend — Mappings

**Location:** `com.tfione.repo/{module}/{Module}Mappings.cs`

The project uses **static `Expression<Func<T, TModel>>` fields** (NOT AutoMapper profiles):

```csharp
public static class ProviderMappings
{
    public static readonly Expression<Func<ProviderAlert, ProviderAlertListModel>>
        ToProviderAlertListModel = dbModel => new ProviderAlertListModel()
    {
        ProviderAlertId = dbModel.ProviderAlertId,
        ProviderAlertType = dbModel.ProviderAlertType != null
            ? dbModel.ProviderAlertType.Description : string.Empty,
        BeginDate = dbModel.BeginDate,
    };
}
```

**Usage in LINQ:**
```csharp
.Select(ProviderMappings.ToProviderAlertListModel)
.ToListAsync();
```

**Rules:**
- Class name: `{Module}Mappings`
- Field name: `To{TargetModelName}`
- Always `static readonly Expression<Func<TSource, TTarget>>`
- Navigate FK relationships in the projection (EF translates to JOINs)

---

## 6. Backend — Permissions

**Location:** `com.tfione.model/enumeration/auth/PermissionCode.cs`

```csharp
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum PermissionCode
{
    ViewUsers,
    CreateUsers,
    UpdateUsers,
    DeleteUsers,
    AccessDocuments,
    ViewDocuments,
    // ...
}
```

**Naming:** `{Verb}{Module}{SubEntity}` in PascalCase. Verbs: `View`, `Access`, `Create`, `Update`, `Delete`, `Manage`, `Edit`.

**Usage on endpoints:**
```csharp
[HttpGet("education-overview/{clientId:guid}")]
[PermissionAuthorize(PermissionCode.AccessClientEducation)]
public async Task<ActionResult<ClientEducationOverviewModel>> GetClientEducationOverview(...)
```

---

## 7. Backend — Validation

Two-tier system: **data-driven** (database rules) + **hard-coded** (FluentValidation).

### 7.1 DI Registration

```csharp
// Hard-coded validators
services.AddScoped<IValidator<ProviderCreateModel>, ProviderCreateModelValidator>();
services.AddValidatorsFromAssemblyContaining<AppUserValidator>();

// Fallback: dynamic validator from DB rules
services.AddScoped(typeof(IValidator<>), typeof(DynamicValidator<>));
```

### 7.2 BaseValidator

```csharp
public abstract class BaseValidator<T> : AbstractValidator<T>
{
    public BaseValidator(
        TfiOneContext context,
        IEncryptor encryptor,
        IUserAccessor userAccessor,
        IValidationRuleProvider validationRuleProvider,
        IContentProvider contentProvider)
    {
        // Applies DB-driven rules automatically
        Task.Run(() => this.ConfigureDataDrivenRules()).GetAwaiter().GetResult();
    }
}
```

Rules stored in the database are applied dynamically via reflection + FluentValidation.

---

## 8. Database — Migrations

**Location:** `com.tfione.db/migration/`

### 8.1 File Naming

`V{major}.{minor}.{YYYYMMDD}.{ticketNumber}.{sequence}__{description}.sql`

Example: `V1.0.20250409.3946.1__provider_alert.sql`

### 8.2 Schema Naming

| Schema | Content |
|--------|---------|
| `[ref]` | Reference/lookup tables |
| `[client]` | Client domain tables |
| `[provider]` | Provider domain tables |
| `[sec]` | Security (users, roles, permissions) |
| `[org]` | Organization |

### 8.3 Reference Table Template

```sql
CREATE TABLE [ref].[ProviderAlertCategoryType]
(
    [ProviderAlertCategoryTypeId] [UNIQUEIDENTIFIER] NOT NULL
        PRIMARY KEY CLUSTERED DEFAULT NEWSEQUENTIALID(),
    [Deleted] [bit] NOT NULL,
    [CreatedDate] [datetime] NOT NULL,
    [CreatedBy] [UNIQUEIDENTIFIER] NOT NULL,
    [UpdatedDate] [datetime] NOT NULL,
    [UpdatedBy] [UNIQUEIDENTIFIER] NOT NULL,
    [DeletedDate] [datetime] NULL,
    [DeletedBy] [UNIQUEIDENTIFIER] NULL,
    [OrganizationId] [UNIQUEIDENTIFIER] NULL,
    [Code] [nvarchar](10) NOT NULL,
    [Description] [nvarchar](100) NOT NULL,
    CONSTRAINT [FK_ProviderAlertCategoryType_Organization]
        FOREIGN KEY ([OrganizationId])
        REFERENCES [org].[Organization] ([OrganizationID])
);
```

**Rules:**
- PK: `[{EntityName}Id] [UNIQUEIDENTIFIER] NOT NULL PRIMARY KEY CLUSTERED DEFAULT NEWSEQUENTIALID()`
- 7 audit columns (always, same order)
- `[Code] [nvarchar](10) NOT NULL`
- `[Description] [nvarchar](100) NOT NULL`
- FK constraint to Organization

### 8.4 Business Entity Table Template

```sql
CREATE TABLE [provider].[ProviderAlert](
    [ProviderAlertId] [UNIQUEIDENTIFIER] NOT NULL
        PRIMARY KEY CLUSTERED DEFAULT NEWSEQUENTIALID(),
    [Deleted] [bit] NOT NULL,
    [CreatedDate] [datetime] NOT NULL,
    [CreatedBy] [UNIQUEIDENTIFIER] NOT NULL,
    [UpdatedDate] [datetime] NOT NULL,
    [UpdatedBy] [UNIQUEIDENTIFIER] NOT NULL,
    [DeletedDate] [datetime] NULL,
    [DeletedBy] [UNIQUEIDENTIFIER] NULL,
    [ProviderId] [UNIQUEIDENTIFIER] NOT NULL,
    [Description] [nvarchar](max) NOT NULL,
    CONSTRAINT [FK_ProviderAlert_Provider]
        FOREIGN KEY ([ProviderId])
        REFERENCES [provider].[Provider] ([ProviderID]),
    CONSTRAINT [FK_ProviderAlert_ProviderAlertType]
        FOREIGN KEY ([ProviderAlertTypeId])
        REFERENCES [ref].[ProviderAlertType] ([ProviderAlertTypeId])
);
```

### 8.5 FK Constraint Naming

`CONSTRAINT [FK_{ChildTable}_{ParentTable}] FOREIGN KEY ([Column]) REFERENCES [schema].[Table] ([Column])`

### 8.6 Seed Data

```sql
-- Use hardcoded prime user GUID
DECLARE @PrimeUserId UNIQUEIDENTIFIER = '892e261f-f2a1-4217-8f3c-027a6a4519cc';

INSERT INTO ref.StateType (
    Deleted, CreatedDate, CreatedBy, UpdatedDate, UpdatedBy,
    Code, Description
) VALUES (
    0, GETDATE(), @PrimeUserId, GETDATE(), @PrimeUserId,
    'TX', 'Texas'
);
```

### 8.7 Global Query Filter (Automatic Soft-Delete)

Defined in `TfiOneContext` partial:

```csharp
partial void OnModelCreatingPartial(ModelBuilder modelBuilder)
{
    foreach (var et in modelBuilder.Model.GetEntityTypes())
    {
        if (typeof(IDeletable).IsAssignableFrom(et.ClrType))
        {
            // Adds: .HasQueryFilter(e => !e.Deleted)
        }
    }
}
```

All queries on `IDeletable` entities automatically exclude soft-deleted records.

---

## 9. Frontend — Components

**Location:** `com.tfione.web/src/components/`

### 9.1 File Naming

All files use **snake_case** with `.tsx` extension:
- `household_member_add_edit.tsx`
- `emergency_contacts_edit.tsx`
- `background_checks.tsx`

### 9.2 Component Declaration

```typescript
const HouseholdMembersAddEdit = (props: HouseholdMembersAddEditProps) => {
    // ...
};

export default HouseholdMembersAddEdit;
```

**Rules:**
- `const` arrow function (never `function` declaration)
- PascalCase component name
- `export default` at end of file

### 9.3 Props Interface

Defined directly above the component:

```typescript
interface HouseholdMembersAddEditProps {
    providerId?: string,
    householdMemberId?: string,
    onCancel: () => void
    mode: 'add' | 'view' | 'edit'
}
```

Named `{ComponentName}Props`.

### 9.4 Form Component Template

```typescript
import { useForm, FormProvider } from 'react-hook-form';
import { fluentValidationResolver } from '@hookform/resolvers/fluentvalidation-ts';
import { useValidationRules } from '../../../../hooks/validation_hook';
import { useTokenizedContent } from '../../../../hooks/content_hook';
import HouseholdMemberValidator from '../../../../validation/householdMember_validator';

const HouseholdMembersAddEdit = (props: HouseholdMembersAddEditProps) => {
    const { getValidationRules } = useValidationRules();
    const { getTokenizedContent: content } = useTokenizedContent();
    const validationRules = getValidationRules('HouseholdMemberEditModel');

    const methods = useForm<HouseholdMemberEditModel>({
        resolver: fluentValidationResolver(
            new HouseholdMemberValidator(validationRules, content)
        ),
        defaultValues: { ... }
    });

    return (
        <FormProvider {...methods}>
            <form onSubmit={methods.handleSubmit(onSubmit)}>
                <TfioTextInput
                    name="lastName"
                    required={true}
                    labelToken="householdMember.lastName.required"
                    labelDefault="Last Name"
                    inputProps={{ disabled: formDisabled }}
                />
            </form>
        </FormProvider>
    );
};
```

---

## 10. Frontend — RTK Query Services

**Location:** `com.tfione.web/src/redux/services/com.tfione.api/`

### 10.1 Service File Template

```typescript
import * as TfiOneTypes from '../../../types/com.tfione.api';
import { api } from './api';

export const providerAlertApi = api.injectEndpoints({
    endpoints: (builder) => ({
        searchProviderAlerts: builder.query<
            TfiOneTypes.ProviderAlertSearchModel,
            { providerId: string; params: object }
        >({
            query: ({ providerId, params }) => ({
                url: `providers/${providerId}/alerts`,
                params,
            }),
            providesTags: (_result, _error, { providerId }) => [
                { type: 'providerAlert', id: providerId }
            ],
        }),

        createProviderAlert: builder.mutation<
            TfiOneTypes.ProviderAlertEditModel,
            TfiOneTypes.ProviderAlertEditModel
        >({
            query: (model) => ({
                url: `providers/${model.providerId}/alerts`,
                method: 'POST',
                body: model,
            }),
            invalidatesTags: (_result, _error, model) => [
                { type: 'providerAlert', id: model.providerId }
            ],
        }),
    }),
});

export const {
    useSearchProviderAlertsQuery,
    useCreateProviderAlertMutation,
} = providerAlertApi;
```

### 10.2 Tag Registration

**File:** `src/redux/services/com.tfione.api/tags.ts`

Every new entity tag must be registered:

```typescript
export const tagTypes = [
    'client',
    'provider',
    'providerAlert',
    'backgroundCheck',
    'clienteducation',    // <-- registered here
    // ...
];
```

### 10.3 Rules

- API slice name: `{entityName}Api`
- Use `builder.query<ReturnType, ArgType>` for GET
- Use `builder.mutation<ReturnType, ArgType>` for POST/PUT/DELETE
- Tag invalidation uses id-scoped tags: `{ type: 'tag', id: parentId }`
- Type imports: `import * as TfiOneTypes from '../../../types/com.tfione.api'`

---

## 11. Frontend — Routing

**Location:** `com.tfione.web/src/router/`

### 11.1 Route Definition Pattern

```typescript
{
    path: 'grade_achieved',
    lazy: async () => {
        const { default: GradeAchievedHistory } = await import(
            '../components/client/face_sheet/education/grade_achieved_history'
        );
        return { Component: GradeAchievedHistory };
    },
}
```

**Rules:**
- Paths use **snake_case** (e.g., `household_members`, `worker_assignment`)
- Components are lazy-loaded via dynamic `import()`
- Routes nest under parent entity: `face_sheet/:clientId/grade_achieved`

---

## 12. Frontend — Forms & Validation

### 12.1 The Full Pipeline

```
DB validation rules
    → useValidationRules() hook (fetches rules from API)
        → Validator class (extends BaseValidator<T>)
            → fluentValidationResolver() (bridges to RHF)
                → useForm({ resolver: ... })
                    → TfioTextInput (shows inline errors)
```

### 12.2 Validator Template

```typescript
import { BaseValidator } from './base_validator';
import { ValidationRuleModel } from '../types/com.tfione.api';

class HouseholdMemberValidator extends BaseValidator<HouseholdMemberEditModel> {
    constructor(rules: ValidationRuleModel[]) {
        super(rules);
        this.configureRules();
    }

    protected configureRules() {
        const { getTokenizedContent: content } = useTokenizedContent();

        this.ruleFor('lastName')
            .notEmpty()
            .withMessage(content('householdMember.lastName.required', 'Last Name is required'));
    }
}

export default HouseholdMemberValidator;
```

### 12.3 Connecting Validator to Form

```typescript
const methods = useForm<EditModel>({
    resolver: fluentValidationResolver(new MyValidator(validationRules)),
    defaultValues: { ... },
});
```

**IMPORTANT:** Never do manual imperative validation in `onSubmit`. Always use the `fluentValidationResolver` pipeline for inline field-level error display.

---

## 13. Frontend — Shared Components (Tfio*)

**Location:** `com.tfione.web/src/components/shared/primitives/`

### 13.1 TfioTextInput

```typescript
interface TfioTextInputProps {
    name: string;
    labelToken: string;        // Content token key
    labelDefault: string;      // Fallback label text
    required?: boolean;
    inputProps?: object;       // Pass { disabled: true } here
    // ...
}

// Usage:
<TfioTextInput
    name="lastName"
    required={true}
    labelToken="householdMember.lastName.required"
    labelDefault="Last Name"
    inputProps={{ disabled: formDisabled }}
/>
```

**IMPORTANT:** Use `labelToken`/`labelDefault`, NOT `label`. Use `inputProps={{ disabled }}`, NOT top-level `disabled`.

### 13.2 TfioDateInput

Same prop pattern as TfioTextInput:

```typescript
<TfioDateInput
    name="dateOfBirth"
    required
    labelToken="householdMember.dateOfBirth.required"
    labelDefault="DOB"
    inputProps={{ disabled: formDisabled }}
/>
```

### 13.3 TfioSelectInput

```typescript
<TfioSelectInput
    name="genderTypeId"
    labelToken="provider.gender"
    labelDefault="Gender"
    options={model?.genderTypes ?? []}
    inputProps={{ disabled: formDisabled }}
/>
```

### 13.4 TfioCheckboxInput

```typescript
<TfioCheckboxInput
    name="iep"
    labelToken="education.iep"
    labelDefault="IEP"
/>
```

### 13.5 TfioDataGrid

```typescript
<TfioDataGrid
    rows={data?.list ?? []}
    columns={columns}
    getRowId={(row) => row.providerAlertId}
    // localeText is provided by default -- do NOT override with hardcoded English
/>
```

**Rule:** Do NOT pass `localeText` with hardcoded strings. The wrapper already provides tokenized defaults.

### 13.6 TfioDialog

```typescript
<TfioDialog
    titletext={content('dialog.title.key', 'Default Title')}
    open={dialogOpen}
    actions={
        <>
            <TfioButton onClick={handleCancel}>
                {content('global.cancel', 'Cancel')}
            </TfioButton>
            <TfioButton onClick={handleSave}>
                {content('global.save', 'Save Changes')}
            </TfioButton>
        </>
    }
>
    {/* Dialog content */}
</TfioDialog>
```

**Rule:** Use `content()` tokens for all user-visible strings, including button labels and titles.

### 13.7 TfioButton vs Button

Use `TfioButton` (from shared primitives), NOT plain `Button` from `@mui/material`.

---

## 14. Frontend — State Management

**Location:** `com.tfione.web/src/redux/`

- **RTK Query** for all API calls (no manual `fetch`/`axios`)
- **Redux Toolkit slices** for local state
- Store configured in `src/redux/store.ts`
- API base configured in `src/redux/services/com.tfione.api/api.ts`

---

## 15. Frontend — Hooks

**Location:** `com.tfione.web/src/hooks/`

| Hook | Purpose | Usage |
|------|---------|-------|
| `useSetMessage()` | Toast notifications | `setMessage('Saved!', 'success')` |
| `useTokenizedContent()` | Localized content strings | `content('key', 'default')` |
| `useValidationRules()` | Fetch DB validation rules | `getValidationRules('ModelName')` |
| `useNavigateBack()` | Back navigation | `navigateBack()` |

---

## Quick Checklist — New Module

Before merging any new module, verify:

### Backend
- [ ] Controller uses POST (create) + PUT (update), not POST-for-everything
- [ ] Routes are nested: `{parentId:guid}/child-resource`
- [ ] XML doc comments complete (`<summary>`, `<param>`, `<returns>`)
- [ ] `[PermissionAuthorize]` on endpoints that need it
- [ ] Repository uses `rqProvider.GetRestrictedQuery<>()` on every query
- [ ] Search methods apply `.Skip()` / `.Take()` from BaseSearchModel
- [ ] Access-denied uses `model.Messages` pattern, not exceptions
- [ ] Soft delete only — `Deleted = true`, never physical delete
- [ ] Models have XML doc comments on class + properties
- [ ] EditModel properties match DB nullability

### Database
- [ ] Migration file name: `V{major}.{minor}.{YYYYMMDD}.{ticket}.{seq}__{desc}.sql`
- [ ] Reference tables: `[Code] nvarchar(10)`, `[Description] nvarchar(100)`
- [ ] FK constraints with `[FK_{Child}_{Parent}]` naming
- [ ] All 7 audit columns present
- [ ] Booleans are `[bit] NOT NULL`
- [ ] Seed data uses hardcoded prime user GUID

### Frontend
- [ ] Components: snake_case files, PascalCase names, `export default`
- [ ] Forms use `fluentValidationResolver` + `useValidationRules()` pipeline
- [ ] Input props: `labelToken`/`labelDefault`, NOT `label`
- [ ] Disabled state via `inputProps={{ disabled }}`, NOT top-level `disabled`
- [ ] `TfioButton` everywhere (not plain MUI `Button`)
- [ ] `TfioDataGrid` without hardcoded `localeText`
- [ ] Dialog strings use `content()` tokens
- [ ] RTK Query tags registered in `tags.ts`
- [ ] Address fields use `WithAddress<>` type + `useGetChildReferencesQuery` for counties (see pattern 17)
- [ ] Add/Edit screens are routed (not modals) — View screens use `TfioModelView` (see pattern 18)
- [ ] Context menus have `onClose` + `aria-haspopup="true"` (see pattern 19)

---

## 17. Frontend — Address Component Pattern

**Canonical reference:** `client_address_addEdit.tsx`

When a model has flat address fields (`addressLine1`, `stateTypeId`, `countyTypeId`, etc.) and uses `TfioAddress`:

### 17.1 Form Type

```tsx
import { WithAddress } from '../../../../types/address.types';

type MyFormModel = WithAddress<MyEditModel, 'addressData'>;
```

### 17.2 Default Values

```tsx
const methods = useForm<MyFormModel>({
    defaultValues: {
        addressData: {
            street1: '',
            street2: '',
            city: '',
            state: CONSTANTS.EMPTY_GUID,
            zipCode: '',
            county: CONSTANTS.EMPTY_GUID,
        },
    },
});
```

### 17.3 County Filtering by State

```tsx
const selectedStateId = useWatch({ control: methods.control, name: 'addressData.state' });
const { data: countyTypes } = useGetChildReferencesQuery(
    selectedStateId && selectedStateId !== CONSTANTS.EMPTY_GUID
        ? { referenceType: 'CountyType', parentId: selectedStateId }
        : skipToken
);
```

**NEVER** use `useGetReferencesQuery('CountyType')` — that returns all ~250 counties unfiltered.

### 17.4 TfioAddress Usage

```tsx
<TfioAddress
    name='addressData'         // MUST match WithAddress key
    showStreet1
    showStreet2
    showCounty
    states={stateTypes}
    counties={countyTypes}     // filtered by state
/>
```

### 17.5 Load (flat → nested)

```tsx
useEffect(() => {
    if (record) {
        methods.reset({
            ...record,
            addressData: {
                street1: record.addressLine1 ?? '',
                street2: record.addressLine2 ?? '',
                city: record.city ?? '',
                state: record.stateTypeId ?? CONSTANTS.EMPTY_GUID,
                zipCode: record.zipCode ?? '',
                county: record.countyTypeId ?? CONSTANTS.EMPTY_GUID,
            },
        } as MyFormModel);
    }
}, [record, methods]);
```

### 17.6 Sync nested → flat (for validation)

```tsx
const addressData = useWatch({ control: methods.control, name: 'addressData' });
useEffect(() => {
    if (addressData) {
        methods.setValue('addressLine1', addressData.street1);
        methods.setValue('addressLine2', addressData.street2 ?? '');
        methods.setValue('city', addressData.city);
        methods.setValue('stateTypeId', addressData.state as any);
        methods.setValue('zipCode', addressData.zipCode);
        methods.setValue('countyTypeId', (addressData.county ?? CONSTANTS.EMPTY_GUID) as any);
    }
}, [addressData, methods]);
```

### 17.7 Submit (nested → flat model)

```tsx
const onSubmit = async (model: MyFormModel) => {
    const submitModel: MyEditModel = {
        ...model,
        addressLine1: model.addressData.street1,
        addressLine2: model.addressData.street2,
        city: model.addressData.city,
        stateTypeId: model.addressData.state as any,
        countyTypeId: (model.addressData.county ?? CONSTANTS.EMPTY_GUID) as any,
        zipCode: model.addressData.zipCode,
    };
    // ...
};
```

---

## 18. Frontend — Routed Screens vs Modals

### Rule

- **Add/Edit forms** → Always routed screens. Use `useParams` + `useNavigateBack`.
- **View/read-only** → Always `TfioModelView`. Create a separate `*_view.tsx` file.
- **`TfioDialog`** → Only for confirmation prompts (delete confirm, etc.).

### Routes Pattern

```tsx
// In router file:
{ path: 'items/add', lazy: async () => ({ Component: (await import('./item_add_edit')).default }) },
{ path: 'items/:itemId/edit', lazy: async () => ({ Component: (await import('./item_add_edit')).default }) },
{ path: 'items/:itemId/view', lazy: async () => ({ Component: (await import('./item_view')).default }) },
```

### Add/Edit Component

```tsx
const ItemAddEdit = () => {
    const { clientId, itemId } = useParams<{ clientId: string; itemId: string }>();
    const navigateBack = useNavigateBack();
    const isAdd = !itemId || itemId === CONSTANTS.EMPTY_GUID;
    // ...
    const onSubmit = async (model) => {
        // ...
        navigateBack();
    };
};
```

### View Component (TfioModelView)

```tsx
const ItemView = () => {
    const { itemId } = useParams<{ itemId: string }>();
    const { data } = useGetItemQuery(itemId ?? skipToken);
    const navigateBack = useNavigateBack();

    const items: ViewItem[] = [
        { label: 'Field Name', value: data?.fieldName },
        // ...
    ];

    return (
        <TfioPageWrapper headerText='View Item'>
            <TfioModelView items={items} />
            <TfioButton onClick={navigateBack}>Go Back</TfioButton>
        </TfioPageWrapper>
    );
};
```

### History/List Component Navigation

```tsx
const handleAdd = () => navigate(`/client/face_sheet/${clientId}/items/add`);
const handleEdit = (row) => navigate(`/client/face_sheet/${clientId}/items/${row.itemId}/edit`);
const handleView = (row) => navigate(`/client/face_sheet/${clientId}/items/${row.itemId}/view`);
```

---

## 19. Frontend — Context Menu (Face Sheet Cards)

MUI `<Menu>` on face sheet cards must be set up correctly or it renders with broken positioning and stays open when clicking outside.

### Correct Pattern

```tsx
const [menuAnchorEl, setMenuAnchorEl] = useState<EventTarget & HTMLButtonElement | null>(null);
const menuOpen = Boolean(menuAnchorEl);

const handleMenuClick = (event: React.MouseEvent<HTMLButtonElement>) => setMenuAnchorEl(event.currentTarget);
const handleMenuClose = () => setMenuAnchorEl(null);

// Trigger button — ALL three aria attributes required:
<IconButton
    id="section-menu-button"
    aria-controls={menuOpen ? 'section-menu' : undefined}
    aria-haspopup="true"                              // MUST be "true", not "false"
    aria-expanded={menuOpen ? 'true' : undefined}
    onClick={handleMenuClick}
>
    <MenuIcon />
</IconButton>

// Menu — onClose required or it never closes:
<Menu
    id="section-menu"
    open={menuOpen}
    anchorEl={menuAnchorEl}
    onClose={handleMenuClose}                         // REQUIRED
    slotProps={{ list: { 'aria-labelledby': 'section-menu-button' } }}
>
    <MenuItem onClick={() => { navigate('/path'); handleMenuClose(); }}>
        Label
    </MenuItem>
</Menu>
```

**Common mistakes:**
- `aria-haspopup="false"` → menu button renders incorrectly
- Missing `onClose` → menu never closes on outside click
- Wrapping `<Menu>` in extra `<>` fragment → DOM positioning breaks

---

## 20. Frontend — Document Deep Links

`ClientDocuments` (`documents.tsx`) supports two query params for pre-expanding a category:

```
/client/face_sheet/:clientId/documents?documentCategoryId=<GUID>     # exact GUID
/client/face_sheet/:clientId/documents?documentCategoryName=Education  # label match
```

Use `documentCategoryId` when you have the GUID (e.g., from API data).
Use `documentCategoryName` when the GUID is org-specific runtime data (e.g., deep linking from a card).
- [ ] Tag invalidation uses id-scoped `{ type, id }`
