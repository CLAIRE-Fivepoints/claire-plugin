"""Extract text, sections, and images from a .docx.

Design notes:
    * A .docx is a ZIP. Images live in ``word/media/``; ``word/document.xml`` holds
      the flow; ``word/_rels/document.xml.rels`` maps relationship IDs to media parts.
    * We walk document.xml in document order so each image can be tagged with its
      nearest preceding heading (H1/H2/H3) — this produces the IMAGE_INDEX.md
      cross-reference an agent needs to map a wireframe to an FDS section.
    * **Accepted-version only:** runs inside ``<w:ins>`` represent unaccepted
      insertions and are excluded. Content inside ``<w:del>`` represents not-yet-
      applied deletions and is included (it is still part of the document today).
      Comments (``<w:commentRangeStart>`` / ``commentReference``) are ignored.
"""

from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS = {
    "w": _W,
    "r": _R,
    "pkg": _PKG,
}

_INS_TAG = f"{{{_W}}}ins"
_DEL_TAG = f"{{{_W}}}del"
_T_TAG = f"{{{_W}}}t"
_P_TAG = f"{{{_W}}}p"
_PPR_TAG = f"{{{_W}}}pPr"
_PSTYLE_TAG = f"{{{_W}}}pStyle"
_DRAWING_TAG = f"{{{_W}}}drawing"
_EMBED_ATTR = f"{{{_R}}}embed"


@dataclass
class ExtractedImage:
    filename: str          # e.g. image001.png
    bytes_: bytes
    paragraph_index: int   # index of <w:p> in document.xml
    section: str           # nearest preceding heading text
    surrounding_text: str  # a few paragraphs of context


@dataclass
class ExtractedSection:
    level: int             # 1 = H1, 2 = H2, etc. (numberless default = 1)
    title: str
    paragraph_index: int


@dataclass
class ExtractionResult:
    sections: list[ExtractedSection] = field(default_factory=list)
    images: list[ExtractedImage] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)


def _heading_level(paragraph: ET.Element) -> int | None:
    """Return the heading level (1..N) for a ``<w:p>``, or None if not a heading.

    Standard Word style IDs are ``Heading1`` .. ``Heading9``. Five Points templates
    also use ``berschrift1`` (German) and numeric aliases; we accept any style ID
    that ends in a digit and starts with a heading-like prefix.
    """
    ppr = paragraph.find(_PPR_TAG)
    if ppr is None:
        return None
    pstyle = ppr.find(_PSTYLE_TAG)
    if pstyle is None:
        return None
    val = pstyle.get(f"{{{_W}}}val", "")
    match = re.search(r"(?:heading|berschrift|titre)\s*(\d+)", val, re.IGNORECASE)
    if match:
        try:
            level = int(match.group(1))
        except ValueError:
            return None
        return max(1, min(level, 9))
    if val.lower() == "title":
        return 1
    return None


def _paragraph_text(paragraph: ET.Element) -> str:
    """Extract the accepted-only text of a paragraph.

    * Text inside ``<w:ins>`` (unaccepted insertion) is skipped.
    * Text inside ``<w:del>`` (unaccepted deletion) is kept — it is still part of
      the document until the deletion is accepted.
    """
    chunks: list[str] = []

    def walk(node: ET.Element, inside_ins: bool) -> None:
        if node.tag == _INS_TAG:
            return
        if node.tag == _T_TAG:
            if not inside_ins and node.text:
                chunks.append(node.text)
            return
        for child in node:
            walk(child, inside_ins)

    walk(paragraph, inside_ins=False)
    return "".join(chunks).strip()


def _paragraph_image_rids(paragraph: ET.Element) -> list[str]:
    """Return the r:embed IDs of every drawing anchored in this paragraph."""
    ids: list[str] = []
    for drawing in paragraph.iter(_DRAWING_TAG):
        for node in drawing.iter():
            rid = node.get(_EMBED_ATTR)
            if rid:
                ids.append(rid)
    return ids


def _parse_relationships(rels_xml: bytes) -> dict[str, str]:
    """Map relationship Id → Target (relative path inside the docx)."""
    root = ET.fromstring(rels_xml)
    out: dict[str, str] = {}
    for node in root.iter():
        if node.tag.endswith("Relationship"):
            rid = node.get("Id")
            target = node.get("Target")
            if rid and target:
                out[rid] = target
    return out


def extract_docx(docx_path: Path) -> ExtractionResult:
    """Parse a .docx into sections, paragraphs, and image-to-section links."""
    result = ExtractionResult()
    with zipfile.ZipFile(docx_path) as zf:
        document_xml = zf.read("word/document.xml")
        try:
            rels_xml = zf.read("word/_rels/document.xml.rels")
        except KeyError:
            rels_xml = b"<Relationships/>"
        rid_map = _parse_relationships(rels_xml)

        media_blobs: dict[str, bytes] = {}
        for info in zf.infolist():
            if info.filename.startswith("word/media/"):
                media_blobs[info.filename[len("word/") :]] = zf.read(info.filename)

    doc_root = ET.fromstring(document_xml)
    body = doc_root.find(f"{{{_W}}}body")
    if body is None:
        return result

    paragraphs = [node for node in body.iter(_P_TAG)]
    text_by_index: list[str] = []
    current_section: str = ""
    image_counter = 0

    for p_index, paragraph in enumerate(paragraphs):
        text = _paragraph_text(paragraph)
        text_by_index.append(text)

        level = _heading_level(paragraph)
        if level is not None and text:
            current_section = text
            result.sections.append(
                ExtractedSection(level=level, title=text, paragraph_index=p_index)
            )

        for rid in _paragraph_image_rids(paragraph):
            target = rid_map.get(rid)
            if not target:
                continue
            target_name = target.split("/")[-1]
            blob = media_blobs.get(target) or media_blobs.get(f"media/{target_name}")
            if blob is None:
                logger.debug("No media blob for rId=%s target=%s", rid, target)
                continue
            ext = Path(target_name).suffix or ".bin"
            image_counter += 1
            filename = f"image{image_counter:03d}{ext}"
            start = max(0, p_index - 3)
            end = min(len(paragraphs), p_index + 4)
            surrounding = "\n".join(
                s for s in text_by_index[start:p_index] if s
            ) + "\n" + "\n".join(
                _paragraph_text(paragraphs[i]) for i in range(p_index, end)
                if _paragraph_text(paragraphs[i])
            )
            result.images.append(
                ExtractedImage(
                    filename=filename,
                    bytes_=blob,
                    paragraph_index=p_index,
                    section=current_section,
                    surrounding_text=surrounding.strip(),
                )
            )

    result.paragraphs = text_by_index
    return result


def write_images(result: ExtractionResult, output_dir: Path) -> list[Path]:
    """Write extracted images and per-image markdown sidecars."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for image in result.images:
        image_path = output_dir / image.filename
        image_path.write_bytes(image.bytes_)
        sidecar = image_path.with_suffix(".md")
        sidecar.write_text(
            (
                f"# {image.filename}\n\n"
                f"**Section:** {image.section or '(unknown)'}\n\n"
                f"**Surrounding text:**\n\n{image.surrounding_text}\n"
            ),
            encoding="utf-8",
        )
        written.append(image_path)
    return written


def write_image_index(
    result: ExtractionResult,
    index_path: Path,
    doc_name: str,
) -> Path:
    """Generate the FDS_<NAME>_IMAGE_INDEX.md domain document."""
    lines: list[str] = [
        "---",
        f"name: FDS_{doc_name}_IMAGE_INDEX",
        f'title: "Five Points — FDS {doc_name}: Image Index"',
        (
            'description: "Cross-reference mapping each extracted wireframe to its '
            'nearest FDS heading."'
        ),
        f"keywords: [fds, {doc_name.lower()}, images, wireframe, index]",
        "type: knowledge",
        "---",
        "",
        f"# FDS {doc_name} — Image Index",
        "",
        "Generated by `claire fivepoints ado-fetch-attachments`.",
        "Each row maps a wireframe image to the nearest preceding heading in the FDS.",
        "",
        "| # | Section | File |",
        "|---|---------|------|",
    ]
    for idx, image in enumerate(result.images, start=1):
        section = image.section or "(unknown)"
        section = section.replace("|", "\\|")
        lines.append(f"| {idx} | {section} | {image.filename} |")
    lines.append("")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path


def section_titles(result: ExtractionResult) -> list[str]:
    return [s.title for s in result.sections]
