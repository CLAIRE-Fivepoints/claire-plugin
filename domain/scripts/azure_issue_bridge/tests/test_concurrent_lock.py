"""
Unit tests for the pre-creation duplicate guard in azure_issue_bridge.bridge.

Verifies that a GitHub issue is NOT created when a concurrent bridge run
has already created one between triage and the create step.

Bug: https://github.com/claire-labs/claire/issues/2256
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from azure_issue_bridge.bridge import process_emails


def make_email(subject: str, message_id: str = "msg-001") -> Any:
    """Create a mock email object."""
    email = MagicMock()
    email.subject = subject
    email.message_id = message_id
    return email


class TestPreCreationDuplicateGuard:
    """Tests for the last-mile duplicate check added before create_github_issue()."""

    def test_issue_not_created_when_already_exists_at_creation_time(self) -> None:
        """When a concurrent run created the issue between triage and creation,
        the pre-creation check detects it and skips — no duplicate is created."""
        emails = [make_email("Task 13644 - DEV - My Task", "msg-001")]

        # Triage says "create" (no issue found yet)
        create_decision = MagicMock()
        create_decision.action = "create"
        create_decision.pbi_id = "13644"
        create_decision.emails = emails

        fake_work_item = MagicMock()
        fake_work_item.id = "13644"
        fake_work_item.title = "My Task"

        with (
            patch(
                "azure_issue_bridge.bridge.load_processed_ids",
                return_value=set(),
            ),
            # list_unread_replies is imported locally inside process_emails
            patch(
                "claire_py.email.watcher.list_unread_replies",
                return_value=emails,
            ),
            patch(
                "azure_issue_bridge.bridge.is_ado_assignment_email",
                return_value=True,
            ),
            patch(
                "azure_issue_bridge.bridge.triage_emails",
                return_value=[create_decision],
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_work_item",
                return_value=fake_work_item,
            ),
            # Pre-creation check finds the issue (created by a concurrent run)
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value="https://github.com/claire-labs/fivepoints/issues/102",
            ),
            patch(
                "azure_issue_bridge.bridge.create_github_issue"
            ) as mock_create,
            patch("azure_issue_bridge.bridge.save_processed_id"),
            patch("azure_issue_bridge.bridge.archive_email"),
            patch("azure_issue_bridge.bridge.save_state"),
        ):
            results = process_emails()

        # create_github_issue must NOT have been called
        mock_create.assert_not_called()

        # Result should be marked as skipped/duplicate
        assert len(results) == 1
        assert results[0].skipped is True
        assert results[0].skip_reason == "duplicate"
        assert results[0].github_issue_url == (
            "https://github.com/claire-labs/fivepoints/issues/102"
        )

    def test_issue_created_normally_when_no_duplicate_found(self) -> None:
        """When the pre-creation check finds no existing issue, creation proceeds."""
        emails = [make_email("Task 13644 - DEV - My Task", "msg-001")]

        create_decision = MagicMock()
        create_decision.action = "create"
        create_decision.pbi_id = "13644"
        create_decision.emails = emails

        fake_work_item = MagicMock()
        fake_work_item.id = "13644"
        fake_work_item.title = "My Task"

        with (
            patch(
                "azure_issue_bridge.bridge.load_processed_ids",
                return_value=set(),
            ),
            patch(
                "claire_py.email.watcher.list_unread_replies",
                return_value=emails,
            ),
            patch(
                "azure_issue_bridge.bridge.is_ado_assignment_email",
                return_value=True,
            ),
            patch(
                "azure_issue_bridge.bridge.triage_emails",
                return_value=[create_decision],
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_work_item",
                return_value=fake_work_item,
            ),
            # Pre-creation check: no issue found
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
            patch(
                "azure_issue_bridge.bridge.create_github_issue",
                return_value="https://github.com/claire-labs/fivepoints/issues/105",
            ) as mock_create,
            patch("azure_issue_bridge.bridge.save_processed_id"),
            patch("azure_issue_bridge.bridge.archive_email"),
            patch("azure_issue_bridge.bridge.save_state"),
        ):
            results = process_emails()

        # create_github_issue must have been called exactly once
        mock_create.assert_called_once()

        assert len(results) == 1
        assert results[0].skipped is False
        assert results[0].github_issue_url == (
            "https://github.com/claire-labs/fivepoints/issues/105"
        )
