"""Unit tests for bridge_pipeline — zero network calls, zero subprocess."""
from __future__ import annotations

import pytest

from claire_fivepoints.azure_issue_bridge.adapters import (
    BridgeAdapters,
    MockEmailAdapter,
    MockGitHubAdapter,
    MockLabelAdapter,
)
from claire_fivepoints.azure_issue_bridge.pipeline import BridgeTask, bridge_pipeline
from claire_fivepoints.azure_issue_bridge.steps import add_label_step

_ADO_SENDER = "azuredevops@microsoft.com"
_TEST_SENDER = "andreoperez@gmail.com"


def _make_email(subject: str, sender: str = _ADO_SENDER, thread_id: str = "t1") -> dict:
    return {
        "message_id": "1",
        "subject": subject,
        "from_addr": sender,
        "thread_id": thread_id,
    }


def _make_adapters(emails: list[dict], gh: MockGitHubAdapter | None = None) -> BridgeAdapters:
    return BridgeAdapters(
        email=MockEmailAdapter(emails),
        github=gh or MockGitHubAdapter(),
        labels=MockLabelAdapter(),
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_bridge_detects_pbi_email() -> None:
    emails = [_make_email("Product Backlog Item 42 - DEV - Title")]
    adapters = _make_adapters(emails)
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert len(result.data["created"]) == 1
    assert result.data["created"][0]["issue"] == 1


def test_bridge_creates_issue_with_correct_title() -> None:
    subject = "Product Backlog Item 99 - AREA - My Feature"
    emails = [_make_email(subject)]
    gh = MockGitHubAdapter()
    adapters = _make_adapters(emails, gh)
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    bridge_pipeline(task, adapters)
    assert gh.created[0]["title"] == f"PBI: {subject}"
    assert gh.created[0]["repo"] == "owner/repo"


def test_bridge_test_sender() -> None:
    emails = [_make_email("Product Backlog Item 7 - DEV - Test", sender=_TEST_SENDER)]
    adapters = _make_adapters(emails)
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
    adapters = _make_adapters(emails, gh)
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo", dry_run=True)
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert gh.created == []
    assert result.data["created"][0]["dry_run"] is True


def test_bridge_dry_run_no_repo_required() -> None:
    emails = [_make_email("Product Backlog Item 1 - DEV - Title")]
    adapters = _make_adapters(emails)
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
    adapters = _make_adapters(emails, gh)
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert len(result.data["created"]) == 1


def test_bridge_sender_mismatch_filtered() -> None:
    """Emails from a different sender are dropped even with a valid subject."""
    emails = [_make_email("Product Backlog Item 5 - DEV - Title", sender=_TEST_SENDER)]
    gh = MockGitHubAdapter()
    adapters = _make_adapters(emails, gh)
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert result.data["created"] == []


def test_bridge_empty_inbox() -> None:
    adapters = _make_adapters([])
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert result.data["created"] == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_bridge_fails_without_repo_when_not_dry_run() -> None:
    emails = [_make_email("Product Backlog Item 1 - DEV - Title")]
    adapters = _make_adapters(emails)
    task = BridgeTask(sender=_ADO_SENDER, dry_run=False)  # repo=None
    result = bridge_pipeline(task, adapters)
    assert not result.ok
    assert "repo" in result.error


def test_bridge_max_results_respected() -> None:
    emails = [_make_email(f"Product Backlog Item {i} - DEV - Title") for i in range(10)]
    gh = MockGitHubAdapter()
    adapters = _make_adapters(emails, gh)
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo", max_results=3)
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert len(result.data["created"]) == 3


# ---------------------------------------------------------------------------
# add_label_step — unit tests
# ---------------------------------------------------------------------------


def _simple_adapters() -> tuple[MockLabelAdapter, BridgeAdapters]:
    labels = MockLabelAdapter()
    adapters = BridgeAdapters(
        email=MockEmailAdapter([]),
        github=MockGitHubAdapter(),
        labels=labels,
    )
    return labels, adapters


def test_add_label_step_calls_adapter() -> None:
    labels, adapters = _simple_adapters()
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo", client="fivepoints")
    ctx = {"created": [{"subject": "S", "issue": 42}]}
    result = add_label_step(task, ctx, adapters)
    assert result.ok
    assert labels.calls == [{"repo": "owner/repo", "issue": 42, "label": "role:fivepoints-dev"}]
    assert result.data["labeled"][0]["label"] == "role:fivepoints-dev"


def test_add_label_step_custom_client() -> None:
    labels, adapters = _simple_adapters()
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo", client="acme")
    ctx = {"created": [{"subject": "S", "issue": 7}]}
    result = add_label_step(task, ctx, adapters)
    assert result.ok
    assert labels.calls[0]["label"] == "role:acme-dev"


def test_add_label_step_multiple_issues() -> None:
    labels, adapters = _simple_adapters()
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    ctx = {"created": [{"subject": "A", "issue": 1}, {"subject": "B", "issue": 2}]}
    result = add_label_step(task, ctx, adapters)
    assert result.ok
    assert len(labels.calls) == 2
    assert labels.calls[0]["issue"] == 1
    assert labels.calls[1]["issue"] == 2


def test_add_label_step_dry_run_skips_adapter() -> None:
    labels, adapters = _simple_adapters()
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo", dry_run=True)
    # dry_run items have no "issue" key
    ctx = {"created": [{"subject": "S", "dry_run": True}]}
    result = add_label_step(task, ctx, adapters)
    assert result.ok
    assert labels.calls == []
    assert result.data["labeled"][0]["dry_run"] is True


def test_add_label_step_empty_created() -> None:
    labels, adapters = _simple_adapters()
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    result = add_label_step(task, {"created": []}, adapters)
    assert result.ok
    assert labels.calls == []


def test_add_label_step_failure_aborts_pipeline() -> None:
    class FailingLabelAdapter:
        def add_label(self, repo: str, issue: int, label: str) -> None:
            raise RuntimeError("gh error")

    adapters = BridgeAdapters(
        email=MockEmailAdapter([]),
        github=MockGitHubAdapter(),
        labels=FailingLabelAdapter(),
    )
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo")
    ctx = {"created": [{"subject": "S", "issue": 1}]}
    result = add_label_step(task, ctx, adapters)
    assert not result.ok
    assert "add_label failed" in result.error


def test_bridge_pipeline_labels_created_issues() -> None:
    """Full pipeline: label adapter receives call for each created issue."""
    emails = [
        _make_email("Product Backlog Item 10 - DEV - Feature A"),
        _make_email("Product Backlog Item 11 - DEV - Feature B"),
    ]
    labels = MockLabelAdapter()
    adapters = BridgeAdapters(
        email=MockEmailAdapter(emails),
        github=MockGitHubAdapter(),
        labels=labels,
    )
    task = BridgeTask(sender=_ADO_SENDER, repo="owner/repo", client="fivepoints")
    result = bridge_pipeline(task, adapters)
    assert result.ok
    assert len(labels.calls) == 2
    assert all(c["label"] == "role:fivepoints-dev" for c in labels.calls)
