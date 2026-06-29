"""azure_issue_bridge.adapters — EmailAdapter, GitHubAdapter, LabelAdapter, BranchSyncAdapter, WorktreePrepareAdapter, AssignAdapter protocols, concrete adapters, and test doubles.

- GmailApiAdapter: accesses Gmail via the Google API directly (OAuth2) — no subprocess.
- RealBranchSync: syncs branches via the GitHub REST API (urllib) — no subprocess.
- RealWorktreePrepare: creates git worktrees via subprocess git — no GitHub CLI.
- CLI-backed adapters (GhCliAdapter, RealLabelAdapter, RealAssignAdapter) remain in cli.py (subprocess.run in CLI entry points only).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from claire_fivepoints.azure_issue_bridge.worktree import (
    MockWorktreePrepare,
    RealWorktreePrepare,
    WorktreePrepareAdapter,
)

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"

__all__ = [
    "EmailAdapter",
    "GitHubAdapter",
    "LabelAdapter",
    "BranchSyncAdapter",
    "WorktreePrepareAdapter",
    "AssignAdapter",
    "BridgeAdapters",
    "GmailApiAdapter",
    "RealBranchSync",
    "RealWorktreePrepare",
    "MockBranchSync",
    "MockEmailAdapter",
    "MockGitHubAdapter",
    "MockLabelAdapter",
    "MockWorktreePrepare",
    "MockAssignAdapter",
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


class BranchSyncAdapter(Protocol):
    def sync_branch(
        self,
        source_repo: str,
        source_branch: str,
        target_repo: str,
        target_branch: str,
    ) -> None:
        """Force-update target_branch in target_repo to match source_branch in source_repo."""
        ...


class AssignAdapter(Protocol):
    def assign(self, repo: str, issue: int, agent: str) -> None:
        """Assign the issue to the agent. Triggers the session-monitor."""
        ...


@dataclass
class BridgeAdapters:
    email: EmailAdapter
    github: GitHubAdapter
    labels: LabelAdapter
    branch_sync: BranchSyncAdapter
    worktree: WorktreePrepareAdapter
    assign: AssignAdapter


# ---------------------------------------------------------------------------
# Concrete adapters
# ---------------------------------------------------------------------------


class RealBranchSync:
    """Syncs a branch from source_repo to target_repo via the GitHub REST API."""

    def sync_branch(
        self,
        source_repo: str,
        source_branch: str,
        target_repo: str,
        target_branch: str,
    ) -> None:
        gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
        if not gh_token:
            logger.debug("No GitHub token found — proceeding unauthenticated")
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if gh_token:
            headers["Authorization"] = f"Bearer {gh_token}"

        sha = self._get_branch_sha(source_repo, source_branch, headers)
        self._set_branch_sha(target_repo, target_branch, sha, headers)
        logger.info(
            "Synced %s/%s → %s/%s (sha=%.7s)",
            source_repo, source_branch, target_repo, target_branch, sha,
        )

    @staticmethod
    def _get_branch_sha(repo: str, branch: str, headers: dict[str, str]) -> str:
        url = f"{_GITHUB_API}/repos/{repo}/git/refs/heads/{branch}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())["object"]["sha"]
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"Cannot read {repo}/{branch}: GitHub API returned HTTP {exc.code}"
            ) from exc

    @staticmethod
    def _set_branch_sha(
        repo: str, branch: str, sha: str, headers: dict[str, str]
    ) -> None:
        """Force-update branch in repo to sha. Creates the ref if absent."""
        content_headers = {**headers, "Content-Type": "application/json"}
        patch_payload = json.dumps({"sha": sha, "force": True}).encode()
        patch_req = urllib.request.Request(
            f"{_GITHUB_API}/repos/{repo}/git/refs/heads/{branch}",
            data=patch_payload,
            headers=content_headers,
            method="PATCH",
        )
        try:
            with urllib.request.urlopen(patch_req):
                return
        except urllib.error.HTTPError as exc:
            if exc.code != 422:
                raise RuntimeError(
                    f"Cannot update {repo}/{branch}: GitHub API returned HTTP {exc.code}"
                ) from exc
            body = exc.read().decode(errors="replace")
            if "Reference does not exist" not in body:
                raise RuntimeError(
                    f"Cannot update {repo}/{branch}: GitHub API returned HTTP 422: {body}"
                ) from exc
        # 422 "Reference does not exist" → create it
        post_payload = json.dumps(
            {"ref": f"refs/heads/{branch}", "sha": sha}
        ).encode()
        post_req = urllib.request.Request(
            f"{_GITHUB_API}/repos/{repo}/git/refs",
            data=post_payload,
            headers=content_headers,
        )
        try:
            with urllib.request.urlopen(post_req):
                return
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"Cannot create {repo}/{branch}: GitHub API returned HTTP {exc.code}"
            ) from exc


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


class MockBranchSync:
    def __init__(self) -> None:
        self.syncs: list[tuple[str, str, str, str]] = []

    def sync_branch(
        self,
        source_repo: str,
        source_branch: str,
        target_repo: str,
        target_branch: str,
    ) -> None:
        self.syncs.append((source_repo, source_branch, target_repo, target_branch))


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


class MockAssignAdapter:
    def __init__(self) -> None:
        self.assignments: list[dict] = []

    def assign(self, repo: str, issue: int, agent: str) -> None:
        self.assignments.append({"repo": repo, "issue": issue, "agent": agent})
