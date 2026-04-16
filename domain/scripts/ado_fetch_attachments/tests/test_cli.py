"""End-to-end CLI tests exercising --diff-only and drift action generation.

ADO calls and attachment downloads are stubbed at the module level — the test
walks the CLI from argparse to action-file emission without touching the network.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ado_fetch_attachments import cli as cli_module
from ado_fetch_attachments.ado_client import Attachment


@pytest.fixture
def stub_ado(monkeypatch, docx_builder, tmp_path):
    """Stub PAT resolution, attachment listing, and download with a local docx."""
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
    def test_match_exits_zero(self, tmp_path, stub_ado):
        # Put the same docx into the cache dir as FDS_CLIENT_MANAGEMENT.docx
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        shutil.copy(stub_ado, cache_dir / "FDS_CLIENT_MANAGEMENT.docx")
        staging = tmp_path / "staging"
        rc = cli_module.main(
            [
                "--pbi",
                "17113",
                "--diff-only",
                "--cache-dir",
                str(cache_dir),
                "--staging-dir",
                str(staging),
            ]
        )
        assert rc == 0
        # diff-only: no image index was written
        assert not list(staging.rglob("FDS_*_IMAGE_INDEX.md"))

    def test_drift_diff_only_exits_one(self, tmp_path, stub_ado, docx_builder):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        # Cached version is intentionally different (no Face Sheet section)
        docx_builder(
            cache_dir / "FDS_CLIENT_MANAGEMENT.docx",
            sections=[(1, "Overview"), (2, "Workflows")],
            image_anchors=[],
        )
        staging = tmp_path / "staging"
        rc = cli_module.main(
            [
                "--pbi",
                "17113",
                "--diff-only",
                "--cache-dir",
                str(cache_dir),
                "--staging-dir",
                str(staging),
            ]
        )
        assert rc == 1
        # diff-only: did not write images/index yet
        assert not list(staging.rglob("FDS_*_IMAGE_INDEX.md"))

    def test_drift_writes_action_for_auto_issue(self, tmp_path, stub_ado, docx_builder):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        docx_builder(
            cache_dir / "FDS_CLIENT_MANAGEMENT.docx",
            sections=[(1, "Overview")],
            image_anchors=[],
        )
        staging = tmp_path / "staging"
        rc = cli_module.main(
            [
                "--pbi",
                "17113",
                "--auto-issue",
                "--cache-dir",
                str(cache_dir),
                "--staging-dir",
                str(staging),
                "--issue-repo",
                "test/repo",
            ]
        )
        assert rc == 1
        actions = list((staging / "17113").glob("drift_action_*.json"))
        assert len(actions) == 1
        payload = json.loads(actions[0].read_text())
        assert payload["action"] == "create_issue"
        assert payload["repo"] == "test/repo"
        assert "PBI #17113" in payload["title"]
        body = Path(payload["body_file"]).read_text()
        assert "Face Sheet" in body  # added section shown in body
        # image index + images written for auto-issue flow
        assert (staging / "17113" / "FDS_CLIENT_MANAGEMENT_IMAGE_INDEX.md").is_file()
        assert list((staging / "17113" / "FDS_CLIENT_MANAGEMENT_images").glob("image*.png"))

    def test_drift_without_auto_issue_marks_action_none(self, tmp_path, stub_ado, docx_builder):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        docx_builder(
            cache_dir / "FDS_CLIENT_MANAGEMENT.docx",
            sections=[(1, "Overview")],
            image_anchors=[],
        )
        staging = tmp_path / "staging"
        rc = cli_module.main(
            [
                "--pbi",
                "17113",
                "--cache-dir",
                str(cache_dir),
                "--staging-dir",
                str(staging),
            ]
        )
        # exit 1 because drift detected, but no auto-issue flag
        assert rc == 1
        action = json.loads(
            next((staging / "17113").glob("drift_action_*.json")).read_text()
        )
        assert action["action"] == "none"

    def test_missing_pat_returns_2(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_module, "resolve_pat", lambda: None)
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        rc = cli_module.main(
            [
                "--pbi",
                "1",
                "--diff-only",
                "--cache-dir",
                str(cache_dir),
                "--staging-dir",
                str(tmp_path / "s"),
            ]
        )
        assert rc == 2
