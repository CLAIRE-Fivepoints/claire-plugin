"""
Shared helpers for TFI One Playwright E2E scripts.

Import in any E2E script:
    from tfi_helpers import login, get_bearer_token, TFI_BASE_URL, TFI_API_URL

Credentials are read from environment variables:
    TFI_USERNAME  (default: prime.user)
    TFI_PASSWORD  (default: Test1234!)
"""

import os
import time

import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# -- Defaults -----------------------------------------------------------------

TFI_BASE_URL = os.environ.get("TFI_BASE_URL", "https://localhost:5173")
TFI_API_URL = os.environ.get("TFI_API_URL", "https://localhost:58337")
TFI_USERNAME = os.environ.get("TFI_USERNAME", "prime.user")
TFI_PASSWORD = os.environ.get("TFI_PASSWORD", "Test1234!")


# -- Login --------------------------------------------------------------------


def login(page, base_url: str = TFI_BASE_URL) -> None:
    """Login to TFI One via the frontend (Non TFI Employees flow).

    Navigates to /login, clicks the non-TFI button, fills credentials,
    and waits for redirect away from /login.

    Args:
        page: Playwright Page instance.
        base_url: Frontend base URL (default: TFI_BASE_URL env var or https://localhost:5173).

    Raises:
        RuntimeError: If login redirect does not occur within 15 seconds.
    """
    page.goto(f"{base_url}/login")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    non_tfi = page.get_by_text("Non TFI Employees", exact=False)
    if non_tfi.is_visible():
        non_tfi.click()
        time.sleep(1)

    page.locator("input[name='userName']").fill(TFI_USERNAME)
    time.sleep(0.5)
    page.locator("input[name='password']").fill(TFI_PASSWORD)
    time.sleep(0.5)

    page.get_by_role("button", name="Login", exact=True).click()
    time.sleep(5)

    try:
        page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
    except Exception as err:
        raise RuntimeError(
            f"Login failed — still on {page.url}. "
            f"Credentials: TFI_USERNAME={TFI_USERNAME!r} (override with env vars)"
        ) from err

    time.sleep(2)
    print(f"  Login complete — URL: {page.url}")


# -- Bearer token (API calls) -------------------------------------------------


def get_bearer_token(api_url: str = TFI_API_URL) -> str:
    """Obtain a Bearer token from the TFI One API for Swagger verification.

    Uses the /api/Auth/login endpoint with the configured credentials.

    Args:
        api_url: Backend API base URL (default: TFI_API_URL env var).

    Returns:
        Bearer token string.

    Raises:
        RuntimeError: If authentication fails.
    """
    response = requests.post(
        f"{api_url}/api/Auth/login",
        json={"userName": TFI_USERNAME, "password": TFI_PASSWORD},
        verify=False,
        timeout=15,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Auth failed: HTTP {response.status_code} — {response.text[:200]}"
        )
    data = response.json()
    token = data.get("token") or data.get("accessToken") or data.get("access_token")
    if not token:
        raise RuntimeError(f"No token in auth response: {list(data.keys())}")
    return str(token)
