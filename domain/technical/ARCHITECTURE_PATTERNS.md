---
keywords: [five-points, tfi-one, architecture, patterns, layers, controllers, repository, orm]
---

# TFI One - Architecture Patterns Reference

> Source: `azure/feature/10399-client-mgmt-education` branch (Azure DevOps)
> Generated: 2026-02-27

---

## Request Flow (End-to-End)

```
HTTP Request
  → [Authorize]                    JWT Bearer (base class)
  → [PermissionAuthorize]          Per-endpoint permission check (optional)
  → ValidationFilter               FluentValidation (data-driven or hard-coded)
  → Controller                     Thin pass-through (2 dependencies: logger + repo)
  → Repository                     Business logic + data access combined
      → IRestrictedQueryProvider    Row-level security (multi-tenant)
      → TfiOneContext               EF Core DbContext
          → MetadataInterceptor     Auto-stamps Created/Updated/Deleted audit fields
          → Global Query Filters    Auto-excludes soft-deleted records
  → Response                       Model with Messages[] list (no exceptions for business errors)
```

---

## Layer 1: API Controllers

### Pattern
- Inherit `BaseController` (`[ApiController] [Authorize] ControllerBase`)
- **Thin pass-through** to repository — no business logic in controllers
- All methods return `Task<ActionResult<T>>`
- Always return `this.Ok(result)` — errors flow through model `Messages`

### Routing
```
[Route("client")]                                   // Top-level resource
[Route("client/{clientId:guid}/adoption")]          // Nested sub-resource
```
- Lowercase, hyphen-separated
- Guid constraints on ID params: `{id:guid}`

### HTTP Verb Mapping

| Operation | Verb | Route Example |
|-----------|------|---------------|
| Search/List | `[HttpGet]` | root with `[FromQuery]` |
| Get single | `[HttpGet]` | `"{id:guid}"` |
| Get for view | `[HttpGet]` | `"{id:guid}/view"` |
| Create | `[HttpPost]` | `"sub-resource"` |
| Update | `[HttpPut]` | `"{id:guid}"` |
| Delete | `[HttpDelete]` | `"{id:guid}"` |
| Partial update | `[HttpPatch]` | `"{id:guid}/resource"` |

### Constructor Pattern
```csharp
public ClientController(ILogger<ClientController> logger, IClientRepo repo)
{
    _ = logger ?? throw new ArgumentNullException(nameof(logger));
    _ = repo ?? throw new ArgumentNullException(nameof(repo));
    this.logger = logger;
    this.repo = repo;
}
```

### Permission Pattern
```csharp
[HttpGet("staffing")]
[PermissionAuthorize(PermissionCode.AccessClientAdoptionStaffing)]
public async Task<ActionResult<AdoptionStaffingSearchModel>> SearchStaffings(...)
```

### Example Endpoint
```csharp
[HttpGet("recruitment/{id:guid}")]
public async Task<ActionResult<RecruitmentEventEditModel>> GetRecruitmentEvent(Guid clientId, Guid id)
{
    var model = await this.repo.GetRecruitmentEvent(clientId, id);
    return this.Ok(model);
}
```

---

## Layer 2: Repository

### Pattern
- Interface: `I{Domain}Repo` — Implementation: `{Domain}Repo`
- Registered as **Transient** in DI
- Some inherit `BaseRepo`, some standalone — both patterns exist
- Business logic lives here (not in a service layer)

### Constructor Dependencies
```csharp
public AdoptionRepo(
    TfiOneContext tfiOneContext,
    IRestrictedQueryProvider rqProvider,    // Row-level security
    IUserAccessor userAccessor,            // Current user context
    IContentProvider contentProvider,      // Localized messages
    IReferenceProvider referenceProvider,  // Lookup data
    IValidationRuleProvider validationRuleProvider,
    IEncryptor encryptor,
    IEmailSender emailSender,
    IFileRepo fileRepo)
```

### CRUD Patterns

**Search:**
```csharp
public async Task<ClientSearchModel> SearchClients(ClientSearchModel model)
{
    var basequery = this.rqProvider.GetRestrictedQuery<Client>();
    var modelList = from client in basequery
                    where client.Deleted == false
                    select new ClientSearchListModel { ... };

    if (!string.IsNullOrEmpty(model.FirstName))
        modelList = modelList.Where(m => m.FirstName.Contains(model.FirstName));

    model.List = await modelList.ToListAsync();
    return model;
}
```

**Create:**
```csharp
public async Task<XxxEditModel> CreateXxx(XxxEditModel model)
{
    // 1. Access check via restricted query
    var hasaccess = basequery.Any(c => c.ClientId == model.ClientId);
    if (!hasaccess) { model.Messages.Add(...); return model; }

    // 2. Map model → entity
    var dbmodel = new Xxx { ... };

    // 3. Add + SaveChanges
    this.tfiOneContext.Xxxs.Add(dbmodel);
    await this.tfiOneContext.SaveChangesAsync();

    // 4. Re-fetch and return
    return await this.GetXxx(model.ClientId, dbmodel.XxxId);
}
```

**Update:**
```csharp
public async Task<XxxEditModel> UpdateXxx(Guid id, XxxEditModel model)
{
    // 1. Fetch entity via restricted query
    var dbmodel = await (...).FirstOrDefaultAsync();
    if (dbmodel == null) { model.Messages.Add(accessDenied); return model; }

    // 2. Map model → entity fields
    dbmodel.Field = model.Field;

    // 3. SaveChanges (EF change tracking)
    await this.tfiOneContext.SaveChangesAsync();

    // 4. Re-fetch and return
    return await this.GetXxx(model.ClientId, id);
}
```

**Delete (always soft delete):**
```csharp
public async Task<bool> DeleteXxx(Guid id)
{
    var dbmodel = await (...).FirstOrDefaultAsync();
    if (dbmodel != null && dbmodel.Deleted == false)
    {
        dbmodel.Deleted = true;
    }
    await this.tfiOneContext.SaveChangesAsync();
    return true;
}
```

### Access Denied Pattern (No Exceptions)
```csharp
var content = await this.contentProvider.GetContent("global.access.denied", "You do not have permission...");
model.Messages.Add(new ModelMessageModel("access-denied", content));
return model;
```

### Mapping Pattern
```csharp
public static class ClientMappings
{
    public static readonly Expression<Func<Client, ClientViewModel>> ToClientViewModel = dbModel =>
        new ClientViewModel() { ... };
}
// Used in: .Select(ClientMappings.ToClientViewModel)
```

---

## Layer 3: Database / ORM Entities

### Pattern
- **Database-first** approach (EF Core scaffolding)
- All entities are `partial class` in `com.tfione.db.orm` namespace
- Custom logic in `com.tfione.db/partial/` partial classes

### Entity Categories

| Type | Interfaces | Example |
|------|-----------|---------|
| Domain entity | `IDeletable, IOrganizationalReference, IRestrictedQuery` | `Client`, `Case` |
| Reference/Lookup | `IDeletable, IOrganizationalReference, IReference` | `GenderType`, `RegionType` |
| Join/Child entity | `IDeletable` | `AdoptionChecklist`, `ClientAlias` |

### Audit Fields (on every entity)
```csharp
public Guid {Entity}Id { get; set; }       // PK
public bool Deleted { get; set; }
public DateTime CreatedDate { get; set; }
public Guid CreatedBy { get; set; }
public DateTime UpdatedDate { get; set; }
public Guid UpdatedBy { get; set; }
public DateTime? DeletedDate { get; set; }
public Guid? DeletedBy { get; set; }
```

### Interface Hierarchy

| Interface | Purpose | Key Properties |
|-----------|---------|----------------|
| `IDeletable` | Soft delete | `bool Deleted` |
| `IRestrictedQuery` | Row-level security | `Guid RestrictedId, Guid OrganizationId` |
| `IOrganizationalReference` | Multi-tenancy | `Guid? OrganizationId` |
| `IReference` | Lookup tables | `Guid Id, string Code, string Description` |

### DbContext
- `TfiOneContext` is a `partial class`
- Auto-generated: `DbSet<T>` for all entities
- Custom partial: Global query filter → auto-excludes `Deleted == true` on all `IDeletable` entities
- `MetadataInterceptor`: Auto-stamps `CreatedBy/Date`, `UpdatedBy/Date`, `DeletedBy/Date`

### Naming
- PK: `{EntityName}Id`
- FK: Matches PK name
- Navigation: Singular for parent, plural `ICollection<T>` for children (initialized as `HashSet<T>`)
- Reference tables: `{Name}Type` suffix

---

## Layer 4: Models / DTOs

### The Quartet Pattern

Every domain resource has 4 models:

| Model | Base Class | Purpose |
|-------|------------|---------|
| `{Entity}SearchModel` | `BaseSearchModel` | Filter params + `List<{Entity}ListModel>` results |
| `{Entity}ListModel` | (none) | Flat DTO for grid rows |
| `{Entity}EditModel` | `BaseModel` | Create AND Update form |
| `{Entity}ViewModel` | (none) | Read-only display |

Additional: `{Entity}FacesheetModel` for summary cards.

### Base Classes
```csharp
public class BaseModel
{
    public List<ModelMessageModel> Messages { get; set; } = [];
}

public class BaseSearchModel : BaseModel
{
    public string? Search { get; set; }
    public string? Sort { get; set; }
    public string? SortDirection { get; set; }
    public int Start { get; set; } = 0;
    public int Length { get; set; } = 20;
    public int RecordCount { get; set; } = 20;
}
```

### Key Design: Search model carries input AND output
```csharp
public class XxxSearchModel : BaseSearchModel
{
    public Guid ClientId { get; set; }               // Filter
    public List<XxxListModel> List { get; set; }     // Results
}
```

### Property Conventions
- IDs: `Guid` type, named `{Entity}Id`
- Nullable: `Guid?`, `DateTime?`, `string?`
- FK + display: `Guid {Type}Id` paired with `string? {Type}Description`

---

## Layer 5: Service Layer (Cross-Cutting Infrastructure)

**No traditional business logic service layer.** Services provide cross-cutting concerns to repos:

| Service | Purpose |
|---------|---------|
| `IRestrictedQueryProvider` | Returns `IQueryable<T>` filtered for current user's org + data permissions |
| `IUserAccessor` | Current user ID, org ID, username, data permission targets |
| `IContentProvider` | Localized content via tokens: `GetContent("token", "default")` |
| `IReferenceProvider` | Lookup data for dropdowns: `GetReferences<GenderType>()` |
| `IValidationRuleProvider` | Database-driven validation rules |
| `IEncryptor` | SSN encryption etc. |
| `IEmailSender` | Email notifications |

### Validation (Dual System)
1. **Data-driven**: Rules stored in DB, applied via `DynamicValidator<T>` using reflection
2. **Hard-coded**: FluentValidation validators extending `BaseValidator<T>`
3. `ValidationFilter` middleware resolves `IValidator<T>` on POST/PUT/PATCH — returns 400 if invalid

---

## Layer 6: Frontend — Redux / RTK Query

### API Pattern: Single slice + `injectEndpoints`
```typescript
// api.ts — single createApi instance
export const api = createApi({
    reducerPath: 'tfione',
    baseQuery: baseQueryWithRefresh,
    tagTypes: tags,
    endpoints: () => ({}),
});

// client.ts — injects domain endpoints
export const clientApi = api.injectEndpoints({
    endpoints: (builder) => ({
        clientSearch: builder.query<ClientSearchModel, ClientSearchModel>({
            query: (model) => ({ url: `client?${getQueryString(model)}`, method: 'GET' }),
            providesTags: ['client']
        }),
        clientUpdate: builder.mutation<ClientEditModel, ClientEditModel>({
            query: (model) => ({ url: `client/edit/${model.clientId}`, method: 'PUT', body: model }),
            invalidatesTags: ['client']
        }),
    }),
});
export const { useClientSearchQuery, useClientUpdateMutation } = clientApi;
```

### Tag Invalidation
- Tags in centralized `tags.ts`
- GUIDs uppercased: `.toUpperCase()`
- Queries: `providesTags: [{ type: 'xxx', id: id.toUpperCase() }]`
- Mutations: `invalidatesTags: [{ type: 'xxx', id: model.xxxId.toUpperCase() }]`

### Reducers: Minimal UI state only
```typescript
export const globalSlice = createSlice({
    name: 'global',
    initialState,
    reducers: {
        wait, endWait, addMessage, removeMessage, resetGlobal
    }
});
```
Server data lives in RTK Query cache — never in reducers.

### Base Query Features
- Dual transport: `fetchBaseQuery` (standard) + `axiosBaseQuery` (file uploads)
- Auto 401 token refresh + replay
- Auto-dispatches server `messages` as toast notifications

---

## Layer 7: Frontend — Components

### Face Sheet Pattern (3 tiers)

```
face_sheet.tsx          → Layout Shell (avatar, name, <Outlet />)
  general_information.tsx → Card Dashboard (Masonry grid of cards)
    cards/xxx_view.tsx    → Individual View Cards (TfioModelView)
```

**Tier 1 — Shell:** Fetches entity, displays header, renders `<Outlet />`
**Tier 2 — Dashboard:** `<Masonry columns={{ sm: 1, md: 2 }}>` with `<Card>` wrappers
**Tier 3 — Cards:** Each card fetches own data via RTK Query hook, builds `ViewItem[]` array

### View Card Pattern
```typescript
const items: ViewItem[] = [
    { label: content("client.name", "Name"), value: client.name },
    { label: content("client.ssn", "SSN"), value: client.ssn, mask: INPUT_MASKS.SSN_MASKED },
];
return <TfioModelView items={items} title="Client Info" actions={[<EditButton />]} />;
```

### CRUD Pattern: Grid + Dialog Modal

**List view** (`{entity}_history.tsx`):
```typescript
const [modalState, setModalState] = useState<'view' | 'edit' | 'delete' | null>(null);
return (
    <TfioDataGrid rows={data?.list} columns={columns}
        slots={{ toolbar: TfioGridToolbar }}
        slotProps={{ toolbar: { showAddButton: true, onAddClick: () => setModalState('edit') } }}
    />
    <TfioDialog open={modalState === 'edit'}>
        <AddEditForm model={selected} closeModal={() => setModalState(null)} />
    </TfioDialog>
);
```

**Add/Edit form** (`{entity}_add_edit.tsx`):
```typescript
const methods = useForm<EditModel>({
    defaultValues: { ...props.model },
    resolver: fluentValidationResolver(new EditModelValidator(rules)),
});
return (
    <FormProvider {...methods}>
        <TfioTextInput name='field' required labelToken='token' labelDefault='Label' />
        <TfioDateInput name='dateField' required labelToken='...' labelDefault='...' />
        <TfioButton onClick={() => handleSubmit(onSubmit)()}>Save</TfioButton>
    </FormProvider>
);
```

---

## Layer 8: Frontend — Shared Components

### Three-Tier Hierarchy
```
shared/
  primitives/    → Thin MUI wrappers (TfioButton, TfioTextField, TfioDataGrid)
  input/         → Form-bound inputs with react-hook-form Controller (TfioTextInput, TfioSelect, TfioDateInput)
  common/        → Layout components (TfioPageWrapper, TfioModelView, TfioDialog, TfioGridToolbar)
  view/          → Read-only display (TfioViewItem)
  filter/        → Column definition factories (DateColumnDefinition, MultiSelectColumnDefinition)
```

### Input Component Convention
All `Tfio*Input` components:
1. Accept `name`, `labelToken`, `labelDefault`, `required?`
2. Use `useFormContextOrProp(control)` — works with `<FormProvider>` or prop-based
3. Use `useFormReadonly()` for read-only mode
4. Use `useTokenizedContent()` for i18n labels
5. Wrap: `<FormControl>` + `<TfioLabel>` + `<Controller>`

---

## Layer 9: Frontend — Validation

### Hybrid System (mirrors backend)
1. **Server rules** fetched at app startup (`GET /validations/rules`) → stored in Redux
2. **Client rules** added in domain validators extending `BaseValidator<T>`

```typescript
class ClientEditValidator extends BaseValidator<ClientEditModel> {
    constructor(rules: ValidationRuleModel[], content: ContentFunction) {
        super(rules);
        this.configureRules();   // server rules + local rules
    }
    protected configureRules() {
        super.configureRules();  // apply server-driven rules
        this.ruleFor('lastName').notEmpty().withMessage(this.content('...', '...'));
    }
}
```

Integration: `resolver: fluentValidationResolver(new XxxValidator(rules))`

---

## Layer 10: Frontend — Router

### Pattern: Modular lazy-loaded routes
```typescript
// routes.tsx
const router = createBrowserRouter([{
    path: "/",
    element: <Secure component={App} />,
    children: [...clientRoutes, ...caseRoutes, ...providerRoutes, ...]
}]);

// client.tsx
const clientRoutes: Array<RouteObject> = [
    { path: "clients", lazy: async () => ({ Component: (await import('...')).default }) },
    { path: "/client/face_sheet/:clientId", lazy: ..., children: [
        { path: "", lazy: ... },
        { path: "characteristics", lazy: ... },
        { path: "aliases", lazy: ... },
    ]},
];
```

---

## Layer 11: Frontend — Types

### Auto-generated from OpenAPI
- Build script reads Swagger spec → generates `com.tfione.api.d.ts` (interfaces) + `com.tfione.api.enums.ts`
- All API types imported via namespace: `TfiOneTypes.ClientEditModel`
- Client-only types in `com.tfione.client.d.ts`

---

## Naming Cheat Sheet

| Artifact | Convention | Example |
|----------|-----------|---------|
| Controller | `{Domain}Controller.cs` | `AdoptionController.cs` |
| Route | lowercase, hyphen-separated | `[Route("client/{clientId:guid}/adoption")]` |
| Repo Interface | `I{Domain}Repo.cs` | `IAdoptionRepo.cs` |
| Repo Implementation | `{Domain}Repo.cs` | `AdoptionRepo.cs` |
| Entity | PascalCase, singular | `Client`, `AdoptionChecklist` |
| Reference Entity | `{Name}Type` suffix | `GenderType` |
| PK Property | `{Entity}Id` | `ClientId` |
| Search Model | `{Entity}SearchModel` | `ClientSearchModel` |
| List Model | `{Entity}ListModel` | `ClientSearchListModel` |
| Edit Model | `{Entity}EditModel` | `AdoptionStaffingEditModel` |
| View Model | `{Entity}ViewModel` | `AdoptionStaffingViewModel` |
| Facesheet Model | `{Entity}FacesheetModel` | `ClientFacesheetModel` |
| Mappings | `{Domain}Mappings.cs` | `ClientMappings.cs` |
| Validator (.NET) | `{Model}Validator.cs` | `AdoptionStaffingEditModelValidator.cs` |
| Validator (TS) | `{model}_validator.ts` | `client_edit_validator.ts` |
| React Component | `PascalCase` | `ClientView`, `AliasAddEdit` |
| React File | `snake_case.tsx` | `alias_add_edit.tsx` |
| Shared Component | `Tfio` prefix | `TfioTextInput`, `TfioDataGrid` |
| RTK Query API | `{domain}Api` | `clientApi` |
| RTK Query Hook | `use{Endpoint}Query/Mutation` | `useClientSearchQuery` |
| Redux Slice | `{domain}Slice` | `globalSlice` |
| Route File | `{domain}.tsx` | `client.tsx` |
| Route Export | `{domain}Routes` | `clientRoutes` |
| Tag | lowercase string | `'client'`, `'clientfacesheet'` |
| URL Path | snake_case | `/client/face_sheet/:clientId` |
| Namespace (.NET) | `com.tfione.{layer}` | `com.tfione.repo.client` |
