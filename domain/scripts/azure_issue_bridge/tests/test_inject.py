"""
Unit tests for azure_issue_bridge inject subcommand and parse_subject_parts helper.

Tests cover:
- parse_subject_parts() extracts (area, title) from ADO subject formats
- cmd_inject dry-run: prints parsed result, no gh calls
- cmd_inject live mode: calls create_github_issue with synthetic WorkItem
- cmd_inject rejects non-PBI subjects
- cmd_inject --repo override sets target repo
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from azure_issue_bridge.bridge import parse_subject_parts
from azure_issue_bridge.cli import cmd_inject


# ---------------------------------------------------------------------------
# parse_subject_parts
# ---------------------------------------------------------------------------


class TestParseSubjectParts:
    def test_standard_pbi_format(self) -> None:
        area, title = parse_subject_parts(
            "Product Backlog Item 12345 - DEV - Client Management test"
        )
        assert area == "DEV"
        assert title == "Client Management test"

    def test_task_format(self) -> None:
        area, title = parse_subject_parts(
            "Task 13644 - DEV - implement feature X"
        )
        assert area == "DEV"
        assert title == "implement feature X"

    def test_title_with_dashes(self) -> None:
        area, title = parse_subject_parts(
            "Product Backlog Item 999 - QA - Fix bug - edge case"
        )
        assert area == "QA"
        assert title == "Fix bug - edge case"

    def test_no_area_no_title(self) -> None:
        area, title = parse_subject_parts("Product Backlog Item 42")
        assert area == ""
        assert title == ""

    def test_non_pbi_subject_returns_empty(self) -> None:
        area, title = parse_subject_parts("Hello from someone")
        assert area == ""
        assert title == ""


# ---------------------------------------------------------------------------
# cmd_inject
# ---------------------------------------------------------------------------


def _make_args(**kwargs: object) -> argparse.Namespace:
    defaults = {
        "from_addr": "azuredevops@microsoft.com",
        "subject": "Product Backlog Item 12345 - DEV - Client Management test",
        "dry_run": False,
        "repo": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdInjectDryRun:
    def test_dry_run_prints_parsed_pbi(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_args(dry_run=True)
        rc = cmd_inject(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "[dry-run]" in out
        assert "12345" in out
        assert "Client Management test" in out
        assert "DEV" in out

    def test_dry_run_no_gh_calls(self) -> None:
        args = _make_args(dry_run=True)
        with patch("azure_issue_bridge.bridge.subprocess.run") as mock_run:
            cmd_inject(args)
            mock_run.assert_not_called()

    def test_dry_run_shows_repo_override(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_args(dry_run=True, repo="CLAIRE-Fivepoints/fivepoints-test")
        cmd_inject(args)
        out = capsys.readouterr().out
        assert "CLAIRE-Fivepoints/fivepoints-test" in out


class TestCmdInjectLive:
    def test_live_calls_create_github_issue(self) -> None:
        args = _make_args()
        with patch(
            "azure_issue_bridge.bridge.create_github_issue",
            return_value="https://github.com/org/repo/issues/99",
        ) as mock_create:
            rc = cmd_inject(args)
        assert rc == 0
        mock_create.assert_called_once()
        work_item = mock_create.call_args[0][0]
        assert work_item.id == 12345
        assert work_item.title == "Client Management test"
        assert work_item.area_path == "DEV"
        assert work_item.state == "To Do"
        assert work_item.work_item_type == "Task"

    def test_live_prints_issue_url(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_args()
        with patch(
            "azure_issue_bridge.bridge.create_github_issue",
            return_value="https://github.com/org/repo/issues/99",
        ):
            cmd_inject(args)
        out = capsys.readouterr().out
        assert "https://github.com/org/repo/issues/99" in out

    def test_live_repo_override_sets_env(self) -> None:
        args = _make_args(repo="CLAIRE-Fivepoints/fivepoints-test")
        captured_repo: list[str] = []

        def fake_create(work_item):  # type: ignore[no-untyped-def]
            import os
            captured_repo.append(os.environ.get("ADO_BRIDGE_REPO", ""))
            return "https://github.com/org/repo/issues/1"

        with patch("azure_issue_bridge.bridge.create_github_issue", side_effect=fake_create):
            cmd_inject(args)

        assert captured_repo == ["CLAIRE-Fivepoints/fivepoints-test"]

    def test_live_runtime_error_returns_nonzero(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_args()
        with patch(
            "azure_issue_bridge.bridge.create_github_issue",
            side_effect=RuntimeError("gh issue create failed: permission denied"),
        ):
            rc = cmd_inject(args)
        assert rc == 1
        out = capsys.readouterr().out
        assert "✗" in out


class TestCmdInjectRejectsNonPBI:
    def test_non_pbi_subject_returns_1(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_args(subject="Hello from someone", dry_run=True)
        rc = cmd_inject(args)
        assert rc == 1
        out = capsys.readouterr().out
        assert "✗" in out

    def test_empty_subject_returns_1(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_args(subject="", dry_run=True)
        rc = cmd_inject(args)
        assert rc == 1
