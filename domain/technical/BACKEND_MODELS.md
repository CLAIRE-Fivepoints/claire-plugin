---
keywords: [models, dto, viewmodel, basemodel, basesearchmodel, enums, settings, permissions, constants]
---

# TFI One — Model Layer (`com.tfione.model`)

**Purpose**: DTOs, ViewModels, SearchModels, Enums, Constants, Settings
**Shared by**: All backend projects (API, Service, Repo, DB, Chron)

---

## Base Classes

### BaseModel
```csharp
public class BaseModel
{
    public Guid Id { get; set; }
    public List<MessageModel> Messages { get; set; } = new();
}
```
All DTOs inherit `BaseModel`. `Messages` carries server-side notifications/errors to client.

### BaseSearchModel : BaseModel
```csharp
public class BaseSearchModel : BaseModel
{
    public int Start { get; set; }           // Pagination offset
    public int Length { get; set; }          // Page size
    public int RecordCount { get; set; }     // Total records (output)
    public string? Sort { get; set; }        // Sort column
    public string? SortDirection { get; set; } // "asc" or "desc"
}
```
All search/list DTOs inherit this for consistent pagination.

### LookupOptionModel
```csharp
public class LookupOptionModel
{
    public Guid Id { get; set; }
    public string Code { get; set; }
    public string Description { get; set; }
    public Guid? ParentId { get; set; }  // For hierarchical lookups
}
```
Used by `ReferenceProvider` for all dropdown/select data.

### MessageModel
```csharp
public class MessageModel
{
    public string Message { get; set; }
    public string Type { get; set; }    // "error", "warning", "info", "success"
    public string? Field { get; set; }  // For field-level validation
}
```

---

## Model Organization

```
com.tfione.model/
├── admin/          # User management DTOs
├── agency/         # Agency DTOs
├── auth/           # Authentication DTOs
├── @case/          # Case management DTOs (@ prefix for C# keyword)
├── client/         # Client DTOs
├── core/           # BaseModel, BaseSearchModel, LookupOptionModel, MessageModel
├── file/           # File handling DTOs
├── provider/       # Provider DTOs (largest set)
├── enumeration/    # Enums
├── settings/       # Configuration classes
└── Extensions.cs   # Model-layer DI extensions
```

---

## DTOs by Domain

### Auth Models (`auth/`)

| Model | Purpose |
|-------|---------|
| `LoginModel` | Login request (username, password, recaptcha token) |
| `LoginSsoModel` | SSO login request (Azure AD token) |
| `AuthenticatedUserModel` | Login response (JWT, refresh token, user info, permissions, orgs) |
| `AuthOrganizationModel` | Organization in user's context |
| `AuthContentModel` | i18n content token (token + value) |
| `ChangePasswordModel` | Password change (old, new, confirm) |
| `ForgotPasswordModel` | Password reset (email) |
| `ChangeMfaPreferenceModel` | MFA method change |
| `ValidateOtpModel` | OTP verification (code) |
| `RefreshTokenModel` | Token refresh request |

### Admin/User Models (`admin/`)

| Model | Purpose |
|-------|---------|
| `AppUserSearchModel : BaseSearchModel` | User search filters |
| `AppUserEditModel : BaseModel` | User create/edit (name, email, username, roles, orgs) |
| `AppUserViewModel : BaseModel` | User detail view (read-only projection) |

### Agency Models (`agency/`)

| Model | Purpose |
|-------|---------|
| `AgencySearchModel : BaseSearchModel` | Agency search filters |
| `AgencyEditModel : BaseModel` | Agency create/edit |
| `AgencyViewModel : BaseModel` | Agency detail view |
| `AgencyAddressEditModel` | Address create/edit |
| `AgencyContractedServiceModel` | Contracted service |
| `AgencyPlacementRateTypeModel` | Placement rate |
| `AgencyAlertEditModel` | Alert create/edit |
| `AgencyAlertSearchModel : BaseSearchModel` | Alert search |

### Provider Models (`provider/`) — Largest set

| Model | Purpose |
|-------|---------|
| `ProviderSearchModel : BaseSearchModel` | Provider search |
| `ProviderCreateModel : BaseModel` | Provider creation |
| `ProviderEditModel : BaseModel` | Provider edit |
| `ProviderViewModel : BaseModel` | Provider view |
| `ProviderWorkerEditModel` | Worker assignment |
| `HouseholdMemberEditModel` | Household member edit |
| `HouseholdMemberTrainingModel` | Training assignment |
| `PetEditModel` | Pet information |
| `PetVaccinationEditModel` | Vaccination record |
| `ProviderAddressEditModel` | Provider address |
| `ProviderAlertEditModel` | Provider alert |
| `ProviderIncidentReportModel` | Incident report |
| `PhaseHistoryModel` | Phase record |
| `PlacementHistoryModel` | Placement record |

### Client Models (`client/`)

| Model | Purpose |
|-------|---------|
| `ClientSearchModel : BaseSearchModel` | Client search |
| `IntakeModel : BaseModel` | Intake record |
| `IntakeClientModel` | Client within intake |
| `IntakeCaseParticipantModel` | Participant within intake |

### Case Models (`@case/`)

| Model | Purpose |
|-------|---------|
| `CaseSearchModel : BaseSearchModel` | Case search |
| `CaseEditModel : BaseModel` | Case edit |
| `CaseAddressEditModel` | Case address |

### File Models (`file/`)

| Model | Purpose |
|-------|---------|
| `FileUploadModel` | Upload request (stream, filename, content type) |
| `FileDownloadModel` | Download response |
| `FileMetaDataModel` | File metadata |

---

## Enumerations

### PermissionCode
```csharp
public enum PermissionCode
{
    ViewUsers, CreateUsers, UpdateUsers, DeleteUsers,
    AccessDocuments, ViewDocuments, DeleteDocuments,
    RenameDocuments, UploadDocuments
    // + domain-specific codes
}
```

### Other Enums

| Enum | Domain | Values |
|------|--------|--------|
| `AuditAction` | Audit | Created, Updated, Deleted |
| `ErrorCode` | Errors | ValidationFailed, Unauthorized, NotFound, etc. |
| `FileSlice` | Azure | Chunk identifiers for large file uploads |
| `ModelTypeCode` | Validation | Identifies which model a validation rule applies to |

---

## Settings Classes (bound via IOptions\<T\>)

| Class | Key Settings |
|-------|-------------|
| `AuthSettings` | Issuer, Audience, SecretKey, TokenLifetime (5min), RefreshLifetime (7days), MfaExpiration (30d), PasswordInterval (90d), MinPasswordLength (12), SuperUserBypass |
| `AppSettings` | FromAddress, BaseUrl, SupportAddress, CompanyPhone, BccAddress |
| `AuditSettings` | AzureTableByDate, AzureTableByUser |
| `AzureLogSettings` | SerilogTable, ErrorTable, ErrorAddress |
| `AzureStorageAccountSettings` | ConnectionString, BlobContainer |
| `BatchSettings` | Schedule configs for recurring jobs |
| `CouchbaseSettings` | Nodes (u1/u2/u3), DefaultBucket, Username, Password |
| `SendGridSettings` | ApiKey, FromAddress |
| `TwilioSettings` | AccountSid, AuthToken, PhoneNumber |
| `AdobeSignSettings` | BaseUrl, ClientId, ClientSecret, RefreshToken |
| `GoogleValidationSettings` | ApiKey |
| `RecaptchaSettings` | SiteKeyV2, SecretKeyV2, SiteKeyV3, SecretKeyV3, ThresholdScore (0.5) |

---

## Constants

### AuthorizationConstants
```csharp
public const string PolicyDelimiter = ",";
public const string PermissionPolicyPrefix = "Permissions:";
public const string SuperUser = "SU";
```

### CustomClaimTypes
```csharp
public const string AppUserId = "app-user-id";
public const string CurrentOrganizationId = "current-org-id";
public const string Organizations = "orgs";
public const string MustChangePassword = "must-change-password";
public const string PermissionDictionary = "permission-dictionary";
```
