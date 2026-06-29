"""Tests for azure_issue_bridge.bridge — email filtering."""
from __future__ import annotations

from email.message import EmailMessage

import pytest

from claire_fivepoints.azure_issue_bridge.bridge import (
    MockEmailFilter,
    is_pbi_email,
)

_ADO_SENDER = "azuredevops@microsoft.com"
_TEST_SENDER = "andreoperez@gmail.com"


def _make_msg(from_: str, subject: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_
    msg["Subject"] = subject
    return msg


_VALID_SUBJECTS = [
    "Product Backlog Item 12345 - DEV - Client Management",
    "Product Backlog Item 10847 - DEV - Client Mgmt - some title",
    "Task 13644 - area - title",
    "Bug 999 - DEV - Crash on login",
]

_INVALID_SUBJECTS = [
    "Re: Weekly sync",
    "Your PBI is ready",
    "ADO notification",
    "",
]


# ---------------------------------------------------------------------------
# is_pbi_email
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subject", _VALID_SUBJECTS)
def test_is_pbi_email_ado_sender_valid_subject(subject: str) -> None:
    msg = _make_msg(_ADO_SENDER, subject)
    assert is_pbi_email(msg, sender=_ADO_SENDER) is True


@pytest.mark.parametrize("subject", _VALID_SUBJECTS)
def test_is_pbi_email_test_sender_valid_subject(subject: str) -> None:
    msg = _make_msg(_TEST_SENDER, subject)
    assert is_pbi_email(msg, sender=_TEST_SENDER) is True


@pytest.mark.parametrize("subject", _INVALID_SUBJECTS)
def test_is_pbi_email_valid_sender_invalid_subject(subject: str) -> None:
    msg = _make_msg(_ADO_SENDER, subject)
    assert is_pbi_email(msg, sender=_ADO_SENDER) is False


def test_is_pbi_email_wrong_sender() -> None:
    """Test sender mismatch — right subject, wrong sender returns False."""
    msg = _make_msg(_TEST_SENDER, "Product Backlog Item 1 - DEV - title")
    assert is_pbi_email(msg, sender=_ADO_SENDER) is False


def test_is_pbi_email_wrong_sender_reversed() -> None:
    msg = _make_msg(_ADO_SENDER, "Product Backlog Item 1 - DEV - title")
    assert is_pbi_email(msg, sender=_TEST_SENDER) is False


def test_is_pbi_email_empty_from() -> None:
    msg = EmailMessage()
    msg["Subject"] = "Product Backlog Item 1 - DEV - title"
    assert is_pbi_email(msg, sender=_ADO_SENDER) is False


def test_is_pbi_email_display_name_ado_sender() -> None:
    """ADO emails arrive with display name — parseaddr must extract the bare address."""
    msg = _make_msg(f"Azure DevOps <{_ADO_SENDER}>", "Product Backlog Item 1 - DEV - title")
    assert is_pbi_email(msg, sender=_ADO_SENDER) is True


def test_is_pbi_email_substring_spoof_rejected() -> None:
    """evil@evil.com azuredevops@microsoft.com must NOT pass the sender check."""
    spoofed_from = f"evil@evil.com {_ADO_SENDER}"
    msg = _make_msg(spoofed_from, "Product Backlog Item 1 - DEV - title")
    assert is_pbi_email(msg, sender=_ADO_SENDER) is False


# ---------------------------------------------------------------------------
# MockEmailFilter
# ---------------------------------------------------------------------------


def test_mock_email_filter_pbi_email() -> None:
    filt = MockEmailFilter()
    msg = _make_msg(_TEST_SENDER, "Product Backlog Item 99 - area - title")
    assert filt.is_pbi_email(msg, sender=_TEST_SENDER) is True


def test_mock_email_filter_non_pbi_email() -> None:
    filt = MockEmailFilter()
    msg = _make_msg(_ADO_SENDER, "Weekly standup notes")
    assert filt.is_pbi_email(msg, sender=_ADO_SENDER) is False


def test_mock_email_filter_sender_mismatch() -> None:
    filt = MockEmailFilter()
    msg = _make_msg(_TEST_SENDER, "Product Backlog Item 1 - area - title")
    assert filt.is_pbi_email(msg, sender=_ADO_SENDER) is False
