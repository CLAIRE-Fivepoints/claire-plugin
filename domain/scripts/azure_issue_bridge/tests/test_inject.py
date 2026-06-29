"""
Unit tests for azure_issue_bridge inject subcommand and parse_subject_parts helper.

Tests cover:
- parse_subject_parts() extracts (area, title) from ADO subject formats
- cmd_inject dry-run: prints parsed result + full pipeline plan, no side effects
- cmd_inject live mode: runs full pipeline (create_issue, add_label, sync_branch,
  prepare_worktree, assign) in order, with cleanup commands in output
- cmd_inject rejects non-PBI subjects
- cmd_inject --repo and --agent overrides
- cmd_inject aborts and returns 1 on each step failure (no assignment if worktree fails)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**kwargs: object) -> argparse.Namespace:
    defaults = {
        "from_addr": "azuredevops@microsoft.com",
        "subject": "Product Backlog Item 12345 - DEV - Client Management test",
        "dry_run": False,
        "repo": None,
        "agent": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@dataclass
class _FakeIssue:
    url: str
    number: int


def _fake_issue(number: int = 99) -> _FakeIssue:
    return _FakeIssue(
        url=f"https://github.com/org/repo/issues/{number}",
        number=number,
    )


# ---------------------------------------------------------------------------
# cmd_inject — dry-run
# ---------------------------------------------------------------------------


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

    def test_dry_run_prints_all_pipeline_steps(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        args = _make_args(dry_run=True)
        cmd_inject(args)
        out = capsys.readouterr().out
        assert "create_issue" in out
        assert "add_label" in out
        assert "sync_branch" in out
        assert "prepare_worktree" in out
        assert "assign" in out

    def test_dry_run_no_gh_calls(self) -> None:
        args = _make_args(dry_run=True)
        with patch("azure_issue_bridge.bridge.subprocess.run") as mock_run:
            cmd_inject(args)
            mock_run.assert_not_called()

    def test_dry_run_shows_repo_override(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_args(dry_run=True, repo="CLAIRE-Fivepoints/fivepoints")
        cmd_inject(args)
        out = capsys.readouterr().out
        assert "CLAIRE-Fivepoints/fivepoints" in out

    def test_dry_run_shows_agent_override(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_args(dry_run=True, agent="my-bot")
        cmd_inject(args)
        out = capsys.readouterr().out
        assert "my-bot" in out


# ---------------------------------------------------------------------------
# cmd_inject — live (mocked)
# ---------------------------------------------------------------------------


class TestCmdInjectLive:
    def _run_live(
        self,
        args: argparse.Namespace,
        issue_number: int = 99,
    ):
        """Run cmd_inject with all external calls mocked. Returns (rc, mocks dict)."""
        fake = _fake_issue(issue_number)

        with (
            patch(
                "azure_issue_bridge.bridge.create_github_issue",
                return_value=fake,
            ) as mock_create,
            patch("azure_issue_bridge.bridge.add_issue_label") as mock_label,
            patch("azure_issue_bridge.sync.RealBranchSync") as MockSyncClass,
            patch(
                "azure_issue_bridge.worktree.RealWorktreePrepare"
            ) as MockWorktreeClass,
            patch(
                "azure_issue_bridge.bridge.assign_github_issue"
            ) as mock_assign,
        ):
            mock_sync = MagicMock()
            MockSyncClass.return_value = mock_sync
            mock_worktree = MagicMock()
            mock_worktree.prepare.return_value = f"/mock/worktrees/pbi-{issue_number}"
            MockWorktreeClass.return_value = mock_worktree

            rc = cmd_inject(args)
            return rc, {
                "create": mock_create,
                "label": mock_label,
                "sync": mock_sync,
                "worktree": mock_worktree,
                "assign": mock_assign,
            }

    def test_happy_path_exits_0(self) -> None:
        rc, _ = self._run_live(_make_args())
        assert rc == 0

    def test_live_calls_create_github_issue(self) -> None:
        _, mocks = self._run_live(_make_args())
        mocks["create"].assert_called_once()
        work_item = mocks["create"].call_args[0][0]
        assert work_item.id == 12345
        assert work_item.title == "Client Management test"
        assert work_item.area_path == "DEV"
        assert work_item.state == "To Do"
        assert work_item.work_item_type == "Task"

    def test_label_called_with_role_label(self) -> None:
        _, mocks = self._run_live(_make_args())
        mocks["label"].assert_called_once()
        _, issue_number, label = mocks["label"].call_args[0]
        assert label.startswith("role:")
        assert label.endswith("-dev")
        assert issue_number == 99

    def test_sync_branch_called(self) -> None:
        _, mocks = self._run_live(_make_args())
        mocks["sync"].sync_branch.assert_called_once()

    def test_worktree_prepare_called_with_pbi_branch(self) -> None:
        _, mocks = self._run_live(_make_args(), issue_number=99)
        mocks["worktree"].prepare.assert_called_once()
        kw = mocks["worktree"].prepare.call_args[1]
        assert kw["branch_name"] == "pbi-99"
        assert kw["issue"] == 99

    def test_assign_called_with_agent(self) -> None:
        _, mocks = self._run_live(_make_args())
        mocks["assign"].assert_called_once()

    def test_pipeline_order_label_sync_worktree_assign(self) -> None:
        """Verify execution order: label → sync → worktree → assign."""
        call_order: list[str] = []
        fake = _fake_issue(42)

        with (
            patch(
                "azure_issue_bridge.bridge.create_github_issue", return_value=fake
            ),
            patch(
                "azure_issue_bridge.bridge.add_issue_label",
                side_effect=lambda *a, **kw: call_order.append("label"),
            ),
            patch("azure_issue_bridge.sync.RealBranchSync") as MockSyncClass,
            patch(
                "azure_issue_bridge.worktree.RealWorktreePrepare"
            ) as MockWorktreeClass,
            patch(
                "azure_issue_bridge.bridge.assign_github_issue",
                side_effect=lambda *a, **kw: call_order.append("assign"),
            ),
        ):
            mock_sync = MagicMock()
            mock_sync.sync_branch.side_effect = (
                lambda *a, **kw: call_order.append("sync")
            )
            MockSyncClass.return_value = mock_sync
            mock_worktree = MagicMock()
            mock_worktree.prepare.side_effect = (
                lambda *a, **kw: call_order.append("worktree") or "/mock/path"
            )
            MockWorktreeClass.return_value = mock_worktree

            rc = cmd_inject(_make_args())

        assert rc == 0
        assert call_order == ["label", "sync", "worktree", "assign"]

    def test_happy_path_prints_summary(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        self._run_live(_make_args(), issue_number=151)
        out = capsys.readouterr().out
        assert "✓ Pipeline complet" in out
        assert "Issue créée" in out
        assert "Label" in out
        assert "Branch" in out
        assert "Assigné à" in out
        assert "Pour nettoyer" in out
        assert "gh issue close 151" in out

    def test_happy_path_prints_worktree_path(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        self._run_live(_make_args(), issue_number=42)
        out = capsys.readouterr().out
        assert "/mock/worktrees/pbi-42" in out
        assert "git worktree remove" in out

    def test_live_prints_issue_url(self, capsys: pytest.CaptureFixture) -> None:
        self._run_live(_make_args(), issue_number=99)
        out = capsys.readouterr().out
        assert "https://github.com/org/repo/issues/99" in out

    def test_repo_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        args = _make_args(repo="CLAIRE-Fivepoints/fivepoints-test")
        fake = _fake_issue(1)

        with (
            patch(
                "azure_issue_bridge.bridge.create_github_issue", return_value=fake
            ) as mock_create,
            patch("azure_issue_bridge.bridge.add_issue_label") as mock_label,
            patch("azure_issue_bridge.sync.RealBranchSync") as MockSyncClass,
            patch("azure_issue_bridge.worktree.RealWorktreePrepare") as MockWorktreeClass,
            patch("azure_issue_bridge.bridge.assign_github_issue"),
        ):
            MockSyncClass.return_value = MagicMock()
            mock_wt = MagicMock()
            mock_wt.prepare.return_value = "/mock/path"
            MockWorktreeClass.return_value = mock_wt
            cmd_inject(args)

        mock_label.assert_called_once_with(
            "CLAIRE-Fivepoints/fivepoints-test", fake.number, mock_label.call_args[0][2]
        )

    def test_live_runtime_error_on_create_returns_nonzero(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        args = _make_args()
        with patch(
            "azure_issue_bridge.bridge.create_github_issue",
            side_effect=RuntimeError("gh issue create failed: permission denied"),
        ):
            rc = cmd_inject(args)
        assert rc == 1
        out = capsys.readouterr().out
        assert "✗" in out

    def test_add_label_failure_exits_1(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        fake = _fake_issue(1)
        with (
            patch(
                "azure_issue_bridge.bridge.create_github_issue", return_value=fake
            ),
            patch(
                "azure_issue_bridge.bridge.add_issue_label",
                side_effect=RuntimeError("label not found"),
            ),
        ):
            rc = cmd_inject(_make_args())
        assert rc == 1
        out = capsys.readouterr().out
        assert "add_label failed" in out

    def test_sync_branch_failure_exits_1(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        fake = _fake_issue(1)
        with (
            patch(
                "azure_issue_bridge.bridge.create_github_issue", return_value=fake
            ),
            patch("azure_issue_bridge.bridge.add_issue_label"),
            patch("azure_issue_bridge.sync.RealBranchSync") as MockSyncClass,
        ):
            mock_sync = MagicMock()
            mock_sync.sync_branch.side_effect = RuntimeError("branch not found")
            MockSyncClass.return_value = mock_sync
            rc = cmd_inject(_make_args())
        assert rc == 1
        out = capsys.readouterr().out
        assert "sync_branch failed" in out

    def test_prepare_worktree_failure_exits_1_no_assign(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        fake = _fake_issue(1)
        with (
            patch(
                "azure_issue_bridge.bridge.create_github_issue", return_value=fake
            ),
            patch("azure_issue_bridge.bridge.add_issue_label"),
            patch("azure_issue_bridge.sync.RealBranchSync") as MockSyncClass,
            patch(
                "azure_issue_bridge.worktree.RealWorktreePrepare"
            ) as MockWorktreeClass,
            patch(
                "azure_issue_bridge.bridge.assign_github_issue"
            ) as mock_assign,
        ):
            MockSyncClass.return_value = MagicMock()
            mock_wt = MagicMock()
            mock_wt.prepare.side_effect = RuntimeError("git failed")
            MockWorktreeClass.return_value = mock_wt
            rc = cmd_inject(_make_args())

        assert rc == 1
        out = capsys.readouterr().out
        assert "prepare_worktree failed" in out
        mock_assign.assert_not_called()

    def test_assign_failure_exits_1(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        fake = _fake_issue(1)
        with (
            patch(
                "azure_issue_bridge.bridge.create_github_issue", return_value=fake
            ),
            patch("azure_issue_bridge.bridge.add_issue_label"),
            patch("azure_issue_bridge.sync.RealBranchSync") as MockSyncClass,
            patch(
                "azure_issue_bridge.worktree.RealWorktreePrepare"
            ) as MockWorktreeClass,
            patch(
                "azure_issue_bridge.bridge.assign_github_issue",
                side_effect=RuntimeError("assignee not found"),
            ),
        ):
            MockSyncClass.return_value = MagicMock()
            mock_wt = MagicMock()
            mock_wt.prepare.return_value = "/mock/path"
            MockWorktreeClass.return_value = mock_wt
            rc = cmd_inject(_make_args())

        assert rc == 1
        out = capsys.readouterr().out
        assert "assign failed" in out


# ---------------------------------------------------------------------------
# cmd_inject — invalid subjects
# ---------------------------------------------------------------------------


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
