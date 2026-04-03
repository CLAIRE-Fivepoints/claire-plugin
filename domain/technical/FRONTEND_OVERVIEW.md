---
keywords: [frontend, react, typescript, vite, source-tree, components, spa, bootstrap]
---

# TFI One — Frontend Architecture (`com.tfione.web`)

**Project**: `com.tfione.web`
**Framework**: React 19.1.1 + TypeScript 5.9.2
**Build**: Vite 7.0.6 (SWC compiler)
**UI Kit**: Material-UI 7.3.1 (Pro license)
**Total Components**: ~245

---

## App Bootstrap Chain

```
main.tsx
├── Sentry.init()                    # Error tracking with PII scrubbing
├── PublicClientApplication (MSAL)   # Azure AD auth instance
├── LicenseInfo.setLicenseKey()      # MUI Pro license
└── <StrictMode>
    └── <MsalProvider>               # Azure AD context
        └── <Provider store={store}> # Redux state
            └── <PersistGate>        # State hydration from localStorage
                └── <StyledEngineProvider>
                    └── <RouterProvider>  # React Router 7
                        └── App.tsx
                            ├── <AppTheme>     # MUI theme + CSS vars
                            ├── <CssBaseline>
                            ├── <Messages>     # Global snackbar
                            ├── <Header>       # Top app bar
                            ├── <MainNavigationDrawer>
                            ├── <Outlet>       # Route content
                            └── <Footer>
```

---

## Source Tree

```
src/
├── main.tsx                    # Entry point
├── app.tsx                     # Root layout
├── components/                 # ~245 components (feature-based)
│   ├── admin/                  # Document configuration
│   ├── agency/                 # Agency CRUD + face sheet (41 routes)
│   ├── auth/                   # Login, logout, MFA, password
│   ├── background_check/       # Background check management
│   ├── client/                 # Client search + intake wizard
│   ├── dashboard/              # Dashboard container
│   ├── form/                   # Dynamic form schema CRUD
│   ├── inquiry/                # Inquiry search + wizard + dashboard
│   ├── provider/               # Provider CRUD + face sheet (52 routes)
│   ├── public/                 # Loading, 404
│   ├── report/                 # Power BI report view
│   ├── serviceprovider/        # Service provider CRUD + face sheet
│   ├── user/                   # User admin, my account
│   └── shared/                 # 80+ shared components
│       ├── navigation/         # Secure wrapper, drawer, menus
│       ├── site/               # Header, footer
│       ├── overlay/            # Messages, wait backdrop
│       ├── common/             # Page wrapper, wizard, grid toolbar
│       ├── primitives/         # 25 MUI wrappers (tfio_*)
│       ├── input/              # 21 custom inputs (tfio_*)
│       ├── filter/             # 15+ data grid filters
│       ├── form/               # Survey.js form builder/viewer
│       └── view/               # Detail view components
├── constants/                  # Constants, masks, regex
├── hooks/                      # 8 custom hooks
├── redux/                      # Store, slices, RTK Query services
│   ├── store.ts                # Store config + persist
│   ├── slices/                 # 7 state slices
│   └── services/               # 20 API service files
├── routes/                     # Feature-based route definitions
├── theme/                      # MUI theme customization
├── utilities/                  # Helpers, env config
├── validation/                 # 18 entity validators
└── types/                      # Generated API types + enums
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| UI | React + TypeScript | 19.1.1 / ~5.9.2 |
| Build | Vite + SWC | 7.0.6 |
| Routing | React Router DOM | 7.7.1 |
| State | Redux Toolkit + Persist | 2.8.2 / 6.0.0 |
| API | RTK Query + Axios | built-in / 1.11.0 |
| Auth | MSAL React (Azure AD) | 3.0.17 |
| UI Kit | Material-UI (Pro) | 7.3.1 |
| Data Grid | MUI X Data Grid Pro | 8.9.2 |
| Date Pickers | MUI X Date Pickers Pro | 8.10.1 |
| Forms | React Hook Form | 7.62.0 |
| Validation | FluentValidation-ts | 5.0.0 |
| Dynamic Forms | Survey.js | 2.3.5 |
| File Upload | React Dropzone | 14.3.8 |
| CSS-in-JS | Emotion | 11.14.x |
| Error Tracking | Sentry | 10.1.0 |
| Analytics | Power BI Client React | 2.0.0 |

---

## Environments

| Env | API URL | Config File |
|-----|---------|-------------|
| Local | `https://localhost:58337` or `http://localhost:8080` | `.env.local` |
| Gate | (configured) | `.env.gate` |
| QA | (configured) | `.env.qa` |

**Env variables**: `VITE_API_URL`, `VITE_SSO_CLIENT_ID`, `VITE_SSO_REDIRECT_URL`, `VITE_ENV_NAME`, `VITE_MUI_LICENSE_KEY`, `VITE_POWERBI_API_URL`, `VITE_RECAPTCHA_SITE_KEY_V3`, `VITE_RECAPTCHA_SITE_KEY_V2`, `SENTRY_AUTH_TOKEN`

---

## UI Patterns

| Pattern | Implementation |
|---------|---------------|
| **Search Page** | DataGrid Pro + toolbar + filters → Row click → Navigate to detail |
| **Face Sheet** | Tabbed layout with Outlet → Nested route per tab → Redux context |
| **Wizard** | Stepper + step components → Validation per step → Submit at end |
| **CRUD Form** | React Hook Form + FluentValidation → tfio_* inputs → API mutation |
| **Inline Edit** | Cell components in DataGrid → Edit mode toggle → Patch API |
| **Card View** | Grouped info in cards → Read/Edit mode toggle |
| **Notifications** | Redux messages → Snackbar stack → Auto-dismiss |
| **Loading** | Redux waiting → Full-screen backdrop |
| **Auth Guard** | Secure wrapper → Check Redux auth → Redirect to /login |
| **File Upload** | Dropzone → Azure Blob → FileMetaData tracking |
| **Dynamic Form** | Survey.js schema → FormBuilder/FormViewer → DB-stored |

---

## Custom Hooks

| Hook | Purpose |
|------|---------|
| `useAppDispatch` | Typed Redux dispatch |
| `useAppSelector` | Typed Redux selector |
| `useSetMessage` | Dispatch snackbar notifications |
| `useSetWait` | Control loading backdrop |
| `useValidationRules` | Get rules for entity type |
| `useTokenizedContent` | i18n content by token |
| `useNavigateBack` | Smart back navigation |
| `useFormContextOrProp` | Form control from context or prop |
| `useFormReadonly` | Readonly mode from context |
