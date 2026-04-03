---
keywords: [theme, mui, colors, typography, poppins, roboto, palette, css-variables, emotion]
---

# TFI One — Theme & Styling

**UI Kit**: Material-UI 7.3.1
**CSS Engine**: Emotion 11.14.x
**CSS Variables**: Enabled (prefix: `template`)
**Dark Mode**: Not implemented

---

## Brand Colors

```
Primary:    #2D6864  (teal green)
Secondary:  #F9D86F  (gold/yellow)
```

## System Colors

```
Info:       #284B63  (blue)
Warning:    #231B00  (dark brown)
Error:      #3B080D  (dark red)
Success:    #1E4620  (dark green)
Greyscale:  #D9D9D9  (neutral)
```

## Background

```
Default:    ~99% white (very light gray)
Paper:      ~97% white
```

---

## Typography

| Level | Font | Size | Weight |
|-------|------|------|--------|
| H1 | Poppins | 48px | 600 |
| H2 | Poppins | 36px | 600 |
| H3 | Poppins | 30px | 600 |
| H4 | Poppins | 24px | 600 |
| H5 | Poppins | 20px | 600 |
| H6 | Poppins | 18px | 600 |
| Body1 | Roboto | 14px | 400 |
| Body2 | Roboto | 14px | 400 |
| Caption | Roboto | 12px | 400 |
| Subtitle1 | Roboto | 18px | 600 |

**Font Loading**: Google Fonts CDN (in `index.html`)
- Roboto: 300, 400, 500, 700
- Poppins: 300, 400, 500, 600, 700

---

## Shape

```
Border Radius: 1px (minimal rounding — sharp/corporate aesthetic)
```

---

## Theme Files

```
src/theme/
├── app_theme.tsx              # AppTheme provider wrapper
├── theme_primitives.ts        # Palette, typography, shape
├── customizations/
│   ├── inputs.tsx             # TextField, Select, Checkbox, Radio, Switch
│   ├── data_display.tsx       # DataGrid, Table, List, Card, Chip
│   ├── feedback.tsx           # Alert, Snackbar, Dialog, Progress
│   ├── navigation.tsx         # AppBar, Drawer, Menu, Breadcrumb
│   └── surfaces.ts            # AppBar, Card, Paper
```

### Custom Palette Extension
```typescript
declare module '@mui/material/styles' {
  interface Palette {
    greyscale: PaletteColor;
  }
}
```

### Theme Provider Pattern
```tsx
<AppTheme>
  {/* Sets data-mui-color-scheme, CSS variable prefix "template" */}
  <CssBaseline />
  <App />
</AppTheme>
```

---

## Component Overrides

### Inputs
- TextField: outlined variant default, consistent sizing
- Select: custom dropdown styling
- Checkbox/Radio: brand primary color (#2D6864)
- Switch: toggle with brand colors

### Data Display
- DataGrid Pro: custom toolbar, row hover, selection colors
- Table: striped rows, compact density
- Card: minimal shadow, sharp corners (1px radius)
- Chip: brand-colored variants

### Feedback
- Alert: color-coded (error/warning/info/success system colors)
- Snackbar: slide from right, stacked
- Dialog: centered, responsive sizing
- Progress: brand primary color

### Navigation
- AppBar: primary color (#2D6864) background
- Drawer: collapsible, tree-based navigation
- Breadcrumb: route-based auto-generation

---

## Responsive Grid Layout

```typescript
// Standard column definitions used across all forms
const COLUMN_DEFINITIONS = {
  DEFAULT:  { sm: 12, md: 4,  lg: 3, xl: 2 },  // Standard field
  LARGE:    { xs: 12, sm: 8,  lg: 6, xl: 4 },  // Wide field
  MODAL:    { xs: 12, lg: 6,  xl: 4 },          // Modal field
};
```

All forms use MUI Grid2 with these standard breakpoints for consistent responsive behavior.
