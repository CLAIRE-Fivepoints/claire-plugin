---
keywords: [forms, react-hook-form, fluent-validation, validation, wizard, dynamic-forms, survey-js, readonly, file-upload]
---

# TFI One — Forms & Validation

---

## Form Stack

| Layer | Library | Version |
|-------|---------|---------|
| State | React Hook Form | 7.62.0 |
| Validation | FluentValidation-ts | 5.0.0 |
| Resolver | @hookform/resolvers | 5.2.1 |
| Dynamic Forms | Survey.js | 2.3.5 |

---

## Two Form Approaches

### Approach 1: React Hook Form + FluentValidation (Primary)

Used for all entity forms (Provider, Agency, Client, User, etc.).

```
Backend                          Frontend
┌──────────────────┐            ┌──────────────────────────┐
│ ValidationRule    │   fetch    │ Redux validation.rules   │
│ table in DB       │ ────────► │                          │
│ (dynamic rules)   │           │ useValidationRules()     │
└──────────────────┘            │     ↓                    │
                                │ EntityValidator          │
                                │ (FluentValidation-ts)    │
                                │     ↓                    │
                                │ React Hook Form          │
                                │ (resolver)               │
                                │     ↓                    │
                                │ tfio_* input components  │
                                └──────────────────────────┘
```

**Flow**:
1. On login → validation rules fetched from `/validation/rules` → stored in Redux
2. `useValidationRules(entityType)` returns rules for a specific model
3. Entity validator extends `BaseValidator`
4. `BaseValidator` maps `ValidationRuleModel` to fluent rules
5. Resolver connects validator to React Hook Form
6. `tfio_*` inputs display field-level errors

### Approach 2: Survey.js (Dynamic/Admin Forms)

Used for admin-configurable forms (form schema management).

```
Form Schema (DB)  →  Survey.js JSON  →  FormBuilder (admin UI)
                                     →  FormViewer (user fills form)
                                     →  FormSubmission (saved to DB)
```

---

## BaseValidator Pattern

```typescript
class BaseValidator extends Validator<T> {
  constructor(rules: ValidationRuleModel[]) {
    for (const rule of rules) {
      switch (rule.ruleType) {
        case 'NotEmpty':
          this.ruleFor(rule.field).notEmpty().withMessage(rule.message);
          break;
        case 'MaxLength':
          this.ruleFor(rule.field).maxLength(rule.value);
          break;
        case 'Matches':
          this.ruleFor(rule.field).matches(rule.pattern);
          break;
        // ... 18 rule types total
      }
    }
  }
}
```

---

## Supported Rule Types (18)

| Rule Type | Validation |
|-----------|-----------|
| `NotNull` | Must not be null |
| `NotEmpty` | Must not be empty |
| `Null` | Must be null |
| `Empty` | Must be empty |
| `Equal` | Must equal value |
| `NotEqual` | Must not equal value |
| `Length` | Exact length |
| `MinLength` | Minimum length |
| `MaxLength` | Maximum length |
| `LessThan` | Must be < value |
| `LessThanOrEqualTo` | Must be ≤ value |
| `GreaterThan` | Must be > value |
| `GreaterThanOrEqualTo` | Must be ≥ value |
| `Matches` | Regex pattern match |
| `Email` | Valid email format |
| `PhoneNumber` | Valid phone format |
| `ExclusiveBetween` | Between (exclusive) |
| `InclusiveBetween` | Between (inclusive) |

---

## Entity Validators (18)

| Validator | Entity |
|-----------|--------|
| `ProviderCreateModelValidator` | New provider |
| `ProviderEditModelValidator` | Edit provider |
| `ProviderWorkerEditModelValidator` | Provider worker |
| `AgencyCreateValidator` | New agency |
| `AgencyEditValidator` | Edit agency |
| `AppUserValidator` | User |
| `ChangePasswordValidator` | Password change |
| `InquiryWorkerValidator` | Inquiry worker |
| `TrainingEditValidator` | Training |
| `TrainingSessionEditValidator` | Training session |
| `PetEditModelValidator` | Pet |
| `PetVaccinationEditModelValidator` | Vaccination |
| `HouseholdMemberValidator` | Household member |
| `BackgroundCheckValidator` | Background check |
| `DocumentDefinitionValidator` | Document definition |
| `IntakeValidator` | Intake |
| `ClientValidator` | Client |
| `CaseParticipantValidator` | Case participant |

---

## Required Field Indicator

All required form fields MUST use the `required` prop to display an asterisk (`*`) next to the label.

- `FormControl required={true}` wraps the field
- MUI automatically adds `*` via `Mui-required` CSS class on `FormLabel`
- The `required` prop on TFIO input components (`TfioTextInput`, `TfioSelect`, `TfioDateInput`) controls this behavior

```tsx
// Required field — shows asterisk
<TfioTextInput
    name='schoolName'
    required={true}
    labelToken='enrollment.schoolName'
    labelDefault='School Name'
/>

// Optional field — no asterisk
<TfioTextInput
    name='isd'
    required={false}
    labelToken='enrollment.isd'
    labelDefault='ISD'
/>
```

**Frontend ↔ Backend alignment**: The `required` prop MUST match the corresponding server-side FluentValidation rule:
- Backend has `RuleFor(x => x.Field).NotEmpty()` → frontend must have `required={true}`
- Backend has no required rule → frontend should have `required={false}`

This ensures:
1. Visual consistency across all forms
2. Accessibility compliance (screen readers announce required state)
3. Frontend validation alignment — the asterisk signals which fields will be validated

---

## Form Readonly Pattern

```tsx
// Provider wraps form in readonly context
<FormReadonlyProvider readonly={!canEdit}>
  <form>
    <TfioTextInput name="firstName" />  {/* auto-disabled if readonly */}
    <TfioSelect name="status" />        {/* auto-disabled if readonly */}
  </form>
</FormReadonlyProvider>
```

- `FormReadonlyProvider` sets context
- `useFormReadonly()` hook reads context in any input
- All `tfio_*` inputs check readonly state automatically
- Enables view/edit toggle without prop drilling

---

## Form Layout Convention

```tsx
<Grid2 container spacing={2}>
  <Grid2 {...COLUMN_DEFINITIONS.DEFAULT}>   {/* sm:12 md:4 lg:3 xl:2 */}
    <TfioTextInput name="firstName" label="First Name" />
  </Grid2>
  <Grid2 {...COLUMN_DEFINITIONS.DEFAULT}>
    <TfioTextInput name="lastName" label="Last Name" />
  </Grid2>
  <Grid2 {...COLUMN_DEFINITIONS.LARGE}>     {/* xs:12 sm:8 lg:6 xl:4 */}
    <TfioTextareaInput name="notes" label="Notes" />
  </Grid2>
</Grid2>
```

---

## Wizard Pattern (Multi-Step Forms)

```
TfioWizard
├── Step 1: Basic Info        ← validate on "Next"
├── Step 2: Details           ← validate on "Next"
├── Step 3: Documents         ← validate on "Next"
├── Step 4: Review            ← final review
└── Submit                    ← API mutation
```

Used in: Client Intake Wizard, Add Inquiry Wizard, Document Configuration Wizard, Provider Create.

---

## File Upload Pattern

```tsx
<TfioDropzone
  onDrop={(files) => handleUpload(files)}
  maxSize={512 * 1024}              // 512KB limit
  accept={{
    'image/*': ['.png', '.jpg', '.gif'],
    'application/pdf': ['.pdf'],
    'application/msword': ['.doc'],
    // + xlsx, text, archives, HTML, CSS, JSON, XML
  }}
/>
```

Files uploaded via `POST /files/upload` → Azure Blob Storage → `FileMetaData` tracked in DB.

---

## Tokenized Messages (i18n)

```typescript
// Validation messages support tokenized content
const requiredMsg = useTokenizedContent("FIELD_REQUIRED", "This field is required");

this.ruleFor("firstName").notEmpty().withMessage(requiredMsg);
```

Content tokens fetched on login → stored in Redux `auth.content`. Enables server-side control of UI text without frontend deployments.
