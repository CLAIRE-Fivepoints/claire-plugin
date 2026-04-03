---
keywords: [api, endpoints, rest, controllers, routes, permissions, auth, swagger]
---

# TFI One — API Surface

**Base**: ASP.NET Core 8.0 Web API
**Auth**: JWT Bearer on all endpoints (except `[AllowAnonymous]`)
**Docs**: Swagger UI at `/swagger`
**Base Class**: `BaseController : ControllerBase` with `[ApiController][Authorize]`

---

## Auth (`/auth`)

*Has `[AllowMustChangePasswordClaim]` on class — all endpoints usable during password change flow*

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/login` | Anonymous | Authenticate with credentials + reCAPTCHA |
| POST | `/auth/login-sso` | Anonymous | Azure AD SSO login |
| POST | `/auth/change-password` | Authenticated | Update password |
| POST | `/auth/change-organization/{orgId}` | Authenticated | Switch org context |
| GET | `/auth/status` | Anonymous | Check auth status |
| POST | `/auth/change-mfa-preference` | Anonymous | Update MFA method |
| POST | `/auth/validate-otp` | Anonymous | Verify OTP code |
| POST | `/auth/refresh` | Anonymous | Refresh JWT token |
| GET | `/auth/logout` | Authenticated | Logout + revoke refresh token |
| GET | `/auth/content` | Anonymous | Get i18n content tokens |
| POST | `/auth/forgot-password` | Anonymous | Password reset email |

---

## App Users (`/users`)

| Method | Endpoint | Permission | Description |
|--------|----------|-----------|-------------|
| GET | `/users` | ViewUsers | Search users (paginated) |
| GET | `/users/{id}/view` | ViewUsers | View user detail (read-only) |
| GET | `/users/{id}` | ViewUsers | Get user for editing |
| GET | `/users/organization` | Authenticated | Users in current org |
| POST | `/users` | CreateUsers | Create user |
| PUT | `/users/{id}` | UpdateUsers | Update user |
| DELETE | `/users/{id}` | DeleteUsers | Soft delete user |

---

## Agencies (`/agencies`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agencies` | Search agencies (paginated) |
| GET | `/agencies/active` | Active agencies only |
| GET | `/agencies/{id}/view` | View agency (read-only) |
| GET | `/agencies/{id}` | Get agency for editing |
| POST | `/agencies` | Create agency |
| PUT | `/agencies/{id}` | Update agency |
| DELETE | `/agencies/{id}` | Soft delete |
| GET/POST/PUT/DELETE | `/agencies/{id}/addresses/...` | Address CRUD |
| GET/POST/PUT/DELETE | `/agencies/{id}/contractedservices/...` | Contracted services |
| GET | `/agencies/{id}/contractedservices/{csId}/approvalroles` | Approval roles |
| POST | `/agencies/{id}/agencyplacementratetype` | Create placement rate |
| GET/POST/PUT | `/agencies/{id}/agency_alerts/...` | Alert management |

---

## Providers (`/providers`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/providers` | Search providers |
| GET | `/providers/{id}/view` | View provider |
| GET | `/providers/{id}` | Get for editing |
| POST | `/providers` | Create provider |
| PUT | `/providers/{id}` | Update provider |
| DELETE | `/providers/{id}` | Soft delete |
| GET/POST/PUT/DELETE | `/providers/{id}/addresses/...` | Addresses |
| GET/POST/PUT/DELETE | `/providers/{id}/workers/...` | Workers |
| GET | `/providers/{id}/workers/assignable` | Assignable workers |
| GET | `/providers/{id}/agencyhistory` | Agency history |
| GET/POST/PUT/DELETE | `/providers/{id}/householdmembers/...` | HH members |
| GET/POST/PUT/DELETE | `/providers/{id}/pets/...` | Pets |
| GET/POST/PUT/DELETE | `/providers/{id}/pets/{petId}/vaccinations/...` | Vaccinations |
| GET/POST/PUT/DELETE | `/providers/{id}/documents/...` | Documents |
| GET/POST/PUT/DELETE | `/providers/{id}/incidents/...` | Incidents |
| GET/POST/PUT/DELETE | `/providers/{id}/phases/...` | Phases |
| GET/POST/PUT | `/providers/{id}/alerts/...` | Alerts |

---

## Clients (`/client`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/client` | Search clients |
| POST | `/client/intake/{intakeId}` | Save intake |
| GET | `/client/intake/{intakeId}` | Get intake |
| GET | `/client/intake/{intakeId}/clients` | Clients by intake |
| GET | `/client/intake/{intakeId}/case_participants` | Participants by intake |
| GET | `/client/intake/case_name/{caseNumber}` | Lookup case by number |
| GET | `/client/client/{intakeClientId}` | Get client |
| GET | `/client/client/pid/{pid}` | Get client by PID |
| POST | `/client/client` | Save client |
| DELETE | `/client/client/{intakeClientId}` | Delete client |
| GET | `/client/case_participant/{id}` | Get case participant |
| POST | `/client/case_participant` | Save participant |
| DELETE | `/client/case_participant/{id}` | Delete participant |

---

## Cases (`/cases`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cases` | Search cases |
| GET | `/cases/{id}` | Get case |
| POST | `/cases` | Create case |
| PUT | `/cases/{id}` | Update case |
| DELETE | `/cases/{id}` | Delete case |
| GET/POST/PUT/DELETE | `/cases/{id}/addresses/...` | Address CRUD |
| GET | `/cases/state/{id}/counties` | Counties by state |

---

## Other Controllers

| Controller | Route | Key Endpoints |
|-----------|-------|---------------|
| BackgroundCheckController | `/backgroundchecks` | Search, Add, View, Update |
| DocumentController | `/documents` | Definitions CRUD, Submissions, Toggle active |
| FileController | `/files` | Upload (Azure Blob), Download, Delete |
| FormController | `/forms` | Schemas, Versions, Submissions, Field Names |
| HouseholdMemberController | `/householdmembers` | CRUD, Training, Background checks |
| InquiryController | `/inquiries` | Search, CRUD, Dashboard, Workers, Contacts |
| PhaseController | `/phases` | Phase history, View, Add/Edit |
| PlacementAdjustmentsController | `/placements` | Rate adjustments |
| ServiceProviderController | `/serviceproviders` | CRUD, Contracts, Services |
| TrainingController | `/training` | Sessions, Roster, Outcomes, CRUD |
| ValidationController | `/validation` | Get validation rules |
| ReferenceController | `/reference` | All lookup/type data |
| PingController | `/ping` | Health check → "Pong!" (Anonymous) |

---

## Request / Response Conventions

### Pagination (Search Endpoints)
```typescript
// Request (query params via BaseSearchModel)
{
  start: 0,       // Offset
  length: 25,     // Page size
  sort: "lastName",
  sortDirection: "asc",
  // + domain-specific filters
}

// Response
{
  id: "...",
  messages: [],
  recordCount: 150,
  data: [ ... ]
}
```

### Messages (BaseModel.Messages)
```typescript
{
  id: "...",
  messages: [
    { message: "Validation failed", type: "error", field: "email" }
  ]
}
```

Message types: `"error"`, `"warning"`, `"info"`, `"success"`

### Auth Headers
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
X-Csrf-Token: <anti-forgery-token>  (only on login/change-password)
```

### CSRF Flow
1. GET/POST `/auth/login` — server sets `XSRF-TOKEN` cookie (HttpOnly=false)
2. Client reads cookie and sends as `X-Csrf-Token` header

---

## Permission Codes (PermissionCode enum)

```csharp
ViewUsers, CreateUsers, UpdateUsers, DeleteUsers,
AccessDocuments, ViewDocuments, DeleteDocuments, RenameDocuments, UploadDocuments
// + domain-specific codes per controller
```

---

## Education Module (`/client/{clientId}/education`) — feature/10399-client-mgmt-education

> **Note:** These routes exist in `feature/10399-client-mgmt-education` branch. The old `feature/10399-education-gaps` branch had flat routes (e.g. `/client/education-overview/{clientId}`) which are deprecated.

### Education Overview
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/client/{clientId}/education/overview` | Get education overview for client |
| PUT | `/client/{clientId}/education/overview` | Update education overview |

### Enrollment (`/client/{clientId}/enrollment`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/client/{clientId}/enrollment` | Search enrollments (paginated) |
| GET | `/client/{clientId}/enrollment/{id}` | Get single enrollment |
| POST | `/client/{clientId}/enrollment` | Create enrollment |
| PUT | `/client/{clientId}/enrollment/{id}` | Update enrollment |
| DELETE | `/client/{clientId}/enrollment/{id}` | Delete enrollment |

**Enrollment model fields** (flat, no nested address):
```
clientEnrollmentId, clientId, schoolName, isd, enrollmentDate, endDate,
gradeAchievedTypeId, creditsCompleted, remainingCredits, gpa,
addressLine1, addressLine2, city, stateTypeId (GUID), countyTypeId (GUID), zipCode
```

> ⚠️ **TfioAddress mapping required:** `TfioAddress` component uses nested `address.{ street1, street2, city, state, county, zipCode }` form fields. When using it with enrollment, you must map flat→nested on load (`methods.reset`) and nested→flat on submit. See `enrollment_add_edit.tsx` for reference implementation.

---

## Swagger

- Available at `/swagger` in Development and Gate
- JWT Bearer security definition configured
- Custom `ModelDocumentFilter` for complex models (ProviderWorkerDeleteModel, PermissionCode enum, etc.)
