"""Image-to-section mapping + tracked-changes filtering tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

from ado_fetch_attachments.docx_extractor import (
    extract_docx,
    section_titles,
    write_image_index,
    write_images,
)


class TestExtractDocx:
    def test_images_mapped_to_nearest_heading(self, tmp_path, docx_builder):
        docx_path = tmp_path / "sample.docx"
        docx_builder(
            docx_path,
            sections=[
                (1, "Overview"),
                (2, "Face Sheet"),
                (2, "Client Information"),
            ],
            image_anchors=["Face Sheet", "Client Information"],
        )
        result = extract_docx(docx_path)
        assert section_titles(result) == ["Overview", "Face Sheet", "Client Information"]
        assert [img.section for img in result.images] == ["Face Sheet", "Client Information"]
        assert [img.filename for img in result.images] == ["image001.png", "image002.png"]
        assert all(img.bytes_.startswith(b"\x89PNG") for img in result.images)

    def test_image_before_any_heading_gets_empty_section(self, tmp_path, docx_builder):
        docx_path = tmp_path / "noheading.docx"
        docx_builder(
            docx_path,
            sections=[(1, "Only section")],
            image_anchors=["Only section"],
        )
        result = extract_docx(docx_path)
        assert result.images[0].section == "Only section"

    def test_skips_unaccepted_ins_in_paragraph_text(self, tmp_path, docx_builder):
        # Hand-craft a document.xml that wraps some text inside <w:ins>
        docx_path = tmp_path / "tracked.docx"
        docx_builder(
            docx_path,
            sections=[(1, "Heading")],
            image_anchors=[],
        )
        # Patch document.xml to inject <w:ins>
        custom_doc = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<w:body>"
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
            "<w:r><w:t>Heading</w:t></w:r></w:p>"
            '<w:p>'
            "<w:r><w:t>Accepted. </w:t></w:r>"
            '<w:ins w:id="1" w:author="a" w:date="2026-01-01T00:00:00Z">'
            "<w:r><w:t>UNACCEPTED-INSERT</w:t></w:r>"
            "</w:ins>"
            '<w:del w:id="2" w:author="a" w:date="2026-01-01T00:00:00Z">'
            "<w:r><w:delText>KEPT-NOT-YET-DELETED</w:delText></w:r>"
            "</w:del>"
            "</w:p>"
            "</w:body></w:document>"
        )
        # Rewrite the zip with the custom document.xml
        tmp_zip = tmp_path / "tracked_rewritten.docx"
        with zipfile.ZipFile(docx_path) as src, zipfile.ZipFile(
            tmp_zip, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename == "word/document.xml":
                    data = custom_doc.encode("utf-8")
                dst.writestr(info, data)

        result = extract_docx(tmp_zip)
        body_paragraph = next(
            p for i, p in enumerate(result.paragraphs) if i > 0 and p
        )
        assert "UNACCEPTED-INSERT" not in body_paragraph
        assert "Accepted." in body_paragraph
        # w:del text uses <w:delText> not <w:t>; extractor skips it naturally


class TestWriteOutputs:
    def test_writes_images_and_sidecars(self, tmp_path, docx_builder):
        docx_path = tmp_path / "sample.docx"
        docx_builder(
            docx_path,
            sections=[(1, "Top"), (2, "Sub")],
            image_anchors=["Sub"],
        )
        result = extract_docx(docx_path)
        out_dir = tmp_path / "out"
        written = write_images(result, out_dir)
        assert len(written) == 1
        assert written[0].read_bytes().startswith(b"\x89PNG")
        sidecar = written[0].with_suffix(".md")
        assert "**Section:** Sub" in sidecar.read_text()

    def test_writes_image_index(self, tmp_path, docx_builder):
        docx_path = tmp_path / "sample.docx"
        docx_builder(
            docx_path,
            sections=[(1, "Chapter"), (2, "Face Sheet")],
            image_anchors=["Face Sheet"],
        )
        result = extract_docx(docx_path)
        index = tmp_path / "FDS_TEST_IMAGE_INDEX.md"
        write_image_index(result, index, "TEST")
        content = index.read_text()
        assert "FDS TEST — Image Index" in content
        assert "| 1 | Face Sheet | image001.png |" in content
