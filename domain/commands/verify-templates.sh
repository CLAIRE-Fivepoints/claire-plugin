#!/usr/bin/env bash
# fivepoints verify-templates
# Verifies no checklist duplication between fivepoints-dev persona and
# operational/CHECKLIST_DEV_PIPELINE — single-source-of-truth guard.
#
# Issue #80 (CLAIRE-Fivepoints/claire-plugin): the persona file used to
# embed the full [1/11]..[11/11] checklist body inline. This script asserts
# that duplication is absent: the persona must reference the checklist but
# never contain its step markers.
#
# Exit codes:
#   0 — no duplication; CHECKLIST_DEV_PIPELINE is the single source of truth
#   1 — duplication detected or required file missing

set -uo pipefail

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Usage: claire fivepoints verify-templates [OPTIONS]

Verify no checklist duplication between the fivepoints-dev persona and
domain/operational/CHECKLIST_DEV_PIPELINE.

Checks:
  1. domain/persona/fivepoints-dev.md does NOT contain [N/11] step markers
  2. domain/operational/CHECKLIST_DEV_PIPELINE.md contains all 11 steps
     (confirms it is the single source of truth)

Options:
  --verbose, -v   Show per-check detail
  --agent-help    Show LLM-optimized help
  -h, --help      Show this help

Exit codes:
  0  No duplication found
  1  Duplication detected or a required file is missing
EOF
    exit 0
fi

if [[ "${1:-}" == "--agent-help" ]]; then
    cat <<'EOF'
fivepoints verify-templates — single-source-of-truth guard for the dev pipeline checklist.

WHEN TO RUN
  Run after any edit to domain/persona/fivepoints-dev.md or
  domain/operational/CHECKLIST_DEV_PIPELINE.md to confirm the persona does
  not embed checklist steps.  Also run in CI / bats tests.

OUTPUT
  Success (exit 0):
    ✓ verify-templates: no duplication — CHECKLIST_DEV_PIPELINE is the single source of truth

  Failure (exit 1):
    ✗ [N/11] found in fivepoints-dev.md  (one line per duplicate step)
    ✗ verify-templates: FAILED (N duplicate steps, M missing steps)

FLAGS
  --verbose  Emit per-check pass/fail lines; useful for debugging.
  --help     Human-readable help.
EOF
    exit 0
fi

# ---------------------------------------------------------------------------
# Parse options
# ---------------------------------------------------------------------------

VERBOSE=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --verbose|-v) VERBOSE=true ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
    shift
done

# ---------------------------------------------------------------------------
# Locate domain root
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOMAIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PERSONA_FILE="${DOMAIN_DIR}/persona/fivepoints-dev.md"
CHECKLIST_FILE="${DOMAIN_DIR}/operational/CHECKLIST_DEV_PIPELINE.md"

FAIL=0
DUPLICATE_STEPS=0
MISSING_STEPS=0

# ---------------------------------------------------------------------------
# Check 1: required files exist
# ---------------------------------------------------------------------------

if [[ ! -f "$PERSONA_FILE" ]]; then
    echo "✗ MISSING: ${PERSONA_FILE}" >&2
    exit 1
fi

if [[ ! -f "$CHECKLIST_FILE" ]]; then
    echo "✗ MISSING: ${CHECKLIST_FILE}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Check 2: persona must NOT contain embedded checklist step definitions
#
# An *embedded step* is a line starting with a markdown checkbox followed by
# the step marker: "- [ ] [N/11]" or "- [x] [N/11]".
# Inline cross-references such as "see [10/11]" or "never skip `[8/11]`" are
# not embedded steps and are intentionally permitted in the persona.
# ---------------------------------------------------------------------------

for step in 1 2 3 4 5 6 7 8 9 10 11; do
    if grep -qE "^- \[[ x]\] \[${step}/11\]" "$PERSONA_FILE"; then
        if [[ "$VERBOSE" == "true" ]]; then
            echo "✗ [${step}/11] embedded as a step definition in $(basename "$PERSONA_FILE")"
        fi
        DUPLICATE_STEPS=$((DUPLICATE_STEPS + 1))
        FAIL=1
    fi
done

if [[ "$VERBOSE" == "true" && $DUPLICATE_STEPS -eq 0 ]]; then
    echo "✓ No checklist steps embedded in $(basename "$PERSONA_FILE")"
fi

# ---------------------------------------------------------------------------
# Check 3: CHECKLIST_DEV_PIPELINE must contain all 11 steps (single source)
# ---------------------------------------------------------------------------

for step in 1 2 3 4 5 6 7 8 9 10 11; do
    if ! grep -qE "^- \[[ x]\] \[${step}/11\]" "$CHECKLIST_FILE"; then
        if [[ "$VERBOSE" == "true" ]]; then
            echo "✗ [${step}/11] missing from $(basename "$CHECKLIST_FILE")"
        fi
        MISSING_STEPS=$((MISSING_STEPS + 1))
        FAIL=1
    fi
done

if [[ "$VERBOSE" == "true" && $MISSING_STEPS -eq 0 ]]; then
    echo "✓ All 11 steps present in $(basename "$CHECKLIST_FILE") (single source of truth)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

if [[ $FAIL -eq 0 ]]; then
    echo "✓ verify-templates: no duplication — CHECKLIST_DEV_PIPELINE is the single source of truth"
else
    echo "✗ verify-templates: FAILED (${DUPLICATE_STEPS} duplicate step(s) in persona, ${MISSING_STEPS} missing step(s) in checklist)" >&2
    exit 1
fi
