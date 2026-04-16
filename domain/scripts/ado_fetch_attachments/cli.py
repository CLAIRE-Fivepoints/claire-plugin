"""Command-line entry point for ``claire fivepoints ado-fetch-attachments``.

Usage:
    python3 -m ado_fetch_attachments.cli --pbi 17113 --diff-only
    python3 -m ado_fetch_attachments.cli --pbi 17113 --auto-issue
"""

from __future__ import annotations

import argparse
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
from .cache_comparator import (
    attachment_token,
    compare_to_cache,
    diff_sections,
    resolve_cache_path,
)
from .docx_extractor import (
    extract_docx,
    section_titles,
    write_image_index,
    write_images,
)
from .issue_creator import DriftReport, write_body_to_file

logger = logging.getLogger(__name__)

DEFAULT_ORG = "FivePointsTechnology"
DEFAULT_PROJECT = "TFIOne"
DEFAULT_ISSUE_REPO = "CLAIRE-Fivepoints/claire-plugin"


def _doc_name_from_attachment(name: str) -> str:
    return attachment_token(name) or "UNKNOWN"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ado-fetch-attachments",
        description="Fetch FDS attachments from an ADO PBI, diff vs domain cache, "
        "link images to sections, auto-issue on drift.",
    )
    parser.add_argument("--pbi", type=int, required=True, help="ADO PBI ID")
    parser.add_argument(
        "--diff-only",
        action="store_true",
        help="Report the delta and exit — no issue, no file writes beyond staging.",
    )
    parser.add_argument(
        "--auto-issue",
        action="store_true",
        help="Open a drift issue when the cache is stale.",
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
        "--cache-dir",
        type=Path,
        required=True,
        help="Domain cache directory (usually <plugin>/domain/knowledge).",
    )
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=Path.home() / "TFIOneGit" / ".fds-cache",
        help="Where to write downloaded .docx + extracted images (default: "
        "~/TFIOneGit/.fds-cache/{pbi}).",
    )
    parser.add_argument(
        "--issue-repo",
        default=DEFAULT_ISSUE_REPO,
        help=f"Repo to open drift issues in (default: {DEFAULT_ISSUE_REPO}).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce log verbosity (default is INFO).",
    )
    return parser


def _cached_sections_for(cache_dir: Path, doc_name: str) -> list[str]:
    cached_path = cache_dir / f"FDS_{doc_name}.docx"
    if not cached_path.is_file():
        return []
    return section_titles(extract_docx(cached_path))


def _process_attachment(args: argparse.Namespace, pbi_id: int, pat: str, attachment, pbi_staging: Path) -> int:
    safe_name = re.sub(r"[^\w.\-]+", "_", attachment.name)
    fresh_path = pbi_staging / safe_name
    print(f"[download] {attachment.name} → {fresh_path}")
    download_attachment(attachment, fresh_path, pat=pat)

    doc_name = _doc_name_from_attachment(attachment.name)
    cached_path = resolve_cache_path(args.cache_dir, attachment.name)
    comparison = compare_to_cache(fresh_path, cached_path)

    if comparison.match:
        print(f"[ok] cache up-to-date for {doc_name} (md5 {comparison.fresh_md5})")
        return 0

    if comparison.cached_path is None:
        print(f"[drift] no cached counterpart found for {attachment.name}")
    else:
        print(
            f"[drift] cached {comparison.cached_md5} != fresh {comparison.fresh_md5}"
        )

    fresh_ext = extract_docx(fresh_path)
    cached_titles = _cached_sections_for(args.cache_dir, doc_name)
    fresh_titles = section_titles(fresh_ext)
    section_diff = diff_sections(cached_titles, fresh_titles)
    print(
        f"[sections] fresh={len(fresh_titles)} cached={len(cached_titles)} "
        f"added={len(section_diff.added)} removed={len(section_diff.removed)}"
    )
    print(f"[images]   extracted={len(fresh_ext.images)}")

    if args.diff_only:
        print("[diff-only] no file writes, no issue")
        return 1

    images_dir = pbi_staging / f"FDS_{doc_name}_images"
    write_images(fresh_ext, images_dir)
    index_path = pbi_staging / f"FDS_{doc_name}_IMAGE_INDEX.md"
    write_image_index(fresh_ext, index_path, doc_name)
    print(f"[write] images → {images_dir}")
    print(f"[write] index  → {index_path}")

    fresh_size = fresh_path.stat().st_size
    cached_size = (
        comparison.cached_path.stat().st_size
        if comparison.cached_path and comparison.cached_path.is_file()
        else None
    )

    report = DriftReport(
        pbi_id=pbi_id,
        attachment_name=attachment.name,
        comparison=comparison,
        section_diff=section_diff,
        fresh_size=fresh_size,
        cached_size=cached_size,
        image_count=len(fresh_ext.images),
    )
    title = report.title(doc_name)
    body = report.body(doc_name)
    body_file = write_body_to_file(body, pbi_staging / f"drift_issue_{doc_name}.md")
    print(f"[write] issue body → {body_file}")

    action_file = pbi_staging / f"drift_action_{doc_name}.json"
    action_file.write_text(
        json.dumps(
            {
                "action": "create_issue" if args.auto_issue else "none",
                "title": title,
                "body_file": str(body_file),
                "repo": args.issue_repo,
                "labels": ["documentation"],
                "doc_name": doc_name,
                "pbi_id": pbi_id,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[write] action   → {action_file}")

    if not args.auto_issue:
        print("[hint] add --auto-issue to open the drift issue automatically")
    return 1


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
    print(f"[pbi] #{args.pbi} — {args.org}/{args.project}")

    relations = fetch_work_item_relations(config, args.pbi)
    attachments = filter_attachments(relations)
    if not attachments:
        print(f"[ok] PBI #{args.pbi} has no attachments")
        return 0

    print(f"[pbi] found {len(attachments)} attachment(s)")
    pbi_staging = args.staging_dir / str(args.pbi)
    pbi_staging.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for attachment in attachments:
        status = _process_attachment(args, args.pbi, pat, attachment, pbi_staging)
        exit_code = max(exit_code, status)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
