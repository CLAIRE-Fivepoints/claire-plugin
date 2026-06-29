"""FivepointsConcreteADOAdapter — push branch to ADO and create a PR.

Reads ADO coordinates from github_repos.yaml:
  ado_org, ado_project, ado_repo

Requires AZURE_DEVOPS_PAT in ~/.config/claire/github_manager.env.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from claire_adapters.ado import ADORestAdapter
from claire_adapters.token import CONFIG_DIR, find_repo_entry, parse_env_file
from claire_core.logging_config import get_logger

logger = get_logger(__name__)


@runtime_checkable
class GitRunner(Protocol):
    """Abstraction for git CLI operations — injectable for tests."""

    def push(self, remote: str, refspec: str) -> None: ...


class SubprocessGitRunner:
    """Concrete GitRunner that delegates to the git CLI."""

    def push(self, remote: str, refspec: str) -> None:
        import subprocess
        subprocess.run(["git", "push", remote, refspec], check=True)


@dataclass
class FivepointsConcreteADOAdapter:
    """Implements FivepointsADOAdapter: push branch to ADO, wait for merge."""

    ado: ADORestAdapter
    git: GitRunner = field(default_factory=SubprocessGitRunner)
    remote_name: str = "ado"

    @classmethod
    def for_repo(
        cls,
        repo: str,
        config_dir: Path | None = None,
    ) -> "FivepointsConcreteADOAdapter":
        _config_dir = config_dir if config_dir is not None else CONFIG_DIR
        entry = find_repo_entry(repo, config_dir=config_dir) or {}
        ado_org = entry.get("ado_org") or os.environ.get("AZURE_DEVOPS_ORG", "")
        ado_project = entry.get("ado_project") or os.environ.get("AZURE_DEVOPS_PROJECT", "")
        ado_repo = entry.get("ado_repo") or os.environ.get("AZURE_DEVOPS_REPO", "")
        if not (ado_org and ado_project and ado_repo):
            raise RuntimeError(
                "ADO not configured for this repo. "
                "Set ado_org, ado_project, ado_repo in github_repos.yaml "
                "or AZURE_DEVOPS_ORG/PROJECT/REPO env vars."
            )
        env = parse_env_file(_config_dir / "github_manager.env")
        pat = env.get("AZURE_DEVOPS_PAT") or os.environ.get("AZURE_DEVOPS_PAT", "")
        return cls(
            ado=ADORestAdapter(org=ado_org, project=ado_project, repo=ado_repo, pat=pat),
        )

    def push_branch_and_create_pr(self, issue: int) -> int:
        branch = f"issue-{issue}"
        self.git.push(self.remote_name, f"{branch}:{branch}")
        pr = self.ado.find_pr_for_branch(branch)
        if pr is None:
            raise RuntimeError(f"No ADO PR found for branch {branch} after push")
        pr_id: int = pr["pullRequestId"]
        logger.info("fivepoints.ado.pr_created", extra={"issue": issue, "ado_pr_id": pr_id})
        return pr_id

    def wait_for_merge(self, ado_pr_id: int) -> None:
        while True:
            status = self.ado.get_pr_status(ado_pr_id)
            if status == "completed":
                logger.info("fivepoints.ado.merged", extra={"ado_pr_id": ado_pr_id})
                return
            if status == "abandoned":
                raise RuntimeError(f"ADO PR {ado_pr_id} was abandoned")
            time.sleep(30)
