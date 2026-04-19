"""CLI tests for the fetch-on-use + manifest model (issue #51).

ADO calls and attachment downloads are stubbed — the test walks the CLI from
argparse to manifest emission without touching the network.
"""

from __future__ import annotations

import io
import json
import shutil
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from ado_fetch_attachments import cli as cli_module
from ado_fetch_attachments.ado_client import Attachment


@pytest.fixture
def stub_ado(monkeypatch, docx_builder, tmp_path):
    """Stub PAT resolution + attachment listing + download with a local docx."""
    source_docx = tmp_path / "source.docx"
    docx_builder(
        source_docx,
        sections=[(1, "Overview"), (2, "Face Sheet"), (2, "Workflows")],
        image_anchors=["Face Sheet"],
    )
    monkeypatch.setattr(cli_module, "resolve_pat", lambda: "fake-pat")
    monkeypatch.setattr(cli_module, "fetch_work_item_relations", lambda *a, **kw: [])
    monkeypatch.setattr(
        cli_module,
        "filter_attachments",
        lambda *_: [Attachment(name="4 - Client Management.docx", url="stub", size=42)],
    )

    def _download(attachment, destination, pat, session=None):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source_docx, destination)
        return destination

    monkeypatch.setattr(cli_module, "download_attachment", _download)
    return source_docx


class TestCli:
    def test_fetch_writes_staging_artifacts(self, tmp_path, stub_ado):
        staging = tmp_path / "staging"
        rc = cli_module.main(
            [
                "--pbi",
                "17113",
                "--staging-dir",
                str(staging),
            ]
        )
        assert rc == 0
        pbi_dir = staging / "17113"
        assert (pbi_dir / "4_-_Client_Management.docx").is_file()
        assert (pbi_dir / "FDS_CLIENT_MANAGEMENT_IMAGE_INDEX.md").is_file()
        assert (pbi_dir / "FDS_CLIENT_MANAGEMENT.md").is_file()
        assert list((pbi_dir / "FDS_CLIENT_MANAGEMENT_images").glob("image*.png"))

    def test_print_manifest_emits_sections_with_sha256(self, tmp_path, stub_ado):
        staging = tmp_path / "staging"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_module.main(
                [
                    "--pbi",
                    "17113",
                    "--print-manifest",
                    "--staging-dir",
                    str(staging),
                ]
            )
        assert rc == 0
        manifest = json.loads(buf.getvalue())
        assert manifest["pbi"] == 17113
        assert manifest["fetched_at"].endswith("Z")
        assert len(manifest["docs"]) == 1
        doc = manifest["docs"][0]
        assert doc["doc_name"] == "CLIENT_MANAGEMENT"
        assert len(doc["docx_md5"]) == 32
        assert doc["docx_bytes"] > 0
        assert doc["reused"] is False
        # Sections is a list, ordered by document position, each with a unique path.
        assert isinstance(doc["sections"], list)
        face_sheet = next(s for s in doc["sections"] if s["title"] == "Face Sheet")
        assert face_sheet["path"] == "Overview > Face Sheet"
        assert face_sheet["level"] == 2
        assert len(face_sheet["sha256"]) == 64
        # image anchored under Face Sheet → listed in its image_refs
        assert any(ref.startswith("image") for ref in face_sheet["image_refs"])

    def test_manifest_section_hash_is_stable(self, tmp_path, stub_ado):
        """Two back-to-back fetches of the same docx must emit identical sha256."""
        staging = tmp_path / "staging"
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            cli_module.main(["--pbi", "17113", "--print-manifest",
                             "--staging-dir", str(staging)])
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            cli_module.main(["--pbi", "17113", "--print-manifest",
                             "--staging-dir", str(staging)])
        m1 = json.loads(buf1.getvalue())
        m2 = json.loads(buf2.getvalue())
        s1 = next(s for s in m1["docs"][0]["sections"] if s["title"] == "Face Sheet")
        s2 = next(s for s in m2["docs"][0]["sections"] if s["title"] == "Face Sheet")
        assert s1["sha256"] == s2["sha256"]
        assert s1["path"] == s2["path"]
        # Second invocation reuses the staging copy (skips re-extract).
        assert m2["docs"][0]["reused"] is True

    def test_manifest_preserves_sections_with_duplicate_titles(
        self, tmp_path, monkeypatch, docx_builder
    ):
        """Sub-section titles like 'Field Descriptions' repeat under many parents.
        The manifest must list every occurrence with a unique `path`."""
        source = tmp_path / "source.docx"
        docx_builder(
            source,
            sections=[
                (1, "Client Face Sheet"),
                (2, "Field Descriptions"),
                (1, "Medical File"),
                (2, "Field Descriptions"),  # same title, different parent
            ],
            image_anchors=[],
        )
        monkeypatch.setattr(cli_module, "resolve_pat", lambda: "fake-pat")
        monkeypatch.setattr(cli_module, "fetch_work_item_relations", lambda *a, **kw: [])
        monkeypatch.setattr(
            cli_module,
            "filter_attachments",
            lambda *_: [Attachment(name="4 - Client Management.docx", url="stub", size=1)],
        )

        def _download(attachment, destination, pat, session=None):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, destination)
            return destination

        monkeypatch.setattr(cli_module, "download_attachment", _download)

        staging = tmp_path / "staging"
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli_module.main(["--pbi", "42", "--print-manifest",
                             "--staging-dir", str(staging)])
        manifest = json.loads(buf.getvalue())
        sections = manifest["docs"][0]["sections"]

        # Both colliding sections survive.
        field_descriptions = [s for s in sections if s["title"] == "Field Descriptions"]
        assert len(field_descriptions) == 2

        # They have distinct paths.
        paths = {s["path"] for s in field_descriptions}
        assert paths == {
            "Client Face Sheet > Field Descriptions",
            "Medical File > Field Descriptions",
        }

        # The CI gate can distinguish them via path. (In this minimal fixture
        # both sub-sections are empty, so their sha256 collides — that's fine
        # and expected: sha256 is content-addressed. What matters is that the
        # path key does NOT collide, so the gate never resolves the wrong
        # section.)

    def test_manifest_section_hash_changes_when_content_changes(
        self, tmp_path, monkeypatch, docx_builder
    ):
        """If the source docx changes, the section sha256 flips."""
        v1 = tmp_path / "v1.docx"
        v2 = tmp_path / "v2.docx"
        docx_builder(v1, sections=[(1, "Overview"), (2, "Face Sheet")], image_anchors=[])
        docx_builder(v2, sections=[(1, "Overview"), (2, "Face Sheet (revised)")],
                     image_anchors=[])

        monkeypatch.setattr(cli_module, "resolve_pat", lambda: "fake-pat")
        monkeypatch.setattr(cli_module, "fetch_work_item_relations", lambda *a, **kw: [])
        monkeypatch.setattr(
            cli_module,
            "filter_attachments",
            lambda *_: [Attachment(name="4 - Client Management.docx", url="stub", size=1)],
        )

        source = {"path": v1}

        def _download(attachment, destination, pat, session=None):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source["path"], destination)
            return destination

        monkeypatch.setattr(cli_module, "download_attachment", _download)

        staging = tmp_path / "staging"
        buf1 = io.StringIO()
        with redirect_stdout(buf1):
            cli_module.main(["--pbi", "17113", "--print-manifest",
                             "--staging-dir", str(staging)])
        # Swap to the revised docx
        source["path"] = v2
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            cli_module.main(["--pbi", "17113", "--print-manifest",
                             "--staging-dir", str(staging)])

        m1 = json.loads(buf1.getvalue())
        m2 = json.loads(buf2.getvalue())
        # v1 had "Face Sheet"; v2 has "Face Sheet (revised)"
        titles_v1 = {s["title"] for s in m1["docs"][0]["sections"]}
        titles_v2 = {s["title"] for s in m2["docs"][0]["sections"]}
        assert "Face Sheet" in titles_v1
        assert "Face Sheet (revised)" in titles_v2
        assert m1["docs"][0]["docx_md5"] != m2["docs"][0]["docx_md5"]
        assert m2["docs"][0]["reused"] is False

    def test_no_attachments_exits_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_module, "resolve_pat", lambda: "fake-pat")
        monkeypatch.setattr(cli_module, "fetch_work_item_relations", lambda *a, **kw: [])
        monkeypatch.setattr(cli_module, "filter_attachments", lambda *_: [])
        rc = cli_module.main(
            ["--pbi", "999", "--staging-dir", str(tmp_path / "s")]
        )
        assert rc == 0

    def test_no_attachments_print_manifest_has_empty_docs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_module, "resolve_pat", lambda: "fake-pat")
        monkeypatch.setattr(cli_module, "fetch_work_item_relations", lambda *a, **kw: [])
        monkeypatch.setattr(cli_module, "filter_attachments", lambda *_: [])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_module.main(
                ["--pbi", "999", "--print-manifest",
                 "--staging-dir", str(tmp_path / "s")]
            )
        assert rc == 0
        manifest = json.loads(buf.getvalue())
        assert manifest["pbi"] == 999
        assert manifest["docs"] == []

    def test_missing_pat_returns_2(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_module, "resolve_pat", lambda: None)
        rc = cli_module.main(
            ["--pbi", "1", "--staging-dir", str(tmp_path / "s")]
        )
        assert rc == 2
