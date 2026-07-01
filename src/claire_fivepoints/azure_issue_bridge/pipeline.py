"""azure_issue_bridge.pipeline — BridgeTask and the composed bridge_pipeline."""
from __future__ import annotations

from claire_core.pipeline import pipe
from claire_core.types import Task

from claire_fivepoints.azure_issue_bridge.steps import (
    create_issues_step,
    fetch_emails_step,
    filter_pbi_step,
)


class BridgeTask(Task):
    description: str = "Azure DevOps PBI email bridge"
    sender: str = "azuredevops@microsoft.com"
    max_results: int = 20
    dry_run: bool = False
    client: str = "fivepoints"
    source_repo: str = "CLAIRE-Fivepoints/fivepoints-test"
    branch_prefix: str = "pbi"
    agent: str = "claire-test-ai"


bridge_pipeline = pipe(
    fetch_emails_step,
    filter_pbi_step,
    create_issues_step,
)
