---
keywords: [five-points, tfi-one, face-sheet, section, education, history, add-edit, rtk, validator, modal, patterns]
---

# TFI One — Face Sheet Section Patterns

**Source branch:** `feature/10399-education-gaps` (Azure DevOps)
**Purpose:** Canonical rules for implementing a face sheet section with history sub-tables. Derived from the Education section implementation. Any new face sheet section MUST follow these conventions exactly.

---

## Table of Contents

1. [File Structure — One File Per Entity](#1-file-structure--one-file-per-entity)
2. [RTK Query — Per-Entity Files with Dual Tags](#2-rtk-query--per-entity-files-with-dual-tags)
3. [TypeScript Validators — One File Per Entity](#3-typescript-validators--one-file-per-entity)
4. [C# Validators — One File Per Entity, All Registered](#4-c-validators--one-file-per-entity-all-registered)
5. [Repo — PopulateX Private Static Methods](#5-repo--populatex-private-static-methods)
6. [Overview Card — Display Helpers and N/A Fallback](#6-overview-card--display-helpers-and-na-fallback)
7. [Boolean Fields — TfioSelect with GUID Conversion](#7-boolean-fields--tfioselect-with-guid-conversion)
8. [Edit Form — useValidationRules + useSetWait + useNavigateBack](#8-edit-form--usevalidationrules--usesetwait--usenavigaateback)
9. [History Grid — CONSTANTS.DEFAULT_SEARCH_MODEL + formatDate in valueGetter](#9-history-grid--constantsdefault_search_model--formatdate-in-valuegetter)
10. [History Grid — Delete Dialog with actions prop](#10-history-grid--delete-dialog-with-actions-prop)
11. [Add/Edit Modal — ID Prop + Self-Fetch with skip](#11-addedit-modal--id-prop--self-fetch-with-skip)
12. [View Mode — TfioModelView (NOT disabled form)](#12-view-mode--tfiomodelview-not-disabled-form)
13. [Routes — Sub-sections at same level, Add/Edit/View as sub-routes](#13-routes--sub-sections-at-same-level-addeditview-as-sub-routes)
14. [TfioAddress — Contract and Dependencies](#14-tfioaddress--contract-and-dependencies)
15. [RTK Hook Naming — Enrollment Specific](#15-rtk-hook-naming--enrollment-specific)
16. [Content Token Namespace](#16-content-token-namespace)
17. [Tests — Controller Tests with Mock<IRepo>](#17-tests--controller-tests-with-mockirepо)
18. [Tags Registration in tags.ts](#18-tags-registration-in-tagsts)

---

## 1. File Structure — One File Per Entity

A face sheet section with sub-tables creates **one file per entity** at every layer.

```
RTK Query files (one per entity):
  src/redux/services/com.tfione.api/
    education.ts          ← overview + edit education only (3 endpoints)
    grade_achieved.ts     ← grade achieved CRUD (5 endpoints)
    ged_test.ts           ← GED test CRUD (5 endpoints)
    enrollment.ts         ← enrollment CRUD (5 endpoints)
    report_card.ts        ← report card CRUD (5 endpoints)

TypeScript validator files (one per entity):
  src/validation/
    education_validator.ts
    grade_achieved_validator.ts
    ged_test_validator.ts
    enrollment_validator.ts
    report_card_validator.ts

C# validator files (one per entity):
  com.tfione.repo/client/
    ClientEducationEditModelValidator.cs
    ClientEnrollmentEditModelValidator.cs
    ClientGedTestEditModelValidator.cs
    ClientReportCardEditModelValidator.cs
```

**Rule:** Never combine multiple entities into one RTK file or one validator file. Each entity gets its own file.

---

## 2. RTK Query — Per-Entity Files with Dual Tags

Each sub-entity RTK file uses **two tags**: lowercase for the collection, PascalCase for the individual item. Mutations that affect the overview card also invalidate `EducationOverview`.

```typescript
// grade_achieved.ts
export const gradeAchievedApi = api.injectEndpoints({
    endpoints: (builder) => ({
        searchGradeAchieved: builder.query<...>({
            query: (model) => ({ url: `client/${model.clientId}/education/grade-achieved?${getQueryString(model)}`, method: 'GET' }),
            providesTags: ['gradeAchieved'],                                              // lowercase = collection
        }),
        getGradeAchieved: builder.query<..., { clientId: string; id: string }>({
            query: ({ clientId, id }) => ({ url: `client/${clientId}/education/grade-achieved/${id}`, method: 'GET' }),
            providesTags: (_result, _error, { id }) => [{ type: 'GradeAchieved', id: id.toUpperCase() }],  // PascalCase = individual
        }),
        createGradeAchieved: builder.mutation<...>({
            query: (model) => ({ url: `client/${model.clientId}/education/grade-achieved`, method: 'POST', body: model }),
            invalidatesTags: (_result, _error, model) => [
                'gradeAchieved',
                { type: 'EducationOverview', id: model.clientId.toUpperCase() }  // invalidate overview card
            ],
        }),
        updateGradeAchieved: builder.mutation<...>({
            invalidatesTags: (_result, _error, model) => [
                'gradeAchieved',
                { type: 'EducationOverview', id: model.clientId.toUpperCase() }
            ],
        }),
        deleteGradeAchieved: builder.mutation<boolean, { clientId: string; id: string }>({
            query: ({ clientId, id }) => ({ url: `client/${clientId}/education/grade-achieved/${id}`, method: 'DELETE' }),
            invalidatesTags: ['gradeAchieved', 'EducationOverview'],
        }),
    })
});
```

**Key rules:**
- `get` param type: `{ clientId: string; id: string }` — NOT the full model object
- `delete` param type: `{ clientId: string; id: string }` — NOT the full model object
- `create`/`update` invalidate the parent overview tag by clientId

The parent `education.ts` only contains overview + edit education (3 endpoints):

```typescript
// education.ts — only overview and edit
saveEducation mutation invalidates:
  { type: 'Education', id: model.clientId.toUpperCase() }
  { type: 'EducationOverview', id: model.clientId.toUpperCase() }
```

---

## 3. TypeScript Validators — One File Per Entity

Each validator is in its own file, uses `useTokenizedContent`, and calls `super.configureRules()` at the end.

```typescript
// grade_achieved_validator.ts
import { useTokenizedContent } from '../hooks/content_hook';
import { ClientGradeAchievedEditModel, ValidationRuleModel } from '../types/com.tfione.api';
import BaseValidator from './base_validator';

class GradeAchievedValidator extends BaseValidator<ClientGradeAchievedEditModel> {
    constructor(rules: ValidationRuleModel[]) {
        super(rules);
        this.configureRules();
    }

    protected configureRules() {
        const { getTokenizedContent: content } = useTokenizedContent();

        this.ruleFor('gradeAchievedTypeId')
            .notEmpty()
            .notNull()
            .withMessage(content('gradeAchieved.gradeAchievedTypeId.required', 'Highest Grade Achieved is required.'));

        // ... other rules ...

        super.configureRules();  // ALWAYS last
    }
}

export default GradeAchievedValidator;
```

**Token namespace:** `{entityName}.{fieldName}.{ruleName}` — e.g., `gradeAchieved.dateLastAttended.required`

---

## 4. C# Validators — One File Per Entity, All Registered

Each sub-entity that has validation rules gets its own `ClientXxxEditModelValidator.cs`. All are registered in DI.

```csharp
// ClientEnrollmentEditModelValidator.cs
public class ClientEnrollmentEditModelValidator : BaseValidator<ClientEnrollmentEditModel>
{
    public ClientEnrollmentEditModelValidator(
        TfiOneContext context, IUserAccessor userAccessor,
        IValidationRuleProvider validationRuleProvider,
        IContentProvider contentProvider, IEncryptor encryptor)
        : base(context, encryptor, userAccessor, validationRuleProvider, contentProvider)
    {
        this.RuleFor(x => x.SchoolName)
            .NotEmpty()
            .WithMessage(this.ContentProvider.GetContent("enrollment.schoolName.required", "School Name is required.").Result);

        this.RuleFor(x => x.EndDate)
            .GreaterThanOrEqualTo(x => x.EnrollmentDate)
            .When(x => x.EndDate.HasValue)
            .WithMessage(this.ContentProvider.GetContent("enrollment.endDate.afterEnrollmentDate", "...").Result);

        this.RuleFor(x => x.GPA)
            .InclusiveBetween(0, 4.0m)
            .When(x => x.GPA.HasValue)
            .WithMessage(...);
    }
}
```

**DI registration in Extensions.cs** — all sub-entity validators:
```csharp
services.AddScoped<IValidator<ClientEducationEditModel>, ClientEducationEditModelValidator>();
services.AddScoped<IValidator<ClientEnrollmentEditModel>, ClientEnrollmentEditModelValidator>();
services.AddScoped<IValidator<ClientGedTestEditModel>, ClientGedTestEditModelValidator>();
services.AddScoped<IValidator<ClientReportCardEditModel>, ClientReportCardEditModelValidator>();
```

---

## 5. Repo — PopulateX Private Static Methods

The repo uses private static `PopulateX(entity, model)` methods to separate mapping from persistence logic. This is the standard pattern for `SaveX`/`CreateX`/`UpdateX`.

```csharp
public async Task<ClientGradeAchievedEditModel> CreateGradeAchieved(Guid clientId, ClientGradeAchievedEditModel model)
{
    // ...access check...
    var entity = new ClientGradeAchieved { ClientId = clientId, CreatedDate = now, ... };
    PopulateGradeAchieved(entity, model);    // <-- mapping in dedicated method
    this.tfiOneContext.ClientGradeAchieveds.Add(entity);
    await this.tfiOneContext.SaveChangesAsync();
    return (await this.GetGradeAchieved(clientId, entity.ClientGradeAchievedId))!;
}

private static void PopulateGradeAchieved(ClientGradeAchieved entity, ClientGradeAchievedEditModel model)
{
    entity.GradeAchievedTypeId = model.GradeAchievedTypeId;
    entity.DateLastAttended = model.DateLastAttended;
    entity.DateAchieved = model.DateAchieved;
}
```

---

## 6. Overview Card — Display Helpers and N/A Fallback

The overview card defines local `displayValue`, `displayDate`, `displayBool`, and `displayReference` helpers. Empty values show "N/A", not empty string.

```tsx
const naText = content("global.notAvailable", "N/A");
const yesText = content("global.yes", "Yes");
const noText = content("global.no", "No");

const displayValue = (value: string | undefined | null): string =>
    (!value || value === "") ? naText : value;

const displayDate = (dateValue: string | undefined | null): string =>
    dateValue ? (formatDate(dateValue) || naText) : naText;

const displayBool = (value: boolean | undefined | null): string => {
    if (value === null || value === undefined) return naText;
    return value ? yesText : noText;
};

// For fields stored as GUID (e.g., 504 Plan uses YesNoUnknownType GUID)
const displayReference = (value: string | undefined | null, items: any[] | undefined): string => {
    if (!value || value === "" || value === CONSTANTS.EMPTY_GUID) return naText;
    const match = items?.find(t => t.value === value || t.id === value);
    return match?.text || naText;
};
```

The card header uses an icon avatar:
```tsx
<CardHeader
    title={content("education.overview", "Education")}
    avatar={<SchoolIcon color="primary" />}
    action={action}
/>
```

---

## 7. Boolean Fields — DEPRECATED: Use GUIDs Directly

> ⚠️ **OUTDATED PATTERN** — Do not use for new code.
>
> The bool↔GUID conversion documented below was the old approach. The canonical pattern
> is to store and work with GUIDs directly (`iepId`, `plan504Id`, `ardId`, `onGradeLevelId`).
> See `fivepoints/technical/PATTERNS.md §16` for the current pattern.

~~Boolean fields (IEP, ARD, On Grade Level) in TFI One are stored as `bool?` in DB but rendered as `TfioSelect` using `YesNoType` or `YesNoUnknownType` reference data. The component must convert bool↔GUID.~~

**Load (bool → GUID):**
```tsx
const { data: yesNoTypes } = useGetReferencesQuery('YesNoType');
const yesValue = yesNoTypes?.find(t => t.text?.toLowerCase().includes('yes'))?.value;
const noValue  = yesNoTypes?.find(t => t.text?.toLowerCase().includes('no'))?.value;

useEffect(() => {
    if (education && yesNoTypes) {
        const boolToGuid = (val: any) =>
            val === true ? yesValue : val === false ? noValue : undefined;
        methods.reset({
            ...education,
            iep: boolToGuid(education.iep),
            ard: boolToGuid(education.ard),
            onGradeLevel: boolToGuid(education.onGradeLevel),
        } as any);
    }
}, [education, yesNoTypes, yesValue, noValue, methods]);
```

**Submit (GUID → bool):**
```tsx
const guidToBool = (val: any): boolean | null => {
    if (!val || val === CONSTANTS.EMPTY_GUID) return null;
    return val === yesValue ? true : false;
};
const submitModel = {
    ...model,
    iep: guidToBool(model.iep),
    ard: guidToBool(model.ard),
    onGradeLevel: guidToBool(model.onGradeLevel),
};
```

**Conditional date field visibility with useWatch:**
```tsx
const iepValue = useWatch({ control: methods.control, name: 'iep' });
const iepIsYes = iepValue === yesValue;

{iepIsYes && (
    <TfioDateInput name='iepDate' required={iepIsYes} labelToken='...' labelDefault='IEP Date' />
)}
```

---

## 8. Edit Form — useValidationRules + useSetWait + useNavigateBack

Every edit form MUST use these three hooks:

```tsx
const { getValidationRules } = useValidationRules();
const { setWait } = useSetWait();
const navigateBack = useNavigateBack();

const validationRules = [...getValidationRules('ClientEducationEditModel')];
const methods = useForm<ClientEducationEditModel>({
    resolver: fluentValidationResolver(new EducationValidator(validationRules)),
});

const [saveEducation, { isLoading: isSaving }] = useSaveEducationMutation();
const { data: education, isLoading, isFetching } = useGetEducationQuery(
    clientId ?? CONSTANTS.EMPTY_GUID,
    { skip: !clientId || clientId === CONSTANTS.EMPTY_GUID }
);

useEffect(() => {
    setWait(isLoading || isFetching || isSaving);
}, [isLoading, isFetching, isSaving, setWait]);

const onSubmit = async (model) => {
    const response = await saveEducation(model).unwrap();
    if (response.messages.length === 0) {
        navigateBack();   // NOT navigate('/specific/path')
        setMessage(content('education.save.success', '...'), 'success');
    }
};
```

**NEVER** pass `[]` to validators. Always use `getValidationRules('ModelClassName')`.
**NEVER** use `navigate('/specific/path')` for back navigation. Always use `navigateBack()`.

---

## 9. History Grid — CONSTANTS.DEFAULT_SEARCH_MODEL + formatDate in valueGetter

```tsx
// Search model — spread CONSTANTS.DEFAULT_SEARCH_MODEL
const searchModel: ClientGradeAchievedSearchModel = {
    ...CONSTANTS.DEFAULT_SEARCH_MODEL,
    clientId: clientId ?? '',
};
const { data: gradeAchievedRecords } = useSearchGradeAchievedQuery(searchModel);

// Columns — use formatDate in valueGetter, NOT DateColumnDefinition
const columns: GridColDef[] = [
    {
        field: 'dateLastAttended',
        headerName: content('gradeAchieved.dateLastAttended', 'Date Last Attended'),
        flex: 2,
        filterable: false,
        valueGetter: (value: string) => formatDate(value),
    },
    {
        field: 'actions',
        headerName: content('global.actions', 'Actions'),
        flex: 2,
        sortable: false,
        filterable: false,
        disableColumnMenu: true,
        disableExport: true,          // REQUIRED on actions column
        renderCell: (params) =>
            <TfioBox display="flex" alignItems="center" height="100%" width="100%" flexDirection="row">
                <TfioButton sx={{ mr: 1 }} onClick={() => handleEdit(params.row)}>
                    {content('global.edit', 'Edit')}
                </TfioButton>
                <TfioButton sx={{ mr: 1 }} onClick={() => { ... setDeleteModalOpen(true); }}>
                    {content('global.Delete', 'Delete')}
                </TfioButton>
            </TfioBox>
    },
];

// Grid — no permission guards, no localeText override, use initialState for sort
<TfioDataGrid
    disableRowSelectionOnClick
    rows={gradeAchievedRecords?.list ?? []}
    columns={columns}
    getRowId={(row) => row.clientGradeAchievedId ?? ''}
    slots={{ toolbar: TfioGridToolbar }}
    initialState={{ sorting: { sortModel: [{ field: 'dateAchieved', sort: 'desc' }] } }}
    slotProps={{
        toolbar: {
            showSearch: false,
            showAddButton: true,
            showExportButton: true,
            onAddClick: handleAdd,
            addButtonText: content('gradeAchieved.add', 'Add Grade'),
        } as TfioGridToolbarProps & ToolbarPropsOverrides & GridToolbarProps,
    }}
/>
```

**Key rules:**
- `filterable: false` on all data columns
- `disableExport: true` on the actions column
- `initialState.sorting` for default sort order
- `showSearch: false` on toolbar (search not used in face sheet history grids)
- Use `TfioBox` + `TfioButton` in `renderCell`, NOT raw `<>` fragments

---

## 10. History Grid — Delete Dialog with actions prop

The delete confirmation dialog uses `TfioDialog`'s `actions` prop for buttons and `TfioBox`/`TfioTypography` for the body. Never use raw HTML (`<div>`, `<p>`).

```tsx
// State — separate state per modal
const [enrollmentId, setEnrollmentId] = useState<string>('');
const [deleteModalOpen, setDeleteModalOpen] = useState(false);
const [addEditModalOpen, setAddEditModalOpen] = useState(false);
const [modalMode, setModalMode] = useState<'add' | 'edit' | 'view'>('add');

// Delete dialog
<TfioDialog
    open={deleteModalOpen}
    titletext={content('gradeAchieved.deleteTitle', 'Delete Grade Achieved')}
    actions={
        <>
            <TfioButton onClick={() => setDeleteModalOpen(false)}>
                {content('global.cancel', 'Cancel')}
            </TfioButton>
            <TfioButton onClick={handleDelete}>
                {content('global.confirm', 'Confirm')}
            </TfioButton>
        </>
    }
>
    <TfioBox sx={{ margin: 5 }}>
        <TfioTypography variant='body2'>
            {content('gradeAchieved.deleteMessage', 'Are you sure you want to delete this grade achieved record?')}
        </TfioTypography>
    </TfioBox>
</TfioDialog>
```

**Key rules:**
- Buttons go in the `actions` prop, NOT inside children
- Use `TfioBox` + `TfioTypography` for the message body
- Use `content('global.cancel')` and `content('global.confirm')` tokens

---

## 11. Add/Edit Modal — ID Prop + Self-Fetch with skip

The add/edit component receives only the record ID (not the full model). It fetches its own data via RTK Query with `skip` when adding new.

```tsx
// Props interface
interface GradeAchievedAddEditProps {
    gradeAchievedId: string;
    mode: 'add' | 'edit';
    onCancel: () => void;
}

const GradeAchievedAddEdit = (props: GradeAchievedAddEditProps) => {
    const { clientId } = useParams<{ clientId: string }>();
    const { getValidationRules } = useValidationRules();
    const { setWait } = useSetWait();

    const validationRules = [...getValidationRules('ClientGradeAchievedEditModel')];
    const methods = useForm<ClientGradeAchievedEditModel>({
        resolver: fluentValidationResolver(new GradeAchievedValidator(validationRules)),
    });

    const [createGradeAchieved, { isLoading: isCreating }] = useCreateGradeAchievedMutation();
    const [updateGradeAchieved, { isLoading: isUpdating }] = useUpdateGradeAchievedMutation();

    // Fetch existing data — skip when adding new
    const { data: gradeAchieved, isLoading, isFetching } = useGetGradeAchievedQuery(
        { clientId: clientId ?? '', id: props.gradeAchievedId },
        { skip: !props.gradeAchievedId || props.gradeAchievedId === CONSTANTS.EMPTY_GUID }
    );

    // Populate form when data loads
    useEffect(() => {
        if (gradeAchieved) methods.reset(gradeAchieved);
    }, [gradeAchieved, methods]);

    // Global loading indicator
    useEffect(() => {
        setWait(isLoading || isFetching || isCreating || isUpdating);
    }, [isLoading, isFetching, isCreating, isUpdating, setWait]);

    const onSubmit = async (model: ClientGradeAchievedEditModel) => {
        if (model.clientId == null || model.clientId === CONSTANTS.EMPTY_GUID) {
            model.clientId = clientId ?? '';
        }

        let response: ClientGradeAchievedEditModel;
        if (!model.clientGradeAchievedId || model.clientGradeAchievedId === CONSTANTS.EMPTY_GUID) {
            response = await createGradeAchieved(model).unwrap();
        } else {
            response = await updateGradeAchieved(model).unwrap();
        }

        if (response.messages.length === 0) {
            props.onCancel();
            setMessage(content('gradeAchieved.save.success', '...'), 'success');
        }
    };
    // ...
};
```

**From the history component — how to open:**
```tsx
const [gradeAchievedId, setGradeAchievedId] = useState<string>('');
const [addEditModalOpen, setAddEditModalOpen] = useState(false);
const [modalMode, setModalMode] = useState<'add' | 'edit'>('add');

const handleEdit = (row) => {
    setGradeAchievedId(row.clientGradeAchievedId ?? '');
    setModalMode('edit');
    setAddEditModalOpen(true);
};

const handleAdd = () => {
    setGradeAchievedId(CONSTANTS.EMPTY_GUID);
    setModalMode('add');
    setAddEditModalOpen(true);
};

<TfioDialog open={addEditModalOpen}>
    <GradeAchievedAddEdit
        mode={modalMode}
        gradeAchievedId={gradeAchievedId}
        onCancel={() => setAddEditModalOpen(false)}
    />
</TfioDialog>
```

---

## 12. View Mode — TfioModelView (NOT disabled form)

**⚠️ Lesson from issue #51:** The old pattern used a disabled form for read-only views. This is **incorrect** — disabled inputs are inaccessible and visually inconsistent.

**Correct pattern:** Create a separate `*_view.tsx` component using `TfioModelView` + `TfioDisplayField`.

```tsx
// enrollment_view.tsx — correct read-only view
import TfioModelView from '../../../../shared/common/tfio_model_view';
import TfioDisplayField from '../../../../shared/common/tfio_display_field';

const EnrollmentView = () => {
    const { enrollmentId } = useParams<{ enrollmentId: string }>();
    const { data: enrollment } = useGetClientEnrollmentQuery(
        enrollmentId ?? '',
        { skip: !enrollmentId || enrollmentId === CONSTANTS.EMPTY_GUID }
    );
    const navigateBack = useNavigateBack();

    return (
        <TfioPageWrapper headerText={content('enrollment.view.headerText', 'View Enrollment')}>
            <TfioPrimaryStack>
                <TfioModelView>
                    <TfioDisplayField label={content('enrollment.schoolName', 'School Name')} value={enrollment?.schoolName} />
                    <TfioDisplayField label={content('enrollment.gpa', 'GPA')} value={enrollment?.gpa?.toString()} />
                    {/* ... other fields ... */}
                </TfioModelView>
                <TfioButton onClick={navigateBack}>{content('global.go.back', 'Go Back')}</TfioButton>
            </TfioPrimaryStack>
        </TfioPageWrapper>
    );
};
```

**Rules:**
- Never use a form with `disabled` inputs for read-only display
- Never use `mode: 'view'` with `inputProps={{ disabled: isReadOnly }}`
- A separate `*_view.tsx` file with `TfioModelView` is always required
- The view route must be `enrollment/:enrollmentId/view` (see section 13)

---

## 13. Routes — Sub-sections at same level, Add/Edit/View as sub-routes

Sub-section history grids are at the SAME level as the parent, using descriptive paths WITHOUT a parent prefix.

Add/Edit/View screens for complex forms (like Enrollment) use **sub-routes**, not modals.

```tsx
// CORRECT — history at same level as parent
{ path: 'education', lazy: ... }          // Edit Education
{ path: 'grade_achieved', lazy: ... }     // Grade Achieved History
{ path: 'ged_test', lazy: ... }           // GED History
{ path: 'enrollment', lazy: ... }         // Enrollment History
{ path: 'report_card', lazy: ... }        // Report Card History

// CORRECT — complex forms use routed sub-screens (not modals)
{ path: 'enrollment/add', lazy: ... }                       // Add Enrollment
{ path: 'enrollment/:enrollmentId/edit', lazy: ... }        // Edit Enrollment
{ path: 'enrollment/:enrollmentId/view', lazy: ... }        // View Enrollment

// WRONG — do NOT nest under education/
{ path: 'education/edit', ... }
{ path: 'education/grade_achieved', ... }
```

**Source of truth for screen type:** The FDS document specifies whether each screen is a `Modal` or `Form Screen` in the **Element Type** column of the element description tables. Always check the FDS first — the heuristic below is a guideline, not a substitute.

> Example from Client Management FDS, Section 24 (Education):
> - `Add/Edit Grade Information Modal | | Modal` → use a Modal
> - `Add/Edit Enrollment Information | | Form Screen` → use a Routed screen

**When to use routed screens vs modals (heuristic — verify against FDS):**
- **Modal** — simple forms with few fields (GradeAchieved, GedTest, ReportCard)
- **Routed screen** — complex forms with address, many fields, or their own sub-navigation (Enrollment)
- The history grid navigates via `navigate()` for routed screens:
```tsx
// In history grid — navigate to routed add/edit
const handleEdit = (row) => navigate(`/client/face_sheet/${clientId}/enrollment/${row.id}/edit`);
const handleAdd = () => navigate(`/client/face_sheet/${clientId}/enrollment/add`);
const handleView = (row) => navigate(`/client/face_sheet/${clientId}/enrollment/${row.id}/view`);
```

And the overview card menu navigates to:
```tsx
handleNavigate(`/client/face_sheet/${clientId}/education`)
handleNavigate(`/client/face_sheet/${clientId}/grade_achieved`)
handleNavigate(`/client/face_sheet/${clientId}/enrollment`)
```

---

## 14. TfioAddress — Contract and Dependencies

The `TfioAddress` shared input component requires specific setup in the parent form. Never use it without all four elements.

**1. Form type must use `WithAddress<T, 'addressData'>`:**
```tsx
import { WithAddress } from '../../../../types/address.types';
type EnrollmentFormModel = WithAddress<ClientEnrollmentEditModel, 'addressData'>;
```

**2. Default values must initialize the `addressData` object:**
```tsx
const methods = useForm<EnrollmentFormModel>({
    resolver: fluentValidationResolver(new EnrollmentValidator(validationRules)) as any,
    defaultValues: {
        addressData: {
            street1: '', street2: '', city: '',
            state: CONSTANTS.EMPTY_GUID,
            zipCode: '',
            county: CONSTANTS.EMPTY_GUID,
        },
    },
});
```

**3. County must be filtered by selected state via `useGetChildReferencesQuery`:**
```tsx
const selectedStateId = useWatch({ control: methods.control, name: 'addressData.state' });
const { data: countyTypes } = useGetChildReferencesQuery(
    selectedStateId && selectedStateId !== CONSTANTS.EMPTY_GUID
        ? { referenceType: 'CountyType', parentId: selectedStateId }
        : skipToken
);
```

**4. `addressData` must sync back to flat model fields before submit:**
```tsx
const addressData = useWatch({ control: methods.control, name: 'addressData' });
useEffect(() => {
    if (addressData) {
        methods.setValue('addressLine1', addressData.street1);
        methods.setValue('addressLine2', addressData.street2 ?? '');
        methods.setValue('city', addressData.city);
        methods.setValue('stateTypeId', addressData.state as any);
        methods.setValue('zipCode', addressData.zipCode);
        methods.setValue('countyTypeId', (addressData.county ?? CONSTANTS.EMPTY_GUID) as any);
    }
}, [addressData, methods]);
```

**5. `validation.ts` must export `useValidateAddressMutation`** (required by `TfioAddress` internally).

**6. Submit must map from `addressData` to flat fields explicitly:**
```tsx
const submitModel: ClientEnrollmentEditModel = {
    ...model,
    addressLine1: model.addressData.street1,
    addressLine2: model.addressData.street2,
    city: model.addressData.city,
    stateTypeId: model.addressData.state as any,
    countyTypeId: (model.addressData.county ?? CONSTANTS.EMPTY_GUID) as any,
    zipCode: model.addressData.zipCode,
};
```

---

## 15. RTK Hook Naming — Enrollment Specific

**⚠️ Lesson from issue #51:** Enrollment hooks use `Client` prefix and a unified `Save` mutation (not separate create/update).

```typescript
// enrollment.ts — CORRECT hook names
useSearchClientEnrollmentQuery       // NOT useSearchEnrollmentQuery
useGetClientEnrollmentQuery          // NOT useGetEnrollmentQuery
useSaveClientEnrollmentMutation      // NOT useCreateEnrollmentMutation / useUpdateEnrollmentMutation
useDeleteClientEnrollmentMutation    // NOT useDeleteEnrollmentMutation
```

**Rule:** Always verify hook names against the actual exports in the service file before using them. Never guess based on naming patterns from other entities.

The `useSaveClientEnrollmentMutation` handles both create and update — the API endpoint determines the behavior based on whether `enrollmentId` is set.

---

## 16. Content Token Namespace

Tokens use the **entity name** as the namespace, NOT `client.{entity}.*`.

```
CORRECT:
  education.iep
  education.iepDate
  gradeAchieved.gradeAchievedTypeId.required
  enrollment.schoolName.required
  gedTest.testDate.required
  reportCard.reportCard.required
  global.cancel
  global.confirm
  global.edit
  global.notAvailable

WRONG:
  client.education.iep
  client.education.gradeAchieved.required
```

---

## 17. Tests — Controller Tests with Mock\<IRepo\>

> **Note:** These are **controller integration tests** — the exception category that IS committed to the repo.
> Per CODING_STANDARDS.md §8: unit tests are written locally but not checked in. Controller tests and repo tests are the committed exception.

Tests go in `com.tfione.service.test/client/` and test the controller via `Mock<IEducationRepo>`. This verifies the wiring between controller and repo.

```csharp
public class EducationControllerTests
{
    private readonly Mock<ILogger<EducationController>> loggerMock;
    private readonly Mock<IEducationRepo> repoMock;
    private readonly EducationController controller;

    private static readonly Guid ClientId = Guid.NewGuid();
    private static readonly Guid RecordId = Guid.NewGuid();

    public EducationControllerTests()
    {
        this.loggerMock = new Mock<ILogger<EducationController>>();
        this.repoMock = new Mock<IEducationRepo>();
        this.controller = new EducationController(this.loggerMock.Object, this.repoMock.Object);
    }

    [Fact]
    public void Constructor_NullLogger_ThrowsArgumentNullException()
        => Assert.Throws<ArgumentNullException>(() => new EducationController(null!, this.repoMock.Object));

    [Fact]
    public async Task GetEducationOverview_ReturnsOkWithModel()
    {
        var model = new ClientEducationOverviewModel();
        this.repoMock.Setup(r => r.GetEducationOverview(ClientId)).ReturnsAsync(model);

        var result = await this.controller.GetEducationOverview(ClientId);

        var ok = Assert.IsType<OkObjectResult>(result.Result);
        Assert.Equal(model, ok.Value);
    }

    [Fact]
    public async Task SearchGradeAchieved_SetsClientIdAndReturnsOk()
    {
        var searchModel = new ClientGradeAchievedSearchModel();
        this.repoMock.Setup(r => r.SearchGradeAchieved(It.IsAny<ClientGradeAchievedSearchModel>()))
                     .ReturnsAsync(searchModel);

        var result = await this.controller.SearchGradeAchieved(ClientId, searchModel);

        Assert.Equal(ClientId, searchModel.ClientId);  // verify ClientId is assigned
        var ok = Assert.IsType<OkObjectResult>(result.Result);
        Assert.Equal(searchModel, ok.Value);
    }
    // One test per endpoint
}
```

**Requirements:**
- One test per endpoint (constructor null checks + each HTTP action)
- Search tests verify that `ClientId` is assigned in the controller before calling repo
- Test project must reference `com.tfione.api` and `com.tfione.repo` projects

---

## 19. Overview Card Context Menu — `onClose` + Deep Links

### MUI Menu — Always include `onClose`

Every `<Menu>` on an overview card MUST have `onClose` wired to the close handler. Without it:
- Escape key does nothing
- Clicking outside the menu does nothing
- The menu stays open with visually odd state (backdrop but no dismiss)

```tsx
// ✅ CORRECT
<Menu
    id="education-menu"
    open={menuOpen}
    anchorEl={menuAnchorEl}
    onClose={handleMenuClose}           // ← REQUIRED
    slotProps={{ list: { 'aria-labelledby': 'education-menu-button' } }}
>
    <TfioMenuItem onClick={() => handleNavigate(...)}>...</TfioMenuItem>
</Menu>

// ❌ WRONG — menu cannot be dismissed without clicking an item
<Menu id="education-menu" open={menuOpen} anchorEl={menuAnchorEl}>
```

### Documents Deep Link — Use `documentCategoryName`

When navigating to the documents page from a context menu, always pass `?documentCategoryName=X` so the correct category auto-expands:

```tsx
// ✅ Deep link — auto-expands "Education" category in the tree
<TfioMenuItem onClick={() => handleNavigate(
    `/client/face_sheet/${clientId}/documents?documentCategoryName=Education`
)}>
    View Education Documents
</TfioMenuItem>

// ❌ Bare link — user must manually find the category
<TfioMenuItem onClick={() => handleNavigate(
    `/client/face_sheet/${clientId}/documents`
)}>
```

Use `documentCategoryName` (human-readable string) not `documentCategoryId` (GUID) — the name survives database re-seeding and is self-documenting.

---

## 18. Tags Registration in tags.ts

Each entity needs two tags — lowercase for list, PascalCase for individual:

```typescript
// tags.ts additions for education section
'EducationOverview',
'Education',
'gradeAchieved',    // collection tag
'GradeAchieved',    // individual item tag
'gedTest',
'GedTest',
'enrollment',
'Enrollment',
'reportCard',
'ReportCard',
```

---

## Quick Checklist — Face Sheet Section

### Backend
- [ ] **Every public class and property in `com.tfione.model` and `com.tfione.api` MUST have `/// <summary>` XML doc comment** — Gate build uses `-WarnAsError` with CS1591/SA1600. Local dev does NOT enforce this, so it will build locally but fail the pipeline.
- [ ] One `ClientXxxEditModelValidator.cs` per sub-entity with business rules
- [ ] All validators registered in `Extensions.cs`
- [ ] Repo uses private static `PopulateX(entity, model)` for mappings
- [ ] Controller uses `Guid id` (not the typed GUID) for Get/Update/Delete child params
- [ ] `EducationControllerTests.cs` with one test per endpoint

### Frontend RTK
- [ ] One RTK file per entity (not one big `education.ts`)
- [ ] Get/Delete params: `{ clientId: string; id: string }` (not model objects)
- [ ] Create/Update mutations invalidate collection tag + `EducationOverview` by clientId
- [ ] Delete mutations invalidate collection tag + `EducationOverview` (no clientId needed)
- [ ] Tags registered in `tags.ts` (lowercase + PascalCase pair per entity)

### Frontend Validators
- [ ] One validator file per entity
- [ ] `useValidationRules('ModelClassName')` used in every form (NOT `[]`)
- [ ] Token namespace: `{entityName}.{field}.{rule}` (not `client.{entity}.*`)

### Frontend Components
- [ ] Boolean fields: `TfioSelect` with `YesNoType` + `useWatch` + bool↔GUID conversion
- [ ] Edit form: `useValidationRules` + `useSetWait` + `useNavigateBack`
- [ ] History grid: `CONSTANTS.DEFAULT_SEARCH_MODEL` spread, `formatDate` in `valueGetter`
- [ ] History grid: `disableExport: true` on actions column, `TfioBox` in `renderCell`
- [ ] History grid: `showSearch: false` on toolbar
- [ ] Add/edit modal: ID prop + self-fetch + `skip` + `useEffect` reset + `useSetWait`
- [ ] Large forms: `<TfioDialog maxWidth='md' fullWidth>` (simple forms only)
- [ ] Complex forms (e.g. Enrollment): use routed screens, NOT modals; add 3 sub-routes (add/edit/view)
- [ ] View screen: separate `*_view.tsx` with `TfioModelView` + `TfioDisplayField` (NOT disabled inputs)
- [ ] Forms with address: use `WithAddress<T>` type, county filtered by state, field sync via `useWatch`, submit maps addressData back to flat fields
- [ ] Delete dialog: `actions` prop + `TfioBox` + `TfioTypography` body
- [ ] Verify all RTK hooks against actual exports in the service file before use
- [ ] Overview card: `displayValue`/`displayDate`/`displayBool`/`displayReference` helpers
- [ ] Overview card: "N/A" fallback via `content("global.notAvailable", "N/A")`
- [ ] Overview card: icon avatar in `CardHeader`
- [ ] Routes: sub-sections at same level (no `education/` prefix)
- [ ] Route paths in overview card menu must match router paths exactly
- [ ] Overview card context menu: `<Menu>` MUST have `onClose={handleMenuClose}` — without it, Escape and click-outside do nothing
- [ ] Overview card context menu: navigation items use `?documentCategoryName=X` (by name, not GUID) for deep links to Documents page
