"""Unit tests for GmailApiAdapter — zero real network calls."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claire_fivepoints.azure_issue_bridge.adapters import (
    BridgeAdapters,
    GmailApiAdapter,
    MockBranchSync,
    MockGitHubAdapter,
    MockLabelAdapter,
    MockWorktreePrepare,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token_file(tmp_path: Path, token: str = "tok", expiry: str | None = None) -> Path:
    token_path = tmp_path / "gmail_token.json"
    data: dict = {
        "token": token,
        "refresh_token": "refresh-tok",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    }
    if expiry is not None:
        data["expiry"] = expiry
    token_path.write_text(json.dumps(data))
    return token_path


def _make_service_mock(messages: list[dict]) -> MagicMock:
    """Return a mock Gmail service that returns *messages* from list()."""
    service = MagicMock()
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": m["id"]} for m in messages]
    }

    def _get_side_effect(**kwargs):
        msg_id = kwargs["id"]
        msg = next(m for m in messages if m["id"] == msg_id)
        mock_get = MagicMock()
        mock_get.execute.return_value = {
            "threadId": msg.get("threadId", "t1"),
            "payload": {
                "headers": [
                    {"name": "From", "value": msg.get("from_addr", "")},
                    {"name": "Subject", "value": msg.get("subject", "")},
                ]
            },
        }
        return mock_get

    service.users.return_value.messages.return_value.get.side_effect = _get_side_effect
    return service


def _make_mock_creds(expired: bool = False, new_token: str = "new-token") -> MagicMock:
    creds = MagicMock()
    creds.expired = expired
    creds.refresh_token = "refresh-tok"
    creds.token = new_token
    return creds


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


def test_gmail_api_adapter_satisfies_email_adapter_protocol(tmp_path: Path) -> None:
    """GmailApiAdapter is usable anywhere EmailAdapter is expected."""
    adapter = GmailApiAdapter(credentials_path=tmp_path / "token.json")
    adapters = BridgeAdapters(
        email=adapter,
        github=MockGitHubAdapter(),
        labels=MockLabelAdapter(),
        branch_sync=MockBranchSync(),
        worktree=MockWorktreePrepare(),
    )
    assert adapters.email is adapter


# ---------------------------------------------------------------------------
# fetch — happy path
# ---------------------------------------------------------------------------


def test_fetch_returns_emails(tmp_path: Path) -> None:
    token_path = _make_token_file(tmp_path)
    messages = [
        {"id": "msg1", "threadId": "t1", "from_addr": "azuredevops@microsoft.com", "subject": "PBI 1 - DEV - Title"},
        {"id": "msg2", "threadId": "t2", "from_addr": "azuredevops@microsoft.com", "subject": "PBI 2 - DEV - Other"},
    ]
    mock_service = _make_service_mock(messages)
    mock_creds = _make_mock_creds()

    with (
        patch("google.oauth2.credentials.Credentials.from_authorized_user_info", return_value=mock_creds),
        patch("googleapiclient.discovery.build", return_value=mock_service),
    ):
        adapter = GmailApiAdapter(credentials_path=token_path)
        result = adapter.fetch(sender="azuredevops@microsoft.com", max_results=10)

    assert len(result) == 2
    assert result[0] == {
        "message_id": "msg1",
        "thread_id": "t1",
        "from_addr": "azuredevops@microsoft.com",
        "subject": "PBI 1 - DEV - Title",
    }
    assert result[1]["message_id"] == "msg2"


def test_fetch_empty_inbox(tmp_path: Path) -> None:
    token_path = _make_token_file(tmp_path)
    mock_service = _make_service_mock([])
    mock_creds = _make_mock_creds()

    with (
        patch("google.oauth2.credentials.Credentials.from_authorized_user_info", return_value=mock_creds),
        patch("googleapiclient.discovery.build", return_value=mock_service),
    ):
        adapter = GmailApiAdapter(credentials_path=token_path)
        result = adapter.fetch(sender="azuredevops@microsoft.com", max_results=10)

    assert result == []


def test_fetch_passes_sender_query_to_gmail(tmp_path: Path) -> None:
    token_path = _make_token_file(tmp_path)
    mock_service = _make_service_mock([])
    mock_creds = _make_mock_creds()

    with (
        patch("google.oauth2.credentials.Credentials.from_authorized_user_info", return_value=mock_creds),
        patch("googleapiclient.discovery.build", return_value=mock_service),
    ):
        adapter = GmailApiAdapter(credentials_path=token_path)
        adapter.fetch(sender="test@example.com", max_results=5)

    list_call = mock_service.users.return_value.messages.return_value.list
    list_call.assert_called_once_with(userId="me", q="from:test@example.com", maxResults=5)


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


def test_fetch_refreshes_expired_token(tmp_path: Path) -> None:
    token_path = _make_token_file(tmp_path)
    mock_service = _make_service_mock([])
    mock_creds = _make_mock_creds(expired=True, new_token="refreshed-token")

    with (
        patch("google.oauth2.credentials.Credentials.from_authorized_user_info", return_value=mock_creds),
        patch("google.auth.transport.requests.Request"),
        patch("googleapiclient.discovery.build", return_value=mock_service),
    ):
        adapter = GmailApiAdapter(credentials_path=token_path)
        adapter.fetch(sender="any@example.com", max_results=5)

        mock_creds.refresh.assert_called_once()

    saved = json.loads(token_path.read_text())
    assert saved["token"] == "refreshed-token"


def test_fetch_no_refresh_when_not_expired(tmp_path: Path) -> None:
    token_path = _make_token_file(tmp_path)
    mock_service = _make_service_mock([])
    mock_creds = _make_mock_creds(expired=False)

    with (
        patch("google.oauth2.credentials.Credentials.from_authorized_user_info", return_value=mock_creds),
        patch("googleapiclient.discovery.build", return_value=mock_service),
    ):
        adapter = GmailApiAdapter(credentials_path=token_path)
        adapter.fetch(sender="any@example.com", max_results=5)

        mock_creds.refresh.assert_not_called()
