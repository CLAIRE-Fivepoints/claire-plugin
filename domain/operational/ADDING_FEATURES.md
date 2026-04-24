---
keywords: [feature, how-to, new-endpoint, new-entity, controller, repository, dto, frontend, rtk-query]
---

# TFI One — Adding New Features

Step-by-step guide for adding a new feature end-to-end.

---

## Example: Add a New Entity (e.g., "CaseNote")

### 1. Database (SQL Migration)

Create a Flyway migration in `com.tfione.db/migration/`:

```sql
-- V1.0.20240115.001.001__add_case_note_table.sql

CREATE TABLE [case].[CaseNote](
    [CaseNoteId]    [UNIQUEIDENTIFIER] NOT NULL PRIMARY KEY CLUSTERED DEFAULT NEWSEQUENTIALID(),
    [CaseId]        [UNIQUEIDENTIFIER] NOT NULL,
    [OrganizationId] [UNIQUEIDENTIFIER] NOT NULL,
    [NoteText]      [nvarchar](4000)   NOT NULL,
    [Deleted]       [bit]              NOT NULL,
    [CreatedDate]   [datetime]         NOT NULL,
    [CreatedBy]     [UNIQUEIDENTIFIER] NOT NULL,
    [UpdatedDate]   [datetime]         NOT NULL,
    [UpdatedBy]     [UNIQUEIDENTIFIER] NOT NULL,
    [DeletedDate]   [datetime]         NULL,
    [DeletedBy]     [UNIQUEIDENTIFIER] NULL,
    CONSTRAINT [FK_CaseNote_Case] FOREIGN KEY ([CaseId])
        REFERENCES [case].[Case] ([CaseId]),
    CONSTRAINT [FK_CaseNote_Organization] FOREIGN KEY ([OrganizationId])
        REFERENCES [org].[Organization] ([OrganizationId])
);
```

Rules:
- Always use `UNIQUEIDENTIFIER` PK with `NEWSEQUENTIALID()`
- Always include all 8 audit columns
- Always add FK constraints with explicit names
- Use the appropriate schema (`case`, `provider`, `agency`, etc.)
- Naming: `FK_{ChildTable}_{ParentTable}` (add `_{Column}` when multiple FKs to same table)
- Use `Deleted bit`, never `Active bit`
- Never use `bit` for user-selectable booleans — use FK to `ref.YesNoType` or `ref.YesNoUnknownType`

**If creating a reference table (`ref.*`):**
- [ ] Follows exact ref table template (see `BACKEND_DATABASE.md → Reference Table Pattern`)
- [ ] Has all 8 audit columns (Deleted, CreatedDate/By, UpdatedDate/By, DeletedDate/By)
- [ ] `OrganizationId` is nullable (`NULL` = shared across orgs)
- [ ] No `SortOrder` column
- [ ] `Code` is `nvarchar(10)`, `Description` is `nvarchar(100)`
- [ ] All constraints have explicit names

### 2. EF Core Entity (`com.tfione.db`)

Add ORM entity (or scaffold from existing DB):

```csharp
public partial class CaseNote : IDeletable, IAuditable
{
    public Guid CaseNoteId { get; set; }
    public Guid CaseId { get; set; }
    public Guid OrganizationId { get; set; }
    public string NoteText { get; set; }
    public bool Deleted { get; set; }
    public DateTime CreatedDate { get; set; }
    public Guid CreatedBy { get; set; }
    public DateTime UpdatedDate { get; set; }
    public Guid UpdatedBy { get; set; }
    public DateTime? DeletedDate { get; set; }
    public Guid? DeletedBy { get; set; }

    public virtual Case Case { get; set; }
}
```

Add `DbSet<CaseNote> CaseNotes { get; set; }` to `TfiOneContext`.

### 3. DTOs (`com.tfione.model`)

```csharp
// Search model
public class CaseNoteSearchModel : BaseSearchModel
{
    public Guid CaseId { get; set; }
    public string? NoteText { get; set; }
}

// Edit model
public class CaseNoteEditModel : BaseModel
{
    public Guid CaseId { get; set; }
    public string NoteText { get; set; }
}
```

### 4. Repository (`com.tfione.repo`)

```csharp
public interface ICaseNoteRepo
{
    Task<List<CaseNoteSearchModel>> Search(CaseNoteSearchModel model);
    Task<CaseNoteEditModel> Get(Guid id);
    Task<BaseModel> Create(CaseNoteEditModel model);
    Task<BaseModel> Update(Guid id, CaseNoteEditModel model);
    Task<BaseModel> Delete(Guid id);
}

public class CaseNoteRepo : BaseRepo, ICaseNoteRepo
{
    public CaseNoteRepo(TfiOneContext context, IUserAccessor userAccessor)
        : base(context, userAccessor) { }

    public async Task<List<CaseNoteSearchModel>> Search(CaseNoteSearchModel model)
    {
        var query = Context.CaseNotes
            .Where(n => n.OrganizationId == UserAccessor.GetCurrentOrganizationId())
            .Where(n => n.CaseId == model.CaseId)
            .AsQueryable();

        model.RecordCount = await query.CountAsync();

        return await query
            .Select(n => new CaseNoteSearchModel
            {
                Id = n.CaseNoteId,
                NoteText = n.NoteText
            })
            .Skip(model.Start)
            .Take(model.Length)
            .ToListAsync();
    }
    // ... Create, Update, Delete
}
```

Register in `Extensions.AddRepoDependencies()`:
```csharp
services.AddTransient<ICaseNoteRepo, CaseNoteRepo>();
```

### 5. FluentValidation (`com.tfione.repo`)

```csharp
public class CaseNoteValidator : AbstractValidator<CaseNoteEditModel>
{
    public CaseNoteValidator()
    {
        RuleFor(x => x.NoteText).NotEmpty().MaximumLength(4000);
        RuleFor(x => x.CaseId).NotEmpty();
    }
}
```

Register:
```csharp
services.AddScoped<IValidator<CaseNoteEditModel>, CaseNoteValidator>();
```

### 6. Controller (`com.tfione.api`)

```csharp
[ApiController]
[Route("cases/{caseId}/notes")]
public class CaseNoteController : BaseController
{
    private readonly ICaseNoteRepo _repo;

    public CaseNoteController(ICaseNoteRepo repo) => _repo = repo;

    [HttpGet]
    [PermissionAuthorize(PermissionCode.CaseView)]
    public async Task<ActionResult<List<CaseNoteSearchModel>>> Search(
        Guid caseId,
        [FromQuery] CaseNoteSearchModel model)
    {
        model.CaseId = caseId;
        return Ok(await _repo.Search(model));
    }

    [HttpPost]
    [PermissionAuthorize(PermissionCode.CaseCreate)]
    public async Task<ActionResult<BaseModel>> Create(
        Guid caseId,
        [FromBody] CaseNoteEditModel model)
    {
        model.CaseId = caseId;
        return Ok(await _repo.Create(model));
    }

    [HttpPut("{id}")]
    [PermissionAuthorize(PermissionCode.CaseEdit)]
    public async Task<ActionResult<BaseModel>> Update(
        Guid caseId, Guid id,
        [FromBody] CaseNoteEditModel model)
    {
        model.CaseId = caseId;
        return Ok(await _repo.Update(id, model));
    }

    [HttpDelete("{id}")]
    [PermissionAuthorize(PermissionCode.CaseDelete)]
    public async Task<ActionResult<BaseModel>> Delete(Guid caseId, Guid id)
    {
        return Ok(await _repo.Delete(id));
    }
}
```

### 7. Frontend: RTK Query Service

Add to `redux/services/case.ts` (or create `case_notes.ts`):

```typescript
export const caseNoteApi = createApi({
  reducerPath: 'caseNoteApi',
  baseQuery: fetchBaseQuery({ ... }),
  tagTypes: ['caseNote'],
  endpoints: (builder) => ({
    getCaseNotes: builder.query<CaseNoteSearchModel[], Partial<CaseNoteSearchModel>>({
      query: ({ caseId, ...params }) => ({
        url: `/cases/${caseId}/notes`,
        params
      }),
      providesTags: ['caseNote']
    }),
    createCaseNote: builder.mutation<BaseModel, CaseNoteEditModel>({
      query: ({ caseId, ...body }) => ({
        url: `/cases/${caseId}/notes`,
        method: 'POST',
        body
      }),
      invalidatesTags: ['caseNote']
    }),
    // ... update, delete
  })
});
```

### 8. Frontend: Components

```typescript
// case_notes_list.tsx — one component per file
function CaseNotesList({ caseId }: { caseId: string }) {
  const { data: notes } = useGetCaseNotesQuery({ caseId });

  return (
    <TfioPageWrapper title={content("caseNotes.title", "Case Notes")}>
      <TfioDataGrid rows={notes || []} columns={columns} />
    </TfioPageWrapper>
  );
}
```

**Frontend Component Checklist:**
- [ ] One component per file — file name matches component (`snake_case.tsx`)
- [ ] Using `tfio_*` wrappers, not raw MUI components
- [ ] All user-facing strings through content hook (`content()` or `labelToken`/`labelDefault`)
- [ ] No GUID-to-boolean translation — use `TfioSelectInput` with reference data
- [ ] Inputs support readonly mode via `useFormReadonly()` context

### 9. Add to Route

In `routes/case.tsx`:
```tsx
{
  path: "cases/:id/notes",
  element: <CaseNotesList />
}
```

---

## Adding a New Reference Type

1. Create migration with the standard ref table template (see `BACKEND_DATABASE.md → Reference Table Pattern`)
   - All 8 audit columns, `OrganizationId` nullable, `Code nvarchar(10)`, `Description nvarchar(100)`
   - All constraints explicitly named
   - No `SortOrder`, no `Active bit`
2. Add seed data: `INSERT INTO [ref].[NewReferenceType] ...`
3. Add EF entity implementing `IReference`
3. Add `DbSet<NewReferenceType>` to `TfiOneContext`
4. Expose via `ReferenceController` using `IReferenceProvider.GetReferences<NewReferenceType>()`
5. Frontend: add to `reference.ts` RTK Query service
6. Use `tfio_select` with `useGetReferencesQuery` in forms

---

## Adding a New Permission

1. Add to `PermissionCode` enum in `com.tfione.model`
2. Add migration: insert into `sec.Permission` table
3. Assign to appropriate roles via `sec.RolePermission`
4. Use `[PermissionAuthorize(PermissionCode.NewPermission)]` on controller actions
5. Frontend: check `user.currentPermissionDictionary["NewPermission"]` to show/hide UI

---

## Key Rules to Remember

- **All entities** need the 8 universal audit columns
- **All PKs** are `UNIQUEIDENTIFIER` with `NEWSEQUENTIALID()`
- **All constraints** must have explicit names (`FK_`, `PK_`, `UQ_`, `CK_`)
- **No `bit` for user booleans** — use FK to `ref.YesNoType` or `ref.YesNoUnknownType`
- **Ref tables**: `OrganizationId` nullable, no `SortOrder`, use `Deleted` not `Active`
- **No raw SQL** — pure EF Core LINQ only
- **Soft delete** — never SQL DELETE, always set `Deleted = true`
- **Multi-tenant** — always scope queries to `UserAccessor.GetCurrentOrganizationId()`
- **Repo lifetime** — always Transient
- **DTOs** inherit `BaseModel` (or `BaseSearchModel` for search)
- **Routes** use lowercase plural nouns
- **Flyway** for all schema changes — never EF Core migrations

---

## Pre-PR Checklist (Steven's Rules)

Validate every item before creating a PR. Source: Azure DevOps PR #228, Thread #1839.

- [ ] **Rule 1 — Correct branch**: Using the branch created for the PBI, not a custom one
- [ ] **Rule 2 — No cross-branch merges**: Not merging dev into child branches directly
- [ ] **Rule 3 — Named constraints**: Every FK, PK, UQ, CHECK has an explicit name in DDL
- [ ] **Rule 4 — Permission errors**: Repos propagate auth/permission errors to the client
- [ ] **Rule 5 — Dual validation**: All validations exist on BOTH client (React) AND server (FluentValidation)
- [ ] **Rule 6 — Content hooks**: All string literals go through content hook (no hardcoded labels/messages)
- [ ] **Rule 7 — Wrapped components**: Using tfio_* wrappers, not raw MUI components
- [ ] **Rule 8 — One per file**: Each file contains exactly one component (React) or class (C#)
- [ ] **Rule 9 — Testable, no tests**: Code is unit-testable but no test files are committed
