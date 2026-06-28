"""
Unit tests for WorktreePrepare adapters and pipeline integration.

Tests:
- MockWorktreePrepare records calls in self.prepared
- RealWorktreePrepare raises on git failures
- process_emails calls prepare_worktree before assign_github_issue
- process_emails aborts (no assignment) when prepare_worktree raises
- Branch name is configurable (not hard-coded)
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from azure_issue_bridge.worktree import MockWorktreePrepare


# ---------------------------------------------------------------------------
# MockWorktreePrepare
# ---------------------------------------------------------------------------


class TestMockWorktreePrepare:
    def test_prepare_records_call(self) -> None:
        mock = MockWorktreePrepare()
        path = mock.prepare(
            repo="CLAIRE-Fivepoints/fivepoints",
            issue=42,
            base_branch="develop",
            branch_name="pbi-42",
        )
        assert path == "/mock/worktrees/pbi-42"
        assert len(mock.prepared) == 1
        assert mock.prepared[0] == {
            "repo": "CLAIRE-Fivepoints/fivepoints",
            "issue": 42,
            "base_branch": "develop",
            "branch": "pbi-42",
        }

    def test_prepare_records_multiple_calls(self) -> None:
        mock = MockWorktreePrepare()
        mock.prepare(repo="org/repo", issue=1, base_branch="main", branch_name="pbi-1")
        mock.prepare(repo="org/repo", issue=2, base_branch="main", branch_name="pbi-2")
        assert len(mock.prepared) == 2
        assert mock.prepared[0]["issue"] == 1
        assert mock.prepared[1]["issue"] == 2

    def test_prepare_returns_path_with_branch_name(self) -> None:
        mock = MockWorktreePrepare()
        path = mock.prepare(
            repo="org/repo",
            issue=99,
            base_branch="develop",
            branch_name="custom-branch",
        )
        assert path == "/mock/worktrees/custom-branch"

    def test_instances_do_not_share_prepared_list(self) -> None:
        m1 = MockWorktreePrepare()
        m2 = MockWorktreePrepare()
        m1.prepare(repo="r", issue=1, base_branch="b", branch_name="pbi-1")
        assert len(m1.prepared) == 1
        assert len(m2.prepared) == 0

    def test_branch_name_configurable(self) -> None:
        mock = MockWorktreePrepare()
        branch = "feature/custom-name"
        mock.prepare(repo="r", issue=10, base_branch="develop", branch_name=branch)
        assert mock.prepared[0]["branch"] == branch
        assert mock.prepared[0]["branch"] != "pbi-10"


# ---------------------------------------------------------------------------
# RealWorktreePrepare
# ---------------------------------------------------------------------------


class TestRealWorktreePrepare:
    def test_raises_when_git_fetch_fails(self, tmp_path) -> None:
        from azure_issue_bridge.worktree import RealWorktreePrepare

        prepare = RealWorktreePrepare(local_path=str(tmp_path))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="fatal: error")
            with pytest.raises(RuntimeError, match="git command failed"):
                prepare.prepare(
                    repo="org/repo",
                    issue=1,
                    base_branch="develop",
                    branch_name="pbi-1",
                )

    def test_raises_when_git_worktree_add_fails(self, tmp_path) -> None:
        from azure_issue_bridge.worktree import RealWorktreePrepare

        prepare = RealWorktreePrepare(local_path=str(tmp_path))

        def run_side_effect(cmd, **kwargs):
            if "fetch" in cmd:
                return MagicMock(returncode=0, stderr="", stdout="")
            return MagicMock(returncode=128, stderr="fatal: branch already exists")

        with patch("subprocess.run", side_effect=run_side_effect):
            with pytest.raises(RuntimeError, match="git command failed"):
                prepare.prepare(
                    repo="org/repo",
                    issue=2,
                    base_branch="develop",
                    branch_name="pbi-2",
                )

    def test_returns_existing_worktree_without_git_call(self, tmp_path) -> None:
        from azure_issue_bridge.worktree import RealWorktreePrepare

        worktree_path = tmp_path / ".claire" / "worktrees" / "issue-5"
        worktree_path.mkdir(parents=True)

        prepare = RealWorktreePrepare(local_path=str(tmp_path))

        with patch("subprocess.run") as mock_run:
            result = prepare.prepare(
                repo="org/repo",
                issue=5,
                base_branch="develop",
                branch_name="pbi-5",
            )
        # Existing worktree: no subprocess calls
        mock_run.assert_not_called()
        assert result == str(worktree_path)

    def test_successful_prepare_returns_worktree_path(self, tmp_path) -> None:
        from azure_issue_bridge.worktree import RealWorktreePrepare

        prepare = RealWorktreePrepare(local_path=str(tmp_path))
        expected_path = tmp_path / ".claire" / "worktrees" / "issue-7"

        with patch("subprocess.run", return_value=MagicMock(returncode=0, stderr="")):
            result = prepare.prepare(
                repo="org/repo",
                issue=7,
                base_branch="develop",
                branch_name="pbi-7",
            )
        assert result == str(expected_path)


# ---------------------------------------------------------------------------
# Pipeline integration: process_emails calls worktree then assign
# ---------------------------------------------------------------------------


def _make_email(subject: str, message_id: str = "msg-001") -> MagicMock:
    email = MagicMock()
    email.subject = subject
    email.message_id = message_id
    return email


def _metadata_task_to_do(pbi_id: str) -> dict:
    return {pbi_id: {"type": "Task", "parent_id": None, "state": "To Do"}}


def _make_work_item(item_id: int, title: str) -> MagicMock:
    return MagicMock(
        id=item_id,
        title=title,
        description="",
        acceptance_criteria="",
        tags=[],
        area_path="",
        state="To Do",
        assigned_to="",
        parent_id=None,
        work_item_type="Task",
    )


def _make_config(client: str = "fivepoints"):
    from azure_issue_bridge.bridge import BridgeConfig
    return BridgeConfig(
        agent="claire-test-ai",
        client=client,
        source_repo="org/source",
        target_repo="org/target",
        sync_branch="develop",
    )


class TestPipelineWorktreeIntegration:
    """process_emails must call prepare_worktree before assign_github_issue."""

    def test_worktree_called_before_assign(self) -> None:
        from azure_issue_bridge.bridge import GitHubIssue, process_emails

        mock_wt = MockWorktreePrepare()
        email = _make_email("Task 42 - DEV - some task")
        config = _make_config()

        call_order: list[str] = []

        def mock_prepare(*args, **kwargs):
            call_order.append("prepare")
            return "/mock/worktrees/pbi-42"

        def mock_assign(*args, **kwargs):
            call_order.append("assign")

        mock_wt.prepare = mock_prepare

        with ExitStack() as stack:
            stack.enter_context(patch(
                "claire_py.email.watcher.list_unread_replies",
                return_value=[email],
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=_metadata_task_to_do("42"),
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.fetch_work_item",
                return_value=_make_work_item(42, "Some Task"),
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.create_github_issue",
                return_value=GitHubIssue(
                    url="https://github.com/org/target/issues/42", number=42
                ),
            ))
            stack.enter_context(patch("azure_issue_bridge.bridge.add_issue_label"))
            stack.enter_context(patch("azure_issue_bridge.bridge.sync_github_branch"))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.assign_github_issue",
                side_effect=mock_assign,
            ))
            stack.enter_context(patch("azure_issue_bridge.bridge.save_processed_id"))
            stack.enter_context(patch("azure_issue_bridge.bridge.archive_email"))
            stack.enter_context(patch("azure_issue_bridge.bridge.save_state"))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.load_processed_ids", return_value=set()
            ))
            process_emails(config=config, worktree_prepare=mock_wt)

        assert call_order == ["prepare", "assign"], (
            "Expected prepare before assign, got: {}".format(call_order)
        )

    def test_pipeline_aborts_when_prepare_raises(self) -> None:
        from azure_issue_bridge.bridge import GitHubIssue, process_emails

        mock_wt = MockWorktreePrepare()
        mock_wt.prepare = MagicMock(side_effect=RuntimeError("git worktree add failed"))

        email = _make_email("Task 55 - DEV - failing task")
        config = _make_config()

        with ExitStack() as stack:
            stack.enter_context(patch(
                "claire_py.email.watcher.list_unread_replies",
                return_value=[email],
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=_metadata_task_to_do("55"),
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.fetch_work_item",
                return_value=_make_work_item(55, "Failing Task"),
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.create_github_issue",
                return_value=GitHubIssue(
                    url="https://github.com/org/target/issues/55", number=55
                ),
            ))
            stack.enter_context(patch("azure_issue_bridge.bridge.add_issue_label"))
            stack.enter_context(patch("azure_issue_bridge.bridge.sync_github_branch"))
            mock_assign = stack.enter_context(
                patch("azure_issue_bridge.bridge.assign_github_issue")
            )
            stack.enter_context(patch("azure_issue_bridge.bridge.save_processed_id"))
            stack.enter_context(patch("azure_issue_bridge.bridge.archive_email"))
            stack.enter_context(patch("azure_issue_bridge.bridge.save_state"))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.load_processed_ids", return_value=set()
            ))
            results = process_emails(config=config, worktree_prepare=mock_wt)

        # assign must NOT be called when prepare raises
        mock_assign.assert_not_called()
        # The result should record the error
        assert len(results) == 1
        assert results[0].error is not None
        assert "git worktree add failed" in results[0].error

    def test_branch_name_uses_issue_number(self) -> None:
        from azure_issue_bridge.bridge import GitHubIssue, process_emails

        mock_wt = MockWorktreePrepare()
        email = _make_email("Task 77 - DEV - branch name test")
        config = _make_config()

        with ExitStack() as stack:
            stack.enter_context(patch(
                "claire_py.email.watcher.list_unread_replies",
                return_value=[email],
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=_metadata_task_to_do("77"),
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.fetch_work_item",
                return_value=_make_work_item(77, "Branch Name Task"),
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.create_github_issue",
                return_value=GitHubIssue(
                    url="https://github.com/org/target/issues/77", number=77
                ),
            ))
            stack.enter_context(patch("azure_issue_bridge.bridge.add_issue_label"))
            stack.enter_context(patch("azure_issue_bridge.bridge.sync_github_branch"))
            stack.enter_context(patch("azure_issue_bridge.bridge.assign_github_issue"))
            stack.enter_context(patch("azure_issue_bridge.bridge.save_processed_id"))
            stack.enter_context(patch("azure_issue_bridge.bridge.archive_email"))
            stack.enter_context(patch("azure_issue_bridge.bridge.save_state"))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.load_processed_ids", return_value=set()
            ))
            process_emails(config=config, worktree_prepare=mock_wt)

        assert len(mock_wt.prepared) == 1
        assert mock_wt.prepared[0]["branch"] == "pbi-77"
        assert mock_wt.prepared[0]["issue"] == 77
        assert mock_wt.prepared[0]["base_branch"] == "develop"
        assert mock_wt.prepared[0]["repo"] == "org/target"

    def test_label_uses_client_config(self) -> None:
        from azure_issue_bridge.bridge import GitHubIssue, process_emails

        mock_wt = MockWorktreePrepare()
        email = _make_email("Task 88 - DEV - label test")
        config = _make_config(client="myapp")

        with ExitStack() as stack:
            stack.enter_context(patch(
                "claire_py.email.watcher.list_unread_replies",
                return_value=[email],
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=_metadata_task_to_do("88"),
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.fetch_work_item",
                return_value=_make_work_item(88, "Label Test"),
            ))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.create_github_issue",
                return_value=GitHubIssue(
                    url="https://github.com/org/target/issues/88", number=88
                ),
            ))
            mock_add_label = stack.enter_context(
                patch("azure_issue_bridge.bridge.add_issue_label")
            )
            stack.enter_context(patch("azure_issue_bridge.bridge.sync_github_branch"))
            stack.enter_context(patch("azure_issue_bridge.bridge.assign_github_issue"))
            stack.enter_context(patch("azure_issue_bridge.bridge.save_processed_id"))
            stack.enter_context(patch("azure_issue_bridge.bridge.archive_email"))
            stack.enter_context(patch("azure_issue_bridge.bridge.save_state"))
            stack.enter_context(patch(
                "azure_issue_bridge.bridge.load_processed_ids", return_value=set()
            ))
            process_emails(config=config, worktree_prepare=mock_wt)

        mock_add_label.assert_called_once_with("org/target", 88, "role:myapp-dev")
