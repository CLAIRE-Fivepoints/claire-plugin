"""
azure_issue_bridge.sync — Branch sync adapter.

Syncs a source GitHub branch to a target repo using the GitHub REST API
(GET ref SHA → PATCH/POST ref). Used by the bridge pipeline to mirror
fivepoints-test/develop to fivepoints/develop before agent assignment.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Protocol

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


class BranchSyncAdapter(Protocol):
    def sync_branch(
        self,
        source_repo: str,
        source_branch: str,
        target_repo: str,
        target_branch: str,
    ) -> None: ...


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
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if gh_token:
            headers["Authorization"] = f"Bearer {gh_token}"

        # Step 1: resolve the tip SHA of the source branch
        sha = self._get_branch_sha(source_repo, source_branch, headers)

        # Step 2: force-update the target branch (create if it doesn't exist yet)
        self._set_branch_sha(target_repo, target_branch, sha, headers)

        logger.info(
            "Synced %s/%s → %s/%s (sha=%.7s)",
            source_repo,
            source_branch,
            target_repo,
            target_branch,
            sha,
        )

    # ------------------------------------------------------------------
    # Private helpers — errors never include the Authorization header value
    # ------------------------------------------------------------------

    @staticmethod
    def _get_branch_sha(repo: str, branch: str, headers: dict[str, str]) -> str:
        url = f"{_GITHUB_API}/repos/{repo}/git/ref/heads/{branch}"
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
        """Force-update `branch` in `repo` to `sha`. Creates the ref if absent."""
        content_headers = {**headers, "Content-Type": "application/json"}

        # Attempt PATCH (update existing ref with force=True)
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

        # 422 → ref does not exist yet; create it
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


class MockBranchSync:
    """Test double — records sync_branch calls without hitting the GitHub API."""

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
