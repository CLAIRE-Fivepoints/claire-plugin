"""azure_issue_bridge.bridge — email filtering primitives.

Core primitives:
  is_pbi_email(msg, sender)  — pure predicate: right sender + right subject?
  MockEmailFilter            — testable filter implementation, no network calls
"""
from __future__ import annotations

import re
from email.message import EmailMessage
from email.utils import parseaddr

# Subject pattern for ADO work item assignment notifications.
_PBI_SUBJECT_RE = re.compile(
    r"(?:Product Backlog Item|Task|Bug|Feature|User Story)\s+(\d+)",
    re.IGNORECASE,
)

_DEFAULT_SENDER = "azuredevops@microsoft.com"


def parse_pbi_id(subject: str) -> str | None:
    """Extract the ADO work item ID from a PBI assignment email subject.

    Returns the numeric ID as a string, or None if the subject does not match.
    """
    m = _PBI_SUBJECT_RE.search(subject)
    return m.group(1) if m else None


def is_pbi_email(msg: EmailMessage, sender: str) -> bool:
    """Return True if msg is a PBI assignment email from the given sender.

    Uses email.utils.parseaddr to extract the bare address from the From header
    so that display names ("Azure DevOps <azuredevops@microsoft.com>") are
    handled correctly and substring spoofing is not possible.
    """
    _, addr = parseaddr(msg.get("From", ""))
    if addr.lower() != sender.lower():
        return False
    subject = msg.get("Subject", "")
    return bool(_PBI_SUBJECT_RE.search(subject))


class MockEmailFilter:
    """Testable email filter — wraps is_pbi_email() with no network calls.

    Suitable for unit tests that need to verify filter logic in isolation
    without Gmail auth, subprocess calls, or environment side effects.

    Usage::

        filt = MockEmailFilter()
        assert filt.is_pbi_email(msg, sender="azuredevops@microsoft.com")
    """

    def is_pbi_email(self, msg: EmailMessage, sender: str) -> bool:
        return is_pbi_email(msg, sender)
