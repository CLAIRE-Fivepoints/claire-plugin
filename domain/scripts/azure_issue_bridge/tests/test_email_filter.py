"""
Unit tests for azure_issue_bridge email filter — is_pbi_email and BridgeConfig.

Tests cover:
- is_pbi_email() returns True for PBI subjects regardless of sender value
- is_pbi_email() returns False for non-PBI subjects
- MockEmailFilter binds a sender and exposes is_pbi_email as an instance method
- load_bridge_config() resolves pbi_sender from PBI_TEST_SENDER > PBI_SENDER > default
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from azure_issue_bridge.bridge import BridgeConfig, is_pbi_email, load_bridge_config


def make_msg(subject: str) -> Any:
    """Create a mock email message with the given subject."""
    msg = MagicMock()
    msg.subject = subject
    return msg


class MockEmailFilter:
    """Test utility — binds a sender and exposes is_pbi_email as an instance method.

    Usage:
        f = MockEmailFilter(sender="andreoperez@gmail.com")
        assert f.is_pbi_email(msg)
    """

    def __init__(self, sender: str) -> None:
        self.sender = sender

    def is_pbi_email(self, msg: Any) -> bool:
        return is_pbi_email(msg, sender=self.sender)


class TestIsPbiEmail:
    """Tests for is_pbi_email(msg, sender)."""

    def test_pbi_subject_with_ado_sender(self) -> None:
        msg = make_msg("Product Backlog Item 10847 - DEV - Client Management")
        assert is_pbi_email(msg, sender="azuredevops@microsoft.com")

    def test_task_subject_with_ado_sender(self) -> None:
        msg = make_msg("Task 13644 was assigned to andre.perez dothelpllc.com")
        assert is_pbi_email(msg, sender="azuredevops@microsoft.com")

    def test_pbi_subject_with_test_sender(self) -> None:
        """Test sender (gmail) with same ADO subject format must return True."""
        msg = make_msg("Product Backlog Item 10847 - DEV - Client Management")
        assert is_pbi_email(msg, sender="andreoperez@gmail.com")

    def test_task_subject_with_test_sender(self) -> None:
        msg = make_msg("Task 13644 - DEV - implement feature")
        assert is_pbi_email(msg, sender="andreoperez@gmail.com")

    def test_bug_subject_with_test_sender(self) -> None:
        msg = make_msg("Bug 9999 - DEV - null pointer exception")
        assert is_pbi_email(msg, sender="andreoperez@gmail.com")

    def test_non_pbi_subject_returns_false(self) -> None:
        msg = make_msg("Hello from someone")
        assert not is_pbi_email(msg, sender="azuredevops@microsoft.com")

    def test_unrelated_subject_with_test_sender_returns_false(self) -> None:
        msg = make_msg("Re: your invoice for June")
        assert not is_pbi_email(msg, sender="andreoperez@gmail.com")

    def test_empty_subject_returns_false(self) -> None:
        msg = make_msg("")
        assert not is_pbi_email(msg, sender="azuredevops@microsoft.com")


class TestMockEmailFilter:
    """Tests for MockEmailFilter — sender-bound wrapper around is_pbi_email."""

    def test_ado_sender_filter_passes_pbi_subject(self) -> None:
        f = MockEmailFilter(sender="azuredevops@microsoft.com")
        msg = make_msg("Product Backlog Item 10847 - DEV - some task")
        assert f.is_pbi_email(msg)

    def test_test_sender_filter_passes_pbi_subject(self) -> None:
        f = MockEmailFilter(sender="andreoperez@gmail.com")
        msg = make_msg("Product Backlog Item 10847 - DEV - some task")
        assert f.is_pbi_email(msg)

    def test_filter_rejects_non_pbi_subject(self) -> None:
        f = MockEmailFilter(sender="azuredevops@microsoft.com")
        msg = make_msg("Unrelated email about something else")
        assert not f.is_pbi_email(msg)

    def test_filter_rejects_non_pbi_subject_with_test_sender(self) -> None:
        f = MockEmailFilter(sender="andreoperez@gmail.com")
        msg = make_msg("Hi, here is your receipt")
        assert not f.is_pbi_email(msg)

    def test_sender_is_stored(self) -> None:
        f = MockEmailFilter(sender="andreoperez@gmail.com")
        assert f.sender == "andreoperez@gmail.com"


class TestBridgeConfig:
    """Tests for BridgeConfig and load_bridge_config()."""

    def test_default_sender_is_ado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PBI_TEST_SENDER", raising=False)
        monkeypatch.delenv("PBI_SENDER", raising=False)
        config = load_bridge_config()
        assert config.pbi_sender == "azuredevops@microsoft.com"

    def test_pbi_test_sender_env_overrides_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PBI_TEST_SENDER", "andreoperez@gmail.com")
        monkeypatch.delenv("PBI_SENDER", raising=False)
        config = load_bridge_config()
        assert config.pbi_sender == "andreoperez@gmail.com"

    def test_pbi_sender_env_overrides_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PBI_TEST_SENDER", raising=False)
        monkeypatch.setenv("PBI_SENDER", "custom@example.com")
        config = load_bridge_config()
        assert config.pbi_sender == "custom@example.com"

    def test_pbi_test_sender_takes_priority_over_pbi_sender(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PBI_TEST_SENDER", "andreoperez@gmail.com")
        monkeypatch.setenv("PBI_SENDER", "custom@example.com")
        config = load_bridge_config()
        assert config.pbi_sender == "andreoperez@gmail.com"

    def test_empty_pbi_test_sender_falls_through_to_pbi_sender(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PBI_TEST_SENDER", "")
        monkeypatch.setenv("PBI_SENDER", "custom@example.com")
        config = load_bridge_config()
        assert config.pbi_sender == "custom@example.com"

    def test_bridge_config_dataclass_defaults(self) -> None:
        config = BridgeConfig()
        assert config.pbi_sender == "azuredevops@microsoft.com"

    def test_bridge_config_custom_sender(self) -> None:
        config = BridgeConfig(pbi_sender="andreoperez@gmail.com")
        assert config.pbi_sender == "andreoperez@gmail.com"
