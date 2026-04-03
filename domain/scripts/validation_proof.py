#!/usr/bin/env python3
"""
Validation proof for TFI One Education module.

Records dual proof per module — one video with two parts:
  Part A: Frontend UI validation errors (empty / invalid submit → MUI error visible)
  Part B: Swagger API HTTP 400 (same rule enforced at the API level)

Output (one video per module):
  01_education_validation.webm
  02_grade_validation.webm
  03_ged_validation.webm
  04_enrollment_validation.webm
  05_report_card_validation.webm

Usage:
  python3 validation_proof.py [OPTIONS]

Options:
  --base-url URL     Frontend base URL (default: https://localhost:5173)
  --api-url URL      Backend API URL (default: https://localhost:58337)
  --client-id UUID   Client UUID (default: test client)
  --output-dir DIR   Output directory (default: ./validation_proof_videos)
  --module MODULE    Module to run: education|grade|ged|enrollment|report-card|all
"""

import argparse
import json
import os
import shutil
import ssl
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Swagger UI v3 selectors
# ---------------------------------------------------------------------------

SWAGGER_AUTH_BTN = ".auth-wrapper button.btn.authorize"
SWAGGER_AUTH_INPUT = ".modal-ux input[type='text']"
SWAGGER_AUTHORIZE_BTN = ".modal-ux .auth-btn-wrapper button.btn.authorize"
SWAGGER_CLOSE_BTN = ".modal-ux .auth-btn-wrapper button.btn-done"
SWAGGER_TRY_BTN = "button.btn.try-out__btn"
SWAGGER_BODY_AREA = "textarea.body-param__text"
SWAGGER_EXECUTE_BTN = "button.btn.execute.opblock-control__btn"
SWAGGER_RESP_STATUS = ".live-responses-table td.response-col_status"
SWAGGER_RESP_BODY = ".live-responses-table .microlight"


def swagger_opblock(path):
    """Return the selector for a Swagger POST opblock containing a path span."""
    return f".opblock.opblock-post:has(span[data-path='{path}'])"


# ---------------------------------------------------------------------------
# Login helpers (shared with education_e2e.py)
# ---------------------------------------------------------------------------


def login(page, base_url):
    """Login via the TFI One frontend (Non TFI Employees flow)."""
    page.goto(f"{base_url}/login")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    non_tfi = page.get_by_text("Non TFI Employees", exact=False)
    if non_tfi.is_visible():
        non_tfi.click()
        time.sleep(1)

    page.locator("input[name='userName']").fill("prime.user")
    time.sleep(0.5)
    page.locator("input[name='password']").fill("Test1234!")
    time.sleep(0.5)

    page.get_by_role("button", name="Login", exact=True).click()
    time.sleep(5)

    try:
        page.wait_for_selector("input[name='userName']", state="hidden", timeout=10000)
    except Exception:
        pass
    time.sleep(2)
    print(f"  Login complete — URL: {page.url}")


def login_and_get_token(page, base_url):
    """Login and capture the JWT bearer token from network responses or localStorage."""
    token_holder = {"value": None}

    def on_response(response):
        if token_holder["value"]:
            return
        try:
            ct = response.headers.get("content-type", "")
            if response.status == 200 and "application/json" in ct:
                data = response.json()
                if isinstance(data, dict):
                    for key in (
                        "token",
                        "accessToken",
                        "access_token",
                        "jwt",
                        "bearerToken",
                    ):
                        if (
                            key in data
                            and isinstance(data[key], str)
                            and len(data[key]) > 20
                        ):
                            token_holder["value"] = data[key]
                            print(f"  Captured JWT from response key '{key}'")
                            return
        except Exception:
            pass

    page.on("response", on_response)
    login(page, base_url)
    page.remove_listener("response", on_response)

    # Fallback: search localStorage for a token-like value
    if not token_holder["value"]:
        try:
            entries = page.evaluate("""() => {
                return Object.keys(localStorage)
                    .map(k => ({ key: k, value: localStorage.getItem(k) }))
            }""")
            for entry in entries:
                k = entry.get("key", "").lower()
                v = entry.get("value", "") or ""
                if ("token" in k or "jwt" in k or "auth" in k) and len(v) > 40:
                    token_holder["value"] = v
                    print(f"  Captured JWT from localStorage key '{entry['key']}'")
                    break
        except Exception:
            pass

    if not token_holder["value"]:
        print("  WARNING: Could not capture JWT token — Swagger authorization may fail")

    return token_holder["value"]


def select_option(page, field_id, option_text, wait=1.0):
    """Click a MUI Select and pick an option by text."""
    page.locator(f"#{field_id}").click(force=True)
    option = page.locator(f"[role='option']:has-text('{option_text}')")
    option.wait_for(state="visible", timeout=15000)
    option.click()
    time.sleep(wait)


def fill_date(page, field_name, date_str):
    """Fill a MUI v6 DatePicker using spinbutton sections."""
    inp = page.locator(f"input[name='{field_name}']")
    if inp.count() == 0:
        print(f"  WARNING: date input '{field_name}' not found")
        return False

    container = page.locator(
        f"input[name='{field_name}'] >> xpath=../div[contains(@class, 'MuiPickersSectionList')]"
    )
    if container.count() == 0:
        container = page.locator(
            f"input[name='{field_name}'] >> xpath=../div//span[@aria-label='Month']"
        )
    if container.count() > 0:
        container.first.click()
        time.sleep(0.3)
    else:
        inp.click(force=True)
        time.sleep(0.3)

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
    """Click the Save button."""
    if in_dialog:
        save_btn = page.locator("[role='dialog'] button:has-text('Save')")
        if save_btn.count() == 0:
            save_btn = page.locator("button:has-text('Save')")
    else:
        save_btn = page.locator("button:has-text('Save')")
    if save_btn.count() > 0:
        save_btn.first.click()
        print("  Clicked Save")
        time.sleep(2)
        return True
    print("  WARNING: Save button not found")
    return False


def wait_for_validation_error(page, timeout=8000):
    """Wait for a MUI validation error to become visible. Returns True if found."""
    try:
        page.wait_for_selector(
            ".MuiFormHelperText-root.Mui-error", state="visible", timeout=timeout
        )
        print("  Validation error appeared")
        return True
    except Exception:
        print("  WARNING: No validation error selector found within timeout")
        return False


# ---------------------------------------------------------------------------
# Video helpers
# ---------------------------------------------------------------------------


def new_recording_context(browser, subdir, video_dir):
    """Create a browser context with video recording enabled."""
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
    """Move the recorded .webm to its final location."""
    if os.path.exists(raw_dir):
        for f in os.listdir(raw_dir):
            if f.endswith(".webm"):
                src = os.path.join(raw_dir, f)
                dst = os.path.join(video_dir, output_name)
                shutil.move(src, dst)
                size = os.path.getsize(dst)
                print(f"  Saved: {output_name} ({size / 1024:.0f} KB)")
                break
        shutil.rmtree(raw_dir, ignore_errors=True)


def screenshot(page, video_dir, name):
    """Take a screenshot to the output directory."""
    path = os.path.join(video_dir, name)
    page.screenshot(path=path)
    print(f"  Screenshot: {name}")
    return path


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def fetch_yes_guid(api_url, token):
    """Fetch the GUID for 'Yes' from the YesNoUnknownType reference endpoint."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            f"{api_url}/reference/YesNoUnknownType",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read())
            for item in data:
                name = item.get("name", item.get("label", "")).lower()
                if name in ("yes", "y"):
                    yes_id = item.get("id", item.get("value"))
                    print(f"  Yes GUID: {yes_id}")
                    return yes_id
    except Exception as e:
        print(f"  WARNING: Could not fetch Yes GUID: {e}")
    return None


# ---------------------------------------------------------------------------
# Swagger helpers
# ---------------------------------------------------------------------------


def swagger_authorize(page, swagger_url, token):
    """Open Swagger UI and authorize with the bearer token."""
    print("  [Swagger] Navigating to Swagger UI…")
    page.goto(swagger_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    # Wait for Swagger to render
    try:
        page.wait_for_selector(SWAGGER_AUTH_BTN, state="visible", timeout=15000)
    except Exception:
        print("  WARNING: Swagger auth button not found — page may not have loaded")
        return False

    # Click Authorize
    page.locator(SWAGGER_AUTH_BTN).first.click()
    time.sleep(1.5)

    # Fill Bearer token
    auth_input = page.locator(SWAGGER_AUTH_INPUT)
    if auth_input.count() == 0:
        print("  WARNING: Swagger auth input not found")
        return False
    auth_input.first.fill(f"Bearer {token}")
    time.sleep(0.5)

    # Click Authorize button inside modal
    page.locator(SWAGGER_AUTHORIZE_BTN).first.click()
    time.sleep(1)

    # Close modal
    close_btn = page.locator(SWAGGER_CLOSE_BTN)
    if close_btn.count() > 0:
        close_btn.first.click()
        time.sleep(0.5)
    else:
        # Fallback: close with Escape
        page.keyboard.press("Escape")
        time.sleep(0.5)

    print("  [Swagger] Authorized")
    return True


def swagger_test_endpoint(
    page, swagger_url, api_path, payload, video_dir, screenshot_name, client_id=None
):
    """
    Find a POST endpoint in Swagger, submit an invalid payload, and screenshot the 400 response.

    Args:
        page:            Playwright page (already on Swagger UI and authorized).
        swagger_url:     Swagger base URL (for reference only, page already navigated).
        api_path:        The API path as shown in Swagger (e.g. '/client/{clientId}/education').
        payload:         Dict — the invalid request body to submit.
        video_dir:       Output directory for screenshots.
        screenshot_name: Filename for the response screenshot.
        client_id:       UUID to fill into the clientId path parameter (if present).

    Returns:
        True if a response was received (even non-400), False on failure.
    """
    # Find and expand the endpoint
    opblock_sel = swagger_opblock(api_path)
    opblock = page.locator(opblock_sel)

    if opblock.count() == 0:
        print(f"  ERROR: Cannot find POST endpoint '{api_path}' in Swagger")
        screenshot(page, video_dir, screenshot_name)
        return False

    opblock.first.click()
    time.sleep(1)

    # Click "Try it out" — scoped to this opblock to avoid hitting another
    try_btn = opblock.first.locator(SWAGGER_TRY_BTN)
    if try_btn.count() == 0:
        print("  WARNING: 'Try it out' button not found")
        return False
    try_btn.first.click()
    time.sleep(1)

    # Fill path parameters (e.g. clientId)
    if client_id:
        param_input = opblock.first.locator("input[placeholder='clientId']")
        if param_input.count() > 0:
            param_input.first.fill(client_id)
            print(f"  [Swagger] Filled clientId = {client_id}")
            time.sleep(0.3)

    # Replace the request body textarea
    body_area = opblock.first.locator(SWAGGER_BODY_AREA)
    if body_area.count() == 0:
        print("  WARNING: Request body textarea not found")
        return False
    body_area.first.click()
    body_area.first.fill(json.dumps(payload, indent=2))
    time.sleep(0.5)

    # Execute
    opblock.first.locator(SWAGGER_EXECUTE_BTN).first.click()
    print("  [Swagger] Executing request…")
    time.sleep(4)

    # Wait for response table
    try:
        page.wait_for_selector(SWAGGER_RESP_STATUS, state="visible", timeout=15000)
    except Exception:
        print("  WARNING: Swagger response table did not appear")
        screenshot(page, video_dir, screenshot_name)
        return False

    # Scroll to show response
    resp_el = page.locator(SWAGGER_RESP_STATUS)
    if resp_el.count() > 0:
        resp_el.first.scroll_into_view_if_needed()
        time.sleep(0.5)
        status_text = resp_el.first.inner_text()
        print(f"  [Swagger] Response status: {status_text}")

    screenshot(page, video_dir, screenshot_name)
    return True


# ---------------------------------------------------------------------------
# Module recorders
# ---------------------------------------------------------------------------


def record_education_validation(
    browser, base_url, swagger_url, client_id, video_dir, yes_guid
):
    """
    VIDEO 1: Education Edit validation proof.
    Frontend: set IEP=Yes, save without IEP Date → error.
    Swagger: POST /client/{id}/education with iepDate=null → 400.
    """
    print("\n=== Recording: Education Edit Validation ===")
    ctx, raw_dir = new_recording_context(browser, "education_validation", video_dir)
    page = ctx.new_page()

    token = login_and_get_token(page, base_url)

    # --- Part A: Frontend ---
    print("  [Part A] Frontend validation")
    page.goto(f"{base_url}/client/face_sheet/{client_id}/education")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    # Confirm form loaded — wait for at least one FormHelperText in DOM
    try:
        page.wait_for_selector(
            ".MuiFormHelperText-root", state="attached", timeout=10000
        )
    except Exception:
        pass

    # Trigger validation: set IEP = Yes (makes IEP Date required), then save
    try:
        select_option(page, "iepId", "Yes")
        print("  Selected IEP = Yes")
    except Exception as e:
        print(f"  WARNING: Could not set IEP = Yes: {e}")

    # Clear IEP Date if pre-filled
    iep_date_inp = page.locator("input[name='iepDate']")
    if iep_date_inp.count() > 0:
        iep_date_inp.click(force=True)
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        time.sleep(0.3)

    click_save(page)
    found_error = wait_for_validation_error(page)
    if found_error:
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)
    screenshot(page, video_dir, "01a_education_frontend_error.png")

    # Fill valid data and save to show success
    try:
        fill_date(page, "iepDate", "03/01/2026")
        fill_date(page, "nextIEPDate", "09/01/2026")
        click_save(page)
        time.sleep(3)
        screenshot(page, video_dir, "01b_education_frontend_success.png")
    except Exception as e:
        print(f"  WARNING: Success flow failed: {e}")

    # --- Part B: Swagger ---
    if token:
        print("  [Part B] Swagger API validation")
        swagger_authorize(page, swagger_url, token)

        api_path = "/client/{clientId}/education"
        invalid_payload = {
            "iepId": yes_guid or "00000000-0000-0000-0000-000000000001",
            "iepDate": None,
        }
        swagger_test_endpoint(
            page,
            swagger_url,
            api_path,
            invalid_payload,
            video_dir,
            "01c_education_swagger_400.png",
            client_id=client_id,
        )
    else:
        print("  SKIP [Part B]: No token available")

    page.close()
    ctx.close()
    save_video(raw_dir, "01_education_validation.webm", video_dir)


def record_grade_validation(browser, base_url, swagger_url, client_id, video_dir):
    """
    VIDEO 2: Grade Achieved validation proof.
    Frontend: open Add dialog, save empty → error on gradeAchievedTypeId.
    Swagger: POST /client/{id}/education/grade-achieved with gradeAchievedTypeId=null → 400.
    """
    print("\n=== Recording: Grade Achieved Validation ===")
    ctx, raw_dir = new_recording_context(browser, "grade_validation", video_dir)
    page = ctx.new_page()

    token = login_and_get_token(page, base_url)

    # --- Part A: Frontend ---
    print("  [Part A] Frontend validation")
    page.goto(f"{base_url}/client/face_sheet/{client_id}/grade_achieved")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    add_btn = page.locator("button:has-text('Add')")
    if add_btn.count() > 0:
        add_btn.first.click()
        time.sleep(2)
        print("  Opened Add dialog")
    else:
        print("  WARNING: Add button not found")

    # Wait for dialog form to be in DOM
    try:
        page.wait_for_selector("[role='dialog']", state="visible", timeout=8000)
    except Exception:
        pass

    # Submit empty
    click_save(page, in_dialog=True)
    found_error = wait_for_validation_error(page)
    if found_error:
        time.sleep(0.5)
    screenshot(page, video_dir, "02a_grade_frontend_error.png")

    # Fill valid data and save
    try:
        select_option(page, "gradeAchievedTypeId", "Grade 5")
        fill_date(page, "dateLastAttended", "01/15/2026")
        fill_date(page, "dateAchieved", "06/15/2025")
        click_save(page, in_dialog=True)
        time.sleep(3)
        screenshot(page, video_dir, "02b_grade_frontend_success.png")
    except Exception as e:
        print(f"  WARNING: Success flow failed: {e}")

    # --- Part B: Swagger ---
    if token:
        print("  [Part B] Swagger API validation")
        swagger_authorize(page, swagger_url, token)

        api_path = "/client/{clientId}/education/grade-achieved"
        invalid_payload = {"gradeAchievedTypeId": None}
        swagger_test_endpoint(
            page,
            swagger_url,
            api_path,
            invalid_payload,
            video_dir,
            "02c_grade_swagger_400.png",
            client_id=client_id,
        )
    else:
        print("  SKIP [Part B]: No token available")

    page.close()
    ctx.close()
    save_video(raw_dir, "02_grade_validation.webm", video_dir)


def record_ged_validation(browser, base_url, swagger_url, client_id, video_dir):
    """
    VIDEO 3: GED Test validation proof.
    Frontend: open Add dialog, save empty → error on testDate.
    Swagger: POST /client/{id}/education/ged-test with testDate=null → 400.
    """
    print("\n=== Recording: GED Test Validation ===")
    ctx, raw_dir = new_recording_context(browser, "ged_validation", video_dir)
    page = ctx.new_page()

    token = login_and_get_token(page, base_url)

    # --- Part A: Frontend ---
    print("  [Part A] Frontend validation")
    page.goto(f"{base_url}/client/face_sheet/{client_id}/ged_test")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    add_btn = page.locator("button:has-text('Add')")
    if add_btn.count() > 0:
        add_btn.first.click()
        time.sleep(2)
        print("  Opened Add dialog")

    try:
        page.wait_for_selector("[role='dialog']", state="visible", timeout=8000)
    except Exception:
        pass

    # Submit empty to trigger testDate required error
    click_save(page, in_dialog=True)
    found_error = wait_for_validation_error(page)
    if found_error:
        time.sleep(0.5)
    screenshot(page, video_dir, "03a_ged_frontend_error.png")

    # Fill valid data
    try:
        select_option(page, "gedTestSubjectTypeId", "Science")
        fill_date(page, "testDate", "01/20/2026")
        score_input = page.locator("input[name='score']")
        if score_input.count() > 0:
            score_input.fill("172")
        click_save(page, in_dialog=True)
        time.sleep(3)
        screenshot(page, video_dir, "03b_ged_frontend_success.png")
    except Exception as e:
        print(f"  WARNING: Success flow failed: {e}")

    # --- Part B: Swagger ---
    if token:
        print("  [Part B] Swagger API validation")
        swagger_authorize(page, swagger_url, token)

        api_path = "/client/{clientId}/education/ged-test"
        invalid_payload = {"testDate": None}
        swagger_test_endpoint(
            page,
            swagger_url,
            api_path,
            invalid_payload,
            video_dir,
            "03c_ged_swagger_400.png",
            client_id=client_id,
        )
    else:
        print("  SKIP [Part B]: No token available")

    page.close()
    ctx.close()
    save_video(raw_dir, "03_ged_validation.webm", video_dir)


def record_enrollment_validation(browser, base_url, swagger_url, client_id, video_dir):
    """
    VIDEO 4: Enrollment validation proof.
    Frontend: open Add dialog, submit with gpa=5.0 (out of range) → error.
    Swagger: POST /client/{id}/education/enrollment with gpa=5.0 → 400.
    """
    print("\n=== Recording: Enrollment Validation ===")
    ctx, raw_dir = new_recording_context(browser, "enrollment_validation", video_dir)
    page = ctx.new_page()

    token = login_and_get_token(page, base_url)

    # --- Part A: Frontend ---
    print("  [Part A] Frontend validation")
    page.goto(f"{base_url}/client/face_sheet/{client_id}/enrollment")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    add_btn = page.locator("button:has-text('Add')")
    if add_btn.count() > 0:
        add_btn.first.click()
        time.sleep(2)
        print("  Opened Add dialog")

    try:
        page.wait_for_selector("[role='dialog']", state="visible", timeout=8000)
    except Exception:
        pass

    # Step 1: Submit empty → required fields error
    click_save(page, in_dialog=True)
    found_error = wait_for_validation_error(page)
    if found_error:
        time.sleep(0.5)
    screenshot(page, video_dir, "04a_enrollment_frontend_empty_error.png")

    # Step 2: Fill required fields but with invalid GPA
    try:
        school_input = page.locator("input[name='schoolName']")
        if school_input.count() > 0:
            school_input.fill("X")
        gpa_input = page.locator("input[name='gpa']")
        if gpa_input.count() > 0:
            gpa_input.fill("5.0")
            gpa_input.press("Tab")
            time.sleep(0.5)
        click_save(page, in_dialog=True)
        time.sleep(1)
        found_range_error = wait_for_validation_error(page, timeout=5000)
        if found_range_error:
            time.sleep(0.5)
        screenshot(page, video_dir, "04b_enrollment_frontend_gpa_error.png")
    except Exception as e:
        print(f"  WARNING: GPA error flow failed: {e}")

    # Fill valid data and save
    try:
        school_input = page.locator("input[name='schoolName']")
        if school_input.count() > 0:
            school_input.fill("Lincoln High School")
        isd_input = page.locator("input[name='isd']")
        if isd_input.count() > 0:
            isd_input.fill("Austin ISD")
        fill_date(page, "enrollmentDate", "08/20/2025")
        fill_date(page, "endDate", "05/30/2026")
        gpa_input = page.locator("input[name='gpa']")
        if gpa_input.count() > 0:
            gpa_input.fill("3.75")
        click_save(page, in_dialog=True)
        time.sleep(3)
        screenshot(page, video_dir, "04c_enrollment_frontend_success.png")
    except Exception as e:
        print(f"  WARNING: Success flow failed: {e}")

    # --- Part B: Swagger ---
    if token:
        print("  [Part B] Swagger API validation")
        swagger_authorize(page, swagger_url, token)

        api_path = "/client/{clientId}/education/enrollment"
        invalid_payload = {"schoolName": "X", "gpa": 5.0}
        swagger_test_endpoint(
            page,
            swagger_url,
            api_path,
            invalid_payload,
            video_dir,
            "04d_enrollment_swagger_400.png",
            client_id=client_id,
        )
    else:
        print("  SKIP [Part B]: No token available")

    page.close()
    ctx.close()
    save_video(raw_dir, "04_enrollment_validation.webm", video_dir)


def record_report_card_validation(browser, base_url, swagger_url, client_id, video_dir):
    """
    VIDEO 5: Report Card validation proof.
    Frontend: open Add dialog, save with empty reportCard text → error.
    Swagger: POST /client/{id}/education/report-card with reportCard='' → 400.
    """
    print("\n=== Recording: Report Card Validation ===")
    ctx, raw_dir = new_recording_context(browser, "report_card_validation", video_dir)
    page = ctx.new_page()

    token = login_and_get_token(page, base_url)

    # --- Part A: Frontend ---
    print("  [Part A] Frontend validation")
    page.goto(f"{base_url}/client/face_sheet/{client_id}/report_card")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    add_btn = page.locator("button:has-text('Add')")
    if add_btn.count() > 0:
        add_btn.first.click()
        time.sleep(2)
        print("  Opened Add dialog")

    try:
        page.wait_for_selector("[role='dialog']", state="visible", timeout=8000)
    except Exception:
        pass

    # Submit empty to trigger reportCard required error
    click_save(page, in_dialog=True)
    found_error = wait_for_validation_error(page)
    if found_error:
        time.sleep(0.5)
    screenshot(page, video_dir, "05a_report_card_frontend_error.png")

    # Fill valid data and save
    try:
        textarea = page.locator("textarea[name='reportCard']")
        if textarea.count() == 0:
            textarea = page.locator("[role='dialog'] textarea")
        if textarea.count() > 0:
            textarea.first.fill(
                "Student shows consistent improvement in math and reading. "
                "Recommended for advanced placement in science."
            )
        fill_date(page, "dateSubmitted", "02/28/2026")
        fill_date(page, "nextDueDate", "05/30/2026")
        click_save(page, in_dialog=True)
        time.sleep(3)
        screenshot(page, video_dir, "05b_report_card_frontend_success.png")
    except Exception as e:
        print(f"  WARNING: Success flow failed: {e}")

    # --- Part B: Swagger ---
    if token:
        print("  [Part B] Swagger API validation")
        swagger_authorize(page, swagger_url, token)

        api_path = "/client/{clientId}/education/report-card"
        invalid_payload = {"reportCard": ""}
        swagger_test_endpoint(
            page,
            swagger_url,
            api_path,
            invalid_payload,
            video_dir,
            "05c_report_card_swagger_400.png",
            client_id=client_id,
        )
    else:
        print("  SKIP [Part B]: No token available")

    page.close()
    ctx.close()
    save_video(raw_dir, "05_report_card_validation.webm", video_dir)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

MODULES = {
    "education": record_education_validation,
    "grade": record_grade_validation,
    "ged": record_ged_validation,
    "enrollment": record_enrollment_validation,
    "report-card": record_report_card_validation,
}


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Record dual validation proof for TFI One Education sub-modules: "
            "frontend UI errors + Swagger API HTTP 400 responses."
        )
    )
    parser.add_argument(
        "--base-url",
        default="https://localhost:5173",
        help="Frontend base URL (default: https://localhost:5173)",
    )
    parser.add_argument(
        "--api-url",
        default="https://localhost:58337",
        help="Backend API URL for Swagger (default: https://localhost:58337)",
    )
    parser.add_argument(
        "--client-id",
        default="10000000-0000-0000-0000-000000000001",
        help="Client UUID to test against (default: test client)",
    )
    parser.add_argument(
        "--output-dir",
        default="./validation_proof_videos",
        help="Output directory for videos and screenshots (default: ./validation_proof_videos)",
    )
    parser.add_argument(
        "--module",
        choices=["education", "grade", "ged", "enrollment", "report-card", "all"],
        default="all",
        help="Module to run (default: all)",
    )
    args = parser.parse_args()

    video_dir = os.path.abspath(args.output_dir)
    os.makedirs(video_dir, exist_ok=True)

    swagger_url = f"{args.api_url}/swagger/index.html"

    print("=" * 60)
    print("Education Module — Validation Proof (Frontend + Swagger)")
    print(f"  Frontend:   {args.base_url}")
    print(f"  API/Swagger:{args.api_url}")
    print(f"  Client ID:  {args.client_id}")
    print(f"  Module:     {args.module}")
    print(f"  Output Dir: {video_dir}")
    print("=" * 60)

    # Determine which modules to run
    if args.module == "all":
        modules_to_run = list(MODULES.keys())
    else:
        modules_to_run = [args.module]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Fetch Yes GUID once for Education Edit module (if needed)
        yes_guid = None
        if "education" in modules_to_run:
            # We need a token to fetch the reference data — do a quick login
            temp_ctx = browser.new_context(ignore_https_errors=True)
            temp_page = temp_ctx.new_page()
            token = login_and_get_token(temp_page, args.base_url)
            temp_page.close()
            temp_ctx.close()
            if token:
                yes_guid = fetch_yes_guid(args.api_url, token)

        for module_key in modules_to_run:
            fn = MODULES[module_key]
            try:
                if module_key == "education":
                    fn(
                        browser,
                        args.base_url,
                        swagger_url,
                        args.client_id,
                        video_dir,
                        yes_guid,
                    )
                else:
                    fn(browser, args.base_url, swagger_url, args.client_id, video_dir)
            except Exception as e:
                print(f"\nERROR in module '{module_key}': {e}")
                import traceback

                traceback.print_exc()

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
        if f.endswith(".webm"):
            print(f"  VIDEO: {f} ({size / 1024:.0f} KB)")
            videos += 1
        elif f.endswith(".png"):
            print(f"  SHOT:  {f} ({size / 1024:.0f} KB)")
            screenshots += 1
    expected = len(modules_to_run)
    print(f"\nTotal: {videos}/{expected} videos, {screenshots} screenshots")
    print("=" * 60)

    return 0 if videos == expected else 1


if __name__ == "__main__":
    sys.exit(main())
