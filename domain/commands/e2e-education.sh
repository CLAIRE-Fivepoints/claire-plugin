#!/usr/bin/env bash
# Run Playwright E2E tests for TFI One Education module with video recording.
#
# Usage: claire fivepoints e2e-education [--base-url URL] [--client-id UUID] [--output-dir DIR]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/../scripts/education_e2e.py"

# -- Help --------------------------------------------------------------------

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Usage: claire fivepoints e2e-education [OPTIONS]

Run Playwright E2E tests for all 5 Education sub-modules with video recording.

Options:
  --base-url URL     Frontend base URL (default: https://localhost:5173)
  --client-id UUID   Client UUID to test against (default: test client)
  --output-dir DIR   Directory for video/screenshot output (default: ./education_e2e_videos)
  -h, --help         Show this help message

Sub-modules tested:
  1. Education Edit   - IEP, 504 Plan, ARD, On Grade Level
  2. Grade Achieved   - Add grade record
  3. GED Test         - Add GED test score
  4. Enrollment       - Add school enrollment
  5. Report Card      - Add report card entry

Prerequisites:
  - python3 with playwright installed (pip install playwright)
  - Playwright browsers installed (playwright install chromium)
  - TFI One frontend running on the base URL (default: port 5173)
  - TFI One backend running (default: port 58337)

Output:
  5 .webm video files + screenshots in the output directory
EOF
    exit 0
fi

# -- Prerequisites -----------------------------------------------------------

echo "Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.8+ first."
    exit 1
fi

if ! python3 -c "import playwright" 2>/dev/null; then
    echo "ERROR: playwright not installed. Run: pip install playwright && playwright install chromium"
    exit 1
fi

# -- Check servers -----------------------------------------------------------

check_port() {
    local port="$1"
    local name="$2"
    if lsof -i ":${port}" -sTCP:LISTEN &>/dev/null; then
        echo "  OK: ${name} (port ${port})"
    else
        echo "  WARNING: ${name} not detected on port ${port}"
        echo "           Tests may fail if the server is not running."
    fi
}

echo "Checking servers..."
check_port 5173 "Frontend (Vite)"
check_port 58337 "Backend (.NET API)"

# -- Run tests ---------------------------------------------------------------

echo ""
echo "Starting Education E2E tests..."
echo ""

python3 "${PYTHON_SCRIPT}" "$@"
exit_code=$?

if [[ $exit_code -eq 0 ]]; then
    echo ""
    echo "All 5 Education sub-modules tested successfully."
else
    echo ""
    echo "WARNING: Some tests may have failed (exit code: ${exit_code})."
fi

exit $exit_code
