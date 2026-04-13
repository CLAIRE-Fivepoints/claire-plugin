#!/usr/bin/env python3
"""
E2E test script for TFI One Education module.

Records video proof of adding data through each Education sub-module:
  1. 01_education_edit.mp4 - Main education form (IEP, 504 Plan, ARD, Grade Level)
  2. 02_grade_achieved.mp4 - Add Grade Achieved record
  3. 03_ged_test.mp4       - Add GED Test score
  4. 04_enrollment.mp4     - Add Enrollment record
  5. 05_report_card.mp4    - Add Report Card entry

Usage:
  python3 education_e2e.py [--base-url URL] [--client-id UUID] [--output-dir DIR]
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

# -- Helpers ------------------------------------------------------------------


def login(page, base_url):
    """Login via the TFI One frontend (Non TFI Employees flow)."""
    page.goto(f"{base_url}/login")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    # Click "Non TFI Employees Click Here to Login"
    non_tfi = page.get_by_text("Non TFI Employees", exact=False)
    if non_tfi.is_visible():
        non_tfi.click()
        time.sleep(1)

    # Fill credentials — override with env vars TFI_USERNAME / TFI_PASSWORD
    username = os.environ.get("TFI_USERNAME", "prime.user")
    password = os.environ.get("TFI_PASSWORD", "Test1234!")
    page.locator("input[name='userName']").fill(username)
    time.sleep(0.5)
    page.locator("input[name='password']").fill(password)
    time.sleep(0.5)

    # Click Login
    page.get_by_role("button", name="Login", exact=True).click()
    time.sleep(5)

    # Verify login — wait for redirect away from /login
    try:
        page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
    except Exception as err:
        raise RuntimeError(
            f"Login failed — still on {page.url}. "
            "Check credentials: TFI_USERNAME / TFI_PASSWORD env vars."
        ) from err
    time.sleep(2)
    print(f"  Login complete — URL: {page.url}")


def select_option(page, field_id, option_text, wait=1.0):
    """Click a MUI Select (TfioSelect) and pick an option by text."""
    page.locator(f"#{field_id}").click(force=True)
    # Wait for options to appear (handles cold-start API delays)
    option = page.locator(f"[role='option']:has-text('{option_text}')")
    option.wait_for(state="visible", timeout=15000)
    option.click()
    time.sleep(wait)


def fill_date(page, field_name, date_str):
    """Fill a MUI v6 DatePicker using spinbutton sections.

    MUI v6 DatePicker renders Month/Day/Year as separate spinbutton elements
    instead of a plain text input. We click the section container then type
    digits — MUI auto-advances through sections.

    Args:
        page: Playwright page object.
        field_name: The name attribute of the hidden date input.
        date_str: Date in MM/DD/YYYY format.

    Returns:
        True if the date was filled, False if the input was not found.
    """
    inp = page.locator(f"input[name='{field_name}']")
    if inp.count() == 0:
        print(f"  WARNING: date input '{field_name}' not found")
        return False

    # Click the visible container (MuiPickersSectionList-root div)
    container = page.locator(
        f"input[name='{field_name}'] >> xpath=../div[contains(@class, 'MuiPickersSectionList')]"
    )
    if container.count() == 0:
        # Fallback: click the month spinbutton near the input
        container = page.locator(
            f"input[name='{field_name}'] >> xpath=../div//span[@aria-label='Month']"
        )
    if container.count() > 0:
        container.first.click()
        time.sleep(0.3)
    else:
        # Last resort: force-click the hidden input
        inp.click(force=True)
        time.sleep(0.3)

    # Select all and type digits (MMDDYYYY) — MUI handles separators
    page.keyboard.press("Meta+a")
    time.sleep(0.1)
    digits = date_str.replace("/", "")
    for ch in digits:
        page.keyboard.press(ch)
        time.sleep(0.08)

    time.sleep(0.3)
    page.keyboard.press("Escape")
    time.sleep(0.3)
    return True


def click_save(page, in_dialog=False):
    """Click Save button, optionally within a dialog."""
    if in_dialog:
        save_btn = page.locator("[role='dialog'] button:has-text('Save')")
        if save_btn.count() == 0:
            save_btn = page.locator("button:has-text('Save')")
    else:
        save_btn = page.locator("button:has-text('Save')")
    if save_btn.count() > 0:
        save_btn.first.click()
        print("  Clicked Save")
        time.sleep(3)
        return True
    print("  WARNING: Save button not found")
    return False


def new_recording_context(browser, subdir, video_dir):
    """Create a new browser context with video recording."""
    raw_dir = os.path.join(video_dir, f"{subdir}_raw")
    os.makedirs(raw_dir, exist_ok=True)
    ctx = browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1920, "height": 1080},
        record_video_dir=raw_dir,
        record_video_size={"width": 1920, "height": 1080},
    )
    return ctx, raw_dir


def save_video(raw_dir, output_name, video_dir):
    """Move the recorded video to the final location, converting webm → mp4."""
    if os.path.exists(raw_dir):
        for f in os.listdir(raw_dir):
            if f.endswith(".webm"):
                src = os.path.join(raw_dir, f)
                mp4_name = output_name.replace(".webm", ".mp4")
                dst = os.path.join(video_dir, mp4_name)
                result = subprocess.run(
                    ["ffmpeg", "-i", src, "-c:v", "libx264", "-c:a", "aac", "-y", dst],
                    capture_output=True,
                )
                if result.returncode == 0:
                    size = os.path.getsize(dst)
                    print(f"  Saved: {mp4_name} ({size / 1024:.0f} KB)")
                else:
                    shutil.move(src, os.path.join(video_dir, output_name))
                    print(f"  Saved (webm fallback): {output_name} — ffmpeg not available")
                break
        shutil.rmtree(raw_dir, ignore_errors=True)


# -- Test functions -----------------------------------------------------------


def record_education_edit(browser, base_url, client_id, video_dir):
    """VIDEO 1: Education Edit — IEP, 504 Plan, ARD, On Grade Level."""
    print("\n=== Recording: Education Edit ===")
    ctx, raw_dir = new_recording_context(browser, "education_edit", video_dir)
    page = ctx.new_page()

    login(page, base_url)

    page.goto(f"{base_url}/client/face_sheet/{client_id}/education")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    print("  On education edit page")

    # IEP = Yes
    select_option(page, "iep", "Yes")
    print("  Selected IEP = Yes")
    time.sleep(1)

    # IEP Date
    if fill_date(page, "iepDate", "03/01/2026"):
        print("  Filled IEP Date = 03/01/2026")

    # Next IEP Date
    if fill_date(page, "nextIEPDate", "09/01/2026"):
        print("  Filled Next IEP Date = 09/01/2026")

    # 504 Plan = Unknown
    select_option(page, "plan504", "Unknown")
    print("  Selected 504 Plan = Unknown")

    # Scroll to show ARD section
    page.evaluate("window.scrollBy(0, 300)")
    time.sleep(0.5)

    # ARD = Yes
    select_option(page, "ard", "Yes")
    print("  Selected ARD = Yes")
    time.sleep(1)

    # ARD Date
    if fill_date(page, "ardDate", "02/15/2026"):
        print("  Filled ARD Date = 02/15/2026")

    # Next ARD Date
    if fill_date(page, "nextARDDate", "08/15/2026"):
        print("  Filled Next ARD Date = 08/15/2026")

    # On Grade Level = Yes
    select_option(page, "onGradeLevel", "Yes")
    print("  Selected On Grade Level = Yes")

    # Scroll to show full form before save
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)

    click_save(page)
    time.sleep(2)

    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2)
    page.screenshot(path=os.path.join(video_dir, "education_edit_result.png"))

    page.close()
    ctx.close()
    save_video(raw_dir, "01_education_edit.mp4", video_dir)


def record_grade_achieved(browser, base_url, client_id, video_dir):
    """VIDEO 2: Grade Achieved — Add a grade record."""
    print("\n=== Recording: Grade Achieved ===")
    ctx, raw_dir = new_recording_context(browser, "grade_achieved", video_dir)
    page = ctx.new_page()

    login(page, base_url)

    page.goto(f"{base_url}/client/face_sheet/{client_id}/grade_achieved")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    print("  On grade achieved page")

    add_btn = page.locator("button:has-text('Add')")
    if add_btn.count() > 0:
        add_btn.first.click()
        time.sleep(2)
        print("  Opened Add dialog")

    select_option(page, "gradeAchievedTypeId", "Grade 5")
    print("  Selected Grade = Grade 5")

    if fill_date(page, "dateLastAttended", "01/15/2026"):
        print("  Filled Date Last Attended = 01/15/2026")

    if fill_date(page, "dateAchieved", "06/15/2025"):
        print("  Filled Date Achieved = 06/15/2025")

    time.sleep(1)
    page.screenshot(path=os.path.join(video_dir, "grade_achieved_filled.png"))

    click_save(page, in_dialog=True)
    time.sleep(3)

    # Wait for dialog to close and table to refresh
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    # Scroll to top to show the full table with "Highest Grade Achieved" value
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)

    # Highlight the table to show saved data clearly
    page.screenshot(
        path=os.path.join(video_dir, "grade_achieved_table.png"), full_page=True
    )
    print("  Captured table with Highest Grade Achieved value")

    # Slow scroll down so the video shows the full table
    page.evaluate("window.scrollTo(0, 300)")
    time.sleep(2)
    page.screenshot(path=os.path.join(video_dir, "grade_achieved_result.png"))

    page.close()
    ctx.close()
    save_video(raw_dir, "02_grade_achieved.mp4", video_dir)


def record_ged_test(browser, base_url, client_id, video_dir):
    """VIDEO 3: GED Test — Add a test score."""
    print("\n=== Recording: GED Test ===")
    ctx, raw_dir = new_recording_context(browser, "ged_test", video_dir)
    page = ctx.new_page()

    login(page, base_url)

    page.goto(f"{base_url}/client/face_sheet/{client_id}/ged_test")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    print("  On GED test page")

    add_btn = page.locator("button:has-text('Add')")
    if add_btn.count() > 0:
        add_btn.first.click()
        time.sleep(2)
        print("  Opened Add dialog")

    select_option(page, "gedTestSubjectTypeId", "Science")
    print("  Selected Subject = Science")

    if fill_date(page, "testDate", "01/20/2026"):
        print("  Filled Test Date = 01/20/2026")

    score_input = page.locator("input[name='score']")
    if score_input.count() > 0:
        score_input.click()
        score_input.fill("172")
        time.sleep(0.5)
        print("  Filled Score = 172")

    time.sleep(1)
    page.screenshot(path=os.path.join(video_dir, "ged_test_filled.png"))

    click_save(page, in_dialog=True)
    time.sleep(2)
    page.screenshot(path=os.path.join(video_dir, "ged_test_result.png"))

    page.close()
    ctx.close()
    save_video(raw_dir, "03_ged_test.mp4", video_dir)


def record_enrollment(browser, base_url, client_id, video_dir):
    """VIDEO 4: Enrollment — Add a school enrollment record."""
    print("\n=== Recording: Enrollment ===")
    ctx, raw_dir = new_recording_context(browser, "enrollment", video_dir)
    page = ctx.new_page()

    login(page, base_url)

    page.goto(f"{base_url}/client/face_sheet/{client_id}/enrollment")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    print("  On enrollment page")

    add_btn = page.locator("button:has-text('Add')")
    if add_btn.count() > 0:
        add_btn.first.click()
        time.sleep(2)
        print("  Opened Add dialog")

    school_input = page.locator("input[name='schoolName']")
    if school_input.count() > 0:
        school_input.fill("Lincoln High School")
        time.sleep(0.5)
        print("  Filled School Name = Lincoln High School")

    isd_input = page.locator("input[name='isd']")
    if isd_input.count() > 0:
        isd_input.fill("Austin ISD")
        time.sleep(0.5)
        print("  Filled ISD = Austin ISD")

    if fill_date(page, "enrollmentDate", "08/20/2025"):
        print("  Filled Enrollment Date = 08/20/2025")

    if fill_date(page, "endDate", "05/30/2026"):
        print("  Filled End Date = 05/30/2026")

    credits_input = page.locator("input[name='creditsCompleted']")
    if credits_input.count() > 0:
        credits_input.fill("24")
        time.sleep(0.3)
        print("  Filled Credits Completed = 24")

    remaining_input = page.locator("input[name='remainingCredits']")
    if remaining_input.count() > 0:
        remaining_input.fill("6")
        time.sleep(0.3)
        print("  Filled Remaining Credits = 6")

    gpa_input = page.locator("input[name='gpa']")
    if gpa_input.count() > 0:
        gpa_input.fill("3.75")
        time.sleep(0.3)
        print("  Filled GPA = 3.75")

    # Scroll dialog to show all fields
    dialog_content = page.locator("[role='dialog'] .MuiDialogContent-root")
    if dialog_content.count() > 0:
        dialog_content.evaluate("el => el.scrollTop = el.scrollHeight")
        time.sleep(1)

    time.sleep(1)
    page.screenshot(path=os.path.join(video_dir, "enrollment_filled.png"))

    click_save(page, in_dialog=True)
    time.sleep(2)
    page.screenshot(path=os.path.join(video_dir, "enrollment_result.png"))

    page.close()
    ctx.close()
    save_video(raw_dir, "04_enrollment.mp4", video_dir)


def record_report_card(browser, base_url, client_id, video_dir):
    """VIDEO 5: Report Card — Add a report card entry."""
    print("\n=== Recording: Report Card ===")
    ctx, raw_dir = new_recording_context(browser, "report_card", video_dir)
    page = ctx.new_page()

    login(page, base_url)

    page.goto(f"{base_url}/client/face_sheet/{client_id}/report_card")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    print("  On report card page")

    add_btn = page.locator("button:has-text('Add')")
    if add_btn.count() > 0:
        add_btn.first.click()
        time.sleep(2)
        print("  Opened Add dialog")

    textarea = page.locator("textarea[name='reportCard']")
    if textarea.count() == 0:
        textarea = page.locator("[role='dialog'] textarea")
    if textarea.count() > 0:
        textarea.first.fill(
            "Student shows consistent improvement in math and reading comprehension. "
            "Participates actively in class discussions. "
            "Recommended for advanced placement in science."
        )
        time.sleep(0.5)
        print("  Filled Report Card text")

    if fill_date(page, "dateSubmitted", "02/28/2026"):
        print("  Filled Date Submitted = 02/28/2026")

    if fill_date(page, "nextDueDate", "05/30/2026"):
        print("  Filled Next Due Date = 05/30/2026")

    time.sleep(1)
    page.screenshot(path=os.path.join(video_dir, "report_card_filled.png"))

    click_save(page, in_dialog=True)
    time.sleep(2)
    page.screenshot(path=os.path.join(video_dir, "report_card_result.png"))

    page.close()
    ctx.close()
    save_video(raw_dir, "05_report_card.mp4", video_dir)


# -- Main --------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Run Playwright E2E tests for TFI One Education module with video recording."
    )
    parser.add_argument(
        "--base-url",
        default="https://localhost:5173",
        help="Frontend base URL (default: https://localhost:5173)",
    )
    parser.add_argument(
        "--client-id",
        default="10000000-0000-0000-0000-000000000001",
        help="Client UUID to test against (default: test client)",
    )
    parser.add_argument(
        "--output-dir",
        default="./education_e2e_videos",
        help="Directory for video/screenshot output (default: ./education_e2e_videos)",
    )
    args = parser.parse_args()

    video_dir = os.path.abspath(args.output_dir)
    os.makedirs(video_dir, exist_ok=True)

    print("=" * 60)
    print("Education Module — Frontend Data Entry Video Proof")
    print(f"  Base URL:   {args.base_url}")
    print(f"  Client ID:  {args.client_id}")
    print(f"  Output Dir: {video_dir}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        record_education_edit(browser, args.base_url, args.client_id, video_dir)
        record_grade_achieved(browser, args.base_url, args.client_id, video_dir)
        record_ged_test(browser, args.base_url, args.client_id, video_dir)
        record_enrollment(browser, args.base_url, args.client_id, video_dir)
        record_report_card(browser, args.base_url, args.client_id, video_dir)

        browser.close()

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS:")
    videos = 0
    screenshots = 0
    for f in sorted(os.listdir(video_dir)):
        fpath = os.path.join(video_dir, f)
        if not os.path.isfile(fpath):
            continue
        size = os.path.getsize(fpath)
        if f.endswith(".mp4"):
            print(f"  {f} ({size / 1024:.0f} KB)")
            videos += 1
        elif f.endswith(".png"):
            print(f"  {f} ({size / 1024:.0f} KB)")
            screenshots += 1
    print(f"\nTotal: {videos} videos, {screenshots} screenshots")
    print("=" * 60)

    return 0 if videos == 5 else 1


if __name__ == "__main__":
    sys.exit(main())
