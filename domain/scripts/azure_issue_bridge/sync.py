"""
azure_issue_bridge.sync — Branch sync adapter.

Syncs a source GitHub branch to a target repo by fetching from the source
and force-pushing to the target. Used by the bridge pipeline to mirror
fivepoints-test/develop to fivepoints/develop before agent assignment.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from typing import Protocol

logger = logging.getLogger(__name__)


class BranchSyncAdapter(Protocol):
    def sync_branch(
        self,
        source_repo: str,
        source_branch: str,
        target_repo: str,
        target_branch: str,
    ) -> None: ...


class RealBranchSync:
    """Syncs a branch from source_repo to target_repo via git fetch + force-push."""

    def sync_branch(
        self,
        source_repo: str,
        source_branch: str,
        target_repo: str,
        target_branch: str,
    ) -> None:
        gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
        if gh_token:
            source_url = f"https://x-access-token:{gh_token}@github.com/{source_repo}.git"
            target_url = f"https://x-access-token:{gh_token}@github.com/{target_repo}.git"
        else:
            source_url = f"https://github.com/{source_repo}.git"
            target_url = f"https://github.com/{target_repo}.git"

        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                ["git", "init", "--bare", tmpdir],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git init failed: {result.stderr.strip()}")

            result = subprocess.run(
                ["git", "-C", tmpdir, "fetch", source_url, source_branch],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git fetch failed: {result.stderr.strip()}")

            result = subprocess.run(
                [
                    "git",
                    "-C",
                    tmpdir,
                    "push",
                    "--force",
                    target_url,
                    f"FETCH_HEAD:{target_branch}",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git push failed: {result.stderr.strip()}")

        logger.info(
            "Synced %s/%s → %s/%s",
            source_repo,
            source_branch,
            target_repo,
            target_branch,
        )


class MockBranchSync:
    """Test double — records sync_branch calls without executing git."""

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
