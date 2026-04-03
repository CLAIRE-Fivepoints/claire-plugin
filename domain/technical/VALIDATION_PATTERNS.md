---
keywords: [validation, fluent-validation, fluentvalidation-ts, required, regex, cross-field, date-range, conditional, content-token, dynamic-rules, input-mask]
---

# TFI One — Validation Patterns

---

## Validation Architecture

TFI One uses a dual-layer validation system: frontend and backend enforce the same rules.

### Three Rule Sources

| Source | Technology | Where |
|--------|-----------|-------|
| Data-driven rules | `conf.ValidationRule` table | Loaded at runtime by both layers |
| Hard-coded backend | FluentValidation (C#) | `BaseValidator<T>` subclasses |
| Hard-coded frontend | fluentvalidation-ts | `BaseValidator<T>` subclasses |

### Request Pipeline

```
HTTP Request → ValidationFilter (IAsyncActionFilter) → FluentValidation → Controller Action
```

Returns `400 BadRequest` with field-level messages on validation failure.

### Key Principle

Frontend and backend validators MUST enforce the same rules. The `required` prop on frontend components MUST match the corresponding `NotEmpty()` backend rule.

---

## Patterns by Field Type

### Text Fields

| Rule | Frontend | Backend |
|------|----------|---------|
| Required | `.notEmpty().notNull()` | `.NotEmpty()` |
| Max length | `.maxLength(n)` | `.MaximumLength(n)` |
| Conditional | `.when(m => m.field != '')` | `.When(x => x.Field is not null)` |
| Content token | `entity.fieldName.required` | `entity.fieldName.maximumLength` |

### Date Fields

| Rule | Frontend | Backend |
|------|----------|---------|
| Required | `.notEmpty().notNull()` | `.NotEmpty()` |
| End > Start | `.must((end, m) => !end \|\| m.start < end)` | `.GreaterThan(x => x.Start).When(x => x.End.HasValue)` |
| Conditional required | `.must((date, m) => !m.flag \|\| !!date)` | `.NotEmpty().When(x => x.Flag == true)` |
| No future date | `.must(d => d <= today)` | `.LessThanOrEqualTo(DateTime.Today)` |

### Select / Dropdown (Guid)

| Rule | Frontend | Backend |
|------|----------|---------|
| Required | `.notEmpty().notEqual(CONSTANTS.EMPTY_GUID)` | `.NotEmpty().NotEqual(Guid.Empty)` |
| Conditional | `.when(m => m.flag == false)` | `.When(x => x.Flag != true)` |

**Why NotEqual(EMPTY_GUID)?** `TfioSelect` defaults to `00000000-0000-0000-0000-000000000000` when nothing is selected. `NotEmpty()` alone won't catch this — the field has a value, it's just the empty GUID.

### Number Fields

| Rule | Frontend | Backend |
|------|----------|---------|
| Range | `.inclusiveBetween(min, max)` | `.InclusiveBetween(min, max)` |
| Minimum | `.greaterThanOrEqualTo(0)` | `.GreaterThanOrEqualTo(0)` |
| Conditional | `.when(m => m.field != null)` | `.When(x => x.Field.HasValue)` |

### Email / Phone / Zip (Regex)

| Field | Regex | Constant |
|-------|-------|----------|
| Phone | `^\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})([-. ]?([0-9]){0,4})?$` | `ValidationConstants.TfioRegex.PhoneRegex` |
| Zip | `^([0-9]{5})(([-]?)([0-9]{4}))?$` | `ValidationConstants.TfioRegex.ZipRegex` |
| Email | `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$` | `ValidationConstants.TfioRegex.EmailRegex` |

All applied conditionally: `.when(x => x.Field != null && x.Field != '')`

Frontend and backend share identical regex patterns via `ValidationConstants`.

### Address Fields (Composite)

| Field | Rule |
|-------|------|
| `street1`, `city`, `state` | Required when `homeless != true` |
| `street2`, `county` | Always optional |
| `zipCode` | Required + regex pattern |

Optional USPS verification via Google Maps API (`IAddressValidator`).

### Boolean / Checkbox

- No validation on the boolean itself
- Booleans are used as **conditions** for other fields (e.g., `IEP == true` → `IEPDate` required)

---

## Cross-Field Validation Patterns

### 1. Date Range (Most Common)

```
StartDate < EndDate (when EndDate is provided)
```

**Frontend:**
```typescript
this.ruleFor('endDate')
  .must((end, m) => !end || m.startDate < end)
  .withMessage('End date must be after start date');
```

**Backend:**
```csharp
RuleFor(x => x.EndDate)
  .GreaterThan(x => x.StartDate)
  .When(x => x.EndDate.HasValue);
```

**Found in:** enrollment, insurance, case county, case worker, provider address, emergency contact, phase history, household member, placement request, client address.

### 2. Conditional Required

```
If FieldA = X → FieldB is required
```

| Condition | Required Field |
|-----------|---------------|
| `IEP = true` | `IEPDate` |
| `ARD = true` | `ARDDate` |
| `Homeless = false` | Address fields |
| `DueDateNA = false` | `DueDate` |
| Contact role selected | Phone |

### 3. Unique Constraints (Backend Only — MustAsync)

```csharp
// Email uniqueness
RuleFor(x => x.EmailAddress)
  .MustAsync(async (model, email, ct) =>
    !await _context.AppUsers.AnyAsync(u =>
      u.EmailAddress == email && u.AppUserId != model.AppUserId, ct))
  .WithMessage("global.user.email.exists");

// No overlapping dates
RuleFor(x => x).MustAsync(HasPhaseHistoryOverlap);

// Provider not already closed
RuleFor(x => x).Must(x => x.Status != "Closed");
```

These have no frontend equivalent — they require database access.

### 4. Cross-Field Number Comparisons

- `MinAge` ≤ `MaxAge`
- Mutual exclusion: can't be both primary and secondary contact

---

## Required Field Indicator (Asterisk)

### Pattern

`FormControl required={true}` → MUI adds asterisk `*` via `Mui-required` CSS class on `FormLabel`.

### Rule

The `required` prop MUST match the backend validator:

| Backend Rule | Frontend Prop |
|-------------|--------------|
| Has `NotEmpty()` | `required={true}` |
| No required rule | `required={false}` |

Mismatch = visual inconsistency with actual validation behavior.

---

## Content Token Naming Convention

Format: `{domain}.{fieldName}.{ruleType}`

| Example Token | Meaning |
|--------------|---------|
| `client.firstName.required` | First name is required |
| `client.lastName.maximumLength` | Last name exceeds max length |
| `clientAddress.primaryPhone.numberPattern` | Phone format invalid |
| `caseCounty.endDate.afterStartDate` | End date must be after start |
| `global.user.email.exists` | Email already in use |
| `education.iepDate.requiredWhenIep` | IEP date required when IEP is true |

Content tokens are fetched on login → stored in Redux `auth.content`. Enables server-side control of validation messages without frontend deployments.

---

## Input Masks

| Mask | Format | Component |
|------|--------|-----------|
| PHONE | `000-000-0000[ x00000]` | IMaskInput |
| ZIP | `00000[-0000]` | IMaskInput |
| SSN | `000-00-0000` | IMaskInput |
| INTEGER | Thousand separators, no decimals | react-number-format |
| DECIMAL | Thousand separators, 2 decimals | react-number-format |
| CURRENCY | `$` prefix, 2 decimals | react-number-format |
| PERCENTAGE | `%` suffix, 2 decimals | react-number-format |

Masks enforce format at the input level, complementing (not replacing) regex validation.

---

## Dynamic Validation Rules (DB-Driven)

### Schema

```sql
-- conf.ValidationRule
EntityType      VARCHAR   -- e.g., 'ClientEditModel'
PropertyName    VARCHAR   -- e.g., 'FirstName'
RuleType        VARCHAR   -- e.g., 'NotEmpty', 'MaxLength'
RuleValue       VARCHAR   -- e.g., '100' (for MaxLength)
Pattern         VARCHAR   -- regex (for Matches)
Message         VARCHAR   -- content token or literal message
```

### Supported Rule Types (18)

`NotNull`, `NotEmpty`, `Null`, `Empty`, `Equal`, `NotEqual`, `Length`, `MinLength`, `MaxLength`, `LessThan`, `LessThanOrEqualTo`, `GreaterThan`, `GreaterThanOrEqualTo`, `Matches`, `Email`, `PhoneNumber`, `ExclusiveBetween`, `InclusiveBetween`

### Runtime Flow

```
Login → GET /validation/rules → Redux store → useValidationRules(entityType) → BaseValidator
```

`DynamicValidator<T>` on the backend loads the same rules from DB when no hard-coded validator exists.

---

## Related Documentation

- [Forms & Validation](./FRONTEND_FORMS.md) — Form stack, BaseValidator, entity validators, wizard pattern
- [Frontend Patterns](./FRONTEND_PATTERNS.md) — Required asterisk, input component conventions
- [Design Patterns](./PATTERNS.md) — Two-tier validation overview (section 4)
- [Component Library](./FRONTEND_COMPONENTS.md) — Input components (`tfio_*` inputs)
