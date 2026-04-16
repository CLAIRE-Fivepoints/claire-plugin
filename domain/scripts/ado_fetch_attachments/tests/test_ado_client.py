"""PAT resolution + attachment filter tests."""

from __future__ import annotations

from pathlib import Path

from ado_fetch_attachments.ado_client import (
    Attachment,
    filter_attachments,
    resolve_pat,
)


class TestResolvePat:
    def test_prefers_write_pat_over_dev_pat(self):
        env = {
            "AZURE_DEVOPS_PAT": "read",
            "AZURE_DEVOPS_DEV_PAT": "dev",
            "AZURE_DEVOPS_WRITE_PAT": "write",
        }
        assert resolve_pat(env=env, env_file=Path("/nonexistent")) == "write"

    def test_prefers_dev_pat_over_read_pat(self):
        env = {"AZURE_DEVOPS_PAT": "read", "AZURE_DEVOPS_DEV_PAT": "dev"}
        assert resolve_pat(env=env, env_file=Path("/nonexistent")) == "dev"

    def test_falls_back_to_read_pat(self):
        env = {"AZURE_DEVOPS_PAT": "read"}
        assert resolve_pat(env=env, env_file=Path("/nonexistent")) == "read"

    def test_env_file_when_env_empty(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("AZURE_DEVOPS_PAT=from-file\n")
        assert resolve_pat(env={}, env_file=env_file) == "from-file"

    def test_env_file_respects_priority(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "AZURE_DEVOPS_PAT=read\nAZURE_DEVOPS_WRITE_PAT=write\n"
        )
        assert resolve_pat(env={}, env_file=env_file) == "write"

    def test_env_beats_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("AZURE_DEVOPS_PAT=file\n")
        assert resolve_pat(env={"AZURE_DEVOPS_PAT": "env"}, env_file=env_file) == "env"

    def test_returns_none_when_nothing_set(self, tmp_path):
        assert resolve_pat(env={}, env_file=tmp_path / "missing") is None

    def test_ignores_empty_values(self, tmp_path):
        env = {"AZURE_DEVOPS_WRITE_PAT": "", "AZURE_DEVOPS_PAT": "actual"}
        assert resolve_pat(env=env, env_file=Path("/nonexistent")) == "actual"

    def test_env_file_skips_comments_and_blanks(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# a comment\n\nAZURE_DEVOPS_PAT=ok\n"
        )
        assert resolve_pat(env={}, env_file=env_file) == "ok"


class TestFilterAttachments:
    def test_keeps_only_attached_files(self):
        relations = [
            {"rel": "ParentLink", "url": "http://x/parent"},
            {
                "rel": "AttachedFile",
                "url": "http://x/att/1",
                "attributes": {"name": "fds.docx", "resourceSize": 1234},
            },
            {"rel": "PullRequest", "url": "http://x/pr/1"},
        ]
        attachments = filter_attachments(relations)
        assert attachments == [Attachment(name="fds.docx", url="http://x/att/1", size=1234)]

    def test_ignores_attachment_without_url(self):
        relations = [{"rel": "AttachedFile", "attributes": {"name": "broken"}}]
        assert filter_attachments(relations) == []

    def test_defaults_name_when_missing(self):
        relations = [
            {"rel": "AttachedFile", "url": "http://x/att/a", "attributes": {}}
        ]
        result = filter_attachments(relations)
        assert result == [Attachment(name="attachment", url="http://x/att/a", size=None)]
