---
keywords: [repository, baserepo, linq, efcore, transient, query, pagination, fluent-validation, dynamic-validator, permission-errors, authorization]
---

# TFI One — Repository Layer (`com.tfione.repo`)

**Pattern**: Repository Pattern with interface-based DI
**ORM**: Entity Framework Core 8.0
**Lifetime**: All Transient
**Validation**: FluentValidation 11.3.0 + DynamicValidator

---

## BaseRepo

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

All 38 repositories inherit `BaseRepo`, receiving `TfiOneContext` and `IUserAccessor`.

---

## Repository Registration

```csharp
services.AddTransient<IAuthRepo, AuthRepo>();
services.AddTransient<IAppUserRepo, AppUserRepo>();
services.AddTransient<IProviderRepo, ProviderRepo>();
services.AddTransient<IPhaseHistoryRepo, PhaseHistoryRepo>();
services.AddTransient<IPlacementAdjustmentsRepo, PlacementAdjustmentsRepo>();
services.AddTransient<IProviderAgencyHistoryRepo, ProviderAgencyHistoryRepo>();
services.AddTransient<IInquiryRepo, InquiryRepo>();
services.AddTransient<IBackgroundCheckRepo, BackgroundCheckRepo>();
services.AddTransient<IAgencyRepo, AgencyRepo>();
services.AddTransient<ITrainingRepo, TrainingRepo>();
services.AddTransient<IDocumentRepo, DocumentRepo>();
services.AddTransient<IClientRepo, ClientRepo>();
services.AddTransient<IHouseholdMemberRepo, HouseholdMemberRepo>();
services.AddTransient<ICaseRepo, CaseRepo>();
services.AddTransient<IFormRepo, FormRepo>();
services.AddTransient<IServiceProviderRepo, ServiceProviderRepo>();
services.AddTransient<IFileRepo, FileRepo>();
services.AddTransient<IBatchRepo, BatchRepo>();
```

---

## Repositories by Domain

### IAuthRepo / AuthRepo
Authentication and session management.

| Method | Returns | Purpose |
|--------|---------|---------|
| `Login(model)` | `AuthenticatedUserModel` | Validate credentials, build JWT claims |
| `LoginSso(model)` | `AuthenticatedUserModel` | Azure AD SSO login |
| `ChangePassword(model)` | `BaseModel` | Update password with history check |
| `ChangeOrganization(orgId)` | `AuthenticatedUserModel` | Switch org context |
| `RefreshToken(model)` | `AuthenticatedUserModel` | Issue new JWT from refresh token |
| `Logout()` | `BaseModel` | Revoke tokens |
| `GetContent()` | `List<AuthContentModel>` | i18n content tokens |
| `ForgotPassword(model)` | `BaseModel` | Send password reset email |
| `ChangeMfaPreference(model)` | `BaseModel` | Update MFA settings |
| `ValidateOtp(model)` | `AuthenticatedUserModel` | Verify OTP code |

### IAppUserRepo / AppUserRepo
User management CRUD.

| Method | Returns |
|--------|---------|
| `Search(model)` | `List<AppUserSearchModel>` (paginated) |
| `View(id)` | `AppUserViewModel` |
| `Get(id)` | `AppUserEditModel` |
| `GetByOrganization()` | `List<LookupOptionModel>` |
| `Create(model)` | `BaseModel` |
| `Update(id, model)` | `BaseModel` |
| `Delete(id)` | `BaseModel` |

### IProviderRepo / ProviderRepo
Provider CRUD + extensive sub-resources.

Core: `Search`, `View`, `Get`, `Create`, `Update`, `Delete`

Sub-resources (each with Search/Get/Create/Update/Delete):
- Provider Addresses
- Provider Workers (+ Assignable)
- Household Members (+ Races, Background Checks, Trainings)
- Pets (+ Vaccinations)
- Emergency Contacts
- Incident Reports
- Provider Alerts
- Provider Documents
- Provider Notes
- Phase History
- Placement History
- Location History
- License History
- Background Checks
- Training Management

### IAgencyRepo / AgencyRepo
Agency CRUD + contracted services + alerts.

Methods: `Search/View/Get/Create/Update/Delete`, `GetActive()`, address management, contracted services, approval roles, placement rates, alert management.

### IClientRepo / ClientRepo

| Method | Purpose |
|--------|---------|
| `Search(model)` | Client search |
| `SaveIntake(intakeId, model)` | Save intake record |
| `GetIntake(intakeId)` | Get intake |
| `GetClientsByIntakeId(intakeId)` | Clients in intake |
| `SaveClient(model)` | Save client |
| `DeleteClient(intakeClientId)` | Remove client |
| `SaveCaseParticipant(model)` | Save participant |
| `GetClientByPid(pid)` | Lookup by Person ID |
| `GetCaseNameByCaseNumber(num)` | Lookup case by number |

### ICaseRepo / CaseRepo
Case CRUD + addresses + county lookup.

### IInquiryRepo / InquiryRepo
Provider inquiry management. Includes `GetDashboard()`, `GetWorkers/SaveWorker`, `SearchProviders`.

### ITrainingRepo / TrainingRepo
Training sessions and enrollment. Includes `GetAvailableRoster/GetAssignedRoster`, `EnrollHouseholdMember/RemoveHouseholdMember`, `GetOutcomes/SaveOutcome`.

### IDocumentRepo / DocumentRepo
Document definitions, submissions, requirements. Includes `GetClientDocuments(clientId)`, `GetProviderDocuments(providerId)`.

### IFormRepo / FormRepo
Dynamic form schemas, versions, submissions, field names.

### Additional Repositories

| Repository | Domain |
|-----------|--------|
| `IPhaseHistoryRepo` | Provider phase lifecycle |
| `IPlacementAdjustmentsRepo` | Placement rate adjustments |
| `IProviderAgencyHistoryRepo` | Provider-agency relationships |
| `IBackgroundCheckRepo` | Background check operations |
| `IHouseholdMemberRepo` | Household member management |
| `IServiceProviderRepo` | Service provider CRUD + contracts |
| `IFileRepo` | File upload/download via Azure Blob |
| `IBatchRepo` | Batch job operations (Hangfire) |

---

## Permission Error Handling

Repositories **must communicate permission errors back to the client**. Authorization failures must not be swallowed at the repo layer.

- Permission errors must propagate to the API response as `403 Forbidden` or `401 Unauthorized`
- Multi-tenant data isolation is enforced at the repo level via `IRestrictedQueryProvider` and `OrganizationId` scoping
- If a user attempts to access data outside their organization or without the required permission, the repo must surface this — never return empty results silently

> Source: Steven Franklin's PR review, Rule #4 — "Repos need to communicate permission errors back to the client."

### How It Works

```
Controller → [PermissionAuthorize] → Repo
                                      ├── OrganizationId check (row-level)
                                      ├── RestrictedQueryProvider (column-level)
                                      └── Return error in Messages[] if unauthorized
```

The `[PermissionAuthorize]` attribute handles endpoint-level checks, but repos must also enforce data-level authorization (e.g., a user with `ClientView` permission should only see clients in their organization).

---

## Typical Query Pattern

```csharp
// Multi-tenant search with dynamic filtering and pagination
var query = Context.Providers
    .Where(p => p.OrganizationId == UserAccessor.GetCurrentOrganizationId())
    .AsQueryable();

// Dynamic filtering
if (!string.IsNullOrEmpty(model.ProviderName))
    query = query.Where(p => p.ProviderName.Contains(model.ProviderName));

// Projection to DTO
var results = await query
    .Select(p => new ProviderSearchModel { ... })
    .OrderBy(model.Sort, model.SortDirection)
    .Skip(model.Start)
    .Take(model.Length)
    .ToListAsync();
```

**No raw SQL or Dapper** — pure EF Core LINQ throughout.

---

## Validation Framework

### Hard-Coded Validators (FluentValidation)
```csharp
// Registered as Scoped
AddScoped<IValidator<ChangePasswordModel>, ChangePasswordValidator>();
AddScoped<IValidator<InquiryWorkerAddEditModel>, InquiryWorkerValidator>();
AddScoped<IValidator<TrainingEditModel>, TrainingEditValidator>();
AddScoped<IValidator<ProviderCreateModel>, ProviderCreateModelValidator>();
AddScoped<IValidator<PetEditModel>, ProviderPetEditModelValidator>();
// + All validators from AppUserValidator assembly
```

### Dynamic Validator (Fallback)
```csharp
// Registered as open generic fallback
AddTransient(typeof(IValidator<>), typeof(DynamicValidator<>));
```

When no hard-coded validator exists, `DynamicValidator<T>` loads rules from the `conf.ValidationRule` DB table and applies them at runtime. Enables admin-configurable validation without code changes.

### Validation Rule Types
18 rule types: `NotEmpty`, `NotNull`, `MaxLength`, `MinLength`, `Matches` (regex), `EmailAddress`, `LessThan`, `GreaterThan`, etc.
