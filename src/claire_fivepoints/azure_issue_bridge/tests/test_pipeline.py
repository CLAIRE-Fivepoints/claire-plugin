"""Unit tests for bridge_pipeline — zero network calls, zero subprocess."""
from __future__ import annotations

import pytest

from claire_fivepoints.azure_issue_bridge.adapters import (
    BridgeAdapters,
    MockEmailAdapter,
    MockGitHubAdapter,
)
from claire_fivepoints.azure_issue_bridge.pipeline import BridgeTask, bridge_pipeline

_ADO_SENDER = "azuredevops@microsoft.com"
_TEST_SENDER = "andreoperez@gmail.com"


def _make_email(subject: str, sender: str = _ADO_SENDER, thread_id: str = "t1") -> dict:
    return {
        "message_id": "1",
        "subject": subject,
        "from_addr": sender,
        "thread_id": thread_id,
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_bridge_detects_pbi_email() -> None:
    emails = [_make_email("Product Backlog Item 42 - DEV - Title")]
    adapters = BridgeAdapters(
        email=MockEmailAdapter(emails),
        github=MockGitHubAdapter(),
    )
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert len(result.data["created"]) == 1
    assert result.data["created"][0]["issue"] == 1


def test_bridge_creates_issue_with_correct_title() -> None:
    subject = "Product Backlog Item 99 - AREA - My Feature"
    emails = [_make_email(subject)]
    gh = MockGitHubAdapter()
    adapters = BridgeAdapters(email=MockEmailAdapter(emails), github=gh)
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    bridge_pipeline(task, adapters)
    assert gh.created[0]["title"] == f"PBI: {subject}"
    assert gh.created[0]["repo"] == "owner/repo"


def test_bridge_test_sender() -> None:
    emails = [_make_email("Product Backlog Item 7 - DEV - Test", sender=_TEST_SENDER)]
    adapters = BridgeAdapters(
        email=MockEmailAdapter(emails),
        github=MockGitHubAdapter(),
    )
    task = BridgeTask(sender=_TEST_SENDER, repo="owner/repo")
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert len(result.data["created"]) == 1


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


def test_bridge_dry_run_no_issues_created() -> None:
    emails = [_make_email("Product Backlog Item 1 - DEV - Title")]
    gh = MockGitHubAdapter()
    adapters = BridgeAdapters(email=MockEmailAdapter(emails), github=gh)
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo", dry_run=True)
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert gh.created == []
    assert result.data["created"][0]["dry_run"] is True


def test_bridge_dry_run_no_repo_required() -> None:
    emails = [_make_email("Product Backlog Item 1 - DEV - Title")]
    adapters = BridgeAdapters(
        email=MockEmailAdapter(emails),
        github=MockGitHubAdapter(),
    )
    task = BridgeTask(sender=_ADO_SENDER, dry_run=True)  # no repo
    result = bridge_pipeline(task, adapters)
    assert result.ok


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def test_bridge_filters_non_pbi_emails() -> None:
    emails = [
        _make_email("Product Backlog Item 1 - DEV - Title"),
        _make_email("Re: Weekly sync"),
        _make_email("Your invoice is ready"),
    ]
    gh = MockGitHubAdapter()
    adapters = BridgeAdapters(email=MockEmailAdapter(emails), github=gh)
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert len(result.data["created"]) == 1


def test_bridge_sender_mismatch_filtered() -> None:
    """Emails from a different sender are dropped even with a valid subject."""
    emails = [_make_email("Product Backlog Item 5 - DEV - Title", sender=_TEST_SENDER)]
    gh = MockGitHubAdapter()
    adapters = BridgeAdapters(email=MockEmailAdapter(emails), github=gh)
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert result.data["created"] == []


def test_bridge_empty_inbox() -> None:
    adapters = BridgeAdapters(
        email=MockEmailAdapter([]),
        github=MockGitHubAdapter(),
    )
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert result.data["created"] == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_bridge_fails_without_repo_when_not_dry_run() -> None:
    emails = [_make_email("Product Backlog Item 1 - DEV - Title")]
    adapters = BridgeAdapters(
        email=MockEmailAdapter(emails),
        github=MockGitHubAdapter(),
    )
    task = BridgeTask(sender=_ADO_SENDER, dry_run=False)  # repo=None
    result = bridge_pipeline(task, adapters)
    assert not result.ok
    assert "repo" in result.error


def test_bridge_max_results_respected() -> None:
    emails = [_make_email(f"Product Backlog Item {i} - DEV - Title") for i in range(10)]
    gh = MockGitHubAdapter()
    adapters = BridgeAdapters(email=MockEmailAdapter(emails), github=gh)
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo", max_results=3)
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert len(result.data["created"]) == 3
