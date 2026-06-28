"""
Tests for azure_issue_bridge.sync and the sync_github_branch step in process_emails().

Covers:
- MockBranchSync.syncs records each call
- process_emails() calls sync_github_branch after issue creation, before archiving
- Sync failure aborts the pipeline (result.error set, emails not archived)
- dry-run does not call sync_github_branch
- sync_github_branch is always called (no optional adapter)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from azure_issue_bridge.sync import MockBranchSync


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_email(
    subject: str = "Task 1234 - DEV - Something", message_id: str = "msg-001"
) -> Any:
    email = MagicMock()
    email.subject = subject
    email.message_id = message_id
    return email


def make_work_item(pbi_id: int = 1234) -> Any:
    from azure_issue_bridge.bridge import WorkItem

    return WorkItem(
        id=pbi_id,
        title="Test task",
        description="desc",
        acceptance_criteria="",
        work_item_type="Task",
    )


def make_create_decision(pbi_id: str = "1234", emails: list[Any] | None = None) -> Any:
    decision = MagicMock()
    decision.action = "create"
    decision.pbi_id = pbi_id
    decision.emails = emails or [make_email()]
    return decision


# ---------------------------------------------------------------------------
# MockBranchSync unit tests
# ---------------------------------------------------------------------------


class TestMockBranchSync:
    def test_starts_empty(self) -> None:
        mock = MockBranchSync()
        assert mock.syncs == []

    def test_records_single_call(self) -> None:
        mock = MockBranchSync()
        mock.sync_branch("org/source", "develop", "org/target", "develop")
        assert mock.syncs == [("org/source", "develop", "org/target", "develop")]

    def test_records_multiple_calls(self) -> None:
        mock = MockBranchSync()
        mock.sync_branch("org/a", "main", "org/b", "main")
        mock.sync_branch("org/c", "dev", "org/d", "dev")
        assert len(mock.syncs) == 2
        assert mock.syncs[0] == ("org/a", "main", "org/b", "main")
        assert mock.syncs[1] == ("org/c", "dev", "org/d", "dev")

    def test_each_instance_has_own_list(self) -> None:
        m1 = MockBranchSync()
        m2 = MockBranchSync()
        m1.sync_branch("org/x", "dev", "org/y", "dev")
        assert m2.syncs == []


# ---------------------------------------------------------------------------
# process_emails() + branch_sync integration tests
# ---------------------------------------------------------------------------


def _make_github_issue(number: int = 42) -> Any:
    from azure_issue_bridge.bridge import GitHubIssue

    return GitHubIssue(
        url=f"https://github.com/org/repo/issues/{number}",
        number=number,
    )


def _default_config() -> Any:
    from azure_issue_bridge.bridge import BridgeConfig

    return BridgeConfig(
        agent="claire-test-ai",
        client="fivepoints",
        source_repo="CLAIRE-Fivepoints/fivepoints-test",
        target_repo="CLAIRE-Fivepoints/fivepoints",
        sync_branch="develop",
    )


class TestProcessEmailsSync:
    """process_emails() must call branch_sync.sync_branch after issue creation, before archiving."""

    def _run_process_emails(
        self,
        dry_run: bool = False,
        branch_sync: Any = None,
    ) -> tuple[list[Any], Any, Any, Any]:
        """Standard fixture: returns (results, mock_bs, mock_save, mock_archive)."""
        from azure_issue_bridge.bridge import process_emails
        from azure_issue_bridge.worktree import MockWorktreePrepare

        email = make_email()
        work_item = make_work_item()
        decision = make_create_decision(emails=[email])
        config = _default_config()
        mock_bs = branch_sync if branch_sync is not None else MockBranchSync()

        with (
            patch("claire_py.email.watcher.list_unread_replies", return_value=[email]),
            patch("azure_issue_bridge.bridge.load_processed_ids", return_value=set()),
            patch("azure_issue_bridge.bridge.triage_emails", return_value=[decision]),
            patch("azure_issue_bridge.bridge.fetch_work_item", return_value=work_item),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
            patch(
                "azure_issue_bridge.bridge.create_github_issue",
                return_value=_make_github_issue(42),
            ),
            patch("azure_issue_bridge.bridge.add_issue_label"),
            patch("azure_issue_bridge.bridge.assign_github_issue"),
            patch("azure_issue_bridge.bridge.save_processed_id") as mock_save,
            patch("azure_issue_bridge.bridge.archive_email") as mock_archive,
            patch("azure_issue_bridge.bridge.save_state"),
        ):
            results = process_emails(
                dry_run=dry_run,
                config=config,
                branch_sync=mock_bs,
                worktree_prepare=MockWorktreePrepare(),
            )

        return results, mock_bs, mock_save, mock_archive

    def test_sync_called_once_after_issue_creation(self) -> None:
        results, mock_bs, mock_save, _ = self._run_process_emails()

        assert len(results) == 1
        assert results[0].error is None
        assert mock_bs.syncs == [
            (
                "CLAIRE-Fivepoints/fivepoints-test",
                "develop",
                "CLAIRE-Fivepoints/fivepoints",
                "develop",
            )
        ]
        mock_save.assert_called_once()

    def test_sync_called_before_email_archiving(self) -> None:
        call_order: list[str] = []

        from azure_issue_bridge.bridge import GitHubIssue, process_emails
        from azure_issue_bridge.worktree import MockWorktreePrepare

        email = make_email()
        work_item = make_work_item()
        decision = make_create_decision(emails=[email])

        class OrderTrackingBranchSync:
            def sync_branch(self, *args: Any, **kwargs: Any) -> None:
                call_order.append("sync")

        def fake_archive(msg_id: str) -> None:
            call_order.append("archive")

        with (
            patch("claire_py.email.watcher.list_unread_replies", return_value=[email]),
            patch("azure_issue_bridge.bridge.load_processed_ids", return_value=set()),
            patch("azure_issue_bridge.bridge.triage_emails", return_value=[decision]),
            patch("azure_issue_bridge.bridge.fetch_work_item", return_value=work_item),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
            patch(
                "azure_issue_bridge.bridge.create_github_issue",
                return_value=GitHubIssue(
                    url="https://github.com/org/repo/issues/42", number=42
                ),
            ),
            patch("azure_issue_bridge.bridge.add_issue_label"),
            patch("azure_issue_bridge.bridge.assign_github_issue"),
            patch("azure_issue_bridge.bridge.save_processed_id"),
            patch("azure_issue_bridge.bridge.archive_email", side_effect=fake_archive),
            patch("azure_issue_bridge.bridge.save_state"),
        ):
            process_emails(
                config=_default_config(),
                branch_sync=OrderTrackingBranchSync(),
                worktree_prepare=MockWorktreePrepare(),
            )

        assert call_order == ["sync", "archive"]

    def test_sync_failure_sets_error_and_skips_archiving(self) -> None:
        from azure_issue_bridge.bridge import GitHubIssue, process_emails
        from azure_issue_bridge.worktree import MockWorktreePrepare

        email = make_email()
        work_item = make_work_item()
        decision = make_create_decision(emails=[email])

        failing_sync = MockBranchSync()
        failing_sync.sync_branch = MagicMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("git push failed: unauthorized")
        )

        with (
            patch("claire_py.email.watcher.list_unread_replies", return_value=[email]),
            patch("azure_issue_bridge.bridge.load_processed_ids", return_value=set()),
            patch("azure_issue_bridge.bridge.triage_emails", return_value=[decision]),
            patch("azure_issue_bridge.bridge.fetch_work_item", return_value=work_item),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
            patch(
                "azure_issue_bridge.bridge.create_github_issue",
                return_value=GitHubIssue(
                    url="https://github.com/org/repo/issues/42", number=42
                ),
            ),
            patch("azure_issue_bridge.bridge.add_issue_label"),
            patch("azure_issue_bridge.bridge.assign_github_issue"),
            patch("azure_issue_bridge.bridge.save_processed_id") as mock_save,
            patch("azure_issue_bridge.bridge.archive_email") as mock_archive,
            patch("azure_issue_bridge.bridge.save_state"),
        ):
            results = process_emails(
                config=_default_config(),
                branch_sync=failing_sync,
                worktree_prepare=MockWorktreePrepare(),
            )

        assert len(results) == 1
        assert results[0].error is not None
        assert "git push failed" in results[0].error
        mock_save.assert_not_called()
        mock_archive.assert_not_called()

    def test_dry_run_does_not_call_sync(self) -> None:
        results, mock_bs, _, _ = self._run_process_emails(dry_run=True)

        assert mock_bs.syncs == []
        assert len(results) == 1
        assert results[0].github_issue_url == "(dry-run)"

    def test_sync_is_always_called(self) -> None:
        """branch_sync.sync_branch is always called — defaults to RealBranchSync when None."""
        results, mock_bs, mock_save, _ = self._run_process_emails()

        assert len(results) == 1
        assert results[0].error is None
        assert len(mock_bs.syncs) == 1
        mock_save.assert_called_once()
