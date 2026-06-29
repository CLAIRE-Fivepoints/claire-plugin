"""azure_issue_bridge.adapters — EmailAdapter, GitHubAdapter, LabelAdapter, WorktreePrepareAdapter protocols, concrete adapters, and test doubles.

- GmailApiAdapter: accesses Gmail via the Google API directly (OAuth2) — no subprocess.
- RealWorktreePrepare: creates git worktrees via subprocess git — no GitHub CLI.
- CLI-backed adapters (GhCliAdapter, RealLabelAdapter) remain in cli.py (subprocess.run in CLI entry points only).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from claire_fivepoints.azure_issue_bridge.worktree import (
    MockWorktreePrepare,
    RealWorktreePrepare,
    WorktreePrepareAdapter,
)

__all__ = [
    "EmailAdapter",
    "GitHubAdapter",
    "LabelAdapter",
    "WorktreePrepareAdapter",
    "BridgeAdapters",
    "GmailApiAdapter",
    "MockEmailAdapter",
    "MockGitHubAdapter",
    "MockLabelAdapter",
    "MockWorktreePrepare",
    "RealWorktreePrepare",
]


class EmailAdapter(Protocol):
    def fetch(self, sender: str, max_results: int) -> list[dict]:
        """Return [{message_id, subject, from_addr, thread_id}]."""
        ...


class GitHubAdapter(Protocol):
    def create_issue(self, title: str, body: str, repo: str) -> int:
        """Create a GitHub issue and return its number."""
        ...


class LabelAdapter(Protocol):
    def add_label(self, repo: str, issue: int, label: str) -> None:
        """Add a label to a GitHub issue. Creates the label if it does not exist."""
        ...


@dataclass
class BridgeAdapters:
    email: EmailAdapter
    github: GitHubAdapter
    labels: LabelAdapter
    worktree: WorktreePrepareAdapter


# ---------------------------------------------------------------------------
# Concrete adapters
# ---------------------------------------------------------------------------


@dataclass
class GmailApiAdapter:
    """Access Gmail via the Google API directly (OAuth2).

    Credentials file: ~/.config/claire/gmail_token.json
    No dependency on MCP or claire email commands.
    """

    credentials_path: Path = field(
        default_factory=lambda: Path.home() / ".config/claire/gmail_token.json"
    )

    def fetch(self, sender: str, max_results: int) -> list[dict]:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        raw = json.loads(self.credentials_path.read_text())
        creds = Credentials.from_authorized_user_info(raw)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            raw["token"] = creds.token
            self.credentials_path.write_text(json.dumps(raw, indent=2))

        service = build("gmail", "v1", credentials=creds)
        result = (
            service.users()
            .messages()
            .list(userId="me", q=f"from:{sender}", maxResults=max_results)
            .execute()
        )
        messages = result.get("messages", [])
        emails = []
        for m in messages:
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=m["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject"],
                )
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            emails.append(
                {
                    "message_id": m["id"],
                    "thread_id": msg["threadId"],
                    "from_addr": headers.get("From", ""),
                    "subject": headers.get("Subject", ""),
                }
            )
        return emails


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class MockLabelAdapter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def add_label(self, repo: str, issue: int, label: str) -> None:
        self.calls.append({"repo": repo, "issue": issue, "label": label})


class MockEmailAdapter:
    def __init__(self, emails: list[dict]) -> None:
        self.emails = emails

    def fetch(self, sender: str, max_results: int) -> list[dict]:
        return [e for e in self.emails if e["from_addr"] == sender][:max_results]


class MockGitHubAdapter:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def create_issue(self, title: str, body: str, repo: str) -> int:
        self.created.append({"title": title, "body": body, "repo": repo})
        return len(self.created)
