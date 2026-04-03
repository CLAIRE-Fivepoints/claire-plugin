---
keywords: [domain, entities, foster-care, client, provider, agency, case, appuser, relationships, aggregate]
---

# TFI One — Domain Model

**Core Domain**: Foster Care / Child Welfare Management

---

## Entity Relationship Map

```
Organization (Tenant Root)
├── Agency ────────────────── Provider (N:N via AgencyHistory)
│   ├── Addresses              ├── Addresses
│   ├── FundingSources         ├── Workers
│   ├── PlacementRates         ├── HouseholdMembers
│   ├── ApprovalRoles          │   ├── Races
│   └── ContractedServices     │   ├── BackgroundChecks
│                              │   ├── Trainings
│                              │   └── Pets + Vaccinations
│                              ├── Alerts
│                              ├── Documents
│                              ├── Phases (licensing lifecycle)
│                              ├── Placements
│                              ├── IncidentReports
│                              └── Inquiries (prospect tracking)
│
├── Client ─────────────────── Case (via CaseParticipant)
│   ├── Addresses              ├── CaseAddresses
│   ├── DocumentRequirements   ├── Intakes
│   ├── IncidentReports        │   ├── IntakeCaseParticipants
│   ├── ProgramEnrollments     │   └── IntakeClients
│   └── CaseWorkAssignment     └── CaseParticipants
│
├── AppUser
│   ├── Organizations (N:N via AppUserOrganization)
│   │   └── Roles → Permissions
│   ├── DataPermissions
│   ├── PasswordHistory
│   └── OtpChallenges (MFA)
│
├── ServiceProvider
│   ├── Addresses
│   ├── Contracts → ContractedServices
│   └── Services
│
├── TrainingSession
│   ├── Classes
│   ├── HouseholdMembers (enrolled)
│   └── Outcomes
│
├── DocumentDefinition
│   ├── ClientDocumentRequirements → Submissions
│   └── ProviderDocumentRequirements → Submissions
│
└── FormSchema → FormSchemaVersions → FormSubmissions
```

---

## Primary Aggregates

### 1. Client (Foster Child / Ward)
The person receiving care within the child welfare system.

| Property | Notes |
|----------|-------|
| PersonNumber | System identifier |
| FirstName, MiddleName, LastName | Demographics |
| DateOfBirth | |
| SSN | **Encrypted** at column level |
| Gender → GenderType | Lookup reference |
| Ethnicity → EthnicityType | Lookup reference |
| Status → ClientStatusType | Active, Inactive, etc. |
| PermanencyGoal → PermanencyGoalType | Adoption, Reunification, etc. |
| IcwaStatus → IcwaStatusType | Indian Child Welfare Act status |

**Relationships**: Addresses, DocumentRequirements, IncidentReports, ProgramEnrollments

---

### 2. Provider (Foster Parent / Care Provider)
Licensed individuals/families providing foster care.

| Property | Notes |
|----------|-------|
| ProviderName | Display name |
| ProviderNumber | License/registration number |
| ProviderType → ProviderTypeType | Family, Group, Therapeutic |
| ProviderStatus → ProviderStatusType | Active, Pending, Closed |
| StartDate / EndDate | Active window |

**Relationships**: Addresses, AgencyHistories, Workers, HouseholdMembers, Alerts, Documents, Phases, Placements, IncidentReports, Inquiries

**Lifecycle**: Inquiry → Application → Phase Progression → Licensed → Active → Closure

**Sub-resources** (richest entity):
```
Provider
├── ProviderAddress (N)
├── ProviderAlert (N)
├── ProviderAgencyHistory (N)
├── ProviderWorker (N)
├── HouseholdMember (N)
│   ├── HouseholdMemberRace (N)
│   ├── HouseholdMemberBackgroundCheck (N)
│   ├── HouseholdMemberTraining (N)
│   └── ProviderPet (N)
│       └── ProviderPetVaccination (N)
├── PhaseHistory (N)
│   └── PhaseWithdrawal (N)
└── PlacementAdjustment (1)
```

---

### 3. Agency
Organizations that manage providers and clients under contract.

| Property | Notes |
|----------|-------|
| AgencyName | |
| AgencyNumber | Contract identifier |
| AgencyCode | Short code |
| ContractNumber | Government contract |
| PreferredVendor | Priority flag (bool) |
| BankingInfo | **Encrypted** at column level |

**Relationships**: Addresses, FundingSources, PlacementRates, ApprovalRoles, Clients, Providers

```
Agency
├── AgencyAddress (N)
├── AgencyAlert (N)
├── AgencyBranch (N)
├── AgencyPlacementRateType (N)
│   └── AgencyPlacementRateTypeApprovalRole (N)
└── AgencyFundingSource (N)
```

---

### 4. Case
A legal case record linking participants (children, parents, workers) to agency oversight.

| Property | Notes |
|----------|-------|
| CaseName | |
| CaseNumber | Court/system reference |
| OrganizationId | Tenant scope |

**Relationships**: CaseAddresses, Intakes, CaseParticipants

Participants have roles: child, biological parent, foster parent, social worker, attorney, CASA, etc.

```
Case
├── CaseAddress (N)
├── CaseParticipant (N)
│   └── CaseParticipantAddress (N)
└── Intake
    ├── IntakeCaseParticipant (N)
    └── IntakeClient (N) → Client
```

---

### 5. AppUser (System User)
Internal user with authentication and multi-org access.

| Property | Notes |
|----------|-------|
| Username | Login identifier |
| Email | |
| PasswordHash | Salted hash |
| Salt | Per-user salt |
| EncryptedTotpSecret | **Encrypted** MFA secret |
| MfaEnabled | bool |
| Status → AppUserStatusType | Active, Locked, Disabled |
| LastLogOn | DateTime |
| PasswordFailCount | Lockout tracking |

**Relationships**: Organizations (N:N via AppUserOrganization), Roles (per-org), DataPermissions, PasswordHistory, OtpChallenges

---

## Encrypted Fields

Sensitive data encrypted at column level via `IEncryptor`:
- `Client.SSN` — Social Security Number
- `Agency.BankingInfo` — Banking/payment info
- `AppUser.EncryptedTotpSecret` — MFA TOTP secret

---

## Cross-Cutting Interfaces

| Interface | Purpose | Applied To |
|-----------|---------|-----------|
| `IDeletable` | Soft delete (Deleted bit, DeletedDate, DeletedBy) | All entities |
| `IOrganizationalReference` | Multi-tenancy (OrganizationId) | All tenant-scoped entities |
| `IRestrictedQuery` | Row-level security (RestrictedId) | Provider, Agency, Client, Case |
| `IChildReference` | Parent-child lookup relationships | CountyType, HouseholdMemberRoleSubType |
| `IReference` | Lookup/reference tables (Code, Description) | All 50+ reference tables |
| `IAuditable` | Marks entities for AuditInterceptor tracking | Key business entities |

---

## Metadata (Auto-populated by MetadataInterceptor)

| Field | Set On |
|-------|--------|
| CreatedDate | Insert |
| CreatedBy | Insert (from JWT `app-user-id` claim) |
| UpdatedDate | Update |
| UpdatedBy | Update (from JWT `app-user-id` claim) |
| DeletedDate | Soft delete |
| DeletedBy | Soft delete |

---

## Lookup / Reference Types (50+)

**Person**: GenderType, EthnicityType, RaceType, MaritalStatusType, FamilyStatusType, LevelOfEducationType

**Status**: ClientStatusType, ProviderStatusType, InquiryStatusType, DocumentDefinitionStatusType, TrainingStatusType

**Case/Role**: CaseRoleType, HouseholdMemberRoleType, HouseholdMemberRoleSubType, EmergencyContactRelationshipType

**Document**: DocumentDefinitionFrequencyType, DocumentDefinitionExpirationType, DocumentDefinitionTriggerType

**Background Check**: BackgroundCheckType, BackgroundCheckReasonType

**Incident**: IncidentReportType, IncidentReportNatureType, IncidentReportLocationLevelType, IncidentReportActionType

**Financial**: PlacementRateType, PlacementRateUnitType

**Service**: ServiceType, ServiceCategoryType, ServiceProviderType

**Location**: StateType, CountyType, AddressType, RegionType

**Pet**: PetType, PetVaccinationType

All reference tables live in the `ref` SQL schema with Code (nvarchar 10) + Description (nvarchar 100) columns.
