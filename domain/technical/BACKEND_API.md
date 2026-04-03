---
keywords: [api, middleware, pipeline, jwt, authentication, authorization, csrf, antiforgery, cors, errorhandling, aspnetcore]
---

# TFI One — Backend API Layer (`com.tfione.api`)

**Framework**: ASP.NET Core 8.0
**Auth**: JWT Bearer + Custom Permission System
**Docs**: Swagger/OpenAPI (Swashbuckle 7.2.0)

---

## Middleware Pipeline (order matters)

```
WebApplication.CreateBuilder(args)
│
├── Services Registration
│   ├── AddDbServices()          → EF Core + SQL Server + interceptors
│   ├── AddRepoServices()        → 38 repositories (Transient)
│   ├── AddServiceServices()     → Encryption, cache, messaging, storage
│   ├── AddApiServices()         → Auth, validation, Swagger
│   ├── AddAuthentication()      → JWT Bearer
│   ├── AddAuthorization()       → Custom PolicyProvider
│   ├── AddAntiforgery()         → CSRF protection
│   ├── AddCors()                → Origin whitelist
│   └── Serilog + Sentry         → Logging & error tracking
│
├── Middleware Pipeline
│   ├── ErrorHandling            → Global exception catch
│   ├── UseRouting()
│   ├── UseCors()                → (conditional, not in DockerBuild)
│   ├── UseAuthentication()
│   ├── UseAuthorization()
│   ├── MustChangePassword       → 403 if password expired
│   ├── AntiForgery              → Token injection on login/change-pwd
│   └── MapControllers()
│
└── app.Run()
```

---

## Authentication Settings

| Setting | Value |
|---------|-------|
| JWT Issuer | `https://tfione.com` |
| JWT Audience | `https://tfione.com` |
| JWT Algorithm | HS256 (HMAC-SHA256) |
| Token Lifetime | 5 minutes |
| Refresh Token Lifetime | 7 days |
| MFA Expiration | 30 days |
| Password Change Interval | 90 days |
| Min Password Length | 12 characters |
| SuperUser Bypass (dev) | `true` |

---

## Custom Authorization System

### Flow
```
Request with JWT
  ↓
[PermissionAuthorize(PermissionCode.ViewUsers)]  ← Attribute on action
  ↓
CustomPolicyProvider  ← Parses "Permissions:ViewUsers" policy string
  ↓
PermissionsAuthorizationHandler  ← Evaluates claims
  ↓
ClaimsPrincipal.Claims["permission-dictionary"]  ← JSON dict from JWT
  ↓
Check: Does user have required PermissionCode?
  ↓
SuperUser (RoleCode "SU") bypass in Development
```

### Components

| Class | Role |
|-------|------|
| `PermissionAuthorizeAttribute` | Extends `[Authorize]`, accepts `PermissionCode[]` |
| `CustomPolicyProvider` | Builds policies from `"Permissions:X,Y"` string |
| `PolicyProvider` | Wrapper with fallback to default policy provider |
| `PermissionsAuthorizationHandler` | Evaluates permission claims against requirements |
| `PermissionRequirement` | Holds required `PermissionCode` for a policy |

### Custom Claim Types

| Claim | Key | Content |
|-------|-----|---------|
| App User ID | `app-user-id` | GUID |
| Current Org | `current-org-id` | GUID |
| Organizations | `orgs` | JSON array |
| Must Change Password | `must-change-password` | `"true"/"false"` |
| Permission Dictionary | `permission-dictionary` | JSON `Dict<string, Guid[]>` |

---

## Middleware Detail

### ErrorHandling (Global Exception Handler)
- Catches all unhandled exceptions
- Special handling for `ConnectionResetException`
- Logs to Azure Table Storage (by date + by user)
- Optionally sends email to error address
- Returns `BaseModel` with `Messages` list

### MustChangePasswordMiddleware
- Checks JWT for `MustChangePassword = "true"` claim
- Returns **403 Forbidden** unless endpoint has `[AllowMustChangePasswordClaim]`
- Bypassed on `/auth/change-password`

### AntiForgeryMiddleware
- Active on `/auth/login` and `/auth/change-password`
- Sets non-HTTP cookie `XSRF-TOKEN` with request token
- Cookie: `HttpOnly=false, Secure=true, SameSite=None`
- Client reads cookie → sends as `X-Csrf-Token` header

### ValidationFilter (IAsyncActionFilter)
- Fires on POST, PUT, PATCH actions
- Runs FluentValidation on action arguments
- Returns `400 BadRequest` with field-level validation messages

---

## Cookie Configuration

| Cookie | Name | HttpOnly | Secure | SameSite |
|--------|------|----------|--------|----------|
| Auth Token | `AUTH-TOKEN` | true | true | None |
| CSRF (HTTP) | `CSRF-TOKEN` | true | true | None |
| CSRF (Non-HTTP) | `XSRF-TOKEN` | **false** | true | None |

The `XSRF-TOKEN` cookie is readable by JavaScript (HttpOnly=false) so the frontend can extract it and send it as the `X-Csrf-Token` header.

---

## JSON Converters (registered globally)

| Converter | Purpose |
|-----------|---------|
| `DateOnlyJsonConverter` | Serialize/deserialize `DateOnly` |
| `NullableDateOnlyJsonConverter` | Nullable `DateOnly?` |
| `NullableDateTimeJsonConverter` | Nullable `DateTime?` |
| `NullableGuidConverter` | Nullable `Guid?` |
| `GuidConverter` | `Guid` handling |
| `EmptyStringToNullableIntConverter` | `""` → `null` for int? |
| `GuidArrayFilterEmptyConverter` | Filter empty GUIDs from arrays |

---

## Docker Configuration

```dockerfile
FROM mcr.microsoft.com/dotnet/aspnet:8.0-windowsservercore-ltsc2022
EXPOSE 8080
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "com.tfione.api.dll"]
```

**Windows Server Core image** — not Linux. Required for Windows-specific dependencies.
