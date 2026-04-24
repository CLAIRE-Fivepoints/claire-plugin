---
keywords: [patterns, repository, controller, dto, validation, auth, soft-delete, audit, multi-tenant, encryption, caching, hangfire, naming-conventions, testability, unit-tests, "persona:fivepoints-reviewer"]
---

# TFI One — Design Patterns & Conventions

> **See also**: `fivepoints/operational/CODING_STANDARDS.md` — numbered code review rules (branch discipline, dual validation, StyleCop, CI gate build standards)
> `fivepoints/technical/PATTERNS.md` — architecture overview, feature checklist, naming conventions

---

## 1. Repository Pattern

**Count**: 38 repositories
**Base**: `BaseRepo(TfiOneContext, IUserAccessor)`
**Lifetime**: Transient

```csharp
public abstract class BaseRepo
{
    protected TfiOneContext Context { get; }
    protected IUserAccessor UserAccessor { get; }

    protected BaseRepo(TfiOneContext context, IUserAccessor userAccessor)
    {
        Context = context;
        UserAccessor = userAccessor;
    }
}
```

**Convention**:
- Interface: `IXxxRepo` in domain folder
- Implementation: `XxxRepo` in same location
- Registered: Transient via `AddRepoServices()`
- One repo per aggregate root (not per table)
- Sub-resources handled within the parent's repo

---

## 2. Controller Pattern

**Count**: 20 controllers
**Base**: `BaseController : ControllerBase` with `[ApiController][Authorize]`

```csharp
[ApiController]
[Route("entities")]
public class EntityController : BaseController
{
    private readonly IEntityRepo _repo;

    public EntityController(IEntityRepo repo) => _repo = repo;

    [HttpGet]
    [PermissionAuthorize(PermissionCode.EntityView)]
    public async Task<ActionResult<List<EntityModel>>> Search([FromQuery] EntitySearchModel model)
    {
        var result = await _repo.Search(model);
        return Ok(result);
    }
}
```

**Convention**:
- Inherits `BaseController` — applies `[Authorize]` globally
- Route: lowercase plural noun (`agencies`, `providers`, `clients`)
- Returns: `ActionResult<T>`
- Permission via: `[PermissionAuthorize(PermissionCode.Xxx)]`
- Simple CRUD: repos injected directly (no service layer)
- Complex logic: delegated to service layer

---

## 3. DTO / ViewModel Pattern

All DTOs inherit `BaseModel`:

```csharp
public class BaseModel
{
    public Guid Id { get; set; }
    public List<MessageModel> Messages { get; set; } = new();
}

public class BaseSearchModel : BaseModel
{
    public int Start { get; set; }
    public int Length { get; set; }
    public int RecordCount { get; set; }
    public string? Sort { get; set; }
    public string? SortDirection { get; set; }
}
```

**Naming**:
| Suffix | Purpose |
|--------|---------|
| `XxxSearchModel` | Search/filter parameters (extends BaseSearchModel) |
| `XxxEditModel` | Create/update payload |
| `XxxViewModel` | Read-only detail view |
| `XxxCreateModel` | Create-specific payload |

Repos map entities → DTOs via LINQ `Select` projections. No AutoMapper.

---

## 4. Validation Pattern (Two-Tier)

### Tier 1: Hard-Coded FluentValidation
```csharp
public class AppUserValidator : AbstractValidator<AppUserEditModel>
{
    public AppUserValidator()
    {
        RuleFor(x => x.FirstName).NotEmpty().MaximumLength(100);
        RuleFor(x => x.Email).NotEmpty().EmailAddress();
    }
}
```

Registered validators: `AppUserValidator`, `ChangePasswordValidator`, `InquiryWorkerValidator`, `TrainingEditValidator`, `ProviderCreateModelValidator`, `PetEditModelValidator`, etc.

### Tier 2: Dynamic Validators (DB-Driven)
```
ValidationRule table → DynamicValidator<T> → Runtime execution
```

Fallback `DynamicValidator<T>` loads rules from DB when no hard-coded validator exists. Enables admin-configurable validation without code changes.

**Request pipeline**:
```
HTTP Request → ValidationFilter (IAsyncActionFilter) → FluentValidation → Controller Action
```
Returns `400 BadRequest` with field-level messages on validation failure.

---

## 5. Authentication & Authorization Pattern

### JWT Flow
```
1. POST /auth/login → Server validates → issues JWT (5 min) + Refresh Token (7 days)
2. Client stores JWT → sends: Authorization: Bearer <token>
3. Middleware validates token → extracts claims
4. [PermissionAuthorize] checks permission claims
5. Auto-refresh via RTK Query `baseQuery` on 401
```

### Permission Model
```
AppUser → AppUserOrganization → Role → RolePermission → Permission
                                                          │
                                                     PermissionCode (enum)
```

### Custom Claims in JWT
| Claim Key | Content |
|-----------|---------|
| `app-user-id` | User GUID |
| `current-org-id` | Active organization GUID |
| `orgs` | JSON array of all user orgs |
| `must-change-password` | `"true"/"false"` |
| `permission-dictionary` | JSON `Dict<PermissionCode, Guid[]>` |

### Authorization Attributes
```csharp
[Authorize]                                          // Requires authentication
[AllowAnonymous]                                     // Public endpoint
[PermissionAuthorize(PermissionCode.ClientView)]     // Specific permission
[PermissionAuthorize(PermissionCode.A, PermissionCode.B)] // Any of these
[AllowMustChangePasswordClaim]                       // Password change flow
```

---

## 6. Soft Delete Pattern

```csharp
public interface IDeletable
{
    bool Deleted { get; set; }
    DateTime? DeletedDate { get; set; }
    Guid? DeletedBy { get; set; }
}
```

- Applied to all entities
- EF Core global query filter automatically adds `WHERE Deleted = 0`
- DELETE endpoints set `Deleted = true` — no SQL DELETE
- Preserves referential integrity and audit trail

---

## 7. Audit Trail Pattern

### Automatic Metadata (EF Core Interceptors)
```
MetadataInterceptor → On Insert: Sets CreatedDate, CreatedBy
                    → On Update: Sets UpdatedDate, UpdatedBy
                    → On Delete: Sets DeletedDate, DeletedBy, Deleted=true

AuditInterceptor    → Captures all changes (Added, Modified, Deleted)
                    → Records: old values, new values, property names
                    → Writes to Azure Table Storage
                    → Partitioned by: Date AND by User
```

**Azure Tables**:
- `AuditAppUser{ENV}{YEAR}` — by date partition
- `AuditAppUserByUser{ENV}{YEAR}` — by user partition

---

## 8. Multi-Tenant Data Isolation

```csharp
public interface IOrganizationalReference
{
    Guid? OrganizationId { get; }
}
```

- Every query scoped to `UserAccessor.GetCurrentOrganizationId()`
- `RestrictedQueryProvider` enforces row-level security via `DataPermission` table
- Organization context stored in JWT claims
- Switch org via `POST /auth/change-organization/{orgId}`

---

## 9. Encryption Pattern

### Column-Level Encryption (AES)
- **SSN** — AES encrypted via `IEncryptor`
- **Banking info** — AES encrypted via `IEncryptor`
- **TOTP secrets** — AES encrypted via `IEncryptor`

### Password Security
- Per-user random salt
- Salted hash (PBKDF2)
- Password history tracking (prevents reuse)
- 90-day forced expiry
- Failed attempt lockout

### Key Management
- ASP.NET Core Data Protection API
- Keys persisted to DB (`DataProtectionKeyContext`)
- Algorithm: AES-128-CBC / HMAC-SHA256
- Purpose strings scope keys per entity type

---

## 10. Caching Strategy

```
Development → MemoryCacheProvider (in-process)
Production  → CouchbaseCacheProvider (3-node cluster)
```

Interface: `ICacheProvider` with `GetAsync<T>`, `SetAsync<T>`, `InvalidateAsync`
Swap implementations via DI registration — no code changes needed.

---

## 11. External Integration Patterns

```
Adobe Sign:  AdobeEndpointService → REST API v6
SMS:         IMessenger → TwilioMessenger
Email:       IEmailSender → SendGridEmailSender
Files:       IStorageProvider → AzureBlobStorageProvider (container: "data")
Address:     IAddressValidator → AddressValidator (Google Maps)
```

---

## 12. Background Job Pattern (Hangfire)

```
com.tfione.chron (Windows Service)
├── Hangfire Server (20 workers)
├── SQL Server storage backend
├── Worker.cs (BackgroundService) configures recurring jobs
└── IBatchRepo for job operations
```

- `AssignProviderDocumentsJob` — daily at configurable time
- `AssignClientDocumentsJob` — daily at configurable time
- Scheduling via Hangfire `RecurringJobManager` with cron expressions

---

## 13. Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Project | `com.tfione.<layer>` | `com.tfione.api` |
| Controller | `PascalCase + Controller` | `AgencyController` |
| Repo Interface | `I + PascalCase + Repo` | `IAgencyRepo` |
| Repo Implementation | `PascalCase + Repo` | `AgencyRepo` |
| Service Interface | `I + PascalCase + Service` | `IDocumentService` |
| Edit DTO | `PascalCase + EditModel` | `AgencyEditModel` |
| Search DTO | `PascalCase + SearchModel` | `AgencySearchModel` |
| View DTO | `PascalCase + ViewModel` | `AgencyViewModel` |
| DB Entity | `PascalCase` (no suffix) | `Agency` |
| Lookup Table | `PascalCase + Type` | `GenderType` |
| Enum | `PascalCase` | `PermissionCode` |
| API Route | lowercase plural | `agencies`, `providers` |
| SQL Schema | lowercase | `agency`, `provider`, `sec`, `ref` |
| SQL FK Constraint | `FK_{Source}_{Target}` | `FK_Provider_Organization` |
| SQL PK | `{EntityName}Id` | `ProviderId`, `AgencyId` |

---

## 14. Testability Requirements

All code must be structured for testability, even though unit tests are not committed to the repository.

**Design for testability**:
- Use dependency injection (constructor injection via DI container)
- Program to interfaces (`IXxxRepo`, `IXxxService`, `IEncryptor`, etc.)
- Keep controllers thin — business logic in repos/services where it can be tested in isolation
- Avoid static methods and `new` for dependencies

**Unit test policy**:
- Code must be testable, but unit test files are **not committed** to the repo
- The `com.tfione.service.test` project exists for integration/utility tests only
- E2E tests live in a separate repository (`tfione-e2e`)

> Source: reviewer feedback, Rule #9 — "Make everything unit testable but do not write (or at least don't check in) unit tests."

---

## 15. SQL Migration Rules

Rules learned from PR reviews. These apply to all Flyway SQL migrations.

### Rule 1: Reference Table Standard Structure

Every `ref.*` table MUST follow the exact template in `BACKEND_DATABASE.md → Reference Table Pattern`. Key points:
- All 8 audit columns mandatory
- Use `Deleted bit`, never `Active bit`
- No `SortOrder` column
- `Code` is `nvarchar(10)`, `Description` is `nvarchar(100)`

### Rule 2: YesNo / YesNoUnknown FK Pattern

Never use `bit` columns for user-selectable boolean values. Use FKs to `ref.YesNoType` or `ref.YesNoUnknownType` instead.

```sql
-- WRONG:
[IEP] [bit] NULL,

-- CORRECT:
[IEPTypeId] [uniqueidentifier] NULL,
CONSTRAINT [FK_ClientEducation_YesNoType_IEP] FOREIGN KEY ([IEPTypeId])
    REFERENCES [ref].[YesNoType] ([YesNoTypeID])
```

Why: consistent, translatable, auditable — no GUID-to-bool translation needed.

### Rule 3: OrganizationId Nullability in Ref Tables

`OrganizationId` in ref tables MUST be nullable:
- `NULL` = shared across all orgs (default seed data)
- Has value = org-specific override
- Never `NOT NULL` — would force duplicating ref data per org

### Rule 4: Explicit Constraint Names

Every FK, PK, UQ, and CHECK constraint MUST have an explicit name:
```sql
CONSTRAINT [FK_{TableName}_{ReferencedTable}] FOREIGN KEY (...)
```

Use `FK_{Table}_{ReferencedTable}_{Column}` when multiple FKs reference the same table.

### Rule 5: Seed Data Pattern

Shared ref data uses `OrganizationId = NULL` with the prime user ID. No `CROSS JOIN` to `org.Organization`.

```sql
-- Prime user ID (hardcoded across all migrations):
-- '892E261F-F2A1-4217-8F3C-027A6A4519CC'

INSERT INTO [ref].[XxxType] (
    [Deleted], [CreatedDate], [CreatedBy], [UpdatedDate], [UpdatedBy],
    [Code], [Description])
SELECT 0, GETDATE(), '892E261F-F2A1-4217-8F3C-027A6A4519CC',
       GETDATE(), '892E261F-F2A1-4217-8F3C-027A6A4519CC',
       v.Code, v.Description
FROM (VALUES
    ('CODE1', 'Description 1'),
    ('CODE2', 'Description 2')
) AS v(Code, Description)
WHERE NOT EXISTS (
    SELECT 1 FROM [ref].[XxxType] t
    WHERE t.Code = v.Code AND t.OrganizationId IS NULL
);
```

### Rule 6: No 3-Part Database Name

Flyway migrations must **never** use the 3-part `[database].[schema].[table]` syntax. Flyway connects to the correct database via the connection string — hardcoding the database name causes the migration to fail on any environment where the DB name differs (CI, staging, prod).

```sql
-- Bad: SSMS "Script Table As" auto-generates this — never copy into a migration
ALTER TABLE [tfi_one].[file].[FileMetaData]
    ALTER COLUMN [MimeType] nvarchar(255) not null

-- Good
ALTER TABLE [file].[FileMetaData]
    ALTER COLUMN [MimeType] nvarchar(255) not null
```

Root cause: SSMS "Script Table As" silently adds the database prefix. Always strip it before committing. Fixed in commit `8b816d91` (issue #51).

### Migration Checklist

Before submitting a SQL migration for review:
- [ ] All ref tables follow the standard template (8 audit columns, no extras)
- [ ] No `bit` columns for user-selectable booleans (use YesNo FK)
- [ ] `OrganizationId` is nullable in ref tables
- [ ] All constraints have explicit names
- [ ] FK naming follows `FK_{Child}_{Parent}` convention
- [ ] `Deleted bit` used (not `Active bit`)
- [ ] Seed data uses prime user ID, `OrganizationId = NULL`, no CROSS JOIN
- [ ] No 3-part `[database].[schema].[table]` syntax — use `[schema].[table]` only

---

## 16. Frontend Component Rules

Rules from the PR #228 review that apply to all frontend development. For the full component inventory, see `FRONTEND_COMPONENTS.md`.

### One Component Per File

No file should contain more than one React component. File name matches the exported component in snake_case.

### Always Use Wrapped Components

Never use raw MUI components when a `tfio_*` wrapper exists. The wrappers integrate with:
- **Content hook** — `labelToken`/`labelDefault` props for localization
- **Validation** — FluentValidation resolver integration
- **Readonly mode** — `useFormReadonly()` context auto-disables inputs

| Use This | Instead Of |
|----------|-----------|
| `TfioTextInput` | `TextField` |
| `TfioDateInput` | `DatePicker` |
| `TfioSelectInput` | `Select` |
| `TfioCheckboxInput` | `Checkbox` |
| `TfioButton` | `Button` |
| `TfioDataGrid` | `DataGrid` |
| `TfioDialog` | `Dialog` |

### All Strings Through Content Hook

All user-facing strings must use the content hook on both client and server:
- **Frontend**: `content("token.key", "Fallback text")` or `labelToken`/`labelDefault` props
- **Backend**: `content.GetContent("token.key", "Fallback text")`
- Applies to: labels, validation messages, error messages, placeholders, button text

### Don't Translate GUIDs to Bools ← CANONICAL RULE

**This is the authoritative pattern. The old bool↔GUID conversion in `five_points/FACE_SHEET_SECTION_PATTERNS.md §7` is deprecated.**

When the DB stores a FK to `ref.YesNoType` or `ref.YesNoUnknownType`, the model uses a GUID field (`iepId`, `plan504Id`, `ardId`, `onGradeLevelId`). The frontend works with that GUID directly — never convert to/from boolean.

**Display (overview/view screens):**
```tsx
const { data: yesNoTypes } = useGetReferencesQuery('YesNoType');

const resolveRef = (id: string | undefined | null): string => {
    if (!id || id === CONSTANTS.EMPTY_GUID) return 'N/A';
    return yesNoTypes?.find(t => t.value === id || t.id === id)?.text ?? 'N/A';
};

// Usage:
resolveRef(overview?.iepId)      // → "Yes" / "No" / "N/A"
resolveRef(overview?.plan504Id)
```

**Edit forms:**
```tsx
<TfioSelect name="iepId" items={yesNoTypes} />   // GUID in, GUID out — no conversion
```

**⚠️ Warning:** Before writing a component that uses a model from another branch, always read
`com.tfione.api.d.ts` to confirm field names and types. Branches may differ (one uses `iep: bool`,
another uses `iepId: string`). Copying without checking causes TS2339/TS2551 build errors.

---

## 16. C# Patterns for Reference Tables

### ORM Entity (ref table)

Every `ref.*` ORM entity MUST implement `IDeletable, IOrganizationalReference, IReference`:

```csharp
public partial class XxxType : IDeletable, IOrganizationalReference, IReference
{
    public XxxType()
    {
        // Initialize navigation collections
    }

    public Guid XxxTypeId { get; set; }

    public bool Deleted { get; set; }

    public DateTime CreatedDate { get; set; }

    public Guid CreatedBy { get; set; }

    public DateTime UpdatedDate { get; set; }

    public Guid UpdatedBy { get; set; }

    public DateTime? DeletedDate { get; set; }

    public Guid? DeletedBy { get; set; }

    public Guid? OrganizationId { get; set; }

    public string Code { get; set; } = null!;

    public string Description { get; set; } = null!;

    public virtual Organization? Organization { get; set; }

    // Navigation collections...

    public Guid Id => this.XxxTypeId;
}
```

### TfiOneContext Entity Configuration (ref table)

```csharp
modelBuilder.Entity<XxxType>(entity =>
{
    entity.ToTable("XxxType", "ref");
    entity.Property(e => e.XxxTypeId).HasDefaultValueSql("(newsequentialid())");
    entity.Property(e => e.Code).HasMaxLength(10);
    entity.Property(e => e.Description).HasMaxLength(100);
    entity.Property(e => e.CreatedDate).HasColumnType("datetime");
    entity.Property(e => e.DeletedDate).HasColumnType("datetime");
    entity.Property(e => e.UpdatedDate).HasColumnType("datetime");
    entity.HasOne(d => d.Organization)
        .WithMany()
        .HasForeignKey(d => d.OrganizationId)
        .HasConstraintName("FK_XxxType_Organization");
});
```

### YesNo FK in Entity + Model + Validator + Frontend

When a field uses `ref.YesNoType` or `ref.YesNoUnknownType` FK:

**ORM Entity:**
```csharp
public Guid? FieldName { get; set; }
public virtual YesNoType? FieldNameNavigation { get; set; }
```

**Model DTO:**
```csharp
public Guid? FieldName { get; set; }
```

**TfiOneContext FK config:**
```csharp
entity.HasOne(d => d.FieldNameNavigation)
    .WithMany()
    .HasForeignKey(d => d.FieldName)
    .HasConstraintName("FK_TableName_FieldName");
```

**Validator (FluentValidation):**
```csharp
// Use Guid check, not boolean
this.RuleFor(x => x.RequiredDate)
    .NotEmpty()
    .When(x => x.FieldName.HasValue && x.FieldName != Guid.Empty)
    .WithMessage("Date is required when field is selected.");
```

**Frontend (TypeScript):**
```typescript
// Type: string (GUID), not boolean
interface Model {
    /** Format: uuid */
    fieldName?: string;
}

// TfioSelect handles GUIDs natively — NO bool↔GUID conversion
<TfioSelect name="fieldName" items={yesNoTypes} />

// Overview display: use displayReference, not displayBool
value: displayReference(model.fieldName, yesNoTypes)
```

---

## 17. Address Component Pattern

**Rule**: Always use `WithAddress<TModel, 'addressData'>` as the form type when using `TfioAddress`. Never bind `TfioAddress` to a model with flat address fields.

**Canonical reference**: `client_address_addEdit.tsx`

```tsx
// CORRECT
const form = useForm<WithAddress<ClientEnrollmentEditModel, 'addressData'>>();

<TfioAddress name='addressData' />

// On load — map flat fields → nested addressData for display
form.reset({
  ...model,
  addressData: {
    street1: model.addressLine1,
    street2: model.addressLine2,
    city: model.city,
    state: model.stateTypeId,
    county: model.countyTypeId,
    zipCode: model.zipCode,  // Field is zipCode, NOT zip (matches AddressData interface)
  },
});

// On submit — map nested addressData → flat fields before API call
const { addressData, ...rest } = data;
await save({
  ...rest,
  addressLine1: addressData.street1,
  addressLine2: addressData.street2,
  city: addressData.city,
  stateTypeId: addressData.state,
  countyTypeId: addressData.county,
  zipCode: addressData.zipCode,  // Field is zipCode, NOT zip
});
```

**Never**:
- `useForm<ModelWithFlatAddressFields>()` + `<TfioAddress name='address' />` — address data is silently discarded on submit
- `name='address'` when the model has no `address` field

---

## 18. County Filtering Pattern

**Rule**: County dropdowns MUST be filtered by the selected state. Never load all counties at once.

```tsx
// CORRECT
const selectedState = watch('addressData.state');  // or whatever state field name
const { data: counties } = useGetChildReferencesQuery(
  selectedState
    ? { referenceType: 'CountyType', parentId: selectedState }
    : skipToken
);

// WRONG — loads all ~250 counties unfiltered
const { data: counties } = useGetReferencesQuery('CountyType');
```

County items should reset when state changes (MUI Select handles this automatically if the current county value is no longer in the list).

---

## 19. Routed Screens vs Modals

**Rule**: Add/Edit forms for entity records MUST be routed screens, not modals embedded in a parent list component.

| Use Case | Pattern |
|----------|---------|
| Create/Edit entity (enrollment, home study, etc.) | Routed screen — `useParams` + `useNavigateBack` |
| Confirm destructive action (delete, archive) | `TfioDialog` |
| Quick pick / selector | `TfioDialog` |

**Routed Add/Edit pattern**:
```tsx
// enrollment_add_edit.tsx
const { clientId, enrollmentId } = useParams<{ clientId: string; enrollmentId: string }>();
const navigateBack = useNavigateBack();

// On cancel or after save:
navigateBack();
```

**Routes in client.tsx** (example for enrollment):
```tsx
{ path: 'enrollment/add', element: <EnrollmentAddEdit /> },
{ path: 'enrollment/:enrollmentId/edit', element: <EnrollmentAddEdit /> },
{ path: 'enrollment/:enrollmentId/view', element: <EnrollmentView /> },
```

**Parent list navigates — does not open a dialog**:
```tsx
// enrollment_history.tsx
navigate(`enrollment/${id}/edit`);   // relative, within face sheet outlet
navigate('enrollment/add');
```

---

## 20. View Mode Pattern

**Rule**: View/read-only screens MUST use `TfioModelView`, not a disabled form.

**Canonical reference**: `home_study_view.tsx`

```tsx
// CORRECT — enrollment_view.tsx
export function EnrollmentView() {
  const { enrollmentId } = useParams<{ enrollmentId: string }>();
  const { data } = useGetEnrollmentQuery(enrollmentId ?? skipToken);

  return (
    <TfioModelView
      title='Enrollment'
      navigateBack
    >
      <TfioModelViewRow label='School Name' value={data?.schoolName} />
      <TfioModelViewRow label='GPA' value={data?.gpa} />
      {/* ... */}
    </TfioModelView>
  );
}

// WRONG — disabled form
<TfioTextInput name='gpa' disabled={true} />
```

**Why**: Disabled inputs have accessibility issues and inconsistent styling. `TfioModelView` provides a consistent, accessible read-only display with proper labels.

---

## 21. MUI Context Menu ARIA Pattern

**Rule**: Context menus using `<Menu>` must declare proper ARIA attributes and an `onClose` handler.

```tsx
// CORRECT
const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => setAnchorEl(event.currentTarget);
const handleMenuClose = () => setAnchorEl(null);

<IconButton
  aria-label='Open menu'
  aria-controls='education-menu'
  aria-haspopup='true'
  aria-expanded={Boolean(anchorEl)}
  onClick={handleMenuOpen}
>
  <MoreVertIcon />
</IconButton>

<Menu
  id='education-menu'
  anchorEl={anchorEl}
  open={Boolean(anchorEl)}
  onClose={handleMenuClose}   // ← REQUIRED: without this, menu stays open on outside click
>
  <MenuItem onClick={() => { handleMenuClose(); doSomething(); }}>Action</MenuItem>
</Menu>

// WRONG
aria-haspopup='false'         // incorrect: button DOES open a popup
// missing onClose on <Menu>  // menu won't close on outside click
// <Menu> wrapped in stray <>  // causes DOM positioning issues
```

---

## 22. Document Category Deep Link Pattern

**Rule**: When navigating to the Documents tab for a specific category, use query params — not hardcoded GUIDs (which are org-specific runtime data).

```tsx
// CORRECT — category name (label-based match, works across orgs)
navigate(`/client/face_sheet/${clientId}/documents?documentCategoryName=Education`);

// Also supported — category ID (use when GUID is available at runtime, e.g. from API response)
navigate(`/client/face_sheet/${clientId}/documents?documentCategoryId=${categoryId}`);

// WRONG — no param, opens documents with no category pre-selected
navigate(`/client/face_sheet/${clientId}/documents`);
```

`documents.tsx` supports both `documentCategoryId` and `documentCategoryName` params. The name-based match is case-insensitive and finds the category by label in the document tree.
