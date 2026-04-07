#!/usr/bin/env python3
"""
Unit tests for azure_issue_bridge fetch_work_item_metadata.

Tests cover:
- Correct extraction of state, type, and parent_id from ADO batch API response
- Returns {} on curl error (returncode != 0)
- Returns {} on invalid JSON response
- Missing System.State field defaults to empty string
- Empty pbi_ids list returns {} without subprocess call
- Multiple work items in a single batch
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from azure_issue_bridge.bridge import fetch_work_item_metadata


def _mock_run(stdout: str, returncode: int = 0) -> MagicMock:
    """Build a mock subprocess.CompletedProcess result."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = ""
    return result


def _make_api_response(items: list[dict[str, Any]]) -> str:
    """Wrap items in the ADO batch response envelope."""
    return json.dumps({"value": items})


class TestFetchWorkItemMetadata:
    """Unit tests for fetch_work_item_metadata."""

    def test_returns_state_from_batch_api(self) -> None:
        """System.State is correctly extracted from API response."""
        payload = _make_api_response(
            [
                {
                    "id": 10856,
                    "fields": {
                        "System.WorkItemType": "Product Backlog Item",
                        "System.State": "Done",
                        "System.Parent": None,
                    },
                }
            ]
        )

        with (
            patch("subprocess.run", return_value=_mock_run(payload)),
            patch("azure_issue_bridge.bridge._get_pat", return_value="fake"),
        ):
            result = fetch_work_item_metadata(["10856"])

        assert "10856" in result
        assert result["10856"]["state"] == "Done"
        assert result["10856"]["type"] == "Product Backlog Item"
        assert result["10856"]["parent_id"] is None

    def test_returns_empty_dict_on_curl_error(self) -> None:
        """returncode != 0 → returns {}."""
        with (
            patch("subprocess.run", return_value=_mock_run("", returncode=1)),
            patch("azure_issue_bridge.bridge._get_pat", return_value="fake"),
        ):
            result = fetch_work_item_metadata(["10856"])

        assert result == {}

    def test_returns_empty_dict_on_invalid_json(self) -> None:
        """Bad JSON response → returns {}."""
        with (
            patch("subprocess.run", return_value=_mock_run("not-valid-json")),
            patch("azure_issue_bridge.bridge._get_pat", return_value="fake"),
        ):
            result = fetch_work_item_metadata(["10856"])

        assert result == {}

    def test_state_field_missing_returns_empty_string(self) -> None:
        """If System.State is absent from response, state defaults to ''."""
        payload = _make_api_response(
            [
                {
                    "id": 10856,
                    "fields": {
                        "System.WorkItemType": "Task",
                        # System.State intentionally absent
                    },
                }
            ]
        )

        with (
            patch("subprocess.run", return_value=_mock_run(payload)),
            patch("azure_issue_bridge.bridge._get_pat", return_value="fake"),
        ):
            result = fetch_work_item_metadata(["10856"])

        assert result["10856"]["state"] == ""

    def test_returns_empty_dict_for_empty_ids_list(self) -> None:
        """Empty pbi_ids list → returns {} without calling subprocess."""
        with patch("subprocess.run") as mock_run:
            result = fetch_work_item_metadata([])

        assert result == {}
        mock_run.assert_not_called()

    def test_multiple_work_items_in_batch(self) -> None:
        """All IDs in a batch are returned correctly."""
        payload = _make_api_response(
            [
                {
                    "id": 10856,
                    "fields": {
                        "System.WorkItemType": "Product Backlog Item",
                        "System.State": "Done",
                        "System.Parent": None,
                    },
                },
                {
                    "id": 10857,
                    "fields": {
                        "System.WorkItemType": "Task",
                        "System.State": "Active",
                        "System.Parent": 10856,
                    },
                },
            ]
        )

        with (
            patch("subprocess.run", return_value=_mock_run(payload)),
            patch("azure_issue_bridge.bridge._get_pat", return_value="fake"),
        ):
            result = fetch_work_item_metadata(["10856", "10857"])

        assert "10856" in result
        assert "10857" in result
        assert result["10856"]["state"] == "Done"
        assert result["10857"]["state"] == "Active"
        assert result["10857"]["type"] == "Task"

    def test_parent_id_extracted_as_string(self) -> None:
        """System.Parent (int) is converted to string in the output."""
        payload = _make_api_response(
            [
                {
                    "id": 10857,
                    "fields": {
                        "System.WorkItemType": "Task",
                        "System.State": "Active",
                        "System.Parent": 10856,
                    },
                }
            ]
        )

        with (
            patch("subprocess.run", return_value=_mock_run(payload)),
            patch("azure_issue_bridge.bridge._get_pat", return_value="fake"),
        ):
            result = fetch_work_item_metadata(["10857"])

        assert result["10857"]["parent_id"] == "10856"
        assert isinstance(result["10857"]["parent_id"], str)

    def test_null_parent_id_is_none(self) -> None:
        """System.Parent absent or null → parent_id is None."""
        payload = _make_api_response(
            [
                {
                    "id": 10856,
                    "fields": {
                        "System.WorkItemType": "Product Backlog Item",
                        "System.State": "Active",
                        "System.Parent": None,
                    },
                }
            ]
        )

        with (
            patch("subprocess.run", return_value=_mock_run(payload)),
            patch("azure_issue_bridge.bridge._get_pat", return_value="fake"),
        ):
            result = fetch_work_item_metadata(["10856"])

        assert result["10856"]["parent_id"] is None

    def test_returns_empty_dict_on_empty_value_list(self) -> None:
        """API returns {value: []} → result is {}."""
        payload = json.dumps({"value": []})

        with (
            patch("subprocess.run", return_value=_mock_run(payload)),
            patch("azure_issue_bridge.bridge._get_pat", return_value="fake"),
        ):
            result = fetch_work_item_metadata(["10856"])

        assert result == {}
