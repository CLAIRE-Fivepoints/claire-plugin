"""Entry points for fivepoints.tfone.* workflows.

Registered in pyproject.toml under [project.entry-points."claire.workflows"].
Called by 'claire run-pipeline run --workflow fivepoints.tfone.github'.
"""
from __future__ import annotations

from claire_core.pipeline import StepResult
from claire_workflows.fivepoints_pipeline import (
    FivepointsFullAdapters,
    FivepointsFullWorkflow,
    FivepointsGitHubAdapters,
    FivepointsGitHubWorkflow,
    FivepointsTask,
)

from claire_fivepoints.adapters import FivepointsGhAdapter, FivepointsOsascriptTerminalAdapter


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
    from claire_fivepoints.ado_adapter import FivepointsConcreteADOAdapter

    task = FivepointsTask(issue=issue, repo=repo)
    adapters = FivepointsFullAdapters(
        github=FivepointsGhAdapter.default(repo=repo, poll_interval=poll_interval),
        terminal=FivepointsOsascriptTerminalAdapter.with_role_tokens(repo),
        ado=FivepointsConcreteADOAdapter.for_repo(repo),
    )
    return FivepointsFullWorkflow().run(task, adapters)
