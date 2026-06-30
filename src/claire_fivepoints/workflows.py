"""Entry points for fivepoints.tfone.* workflows.

Registered in pyproject.toml under [project.entry-points."claire.workflows"].
Called by 'claire run-pipeline run --workflow fivepoints.tfone.<variant>'.
"""
from __future__ import annotations

import os
from pathlib import Path

from claire_core.pipeline import StepResult
from claire_workflows.fivepoints_pipeline import (
    FivepointsFullAdapters,
    FivepointsFullWorkflow,
    FivepointsGitHubAdapters,
    FivepointsGitHubWorkflow,
    FivepointsTask,
)

from claire_adapters.osascript import load_local_path
from claire_adapters.token import find_repo_entry
from claire_fivepoints.adapters import FivepointsGhAdapter, FivepointsOsascriptTerminalAdapter
from claire_fivepoints.ado_adapter import FivepointsConcreteADOAdapter
from claire_fivepoints.tfone_dev_steps import (
    FivepointsTfoneDevAdapters,
    FivepointsTfoneDevWorkflow,
)


def run_fivepoints_tfone_github_for_issue(
    issue: int,
    repo: str,
    *,
    poll_interval: float = 30.0,
) -> StepResult:
    """Entry point for run-pipeline: builds adapters and runs FivepointsGitHubWorkflow.

    Workflow shape: analyst → dev → tester → manual merge on GitHub.
    """
    task = FivepointsTask(issue=issue, repo=repo)
    adapters = FivepointsGitHubAdapters(
        github=FivepointsGhAdapter.default(repo=repo, poll_interval=poll_interval),
        terminal=FivepointsOsascriptTerminalAdapter.with_role_tokens(repo),
    )
    return FivepointsGitHubWorkflow().run(task, adapters)


def run_fivepoints_tfone_full_for_issue(
    issue: int,
    repo: str,
    *,
    poll_interval: float = 30.0,
) -> StepResult:
    """Entry point for run-pipeline: builds adapters and runs FivepointsFullWorkflow.

    Workflow shape: analyst → dev → tester → ADO push → ADO merge.

    Requires ADO configuration in github_repos.yaml:
      ado_org, ado_project, ado_repo
    """
    task = FivepointsTask(issue=issue, repo=repo)
    adapters = FivepointsFullAdapters(
        github=FivepointsGhAdapter.default(repo=repo, poll_interval=poll_interval),
        terminal=FivepointsOsascriptTerminalAdapter.with_role_tokens(repo),
        ado=FivepointsConcreteADOAdapter.for_repo(repo),
    )
    return FivepointsFullWorkflow().run(task, adapters)


def run_fivepoints_tfone_dev_for_issue(
    issue: int,
    repo: str,
    *,
    poll_interval: float = 30.0,
) -> StepResult:
    """Entry point for run-pipeline: builds adapters and runs FivepointsTfoneDevWorkflow.

    Workflow shape: DevWithADOContextStep → TesterStep → ADO push → ADO merge.

    The dev reads the ADO work item and downloads attachments before implementing;
    no analyst session is required.

    Requires ADO configuration in github_repos.yaml:
      ado_org, ado_project, ado_repo
    """
    entry = find_repo_entry(repo) or {}
    ado_org = (
        entry.get("ado_org")
        or os.environ.get("AZURE_DEVOPS_ORG", "FivePointsTechnology")
    )
    ado_project = (
        entry.get("ado_project")
        or os.environ.get("AZURE_DEVOPS_PROJECT", "TFIOne")
    )
    local_path = Path(load_local_path(repo))

    task = FivepointsTask(issue=issue, repo=repo)
    adapters = FivepointsTfoneDevAdapters(
        github=FivepointsGhAdapter.default(repo=repo, poll_interval=poll_interval),
        terminal=FivepointsOsascriptTerminalAdapter.with_role_tokens(repo),
        ado=FivepointsConcreteADOAdapter.for_repo(repo),
        local_path=local_path,
        ado_org=ado_org,
        ado_project=ado_project,
    )
    return FivepointsTfoneDevWorkflow().run(task, adapters)
