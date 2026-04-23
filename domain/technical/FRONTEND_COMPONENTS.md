---
keywords: [components, primitives, tfio, inputs, mui, face-sheet, wizard, datagrid, shared, "persona:fivepoints-reviewer"]
---

# TFI One — Component Library

**Total**: ~245 components
**Naming**: `tfio_` prefix for shared reusable components
**UI Kit**: Material-UI 7.3.1 (Pro license)

---

## Component Rules

These rules apply to **all** frontend components. Source: Steven Franklin's PR #228 review.

### Rule 1: One Component Per File

No file should contain more than one React component. Each component gets its own file.

```
-- WRONG: two components in one file
enrollment_history.tsx
  export function EnrollmentHistory() { ... }
  export function EnrollmentAddEdit() { ... }  // ❌ must be its own file

-- CORRECT: one component per file
enrollment_history.tsx    → EnrollmentHistory
enrollment_add_edit.tsx   → EnrollmentAddEdit
```

- File name matches the exported component (`snake_case.tsx` → `PascalCase` component)
- Includes sub-components: even small helper components get their own file
- Applies to both feature components and shared components

### Rule 2: Always Use Wrapped Components

Never use raw MUI components when a `tfio_*` wrapper exists. The wrappers integrate with the content hook system, validation, and readonly mode.

```tsx
// WRONG — raw MUI
import { TextField } from '@mui/material';
<TextField label="School Name" />

// CORRECT — Tfio wrapper
import { TfioTextInput } from 'shared/input/tfio_text_input';
<TfioTextInput labelToken="education.schoolName" labelDefault="School Name" />
```

See the full wrapper inventory in sections 1-4 below.

### Rule 3: All Strings Through Content Hook

All user-facing string literals must run through the content hook. No hardcoded strings.

```tsx
// WRONG — hardcoded string
<h2>Education</h2>
<TfioTextInput label="School Name" />

// CORRECT — content hook
content("education.title", "Education")
<TfioTextInput labelToken="education.schoolName" labelDefault="School Name" />
```

Applies to: labels, validation messages, error messages, placeholders, button text, column headers.

All `tfio_*` input components accept `labelToken` / `labelDefault` props for automatic content hook integration.

### Rule 4: Don't Translate GUIDs to Bools

When the database stores a FK to `ref.YesNoType`, the frontend must work with the GUID directly. Never convert GUID to boolean in the component and back when saving.

```tsx
// WRONG — boolean translation
const hasIEP = model.iepTypeId === YES_GUID;
<TfioCheckboxInput name="hasIEP" value={hasIEP} />
// then on save: model.iepTypeId = hasIEP ? YES_GUID : NO_GUID  ❌

// CORRECT — use the GUID with a select
<TfioSelectInput
  name="iepTypeId"
  options={yesNoTypes}
  labelToken="education.iep"
  labelDefault="IEP"
/>
```

The `tfio_select` components handle reference data natively — no translation needed.

---

## Component Hierarchy

```
Feature Components (pages/views)
    └── use → Shared Common (layouts, toolbars, wizards)
                 └── use → Shared Input (form controls)
                              └── use → Shared Primitives (MUI wrappers)
                                           └── use → Material-UI core
```

---

## 1. Primitives (`shared/primitives/`) — 25 Components

MUI wrapper components with project-consistent defaults (always use these instead of raw MUI):

| Component | Wraps | Purpose |
|-----------|-------|---------|
| `tfio_box` | MUI Box | Layout container |
| `tfio_button` | MUI Button | Action buttons |
| `tfio_card` | MUI Card | Content cards |
| `tfio_checkbox` | MUI Checkbox | Checkbox display |
| `tfio_chip` | MUI Chip | Tag/badge display |
| `tfio_data_grid` | MUI X DataGrid Pro | Complex data tables |
| `tfio_datepicker` | MUI X DatePicker | Date selection |
| `tfio_datetimepicker` | MUI X DateTimePicker | DateTime selection |
| `tfio_dialog_content` | MUI DialogContent | Modal content area |
| `tfio_drawer` | MUI Drawer | Side panel |
| `tfio_form_header` | Custom | Form section headers |
| `tfio_icon_button` | MUI IconButton | Icon-only buttons |
| `tfio_label` | MUI InputLabel | Field labels |
| `tfio_list` | MUI List | Vertical lists |
| `tfio_list_item` | MUI ListItem | List entries |
| `tfio_menu_item` | MUI MenuItem | Menu options |
| `tfio_no_data` | Custom | Empty state display |
| `tfio_radio` | MUI Radio | Radio button display |
| `tfio_stack` | MUI Stack | Flex container |
| `tfio_stepper` | MUI Stepper | Multi-step indicator |
| `tfio_text_field` | MUI TextField | Text display field |
| `tfio_timepicker` | MUI X TimePicker | Time selection |
| `tfio_tree_item` | MUI X TreeItem | Tree node |
| `tfio_typography` | MUI Typography | Text display |
| `tfio_components` | Barrel export | Re-exports all primitives |

---

## 2. Inputs (`shared/input/`) — 21 Components

Custom form inputs integrating React Hook Form + MUI:

| Component | Type | Features |
|-----------|------|----------|
| `tfio_text_input` | Text | Masked input (phone, SSN, zip), validation |
| `tfio_textarea_input` | Multiline | Character counter, expandable |
| `tfio_numeric_formatter` | Number | Currency, percentage, decimal formatting |
| `tfio_select` | Dropdown | Single/multi select, searchable |
| `tfio_autocomplete` | Combobox | Type-ahead search with options |
| `tfio_checkbox_input` | Boolean | Controlled checkbox with label |
| `tfio_radio_group` | Choice | Radio button group |
| `tfio_toggle` | Boolean | Toggle switch |
| `tfio_date_input` | Date | Date picker with format validation |
| `tfio_date_range_input` | Date pair | Start/end date range |
| `tfio_datetime_input` | DateTime | Date + time picker |
| `tfio_datetime_range_input` | DateTime pair | Start/end datetime range |
| `tfio_time_input` | Time | Time picker |
| `tfio_debounce_text_input` | Text | Debounced onChange (search) |
| `tfio_search` | Search | Search bar with icon |
| `tfio_dropzone` | File | Drag-and-drop file upload area |
| `tfio_file_upload_input` | File | File input with preview |
| `tfio_chip_list_input` | Multi-value | Chip-based multi-select |
| `tfio_buttons` | Actions | Save/Cancel/Delete button groups |

### Input Masks
```
PHONE:      000-000-0000[x00000]
ZIP:        00000[-0000]
SSN:        000-00-0000
DATE:       00/00/0000
CURRENCY:   $0,000.00
PERCENTAGE: 00.00%
```

All inputs check `useFormReadonly()` context to disable themselves in view mode.

---

## 3. Filters (`shared/filter/`) — 15+ Components

Custom filters for MUI X DataGrid Pro:

| Component | Purpose |
|-----------|---------|
| `boolean_header_filter` | True/false column filter |
| `multiselect_filter` | Multi-option column filter |
| `date_range_filter` | Date range column filter |
| `contains_all_filter_operator` | Custom "contains all" operator |
| `any_date_in_range_operator` | Date-in-range operator |
| `parent_dropdown_filter` | Dependent dropdown filter |
| `date_column_definition` | Column def for date columns |
| `multiline_text_column_definition` | Column def for long text |
| `multi_select_column_definition` | Column def for enum columns |

---

## 4. Common (`shared/common/`) — Layout Components

| Component | Purpose |
|-----------|---------|
| `tfio_page_wrapper` | Page layout: title, breadcrumbs, action buttons |
| `tfio_wizard` | Multi-step form container with stepper |
| `tfio_grid_toolbar` | Data grid toolbar (search, filter, export) |
| `tfio_model_view` | Read-only model display |
| `tfio_dialog` | Standard modal dialog wrapper |
| `tfio_backdrop` | Loading overlay |
| `tfio_document_tree` | Document tree viewer |
| `subheader` | Section subheader |
| `dateformatter` | Date formatting helper component |

---

## 5. Feature Components

### Auth (`components/auth/`)
| Component | Purpose |
|-----------|---------|
| `login` | Full login page: credentials, SSO, reCAPTCHA, MFA (~800 lines) |
| `mfa` | MFA dialog (TOTP, SMS) |
| `forgot_password` | Password reset flow |
| `must_change_password_dialog` | Forced password change |

### Provider (`components/provider/`) — Largest Feature
52+ routes, ~60 files.

| Sub-area | Purpose |
|----------|---------|
| CRUD | providers search, provider_create, provider_edit, provider_view |
| Face Sheet | face_sheet parent + 20 tab components |
| Cards | info cards, detail cards (display subcomponents) |
| Phase | phase_history, phase_view, phase_add_edit |
| Training | household_member_trainings sub-views |

### Agency (`components/agency/`) — 41 Routes
| Sub-area | Purpose |
|----------|---------|
| CRUD | agencies search, agency_create, agency_edit |
| Face Sheet | face_sheet parent + 7 tab components |

### Client (`components/client/`)
Client search grid + multi-step intake wizard.

### Inquiry (`components/inquiry/`)
Search + dashboard with metrics + add wizard.

### Other Features
Background Check (search/add/view), Service Provider (face sheet), Document Config (wizard), Forms (schema editor, viewer, submissions), User Admin (CRUD + permission editor), Power BI Reports.

---

## 6. Navigation & Overlay

| Component | Purpose |
|-----------|---------|
| `secure` | Auth guard: redirects to `/login` if not authenticated |
| `main_navigation_drawer` | Collapsible sidebar menu (permission-driven) |
| `header` | Top app bar: user menu, org selector, logout |
| `messages` | Snackbar notification stack (slide from right, auto-dismiss 5s) |
| `wait` | Full-screen loading backdrop with spinner |
