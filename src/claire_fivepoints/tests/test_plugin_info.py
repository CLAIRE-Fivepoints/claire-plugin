"""Tests for the claire.plugins entry-point declaration."""
from __future__ import annotations

from pathlib import Path

from claire_fivepoints import plugin_info


class TestPluginInfo:
    def test_has_required_keys(self) -> None:
        assert "docs_dir" in plugin_info

    def test_name(self) -> None:
        assert plugin_info["name"] == "fivepoints"

    def test_docs_dir_is_path(self) -> None:
        assert isinstance(plugin_info["docs_dir"], Path)

    def test_docs_dir_exists(self) -> None:
        assert plugin_info["docs_dir"].exists(), f"docs_dir missing: {plugin_info['docs_dir']}"

    def test_docs_dir_contains_knowledge_doc(self) -> None:
        docs = list(plugin_info["docs_dir"].rglob("*.md"))
        assert docs, "docs_dir has no .md files — plugin would not be indexed by the Librarian"
