---
keywords: [routing, react-router, face-sheet, lazy-loading, auth-guard, nested-routes, tabs]
---

# TFI One — Frontend Routing

**Library**: React Router DOM 7.7.1
**Pattern**: Feature-based route splitting with lazy loading

---

## Route Tree

```
/ ─── <Secure> guard (requires auth)
│
├── /                                     Dashboard
├── /component_test                       Component playground
│
├── /agencies                             Agency search grid
├── /agencies/new                         Create agency
├── /agencies/:id/view                    View agency (read-only)
├── /agency/face_sheet/:agencyId          Agency face sheet (tabbed)
│   ├── general_information               General info tab
│   ├── agency_documents                  Documents tab
│   ├── agency_notes                      Notes tab
│   ├── agency_alerts                     Alerts tab
│   ├── current_placements                Current placements tab
│   ├── contracted_services               Contracted services tab
│   └── signature_requests                Signature requests tab
│
├── /providers                            Provider search grid
├── /providers/new                        Create provider
├── /face_sheet/:providerId               Provider face sheet (tabbed)
│   ├── general_information
│   ├── address
│   ├── household_members
│   ├── emergency_contacts
│   ├── current_placements
│   ├── worker_assignment
│   ├── license_info
│   ├── pets
│   ├── incident_reports
│   ├── notes
│   ├── attributes
│   ├── alerts
│   ├── status_history
│   ├── location_history
│   ├── inquiry
│   ├── placement_proficiency
│   ├── documents
│   ├── facility_history
│   ├── license_history
│   ├── background_checks
│   └── training
│
├── /clients                              Client search
├── /client/intake/:intakeId              Client intake wizard
│
├── /users                                User management grid
├── /users/:id/view                       User detail view
├── /my_account                           Current user profile
│
├── /inquiry_search                       Inquiry search
├── /inquiry/add_inquiry                  Add inquiry wizard
├── /inquiry/dashboard                    Inquiry dashboard
│
├── /form                                 Form schema search
├── /form/:id                             Form schema edit
├── /form/:id/version                     Form version search
├── /form/:id/version/:versionId          Form version edit
├── /form/:id/submission                  Form submission search
├── /form/:id/submission/:submissionId    Form submission edit
│
├── /document/configuration               Document definition config
│
├── /background_check                     Background check search
├── /background_check/add                 Add background check
├── /background_check/:id/view            View background check
│
├── /reports                              Power BI reports
│
├── /serviceprovider                      Service provider search
├── /serviceprovider/new                  Create service provider
├── /serviceprovider/:id                  Service provider face sheet
│
└── *                                     404 Not Found

/login                                    Login page (public)
/logout                                   Logout page (public)
```

---

## Route Guard Pattern

```tsx
function Secure({ children }) {
  const isAuthenticated = useAppSelector(state => state.auth.isAuthenticated);

  if (!isAuthenticated) {
    return <Navigate to="/login" />;
  }

  return children;  // renders <Outlet />
}
```

All routes under `/` are wrapped in `<Secure>`. `/login` and `/logout` are public.

---

## Lazy Loading

All route components use `React.lazy()` with code splitting:

```tsx
const AgencySearch = lazy(() => import("../components/agency/agencies"));
const ProviderFaceSheet = lazy(() => import("../components/provider/face_sheet/face_sheet"));
```

Each route module is its own JS chunk, loaded on demand. `<Suspense>` with a `<Loading>` fallback handles transitions.

---

## Face Sheet Pattern (Most Complex)

Provider and Agency entities use a multi-tab "face sheet" layout:

```
/face_sheet/:providerId (Parent layout with <Outlet>)
├── Tab: General Info      ← default, loaded on navigate
├── Tab: Addresses         ← loaded when tab clicked
├── Tab: Household Members
├── Tab: Documents
├── ...
└── Tab: Training
```

- Parent route renders the tab bar + `<Outlet>`
- Each tab is a nested route rendering in the outlet
- URL reflects active tab — **deep linkable**
- Provider/Agency data loaded **once** at parent level, shared via Redux
- Tab navigation uses `useNavigate()` → React Router `<Link>`

---

## Route File Organization

| File | Routes | Domain |
|------|--------|--------|
| `routes.tsx` | Root layout + imports | App shell |
| `agency.tsx` | ~41 routes | Agency management |
| `provider.tsx` | ~52 routes | Provider management |
| `client.tsx` | 2 routes | Client/intake |
| `user.tsx` | 4 routes | User administration |
| `inquiry.tsx` | 3 routes | Inquiry management |
| `document.tsx` | 3 routes | Document configuration |
| `form.tsx` | 6 routes | Dynamic form management |
| `background_check.tsx` | 3 routes | Background checks |
| `serviceprovider.tsx` | ~4 routes | Service providers |
| `report.tsx` | 1 route | Power BI reports |

---

## Navigation Components

- `main_navigation_drawer` — Collapsible sidebar with tree-based menu
- `header` — Top app bar: user menu, org selector, logout
- `secure` — Auth guard wrapper
- `base_menu_options` — Menu item definitions (driven by user permissions)

Menu visibility is permission-based: menu items only show if user has required `PermissionCode`.

---

## Deep Link Pattern — URL Search Parameters

When a page supports external navigation to a specific sub-item (e.g., a document category, a pre-selected tab), use URL search parameters with `useSearchParams()`.

**Pattern (Documents example):**
```tsx
// Navigate to documents page with a pre-selected category
navigate(`/client/face_sheet/${clientId}/documents?documentCategoryName=Education`);

// In the target component
const [searchParams] = useSearchParams();
const documentCategoryName = searchParams.get('documentCategoryName');
const documentCategoryId = searchParams.get('documentCategoryId');

// Use useMemo to compute derived state from the param
const expandedKeys = useMemo(() => {
    if (!items || !documentCategoryName) return [];
    const key = findItem(items, node =>
        node.label.toLowerCase().includes(documentCategoryName.toLowerCase())
    );
    return key ? [key] : [];
}, [items, documentCategoryName]);

// Pass to the tree component
<TfioDocumentTree defaultExpandedItems={expandedKeys} ... />
```

**Rules:**
- Use `searchParams.get('paramName')` — never read params from `window.location` directly
- Derive UI state via `useMemo` with the param as a dependency
- Support both `id`-based and `name`-based params when possible (name is more human-friendly for deep links from other sections)
