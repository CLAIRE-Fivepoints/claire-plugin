---
keywords: [redux, state-management, rtk-query, slices, api, cache, auth, persistence, 401-refresh]
---

# TFI One — Frontend State Management

**Library**: Redux Toolkit 2.8.2 + Redux Persist 6.0.0
**API Layer**: RTK Query (built into Redux Toolkit)
**Persistence**: localStorage via redux-persist (key: `root`)

---

## Store Architecture

```
Redux Store
├── global          (UI state: loading, messages, org context)
├── auth            (JWT token, user info, permissions, content)
├── validation      (backend-driven validation rules)
├── provider        (current provider + household member context)
├── agency          (current agency context)
├── serviceprovider (current service provider context)
├── backgroundcheck (current background check context)
└── [apiSlice]      (RTK Query cache: 20 API services, 42+ tags)
```

All slices persisted to localStorage.

---

## Slices Detail

### `global.ts` — UI State
```typescript
{
  waiting: boolean;                         // Loading backdrop visible
  messages: MessageModel[];                 // Snackbar notification queue
  selectedOrganization: OrganizationModel | null;  // Active tenant
}
```
Actions: `wait`, `endWait`, `addMessage`, `removeMessage`, `setSelectedOrganization`

### `auth.ts` — Authentication
```typescript
{
  isAuthenticated: boolean;
  user: AuthenticatedUserModel | null;
  // user includes:
  //   token: string (JWT)
  //   refreshToken: string
  //   organizations: OrganizationModel[]
  //   currentPermissionDictionary: Record<string, boolean>
  //   permissionBypass: boolean (admin flag)
  content: AuthContentModel[];    // Tokenized i18n content
}
```
Actions: `logIn`, `resetAuth`, `setContent`

### `validation.ts` — Backend-Driven Rules
```typescript
{
  rules: ValidationRuleModel[];   // Rules fetched from /validation/rules
}
```
Actions: `setRules`

### `provider.ts` — Provider Context
```typescript
{
  provider: ProviderModel | null;
  householdMember: HouseholdMemberModel | null;
}
```
Actions: `setProvider`, `resetProvider`, `setHouseholdMember`, `resetHouseholdMember`

### `agency.ts` / `serviceprovider.ts` / `backgroundcheck.ts`
Single-entity context slices with `setXxx` and `resetXxx` actions.

---

## RTK Query API Layer

### Base Query Configuration

```typescript
// Dual transport
const fetchBaseQuery = ...  // primary (native fetch)
const axiosBaseQuery = ...  // secondary (file operations)

// Headers injected on every request:
// Authorization: Bearer <jwt>
// X-Csrf-Token: <from XSRF-TOKEN cookie>
// Content-Type: application/json
```

### 401 Auto-Refresh Flow

```
Request fails with 401
  ↓
Extract refreshToken from Redux auth slice
  ↓
POST /auth/refresh { refreshToken }
  ↓
Success → Update auth state → Retry original request
Failure → resetAuth() → Redirect to /login
```

### Error Handling Flow

```
API Response
  ↓
Status 400 → Extract validation errors → dispatch addMessage (per field)
Status 401 → Trigger refresh flow (above)
Status 4xx/5xx → Extract message → dispatch addMessage (error type)
  ↓
Messages in response.messages → dispatch addMessage (info/warning)
```

---

## Cache Tag System (42+ tags)

```
auth, user, phase, provider, agency, inquiry, training,
document, householdMember, backgroundCheck, form,
serviceprovider, providerAlert, agencyAlert, file,
branchAssignment, powerbi, reference, validation...
```

Each mutation invalidates relevant tags → RTK Query auto-refetches affected queries.

---

## 20 API Service Files (`redux/services/`)

| Service | Key Operations | Cache Tags |
|---------|---------------|------------|
| `auth.ts` | login, logout, refresh, change-org, MFA | auth |
| `user.ts` | CRUD users, search, org lookup | user |
| `provider.ts` | CRUD providers, workers, households, pets, phases, training, incidents | provider, phase, householdMember |
| `agency.ts` | CRUD agencies, contracted services, rates, approval roles | agency |
| `client.ts` | Search, intake CRUD, case participants | client |
| `document.ts` | Definitions, submissions, toggle active | document |
| `form.ts` | Schemas, versions, submissions, field names | form |
| `inquiry.ts` | Search, dashboard, workers, CRUD | inquiry |
| `training.ts` | Sessions, roster, outcomes, CRUD | training |
| `background_check.ts` | CRUD, dispositions | backgroundCheck |
| `serviceprovider.ts` | CRUD, face sheet | serviceprovider |
| `agency_alert.ts` | Agency alert management | agencyAlert |
| `providerAlert.ts` | Provider alert management | providerAlert |
| `reference.ts` | All lookup/type data | reference |
| `validation.ts` | Validation rules | validation |
| `householdMembers.ts` | Household member operations | householdMember |
| `branch_assignment.ts` | Branch assignments | branchAssignment |
| `file.ts` | Upload/download files | file |
| `com.powerbi.api/api.ts` | Power BI integration | powerbi |

---

## Permission Check Pattern

```typescript
// Check permission in component
const user = useAppSelector(state => state.auth.user);
const canEdit = user?.currentPermissionDictionary["UpdateUsers"] === true;

// Or use permissionBypass for SU (SuperUser) role in dev
const hasPermission = user?.permissionBypass || canEdit;
```

---

## Org Context Pattern

```typescript
// Organization stored in both auth slice and global slice
const currentOrg = useAppSelector(state => state.global.selectedOrganization);

// Switch org
dispatch(auth.changeOrganization(orgId));
// → Calls POST /auth/change-organization/{orgId}
// → Gets new JWT with new org context
// → Updates auth slice
```
