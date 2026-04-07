#!/usr/bin/env python3
"""
Unit tests for azure_issue_bridge triage_emails — terminal state skip rule.

Tests cover:
- triage_emails() skips work items in terminal ADO states (Done, Closed, Removed, Resolved)
- triage_emails() creates issues for work items in active ADO states (To Do)
- Terminal state check is case-insensitive
- Terminal state skip takes priority over parent/duplicate checks
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from azure_issue_bridge.bridge import triage_emails


def make_email(subject: str, message_id: str = "msg-001") -> Any:
    """Create a mock email object with the given subject."""
    email = MagicMock()
    email.subject = subject
    email.message_id = message_id
    return email


def make_metadata(
    pbi_id: str, state: str, item_type: str = "Task", parent_id: str | None = None
) -> dict[str, dict[str, Any]]:
    """Build a mock metadata dict as returned by fetch_work_item_metadata."""
    return {
        pbi_id: {
            "type": item_type,
            "parent_id": parent_id,
            "state": state,
        }
    }


class TestTerminalStateSkip:
    """Tests for Rule 0: skip work items in terminal ADO states."""

    @pytest.mark.parametrize("state", ["Done", "Closed", "Removed", "Resolved"])
    def test_terminal_states_are_skipped(self, state: str) -> None:
        emails = [make_email(f"Task 10852 - DEV - {state} work item")]
        metadata = make_metadata("10852", state=state)

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert len(decisions) == 1
        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "terminal_state"
        assert decisions[0].pbi_id == "10852"

    @pytest.mark.parametrize(
        "state",
        [
            "done",
            "DONE",
            "Done",
            "CLOSED",
            "closed",
            "removed",
            "REMOVED",
            "resolved",
            "RESOLVED",
        ],
    )
    def test_terminal_state_check_is_case_insensitive(self, state: str) -> None:
        emails = [make_email("Task 10852 - DEV - case test")]
        metadata = make_metadata("10852", state=state)

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "terminal_state"

    @pytest.mark.parametrize("state", ["To Do"])
    def test_active_states_are_not_skipped(self, state: str) -> None:
        emails = [make_email(f"Task 10852 - DEV - {state} work item")]
        metadata = make_metadata("10852", state=state)

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert len(decisions) == 1
        assert decisions[0].action == "create"
        assert decisions[0].skip_reason is None

    @pytest.mark.parametrize("state", ["Active", "New", "In Progress", "Committed"])
    def test_non_todo_active_states_are_skipped(self, state: str) -> None:
        """Only 'To Do' is recognized as active — other ADO states are state_unknown."""
        emails = [make_email(f"Task 10852 - DEV - {state} work item")]
        metadata = make_metadata("10852", state=state)

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert len(decisions) == 1
        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "state_unknown"

    def test_terminal_state_takes_priority_over_parent_has_children(self) -> None:
        """Rule 0 fires before Rule 1 — a Done parent with children is still skipped as terminal."""
        emails = [make_email("Product Backlog Item 10800 - DEV - Done PBI")]
        # PBI 10800 is Done, has children
        metadata = make_metadata(
            "10800", state="Done", item_type="Product Backlog Item"
        )

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=["10801", "10802"],
            ) as mock_fetch_children,
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "terminal_state"
        mock_fetch_children.assert_not_called()

    def test_empty_state_string_does_not_create_issue(self) -> None:
        """state='' (API returned field but empty) should be treated as unknown → skip."""
        emails = [make_email("Task 10852 - DEV - some task")]
        metadata = make_metadata("10852", state="")

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert len(decisions) == 1
        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "state_unknown"

    def test_unexpected_state_value_does_not_create_issue(self) -> None:
        """Unknown state like 'Proposed' should be treated as unknown → skip."""
        emails = [make_email("Task 10852 - DEV - some task")]
        metadata = make_metadata("10852", state="Proposed")

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert len(decisions) == 1
        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "state_unknown"


class TestMetadataFetchFailure:
    """Fail-open regression tests: API failure must produce skip, not create."""

    def test_api_error_does_not_create_issue(self) -> None:
        """When fetch_work_item_metadata returns {}, no issue should be created."""
        emails = [make_email("Product Backlog Item 10856 - Client - Some done work")]

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value={},
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert len(decisions) == 1
        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "state_unknown"

    def test_json_decode_error_does_not_create_issue(self) -> None:
        """Bad JSON response → fetch_work_item_metadata returns {} → fail-safe skip."""
        emails = [make_email("Product Backlog Item 10856 - Client - some work")]

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value={},
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert len(decisions) == 1
        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "state_unknown"

    def test_network_timeout_does_not_create_issue(self) -> None:
        """Timeout → fetch_work_item_metadata returns {} → fail-safe skip."""
        emails = [make_email("Task 10857 - DEV - some task")]

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value={},
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert len(decisions) == 1
        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "state_unknown"

    def test_partial_metadata_missing_pbi_does_not_create_issue(self) -> None:
        """If pbi_id is absent from metadata dict (partial API failure), skip it."""
        emails = [
            make_email("Task 10856 - missing from metadata", message_id="msg-001"),
            make_email("Task 10857 - present in metadata", message_id="msg-002"),
        ]
        # Only 10857 in metadata — 10856 is missing (partial API failure)
        metadata = make_metadata("10857", state="To Do")

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert len(decisions) == 2
        by_id = {d.pbi_id: d for d in decisions}
        assert by_id["10856"].action == "skip"
        assert by_id["10856"].skip_reason == "state_unknown"
        assert by_id["10857"].action == "create"


class TestRulePriority:
    """Rule 0 (state check) must short-circuit before any other rules."""

    def test_terminal_state_beats_duplicate_check(self) -> None:
        """Terminal state check runs before duplicate check — find_existing_github_issue not called."""
        emails = [make_email("Product Backlog Item 10856 - Client - Some done work")]
        metadata = make_metadata(
            "10856", state="Done", item_type="Product Backlog Item"
        )

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value="https://github.com/org/repo/issues/99",
            ) as mock_gh,
        ):
            decisions = triage_emails(emails)

        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "terminal_state"
        mock_gh.assert_not_called()

    def test_terminal_state_beats_parent_has_children(self) -> None:
        """Terminal state check runs before parent/child logic — fetch_ado_child_ids not called."""
        emails = [make_email("Product Backlog Item 10800 - Done parent")]
        metadata = make_metadata(
            "10800", state="Done", item_type="Product Backlog Item"
        )

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=["10801"],
            ) as mock_children,
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "terminal_state"
        mock_children.assert_not_called()

    def test_rule_0_before_rule_1a(self) -> None:
        """Parent in batch but state=Done → skip reason is terminal_state, not parent_has_children."""
        emails = [
            make_email("Product Backlog Item 10800 - Done PBI", message_id="msg-001"),
            make_email("Task 10801 - Active Task", message_id="msg-002"),
        ]
        metadata = {
            "10800": {
                "type": "Product Backlog Item",
                "parent_id": None,
                "state": "Done",
            },
            "10801": {"type": "Task", "parent_id": "10800", "state": "To Do"},
        }

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        by_id = {d.pbi_id: d for d in decisions}
        assert by_id["10800"].action == "skip"
        assert by_id["10800"].skip_reason == "terminal_state"
        assert by_id["10801"].action == "create"

    def test_mixed_batch_only_active_task_created(self) -> None:
        """Real-world scenario: batch with parents, Done children, and one active Task.

        Reproduces the fivepoints-test bug where the bridge created 8 issues
        when only 1 (the active Task) should have been created.

        Batch:
        - PBI #10399 (Committed, parent of 10852-10856) → skip (state_unknown — only "To Do" is active)
        - PBI #10847 (Committed, parent of 13644)       → skip (state_unknown — only "To Do" is active)
        - Task #10852 (Done)                             → skip (terminal_state)
        - Task #10853 (Done)                             → skip (terminal_state)
        - Task #10854 (Done)                             → skip (terminal_state)
        - Task #10855 (Done)                             → skip (terminal_state)
        - Task #10856 (Done)                             → skip (terminal_state)
        - Task #13644 (To Do, child of 10847)            → CREATE
        """
        emails = [
            make_email("Product Backlog Item 10399 - Education", message_id="msg-001"),
            make_email("Product Backlog Item 10847 - Adoption", message_id="msg-002"),
            make_email("Task 10852 - Education - Info", message_id="msg-003"),
            make_email("Task 10853 - Education - Grade", message_id="msg-004"),
            make_email("Task 10854 - Education - GED", message_id="msg-005"),
            make_email("Task 10855 - Education - Enrollment", message_id="msg-006"),
            make_email("Task 10856 - Education - Report Card", message_id="msg-007"),
            make_email("Task 13644 - Code Gen", message_id="msg-008"),
        ]
        metadata = {
            "10399": {
                "type": "Product Backlog Item",
                "parent_id": None,
                "state": "Committed",
            },
            "10847": {
                "type": "Product Backlog Item",
                "parent_id": None,
                "state": "Committed",
            },
            "10852": {"type": "Task", "parent_id": "10399", "state": "Done"},
            "10853": {"type": "Task", "parent_id": "10399", "state": "Done"},
            "10854": {"type": "Task", "parent_id": "10399", "state": "Done"},
            "10855": {"type": "Task", "parent_id": "10399", "state": "Done"},
            "10856": {"type": "Task", "parent_id": "10399", "state": "Done"},
            "13644": {"type": "Task", "parent_id": "10847", "state": "To Do"},
        }

        def mock_child_ids(pbi_id: str) -> list[str]:
            children = {
                "10399": ["10852", "10853", "10854", "10855", "10856"],
                "10847": ["13644"],
            }
            return children.get(pbi_id, [])

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                side_effect=mock_child_ids,
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        by_id = {d.pbi_id: d for d in decisions}
        assert len(decisions) == 8

        # Only the active Task should be created
        created = [d for d in decisions if d.action == "create"]
        assert len(created) == 1
        assert created[0].pbi_id == "13644"

        # Done tasks are skipped as terminal
        for pbi_id in ["10852", "10853", "10854", "10855", "10856"]:
            assert by_id[pbi_id].action == "skip"
            assert by_id[pbi_id].skip_reason == "terminal_state"

        # Parent PBIs are skipped (Committed is not an active state — only "To Do" is)
        for pbi_id in ["10399", "10847"]:
            assert by_id[pbi_id].action == "skip"
            assert by_id[pbi_id].skip_reason == "state_unknown"

    def test_state_unknown_beats_duplicate_check(self) -> None:
        """State unknown (missing from metadata) → skip before duplicate check."""
        emails = [make_email("Product Backlog Item 10856 - some work")]

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value={},
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ) as mock_gh,
        ):
            decisions = triage_emails(emails)

        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "state_unknown"
        mock_gh.assert_not_called()


class TestUnconditionalTypeGate:
    """Rule 1b: non-Task types are rejected unconditionally, without ADO API calls."""

    @pytest.mark.parametrize(
        "item_type",
        ["Product Backlog Item", "Feature", "User Story", "Bug", "Epic"],
    )
    def test_non_task_type_skipped_unconditionally(self, item_type: str) -> None:
        """Any non-Task work item in 'To Do' state must be skipped without fetching children."""
        emails = [make_email(f"Product Backlog Item 10900 - DEV - some {item_type}")]
        metadata = make_metadata("10900", state="To Do", item_type=item_type)

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
            ) as mock_fetch_children,
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert len(decisions) == 1
        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "non_task_type"
        # ADO children API must NOT be called — the type gate is unconditional
        mock_fetch_children.assert_not_called()

    def test_pbi_with_no_ado_children_still_skipped(self) -> None:
        """Regression: PBI with no ADO children must be skipped (was previously created as issue).

        This was the bug: fetch_ado_child_ids() returned [] → conditional check failed →
        GitHub issue was created for a PBI. The type gate is now unconditional.
        """
        emails = [make_email("Product Backlog Item 10847 - DEV - Client Management")]
        metadata = make_metadata(
            "10847", state="To Do", item_type="Product Backlog Item"
        )

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],  # no children — old code would have created an issue
            ) as mock_fetch_children,
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "non_task_type"
        mock_fetch_children.assert_not_called()

    def test_task_type_creates_issue(self) -> None:
        """Task in 'To Do' state still creates a GitHub issue after the type gate fix."""
        emails = [make_email("Task 13644 - DEV - implement feature")]
        metadata = make_metadata("13644", state="To Do", item_type="Task")

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                return_value=[],
            ),
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert decisions[0].action == "create"
        assert decisions[0].skip_reason is None

    @pytest.mark.parametrize("item_type", ["", "unknown", "WorkItem"])
    def test_empty_or_unknown_type_does_not_create_issue(self, item_type: str) -> None:
        """Regression #2202: empty or unknown pbi_type must be rejected by the type gate.

        Old code: `if pbi_type and pbi_type.lower() != 'task'` → empty string is falsy
        → condition False → item passed through and a GitHub issue was created.
        Fixed code: `if pbi_type.lower() != 'task'` → empty string != 'task' → skipped.
        """
        emails = [make_email("Task 10854 - DEV - some item")]
        metadata = make_metadata("10854", state="To Do", item_type=item_type)

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
            ) as mock_fetch_children,
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert len(decisions) == 1
        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "non_task_type"
        mock_fetch_children.assert_not_called()

    def test_ado_api_failure_non_task_still_skipped(self) -> None:
        """Even if fetch_ado_child_ids would have failed (exception), non-Task is skipped.

        The old code called fetch_ado_child_ids which could fail silently (return [])
        and let the PBI through. The new unconditional check never calls it.
        """
        emails = [make_email("Product Backlog Item 10850 - DEV - some feature")]
        metadata = make_metadata(
            "10850", state="To Do", item_type="Product Backlog Item"
        )

        with (
            patch(
                "azure_issue_bridge.bridge.fetch_work_item_metadata",
                return_value=metadata,
            ),
            patch(
                "azure_issue_bridge.bridge.fetch_ado_child_ids",
                side_effect=RuntimeError("ADO API timeout"),
            ) as mock_fetch_children,
            patch(
                "azure_issue_bridge.bridge.find_existing_github_issue",
                return_value=None,
            ),
        ):
            decisions = triage_emails(emails)

        assert decisions[0].action == "skip"
        assert decisions[0].skip_reason == "non_task_type"
        mock_fetch_children.assert_not_called()
