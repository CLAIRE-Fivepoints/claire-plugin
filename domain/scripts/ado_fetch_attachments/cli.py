"""Command-line entry point for ``claire fivepoints ado-fetch-attachments``.

Fetch-on-use model (issue #51):

    python3 -m ado_fetch_attachments.cli --pbi 17113
    python3 -m ado_fetch_attachments.cli --pbi 17113 --print-manifest

Behavior:
    * Download every ``AttachedFile`` relation on the PBI into the local staging
      dir (``~/TFIOneGit/.fds-cache/{pbi}/``).
    * If a staging copy already exists and its MD5 matches the live attachment,
      skip re-extract (idempotent).
    * Otherwise, re-extract images, IMAGE_INDEX, and the per-section markdown.
    * ``--print-manifest`` emits a single JSON object to stdout describing every
      docx + every section (sha256, page range, image refs). This is the contract
      the analyst's FDS Read Receipt quotes and the CI gate recomputes.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import re
import sys
from pathlib import Path

from .ado_client import (
    AdoConfig,
    download_attachment,
    fetch_work_item_relations,
    filter_attachments,
    resolve_pat,
)
from .cache_comparator import md5_file
from .docx_extractor import (
    extract_docx,
    section_sha256,
    write_image_index,
    write_images,
    write_sections_markdown,
)

logger = logging.getLogger(__name__)

DEFAULT_ORG = "FivePointsTechnology"
DEFAULT_PROJECT = "TFIOne"


def _doc_name_from_attachment(name: str) -> str:
    """Turn '4 - Client Management(1).docx' into 'CLIENT_MANAGEMENT'."""
    stem = Path(name).stem
    stem = re.sub(r"\([^)]*\)", "", stem)
    stem = re.sub(r"^\s*\d+\s*[-_]\s*", "", stem)
    token = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_").upper()
    return token or "UNKNOWN"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ado-fetch-attachments",
        description=(
            "Fetch FDS attachments from an Azure DevOps PBI into a local staging "
            "dir; extract sections + images; emit a verifiable manifest."
        ),
    )
    parser.add_argument("--pbi", type=int, required=True, help="ADO PBI ID")
    parser.add_argument(
        "--print-manifest",
        action="store_true",
        help=(
            "Emit the fetch manifest (JSON) to stdout. One object per invocation, "
            "listing every docx's md5 and every section's sha256 / pages / image refs."
        ),
    )
    parser.add_argument(
        "--org",
        default=DEFAULT_ORG,
        help=f"Azure DevOps org (default: {DEFAULT_ORG}).",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help=f"Azure DevOps project (default: {DEFAULT_PROJECT}).",
    )
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=Path.home() / "TFIOneGit" / ".fds-cache",
        help=(
            "Where to write downloads + extracted artifacts "
            "(default: ~/TFIOneGit/.fds-cache/{pbi})."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce log verbosity (default is INFO).",
    )
    return parser


def _process_attachment(
    args: argparse.Namespace,
    pbi_id: int,
    pat: str,
    attachment,
    pbi_staging: Path,
) -> dict:
    """Download + extract one attachment. Returns the manifest entry for this docx."""
    safe_name = re.sub(r"[^\w.\-]+", "_", attachment.name)
    fresh_path = pbi_staging / safe_name

    # Staging-MD5 reuse: if the file already exists in staging and its MD5 still
    # matches the live attachment, skip re-download + re-extract.
    reused = False
    if fresh_path.is_file():
        existing_md5 = md5_file(fresh_path)
        # Download to a sibling path first so we do not clobber the cached copy
        # until we confirm it actually changed.
        probe_path = fresh_path.with_suffix(fresh_path.suffix + ".probe")
        download_attachment(attachment, probe_path, pat=pat)
        probe_md5 = md5_file(probe_path)
        if probe_md5 == existing_md5:
            probe_path.unlink(missing_ok=True)
            reused = True
            logger.info("[reuse] %s matches staging (md5 %s)", attachment.name, existing_md5)
        else:
            probe_path.replace(fresh_path)
            logger.info("[refresh] %s changed (%s → %s)", attachment.name, existing_md5, probe_md5)
    else:
        logger.info("[download] %s → %s", attachment.name, fresh_path)
        download_attachment(attachment, fresh_path, pat=pat)

    doc_name = _doc_name_from_attachment(attachment.name)
    fresh_md5 = md5_file(fresh_path)
    fresh_size = fresh_path.stat().st_size

    extraction = extract_docx(fresh_path)

    if not reused:
        images_dir = pbi_staging / f"FDS_{doc_name}_images"
        write_images(extraction, images_dir)
        write_image_index(
            extraction,
            pbi_staging / f"FDS_{doc_name}_IMAGE_INDEX.md",
            doc_name,
        )
        write_sections_markdown(
            extraction,
            pbi_staging / f"FDS_{doc_name}.md",
            doc_name,
        )
        logger.info(
            "[extract] sections=%d images=%d pages_supported=%s",
            len(extraction.sections),
            len(extraction.images),
            extraction.pages_supported,
        )

    sections_manifest: dict[str, dict] = {}
    for section in extraction.sections:
        entry: dict = {
            "sha256": section_sha256(section),
            "image_refs": list(section.image_filenames),
        }
        if extraction.pages_supported and section.page_start is not None:
            entry["pages"] = [section.page_start, section.page_end]
        else:
            entry["pages"] = None
        sections_manifest[section.title] = entry

    return {
        "docx_filename": attachment.name,
        "docx_md5": fresh_md5,
        "docx_bytes": fresh_size,
        "doc_name": doc_name,
        "reused": reused,
        "pages_supported": extraction.pages_supported,
        "sections": sections_manifest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    pat = resolve_pat()
    if not pat:
        print(
            "ERROR: No Azure DevOps PAT found. "
            "Set AZURE_DEVOPS_PAT or AZURE_DEVOPS_DEV_PAT.",
            file=sys.stderr,
        )
        return 2

    config = AdoConfig(org=args.org, project=args.project, pat=pat)
    logger.info("[pbi] #%d — %s/%s", args.pbi, args.org, args.project)

    relations = fetch_work_item_relations(config, args.pbi)
    attachments = filter_attachments(relations)

    pbi_staging = args.staging_dir / str(args.pbi)
    pbi_staging.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "pbi": args.pbi,
        "org": args.org,
        "project": args.project,
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "staging_dir": str(pbi_staging),
        "docs": [],
    }

    if not attachments:
        logger.info("[ok] PBI #%d has no attachments", args.pbi)
    else:
        logger.info("[pbi] found %d attachment(s)", len(attachments))
        for attachment in attachments:
            manifest["docs"].append(
                _process_attachment(args, args.pbi, pat, attachment, pbi_staging)
            )

    if args.print_manifest:
        json.dump(manifest, sys.stdout, indent=2, sort_keys=False)
        sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
