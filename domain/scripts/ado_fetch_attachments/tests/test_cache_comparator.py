"""MD5 comparison + section-delta tests."""

from __future__ import annotations

from ado_fetch_attachments.cache_comparator import (
    compare_to_cache,
    diff_sections,
    md5_file,
    resolve_cache_path,
)


class TestMd5:
    def test_matches_when_content_identical(self, tmp_path):
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"hello world")
        b.write_bytes(b"hello world")
        assert md5_file(a) == md5_file(b)

    def test_differs_when_content_differs(self, tmp_path):
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"hello world")
        b.write_bytes(b"hello worlds")
        assert md5_file(a) != md5_file(b)


class TestCompareToCache:
    def test_match(self, tmp_path):
        cached = tmp_path / "cached.docx"
        fresh = tmp_path / "fresh.docx"
        cached.write_bytes(b"same")
        fresh.write_bytes(b"same")
        result = compare_to_cache(fresh, cached)
        assert result.match is True
        assert result.status == "match"

    def test_drift(self, tmp_path):
        cached = tmp_path / "cached.docx"
        fresh = tmp_path / "fresh.docx"
        cached.write_bytes(b"stale")
        fresh.write_bytes(b"fresh")
        result = compare_to_cache(fresh, cached)
        assert result.match is False
        assert result.status == "drift"
        assert result.cached_md5 != result.fresh_md5

    def test_missing_cache(self, tmp_path):
        fresh = tmp_path / "fresh.docx"
        fresh.write_bytes(b"anything")
        result = compare_to_cache(fresh, None)
        assert result.match is False
        assert result.status == "missing"
        assert result.cached_md5 is None


class TestResolveCachePath:
    def test_strips_leading_prefix_and_parens(self, tmp_path):
        (tmp_path / "FDS_CLIENT_MANAGEMENT.docx").write_bytes(b"x")
        path = resolve_cache_path(tmp_path, "4 - Client Management(1).docx")
        assert path is not None
        assert path.name == "FDS_CLIENT_MANAGEMENT.docx"

    def test_returns_none_when_no_match(self, tmp_path):
        (tmp_path / "FDS_OTHER.docx").write_bytes(b"x")
        assert resolve_cache_path(tmp_path, "Brand New Document.docx") is None

    def test_returns_none_for_empty_stem(self, tmp_path):
        assert resolve_cache_path(tmp_path, "   .docx") is None


class TestDiffSections:
    def test_detects_added_and_removed(self):
        diff = diff_sections(
            cached_sections=["Intake", "Workflows"],
            fresh_sections=["Intake", "Face Sheet", "Legal"],
        )
        assert diff.added == ["Face Sheet", "Legal"]
        assert diff.removed == ["Workflows"]
        assert diff.common == ["Intake"]
        assert diff.has_changes()

    def test_empty_on_identical(self):
        diff = diff_sections(["A", "B"], ["A", "B"])
        assert not diff.has_changes()
