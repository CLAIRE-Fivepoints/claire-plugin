---
domain: fivepoints
category: technical
name: E2E_TESTING
title: "E2E Testing with Playwright"
keywords: [e2e, playwright, testing, education, video-proof, browser-automation, "persona:fivepoints-dev", "persona:fivepoints-tester"]
updated: 2026-03-05
---

# E2E Testing with Playwright

## Overview

Automated browser tests that exercise the TFI One frontend, fill forms, save records, and produce `.webm` video recordings as proof of functionality. Currently covers the **Education module** (5 sub-modules).

## Usage

```bash
claire fivepoints e2e-education
claire fivepoints e2e-education --base-url https://localhost:5173 --output-dir ./videos
claire fivepoints e2e-education --help
```

## Education Sub-Modules Tested

| # | Module | Route | What It Does |
|---|--------|-------|--------------|
| 1 | Education Edit | `/client/face_sheet/{id}/education` | Fill IEP, 504 Plan, ARD, On Grade Level |
| 2 | Grade Achieved | `/client/face_sheet/{id}/grade_achieved` | Add grade record via dialog |
| 3 | GED Test | `/client/face_sheet/{id}/ged_test` | Add test subject + score via dialog |
| 4 | Enrollment | `/client/face_sheet/{id}/enrollment` | Add school enrollment via dialog |
| 5 | Report Card | `/client/face_sheet/{id}/report_card` | Add report card text via dialog |

## Prerequisites

1. **Python 3.8+** with `playwright` package installed
2. **Chromium browser** installed via `playwright install chromium`
3. **TFI One frontend** running on HTTPS (default: `https://localhost:5173`)
4. **TFI One backend** running (default: port `58337`)
5. **CORS match** — frontend and backend must accept each other's origins

## MUI Component Selector Patterns

### TfioSelect (MUI Select)

TFI One wraps MUI Select in a `TfioSelect` component. The select element gets an `id` matching the field name.

```python
# Click to open the dropdown, then select by option text
page.locator(f"#{field_id}").click(force=True)
page.locator(f"[role='option']:has-text('{option_text}')").click()
```

### MUI v6 DatePicker (Spinbutton Workaround)

MUI v6 DatePicker renders Month/Day/Year as separate `spinbutton` elements inside a `MuiPickersSectionList` container — **not** a simple text input. The actual `<input>` is hidden.

```python
# 1. Find the hidden input by name
inp = page.locator(f"input[name='{field_name}']")

# 2. Click the visible section container (sibling of hidden input)
container = page.locator(
    f"input[name='{field_name}'] >> xpath=../div[contains(@class, 'MuiPickersSectionList')]"
)
container.first.click()

# 3. Select all, then type digits — MUI auto-advances sections
page.keyboard.press("Meta+a")
for ch in "03012026":  # MM/DD/YYYY without slashes
    page.keyboard.press(ch)

# 4. Close any picker popup
page.keyboard.press("Escape")
```

### Dialog Save Button

```python
# In-dialog save
page.locator("[role='dialog'] button:has-text('Save')").first.click()

# Page-level save
page.locator("button:has-text('Save')").first.click()
```

## TFI One Login Flow

1. Navigate to `/login`
2. Click "Non TFI Employees Click Here to Login" (reveals the standard form)
3. Fill `input[name='userName']` and `input[name='password']`
4. Click the Login button
5. Wait for redirect (auth token is stored automatically)

## Output

Each test produces:
- A `.webm` video recording (1920x1080) showing the full interaction
- `.png` screenshots at key moments (form filled, after save)

All output goes to `--output-dir` (default: `./education_e2e_videos`).

### Video Proof Format Requirements

**⚠️ `.webm` files are NOT accepted as proof for GitHub issues or ADO PRs.**

Before attaching a video proof to a GitHub issue or Azure DevOps PR:

1. **Convert to MP4** — GitHub and ADO only render MP4 inline; `.webm` is not supported:
   ```bash
   ffmpeg -i proof_recording.webm -c:v libx264 -c:a aac proof_recording.mp4
   ```

2. **Use the full absolute path** — When referencing the file in a comment, always use the full path so it can be found unambiguously:
   ```
   Proof: /Users/andreperez/proof-archive/fivepoints/siblings/proof_20260310.mp4
   ```
   Never use just a filename like `proof_recording.mp4`.

## Architecture

```
plugins/fivepoints/
├── domain/commands/e2e-education.sh   # CLI wrapper (prereq checks, server detection)
└── domain/scripts/education_e2e.py    # Playwright test script (all 5 modules)
```

The bash wrapper checks prerequisites (`python3`, `playwright`), verifies that servers are running on expected ports, then delegates to the Python script with all CLI args passed through.
