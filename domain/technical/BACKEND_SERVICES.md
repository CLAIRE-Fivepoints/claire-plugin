---
keywords: [services, di, dependency-injection, encryption, jwt, cache, couchbase, azure-blob, twilio, sendgrid, adobe-sign, audit, interceptors]
---

# TFI One — Backend Service Layer (`com.tfione.service`)

**Purpose**: Business logic, cross-cutting concerns, external integrations
**Pattern**: Interface-based DI

---

## DI Registration Summary

```csharp
// Singletons (one instance, app lifetime)
AddSingleton<IEncryptor, Encryptor>()
AddSingleton<IPasswordGenerator, PasswordGenerator>()
AddSingleton<IJwtAuthenticator, JwtAuthenticator>()
AddSingleton<IAddressValidator, AddressValidator>()
AddSingleton<ICacheProvider, CouchbaseCacheProvider>()  // Prod
AddSingleton<ICacheProvider, MemoryCacheProvider>()     // Dev

// Scoped (one per request)
AddScoped<IEncryptionProvider, EncryptionProvider>()
AddScoped<IStorageProvider, AzureBlobStorageProvider>()

// Transient (new instance each injection)
AddTransient<IContentProvider, ContentProvider>()
AddTransient<IReferenceProvider, ReferenceProvider>()
AddTransient<IValidationRuleProvider, ValidationRuleProvider>()
AddTransient<IUserAccessor, UserAccessor>()
AddTransient<IRestrictedQueryProvider, RestrictedQueryProvider>()
AddTransient<IAuditHistoryProvider, AuditHistoryHandler>()
AddTransient<IMessenger, TwilioMessenger>()
AddTransient<IEmailSender, SendGridEmailSender>()
AddTransient<IRecaptchaService, RecaptchaService>()
AddTransient<IAuthenticatorService, AuthenticatorService>()

// EF Core Interceptors
AddTransient<ISaveChangesInterceptor, AuditInterceptor>()
AddTransient<ISaveChangesInterceptor, MetadataInterceptor>()
```

---

## Encryption & Security

### IEncryptor / Encryptor (Singleton)
Low-level AES encryption for data at rest.

| Method | Signature |
|--------|-----------|
| `Encrypt` | `(string cleartext) → string` |
| `Encrypt` | `(byte[] clearbytes) → byte[]` |
| `Decrypt` | `(string cryptotext) → string` |
| `Decrypt` | `(byte[] cryptobytes) → byte[]` |
| `Hash` | `(string input) → string` |
| `Hash` | `(byte[] input) → byte[]` |

**Used for**: SSN encryption, banking info, TOTP secrets.

### IEncryptionProvider / EncryptionProvider (Scoped)
Higher-level encryption using ASP.NET Core Data Protection API.

| Method | Signature |
|--------|-----------|
| `Encrypt` | `(purpose, value, enforceDedication) → string` |
| `Encrypt<T>` | `(purpose, value, enforceDedication) → string` |
| `Decrypt` | `(purpose, value, enforceDedication) → string` |
| `Decrypt<T>` | `(purpose, value, enforceDedication) → T` |
| `ValidUserForDecryption` | `(purpose, value) → bool` |

**Purpose strings** scope encryption keys. Data encrypted for "SSN" can't be decrypted by "BankAccount".

### IJwtAuthenticator / JwtAuthenticator (Singleton)

| Method | Signature |
|--------|-----------|
| `GenerateToken` | `(AuthenticatedUserModel) → string` |
| `GenerateRefreshToken` | `() → string` |
| `GetPrincipalFromToken` | `(token, validateLifetime) → ClaimsPrincipal?` |

Token contents: AppUserId, OrganizationId, Organizations (JSON), MustChangePassword, PermissionDictionary (JSON).

---

## Authentication Services

### IAuthenticatorService / AuthenticatorService (Transient)
MFA/OTP support via TOTP.

| Method | Signature |
|--------|-----------|
| `SendOtpChallengeAsync` | `(user) → Task<bool>` |
| `ValidateOtpCode` | `(user, otpCode) → Task<bool>` |

Uses `Otp.NET` for TOTP generation/validation.

### IUserAccessor / UserAccessor (Transient)
Extracts current user context from JWT claims.

| Method | Returns |
|--------|---------|
| `GetCurrentAppUserId()` | `Guid` |
| `GetCurrentOrganizationId()` | `Guid` |
| `GetSystemUserId()` | `Guid` |
| `GetCurrentUserName()` | `string` |
| `HasCurrentUserValidClaims()` | `bool` |
| `GetCurrentUserOrganizations()` | `IEnumerable<AuthOrganizationModel>` |
| `GetUserFullName()` | `string` |
| `GetCurrentRoleCode()` | `string?` |
| `GetDataPermissionTargets(code)` | `IEnumerable<Guid>` |

### IRestrictedQueryProvider / RestrictedQueryProvider (Transient)
Row-level security enforcement.

| Method | Signature |
|--------|-----------|
| `GetRestrictedQuery<T>` | `(permissionCode?) → IQueryable<T>` |

Restricts queries to entities matching user's organization and `DataPermission` entries.

---

## Caching

### ICacheProvider (Environment-dependent)

| Method | Signature |
|--------|-----------|
| `GetAsync<T>` | `(key, region?, ct) → Task<T?>` |
| `SetAsync<T>` | `(key, data, timeoutMins, region?, ct) → Task` |
| `InvalidateAsync` | `(key, region?, ct) → Task` |

| Environment | Class | Backend |
|-------------|-------|---------|
| Development | `MemoryCacheProvider` | In-process memory |
| Production | `CouchbaseCacheProvider` | Couchbase cluster (3 nodes) |

Couchbase config: nodes `tfione-cache-u1/u2/u3`, bucket `default_cache`.

---

## Content & Reference Data

### IContentProvider / ContentProvider (Transient)
Server-driven i18n content.

| Method | Signature |
|--------|-----------|
| `GetContent` | `(token, defaultValue) → Task<string>` |
| `GetContentList` | `() → Task<List<AuthContentModel>>` |

### IReferenceProvider / ReferenceProvider (Transient)
Lookup/reference data.

| Method | Signature |
|--------|-----------|
| `GetReferences` | `(referenceType) → Task<List<LookupOptionModel>>` |
| `GetReferences<T>` | `() → Task<List<LookupOptionModel>>` |
| `GetChildReferences` | `(referenceType, parentId) → Task<List<LookupOptionModel>>` |
| `GetOrgReferences` | `(referenceType) → Task<List<LookupOptionModel>>` |
| `GetOrgEntities` | `(entityType) → Task<List<LookupOptionModel>>` |

### IValidationRuleProvider / ValidationRuleProvider (Transient)
Backend-driven validation rules.

| Method | Signature |
|--------|-----------|
| `GetValidationRules` | `(modelTypeCode, clientSide) → Task<List<ValidationRuleModel>>` |
| `GetValidationRules` | `(clientSide) → Task<List<ValidationRuleModel>>` |

---

## External Integrations

### IMessenger / TwilioMessenger (Transient) — SMS
```
Phone: +19412601808
Config: AccountSid, AuthToken from appsettings/KeyVault
```

### IEmailSender / SendGridEmailSender (Transient) — Email
```
From: info@tfione.com
Config: API key from appsettings/KeyVault
```

### IRecaptchaService / RecaptchaService (Transient)
- `ValidateV2(token) → Task<bool>` — v2 checkbox
- `ValidateV3(token) → Task<RecaptchaResult>` — v3 score (threshold 0.5)

### IStorageProvider / AzureBlobStorageProvider (Scoped)
- `UploadAsync(stream, containerName, blobName) → Task<Uri>`
- `DownloadAsync(containerName, blobName) → Task<Stream>`
- `DeleteAsync(containerName, blobName) → Task`

Container: `data`, account: `tfieu2qa01`.

### IAddressValidator / AddressValidator (Singleton) — Google Maps
- `ValidateAsync(address) → Task<ValidationResult>`

### Adobe Sign Services (Transient)
- `AdobeEndpointService` — REST API v6 orchestration
- `AdobeAgreementsService` — Agreement creation/management
- `AdobeSearchService` — Query agreements
- `AdobeTransientService` — Transient error handling

Base URL: `https://fivepoints.na4.adobesign.com/public/docs/restapi/v6`

---

## Audit & Interceptors

### AuditInterceptor (ISaveChangesInterceptor)
- Fires on `SaveChangesAsync`
- Captures: Added, Modified, Deleted entities
- Records: old values, new values, property names
- Writes to Azure Table Storage (by date + by user)

### MetadataInterceptor (ISaveChangesInterceptor)
Auto-populates audit metadata fields:

| Event | Fields Set |
|-------|-----------|
| Insert | `CreatedDate`, `CreatedBy` (from UserAccessor) |
| Update | `UpdatedDate`, `UpdatedBy` (from UserAccessor) |
| Soft Delete | `DeletedDate`, `DeletedBy`, `Deleted = true` |

### IAuditHistoryProvider / AuditHistoryHandler (Transient)
- `LogAuditAsync` — Write audit record to Azure Tables
- Tables: `AuditAppUser{ENV}{YEAR}` and `AuditAppUserByUser{ENV}{YEAR}`
