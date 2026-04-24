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

Automated browser tests that exercise the TFI One frontend, fill forms, save records, and produce `.mp4` video recordings as proof of functionality. Currently covers the **Education module** (5 sub-modules). Playwright records natively to `.webm`; scripts must post-process to `.mp4` before exiting (see "Video Proof Recording Pattern" below).

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
- An `.mp4` video recording (1920x1080) showing the full interaction — see "Video Proof Recording Pattern" below; Playwright writes `.webm` natively, and the pattern post-processes it to `.mp4` in the same run.
- `.png` screenshots at key moments (form filled, after save)

All output goes to `--output-dir` (default: `./education_e2e_videos`).

### Video Proof Format Requirements

The proof gate (`check_proof_gate` in `domain/scripts/ado_common.sh`) accepts `.mp4` **only**. `.webm` and `.mov` are rejected. This is deliberate — GitHub and ADO render `.mp4` inline, which is what a reviewer needs to confirm the proof without downloading.

### Video Proof Recording Pattern

Playwright's `record_video_dir` writes `.webm` natively, so every recording script MUST transcode to `.mp4` before the run ends. This is **not** a separate "convert before posting" step — it is part of the recording pattern itself. A script that stops at `.webm` is incomplete and will fail the gate (issue #122).

The canonical shape:

1. Record to a raw directory (`.webm` lives here transiently).
2. Transcode the `.webm` to `.mp4` in the final output directory with ffmpeg.
3. Delete the `.webm` so only `.mp4` ships as proof.
4. Print the full absolute `.mp4` path to stdout so the caller can post it.

Reference implementation: `domain/scripts/education_e2e.py` → `save_video()` (the `raw_dir` → `video_dir` conversion). Copy-paste-ready helper for a new script:

```python
import os
import shutil
import subprocess

def save_video(raw_dir: str, output_name: str, video_dir: str) -> str:
    """Transcode the raw .webm Playwright recording to .mp4 in video_dir.

    Returns the absolute .mp4 path. Falls back to keeping the .webm only
    when ffmpeg is not installed — the caller should treat that as a
    broken environment (the proof gate rejects .webm).
    """
    os.makedirs(video_dir, exist_ok=True)
    for name in os.listdir(raw_dir):
        if not name.endswith(".webm"):
            continue
        src = os.path.join(raw_dir, name)
        mp4_name = output_name if output_name.endswith(".mp4") else f"{output_name}.mp4"
        dst = os.path.abspath(os.path.join(video_dir, mp4_name))
        if shutil.which("ffmpeg"):
            subprocess.run(
                ["ffmpeg", "-i", src, "-c:v", "libx264", "-c:a", "aac", "-y", dst],
                check=True,
                capture_output=True,
            )
            os.remove(src)
            return dst
        # ffmpeg missing — record.sh and other orchestrators warn but keep
        # the .webm. The gate will still reject it; install ffmpeg.
        raise RuntimeError(
            f"ffmpeg not found — cannot transcode {src} to .mp4. "
            "Install ffmpeg (brew install ffmpeg) and rerun."
        )
    raise FileNotFoundError(f"No .webm found in {raw_dir}")
```

When posting the path on a GitHub issue or ADO PR, use the full absolute path and one of the recognised prefixes (`MP4:` / `Proof:` / `Recording:` / `Video:`):

```
MP4: /Users/andreperez/proof-archive/fivepoints/siblings/proof_20260310.mp4
```

Never post just a filename like `proof_recording.mp4` — the reviewer can't locate it.

## Architecture

```
plugins/fivepoints/
├── domain/commands/e2e-education.sh   # CLI wrapper (prereq checks, server detection)
└── domain/scripts/education_e2e.py    # Playwright test script (all 5 modules)
```

The bash wrapper checks prerequisites (`python3`, `playwright`), verifies that servers are running on expected ports, then delegates to the Python script with all CLI args passed through.
