"""Streaming MD5 tests."""

from __future__ import annotations

from ado_fetch_attachments.cache_comparator import md5_file


class TestMd5File:
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

    def test_streams_larger_than_chunk(self, tmp_path):
        big = tmp_path / "big.bin"
        big.write_bytes(b"x" * (128 * 1024 + 7))
        assert len(md5_file(big)) == 32
