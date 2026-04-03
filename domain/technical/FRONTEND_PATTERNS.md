---
keywords: [frontend, patterns, required, asterisk, input, form-control, readonly, masks, tfio, conventions]
---

# TFI One — Frontend Patterns

---

## Required Field Indicator (Asterisk)

### How It Works

MUI's `FormControl` component with `required={true}` automatically adds an asterisk (`*`) to the associated `FormLabel` via the `Mui-required` CSS class.

```tsx
<FormControl required={true}>
  <TfioTextInput name="firstName" label="First Name" />
</FormControl>
```

Renders: **First Name \***

### Matching Rule

The `required` prop MUST match the backend `NotEmpty()` validator:

```
Backend: RuleFor(x => x.FirstName).NotEmpty()  →  Frontend: required={true}
Backend: (no required rule for MiddleName)      →  Frontend: required={false}
```

A mismatch means the asterisk is shown but the field isn't actually required (or vice versa), confusing users.

---

## Input Component Conventions

### Always Use `tfio_*` Inputs

Never use raw MUI inputs. The `tfio_*` input components:
- Integrate with React Hook Form automatically
- Check `useFormReadonly()` context to disable in view mode
- Display field-level validation errors from the resolver
- Apply consistent styling and layout

### Component Selection by Field Type

| Data Type | Component | Notes |
|-----------|-----------|-------|
| Short text | `tfio_text_input` | Supports masks (phone, SSN, zip) |
| Long text | `tfio_textarea_input` | Character counter, expandable |
| Number | `tfio_numeric_formatter` | Currency, percentage, decimal |
| Single select | `tfio_select` | Dropdown with searchable options |
| Multi select | `tfio_autocomplete` | Type-ahead with multi-select |
| Boolean | `tfio_checkbox_input` | Controlled checkbox |
| Choice | `tfio_radio_group` | Radio button group |
| Toggle | `tfio_toggle` | Switch control |
| Date | `tfio_date_input` | Date picker |
| Date range | `tfio_date_range_input` | Start/end pair |
| DateTime | `tfio_datetime_input` | Date + time |
| Time | `tfio_time_input` | Time picker |
| File | `tfio_dropzone` | Drag-and-drop upload |
| Search | `tfio_debounce_text_input` | Debounced onChange |

### Input Masks

Applied via `tfio_text_input` with the `mask` prop:

| Mask | Format | Library |
|------|--------|---------|
| PHONE | `000-000-0000[ x00000]` | IMaskInput |
| ZIP | `00000[-0000]` | IMaskInput |
| SSN | `000-00-0000` | IMaskInput |
| INTEGER | Thousand separators, no decimals | react-number-format |
| DECIMAL | Thousand separators, 2 decimals | react-number-format |
| CURRENCY | `$` prefix, 2 decimals | react-number-format |
| PERCENTAGE | `%` suffix, 2 decimals | react-number-format |

---

## Form Readonly Pattern

```tsx
<FormReadonlyProvider readonly={!canEdit}>
  <form>
    <TfioTextInput name="firstName" />   {/* auto-disabled */}
    <TfioSelect name="status" />         {/* auto-disabled */}
  </form>
</FormReadonlyProvider>
```

- `FormReadonlyProvider` sets React context
- `useFormReadonly()` hook reads context inside any input
- All `tfio_*` inputs check readonly state automatically
- Enables view/edit toggle without prop drilling

---

## Form Layout Convention

```tsx
<Grid2 container spacing={2}>
  <Grid2 {...COLUMN_DEFINITIONS.DEFAULT}>   {/* sm:12 md:4 lg:3 xl:2 */}
    <TfioTextInput name="firstName" label="First Name" />
  </Grid2>
  <Grid2 {...COLUMN_DEFINITIONS.LARGE}>     {/* xs:12 sm:8 lg:6 xl:4 */}
    <TfioTextareaInput name="notes" label="Notes" />
  </Grid2>
</Grid2>
```

Use `COLUMN_DEFINITIONS` constants for consistent responsive layout across all forms.

---

## Related Documentation

- [Validation Patterns](./VALIDATION_PATTERNS.md) — All validation rules, cross-field patterns, content tokens
- [Forms & Validation](./FRONTEND_FORMS.md) — Form stack, BaseValidator, wizard pattern
- [Component Library](./FRONTEND_COMPONENTS.md) — Full component inventory
