"""Concrete adapters for the fivepoints pipeline.

FivepointsGhAdapter      — implements FivepointsGitHubAdapter on top of GhProjectAdapter
FivepointsOsascriptTerminalAdapter — implements FivepointsTerminalAdapter via osascript
"""
from __future__ import annotations

import shlex
import time
from dataclasses import dataclass
from pathlib import Path

from claire_adapters.osascript import (
    OsascriptRunner,
    SubprocessOsascriptRunner,
    build_token_export_prefix,
    load_local_path,
)
from claire_adapters.project import GhProjectAdapter
from claire_adapters.token import find_repo_entry, load_token_for_agent, resolve_repo_agent
from claire_core.logging_config import get_logger

logger = get_logger(__name__)

# Labels progress in this order — used by wait_for_label to handle fast pipelines.
_ROLE_ORDER = ["role:dev", "role:tester", "role:ready"]


@dataclass
class FivepointsGhAdapter:
    """Implements FivepointsGitHubAdapter using GhProjectAdapter + direct gh calls.

    get_role_label and wait_for_label are not in GhProjectAdapter (they are
    fivepoints-domain specifics) so they are implemented here.
    """

    _gh: GhProjectAdapter
    poll_interval: float = 30.0

    @classmethod
    def default(cls, repo: str, poll_interval: float = 30.0) -> "FivepointsGhAdapter":
        return cls(_gh=GhProjectAdapter.default(repo=repo), poll_interval=poll_interval)

    def is_issue_closed(self, repo: str, issue: int) -> bool:
        return self._gh.is_issue_closed(repo, issue)

    def get_role_label(self, repo: str, issue: int) -> str | None:
        output = self._gh.runner.run(
            "issue", "view", str(issue),
            "--repo", repo,
            "--json", "labels",
            "-q", '[.labels[].name | select(startswith("role:"))] | first // ""',
        )
        label = output.strip()
        return label if label else None

    def wait_for_label(self, repo: str, issue: int, label: str) -> None:
        target_idx = _ROLE_ORDER.index(label) if label in _ROLE_ORDER else 0
        while True:
            current = self.get_role_label(repo, issue)
            if current:
                current_idx = _ROLE_ORDER.index(current) if current in _ROLE_ORDER else -1
                if current_idx >= target_idx:
                    logger.info(
                        "fivepoints.wait_label.found",
                        extra={"repo": repo, "issue": issue, "wanted": label, "found": current},
                    )
                    return
            time.sleep(self.poll_interval)

    def find_pr_for_issue(self, repo: str, issue: int) -> int | None:
        return self._gh.find_pr_for_issue(repo, issue)


@dataclass
class FivepointsOsascriptTerminalAdapter:
    """Implements FivepointsTerminalAdapter — opens Terminal.app windows via osascript.

    Reads role-specific personas and tokens from github_repos.yaml:
      analyst_persona / analyst_agent
      dev_persona     / dev_agent
      tester_persona  / tester_agent
    """

    runner: OsascriptRunner
    analyst_token: str | None = None
    dev_token: str | None = None
    tester_token: str | None = None
    config_dir: Path | None = None

    @classmethod
    def with_role_tokens(
        cls, repo: str, config_dir: Path | None = None
    ) -> "FivepointsOsascriptTerminalAdapter":
        analyst_agent = resolve_repo_agent(repo, "analyst", config_dir=config_dir)
        dev_agent = resolve_repo_agent(repo, "dev", config_dir=config_dir)
        tester_agent = resolve_repo_agent(repo, "tester", config_dir=config_dir)
        return cls(
            runner=SubprocessOsascriptRunner(),
            analyst_token=load_token_for_agent(analyst_agent, config_dir=config_dir),
            dev_token=load_token_for_agent(dev_agent, config_dir=config_dir),
            tester_token=load_token_for_agent(tester_agent, config_dir=config_dir),
            config_dir=config_dir,
        )

    def spawn_analyst(self, issue: int, repo: str) -> None:
        self._open_role_terminal(issue, repo, "analyst", self.analyst_token)
        logger.info("fivepoints.spawn_analyst.terminal", extra={"issue": issue, "repo": repo})

    def spawn_dev(self, issue: int, repo: str) -> None:
        self._open_role_terminal(issue, repo, "dev", self.dev_token)
        logger.info("fivepoints.spawn_dev.terminal", extra={"issue": issue, "repo": repo})

    def spawn_tester(self, issue: int, repo: str) -> None:
        self._open_role_terminal(issue, repo, "tester", self.tester_token)
        logger.info("fivepoints.spawn_tester.terminal", extra={"issue": issue, "repo": repo})

    def _open_role_terminal(
        self, issue: int, repo: str, role: str, token: str | None
    ) -> None:
        local_path = load_local_path(repo, config_dir=self.config_dir)
        entry = find_repo_entry(repo, config_dir=self.config_dir) or {}
        persona = entry.get(f"{role}_persona", "")
        prefix = build_token_export_prefix(token) if token else ""
        cd_prefix = f"cd {shlex.quote(str(local_path))} && "
        persona_flag = f"--persona {shlex.quote(persona)} " if persona else ""
        cmd = (
            f"{prefix}{cd_prefix}claire start "
            f"--issue {issue} "
            f"--repo {shlex.quote(repo)} "
            f"{persona_flag}"
        )
        escaped = cmd.replace('"', '\\"')
        script = f'tell application "Terminal" to do script "{escaped}"'
        self.runner.run(script)
