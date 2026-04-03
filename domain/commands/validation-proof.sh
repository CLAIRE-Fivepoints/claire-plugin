#!/usr/bin/env bash
# Record dual validation proof for TFI One Education sub-modules.
# Each module produces one video: frontend UI errors + Swagger API HTTP 400.
#
# Usage: claire fivepoints validation-proof [OPTIONS]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/../scripts/validation_proof.py"

# -- Help --------------------------------------------------------------------

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Usage: claire fivepoints validation-proof [OPTIONS]

Record dual validation proof for all 5 Education sub-modules.
Each module produces one video with two parts:
  Part A — Frontend UI: validation errors visible (empty/invalid submit)
  Part B — Swagger API: same rule enforced as HTTP 400 response

Options:
  --base-url URL     Frontend base URL (default: https://localhost:5173)
  --api-url URL      Backend API URL for Swagger (default: https://localhost:58337)
  --client-id UUID   Client UUID to test against (default: test client)
  --output-dir DIR   Directory for video/screenshot output (default: ./validation_proof_videos)
  --module MODULE    Run a specific module only:
                       education   - IEP/504 Plan/ARD form (iepDate required)
                       grade       - Grade Achieved (gradeAchievedTypeId required)
                       ged         - GED Test (testDate required)
                       enrollment  - Enrollment (gpa must be 0-4.0)
                       report-card - Report Card (reportCard text required)
                       all         - Run all modules (default)
  -h, --help         Show this help message

Sub-modules:
  1. Education Edit   - IEP, 504 Plan, ARD, On Grade Level
  2. Grade Achieved   - Add grade record
  3. GED Test         - Add GED test score
  4. Enrollment       - Add school enrollment
  5. Report Card      - Add report card entry

Prerequisites:
  - python3 with playwright installed (pip install playwright)
  - Playwright browsers installed (playwright install chromium)
  - TFI One frontend running on base URL (default: port 5173)
  - TFI One backend running with Swagger UI (default: port 58337)

Output:
  5 .webm video files + screenshots in the output directory
  Each video: frontend error → success → Swagger 400
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
check_port 58337 "Backend (.NET API + Swagger)"

# -- Run proof ---------------------------------------------------------------

echo ""
echo "Starting validation proof recording..."
echo ""

python3 "${PYTHON_SCRIPT}" "$@"
exit_code=$?

if [[ $exit_code -eq 0 ]]; then
    echo ""
    echo "Validation proof completed successfully."
else
    echo ""
    echo "WARNING: Some modules may have failed (exit code: ${exit_code})."
fi

exit $exit_code
