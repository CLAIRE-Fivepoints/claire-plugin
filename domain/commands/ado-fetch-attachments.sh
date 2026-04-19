#!/usr/bin/env bash
# fivepoints ado-fetch-attachments
#
# Fetch FDS attachments from an Azure DevOps PBI into a local staging dir,
# extract sections + images, and (optionally) emit a verifiable manifest.
#
# Usage:
#   claire fivepoints ado-fetch-attachments --pbi <id> [--print-manifest]
#   claire fivepoints ado-fetch-attachments --agent-help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PLUGIN_PYTHON_DIR="$PLUGIN_ROOT/domain/scripts"

show_agent_help() {
    cat <<'HELP'
# fivepoints ado-fetch-attachments — LLM Agent Guide

## Purpose
Fetch every FDS attachment on an Azure DevOps PBI into a local staging dir,
extract sections + images with heading cross-references, and emit a manifest
the analyst quotes in the FDS Read Receipt and the CI gate recomputes.

This command is fetch-on-use. Nothing is committed to the plugin repo.

## Modes
- (no flag)          Download + extract into staging. No stdout JSON.
- `--print-manifest` Download + extract AND emit the manifest to stdout.

## Arguments
- `--pbi <id>`           (required) ADO PBI ID
- `--staging-dir <path>` Where to write downloads (default: ~/TFIOneGit/.fds-cache/{pbi})
- `--org <name>`         ADO organization (default: FivePointsTechnology)
- `--project <name>`     ADO project (default: TFIOne)

## Exit codes
- 0 — success (or PBI has no attachments)
- 2 — error (PAT missing, API failure, …)

## PAT
Read-only PAT is sufficient. Resolved in order:
AZURE_DEVOPS_WRITE_PAT → AZURE_DEVOPS_DEV_PAT → AZURE_DEVOPS_PAT → ~/.config/claire/.env

## Output layout (staging)
  {staging}/{pbi}/{attachment-name}.docx       — the fresh document
  {staging}/{pbi}/FDS_<NAME>_images/            — extracted PNG/JPEG + .md sidecars
  {staging}/{pbi}/FDS_<NAME>_IMAGE_INDEX.md     — image → section cross-reference
  {staging}/{pbi}/FDS_<NAME>.md                 — section-by-section markdown with sha256 markers

## Manifest (emitted by --print-manifest)
{
  "pbi": 17113,
  "org": "FivePointsTechnology",
  "project": "TFIOne",
  "fetched_at": "2026-04-19T20:45:00Z",
  "staging_dir": "/Users/you/TFIOneGit/.fds-cache/17113",
  "docs": [
    {
      "docx_filename": "4 - Client Management(1).docx",
      "docx_md5": "f636b255be9f7e3ab3760b7d2b5f312e",
      "docx_bytes": 6459581,
      "doc_name": "CLIENT_MANAGEMENT",
      "reused": false,
      "pages_supported": true,
      "sections": {
        "Client Face Sheet": {
          "sha256": "<sha256 of section paragraphs>",
          "pages": [142, 157],
          "image_refs": ["image010.png", "image011.png"]
        }
      }
    }
  ]
}

## Staging reuse
On second invocation, if the local docx already matches the live attachment
MD5, extraction is skipped. This makes the command cheap to call repeatedly
inside a session.
HELP
}

# Parse args — pass-through to Python with a local toggle for --agent-help.
ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --agent-help|-h|--help)
            show_agent_help
            exit 0
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done

# Export PYTHONPATH so Python can import ado_fetch_attachments
export PYTHONPATH="$PLUGIN_PYTHON_DIR:${PYTHONPATH:-}"

# Run the Python orchestration — all logic lives there, bash only routes.
python3 -m ado_fetch_attachments.cli "${ARGS[@]+"${ARGS[@]}"}"
