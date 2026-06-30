"""Steps and workflow for fivepoints.tfone.dev — dev does everything, no analyst.

Pipeline shape:
  pipe(
    HydrateStateStep(),   # reads role label; populates ctx for restart recovery
    SpawnDevStep(),       # spawn dev terminal + wait for role:tester label
    TesterStep(),         # spawn tester + wait role:ready
    PushToADOStep(),      # push branch to ADO + create PR  (from fivepoints_pipeline)
    WaitForADOMergeStep(),# block until ADO PR merged        (from fivepoints_pipeline)
  )

The dev agent reads the GitHub issue body (populated by the bridge) and downloads
ADO attachments itself — the workflow does not pre-fetch ADO context.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claire_core.logging_config import get_logger
from claire_core.pipeline import StepResult, pipe
from claire_workflows.fivepoints_pipeline import (
    FivepointsADOAdapter,
    FivepointsGitHubAdapter,
    FivepointsTask,
    FivepointsTerminalAdapter,
    HydrateStateStep,
    PushToADOStep,
    WaitForADOMergeStep,
)

logger = get_logger(__name__)

_LABEL_TESTER = "role:tester"
_LABEL_READY = "role:ready"


# ---------------------------------------------------------------------------
# Adapters dataclass
# ---------------------------------------------------------------------------


@dataclass
class FivepointsTfoneDevAdapters:
    """Adapters required by FivepointsTfoneDevWorkflow."""

    github: FivepointsGitHubAdapter
    terminal: FivepointsTerminalAdapter
    ado: FivepointsADOAdapter
    local_path: Path
    ado_org: str
    ado_project: str


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


class SpawnDevStep:
    """Spawn dev session and wait for role:tester label.

    The dev agent reads the GitHub issue body (populated by the bridge with ADO
    content) and downloads attachments itself via ADO REST API. The workflow
    does not pre-fetch ADO context — the issue contains everything needed.

    On restart, HydrateStateStep pre-populates ctx with dev_done=True when
    role:tester (or role:ready) is already present — this step then no-ops.
    """

    def __call__(
        self,
        task: FivepointsTask,
        ctx: dict[str, Any],
        adapters: FivepointsTfoneDevAdapters,
    ) -> StepResult:
        if ctx.get("dev_done"):
            logger.info(
                "tfone_dev.spawn_dev.skipped",
                extra={"issue": task.issue, "repo": task.repo},
            )
            return StepResult(ok=True, data={})

        adapters.terminal.spawn_dev(task.issue, task.repo)
        logger.info(
            "tfone_dev.spawn_dev.done",
            extra={"issue": task.issue, "repo": task.repo},
        )

        adapters.github.wait_for_label(task.repo, task.issue, _LABEL_TESTER)
        pr_number = adapters.github.find_pr_for_issue(task.repo, task.issue)
        logger.info(
            "tfone_dev.dev_done",
            extra={"issue": task.issue, "repo": task.repo, "pr_number": pr_number},
        )

        return StepResult(ok=True, data={"dev_done": True, "pr_number": pr_number})


class TesterStep:
    """Spawn tester session and wait until role:ready label is applied.

    Skips if ctx already has tester_done=True (set by HydrateStateStep on restart
    when role:ready is already present).
    """

    def __call__(
        self,
        task: FivepointsTask,
        ctx: dict[str, Any],
        adapters: FivepointsTfoneDevAdapters,
    ) -> StepResult:
        if ctx.get("tester_done"):
            logger.info(
                "tfone_dev.tester.skipped",
                extra={"issue": task.issue, "repo": task.repo},
            )
            return StepResult(ok=True, data={})

        adapters.terminal.spawn_tester(task.issue, task.repo)
        logger.info(
            "tfone_dev.spawn_tester.done",
            extra={"issue": task.issue, "repo": task.repo},
        )

        adapters.github.wait_for_label(task.repo, task.issue, _LABEL_READY)
        logger.info(
            "tfone_dev.tester_done",
            extra={"issue": task.issue, "repo": task.repo},
        )

        return StepResult(ok=True, data={"tester_done": True})


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


class FivepointsTfoneDevWorkflow:
    """dev-only variant: HydrateState → SpawnDev → Tester → ADO push → ADO merge.

    HydrateStateStep reads the current role label at startup and populates ctx
    so restart recovery works correctly:
      role:tester present  → dev_done=True  (skip SpawnDevStep)
      role:ready  present  → dev_done=True, tester_done=True (skip both)

    Usage::

        workflow = FivepointsTfoneDevWorkflow()
        result = workflow.run(task, adapters)   # adapters: FivepointsTfoneDevAdapters
    """

    def __init__(self) -> None:
        self._pipeline = pipe(
            HydrateStateStep(),
            SpawnDevStep(),
            TesterStep(),
            PushToADOStep(),
            WaitForADOMergeStep(),
        )

    def run(
        self, task: FivepointsTask, adapters: FivepointsTfoneDevAdapters
    ) -> StepResult:
        return self._pipeline(task, adapters)
