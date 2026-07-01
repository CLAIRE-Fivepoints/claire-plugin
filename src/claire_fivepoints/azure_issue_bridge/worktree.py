"""azure_issue_bridge.worktree — WorktreePrepare adapter: Protocol + real/mock implementations.

Responsible for creating a git worktree for a GitHub issue on a named branch
before the issue is assigned to the agent.  The worktree is created at the
standard path (<local_path>/.claire/worktrees/issue-<N>) so that claire start
--issue N --repo R reuses it without re-creating (idempotent hand-off).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class WorktreePrepareAdapter(Protocol):
    """Protocol for creating a git worktree before issue assignment."""

    def prepare(
        self,
        repo: str,
        issue: int,
        base_branch: str,
        branch_name: str | None = None,
    ) -> str:
        """Create a worktree on base_branch, optionally on a new named branch.

        Args:
            repo:        GitHub repo slug, e.g. "CLAIRE-Fivepoints/fivepoints".
            issue:       GitHub issue number.
            base_branch: Branch to base the worktree on, e.g. "develop".
            branch_name: Name of a new branch to create for the worktree, e.g.
                         "pbi-42". When omitted, the worktree checks out
                         base_branch in a detached HEAD state — no branch is
                         created or named. Branch naming is the dev agent's
                         responsibility (see PrepareWorktreeStep).

        Returns:
            Absolute filesystem path to the created (or already-existing) worktree.

        Raises:
            RuntimeError: When the worktree cannot be created.
        """
        ...


class RealWorktreePrepare:
    """Creates a git worktree under <local_path>/.claire/worktrees/issue-<N>.

    The local_path is resolved from ~/.config/claire/github_repos.yaml.  If not
    found there, falls back to ~/.claire/repos/<owner>/<name> (auto-clone cache).
    """

    def __init__(self, local_path: str | Path | None = None) -> None:
        self._local_path = str(local_path) if local_path is not None else None

    def prepare(
        self,
        repo: str,
        issue: int,
        base_branch: str,
        branch_name: str | None = None,
    ) -> str:
        local_path = Path(self._local_path or self._resolve_local_path(repo))
        worktree_path = local_path / ".claire" / "worktrees" / f"issue-{issue}"

        if worktree_path.exists():
            logger.info("Worktree already exists at %s — reusing", worktree_path)
            return str(worktree_path)

        logger.info(
            "Fetching %s from ado remote to sync %s with TFIOneGit/dev", repo, base_branch
        )
        self._run(["git", "-C", str(local_path), "fetch", "ado", "dev"], repo=repo)
        self._run(
            ["git", "-C", str(local_path), "branch", "-f", base_branch, "ado/dev"],
            repo=repo,
        )

        if branch_name:
            logger.info(
                "Creating worktree %s on branch %s (from %s)",
                worktree_path,
                branch_name,
                base_branch,
            )
            self._run(
                [
                    "git",
                    "-C",
                    str(local_path),
                    "worktree",
                    "add",
                    "--track",
                    "-b",
                    branch_name,
                    str(worktree_path),
                    base_branch,
                ],
                repo=repo,
            )
            logger.info("Worktree created at %s (branch: %s)", worktree_path, branch_name)
        else:
            logger.info(
                "Creating worktree %s on %s (detached — no named branch)",
                worktree_path,
                base_branch,
            )
            self._run(
                [
                    "git",
                    "-C",
                    str(local_path),
                    "worktree",
                    "add",
                    "--detach",
                    str(worktree_path),
                    base_branch,
                ],
                repo=repo,
            )
            logger.info("Worktree created at %s (detached from %s)", worktree_path, base_branch)

        return str(worktree_path)

    @staticmethod
    def _run(cmd: list[str], *, repo: str) -> None:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git command failed for {repo!r}: {' '.join(cmd)}\n"
                f"stderr: {result.stderr.strip()}"
            )

    @staticmethod
    def _resolve_local_path(repo: str) -> str:
        """Resolve the local checkout path for repo from config or auto-clone cache."""
        try:
            import yaml  # type: ignore[import-untyped]

            config = Path("~/.config/claire/github_repos.yaml").expanduser()
            if config.exists():
                with open(config) as f:
                    data = yaml.safe_load(f)
                for entry in (data or {}).get("repos", []):
                    slug = f"{entry.get('owner', '')}/{entry.get('name', '')}"
                    if slug == repo:
                        lp = entry.get("local_path")
                        if lp:
                            return str(Path(lp).expanduser())
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not read github_repos.yaml: %s", exc)

        owner, name = repo.split("/", 1)
        cache = Path("~/.claire/repos").expanduser() / owner / name
        if cache.exists():
            return str(cache)

        raise RuntimeError(
            f"Cannot resolve local path for repo {repo!r}. "
            "Add a local_path entry in ~/.config/claire/github_repos.yaml "
            "or ensure the auto-clone cache exists at ~/.claire/repos/<owner>/<name>."
        )


class MockWorktreePrepare:
    """Test double for WorktreePrepareAdapter.

    Records every prepare() call in self.prepared for assertion in tests.
    Never touches the filesystem.
    """

    def __init__(self) -> None:
        self.prepared: list[dict] = []

    def prepare(
        self,
        repo: str,
        issue: int,
        base_branch: str,
        branch_name: str | None = None,
    ) -> str:
        entry = {
            "repo": repo,
            "issue": issue,
            "base_branch": base_branch,
            "branch": branch_name,
        }
        self.prepared.append(entry)
        logger.debug("MockWorktreePrepare.prepare called: %s", entry)
        return f"/mock/worktrees/{branch_name or f'issue-{issue}'}"
