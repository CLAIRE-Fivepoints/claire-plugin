"""Shared fixtures for ado_fetch_attachments tests.

Provides a builder that emits a minimal but real .docx so docx_extractor and
cache_comparator can be exercised without shipping a binary fixture.
"""

from __future__ import annotations

import io
import struct
import zipfile
import zlib
from pathlib import Path

import pytest


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""


def _minimal_png() -> bytes:
    """Build a valid 1x1 PNG so image extraction has real bytes to write."""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return length + chunk_type + data + struct.pack(">I", crc)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0),
    )
    raw = b"\x00\xff\x00\x00"
    idat = _chunk(b"IDAT", zlib.compress(raw))
    iend = _chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


def _build_document_xml(sections: list[tuple[int, str]], image_anchors: list[str]) -> str:
    """Build a word/document.xml with the given heading/image layout.

    Args:
        sections: list of (level, title) tuples in document order.
        image_anchors: list of heading titles that should carry an image after them.
    """
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"',
        '            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"',
        '            xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"',
        '            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"',
        '            xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">',
        "  <w:body>",
    ]

    img_index = 0
    for level, title in sections:
        parts.extend(
            [
                "    <w:p>",
                "      <w:pPr>",
                f'        <w:pStyle w:val="Heading{level}"/>',
                "      </w:pPr>",
                f"      <w:r><w:t>{title}</w:t></w:r>",
                "    </w:p>",
            ]
        )
        parts.extend(
            [
                "    <w:p>",
                f"      <w:r><w:t>Body under {title}.</w:t></w:r>",
                "    </w:p>",
            ]
        )
        if title in image_anchors:
            img_index += 1
            rid = f"rId{10 + img_index}"
            parts.extend(
                [
                    "    <w:p>",
                    "      <w:r>",
                    "        <w:drawing>",
                    '          <wp:inline distT="0" distB="0" distL="0" distR="0">',
                    "            <a:graphic>",
                    '              <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">',
                    "                <pic:pic>",
                    "                  <pic:blipFill>",
                    f'                    <a:blip r:embed="{rid}"/>',
                    "                  </pic:blipFill>",
                    "                </pic:pic>",
                    "              </a:graphicData>",
                    "            </a:graphic>",
                    "          </wp:inline>",
                    "        </w:drawing>",
                    "      </w:r>",
                    "    </w:p>",
                ]
            )

    parts.extend(["  </w:body>", "</w:document>"])
    return "\n".join(parts)


def _build_document_rels(image_count: int) -> str:
    rels = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    for n in range(1, image_count + 1):
        rid = f"rId{10 + n}"
        target = f"media/image{n}.png"
        rels.append(
            f'  <Relationship Id="{rid}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="{target}"/>'
        )
    rels.append("</Relationships>")
    return "\n".join(rels)


def build_docx(
    path: Path,
    sections: list[tuple[int, str]],
    image_anchors: list[str],
    extra_files: dict[str, bytes] | None = None,
) -> Path:
    """Write a minimal valid .docx at ``path`` and return the path."""
    document_xml = _build_document_xml(sections, image_anchors)
    rels_xml = _build_document_rels(len(image_anchors))
    png = _minimal_png()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _ROOT_RELS)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", rels_xml)
        for n in range(1, len(image_anchors) + 1):
            zf.writestr(f"word/media/image{n}.png", png)
        for name, data in (extra_files or {}).items():
            zf.writestr(name, data)

    path.write_bytes(buffer.getvalue())
    return path


@pytest.fixture
def docx_builder():
    return build_docx
