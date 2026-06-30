"""Steps and workflow for fivepoints.tfone.dev — dev does everything, no analyst.

Pipeline shape:
  pipe(
    DevWithADOContextStep(),   # fetch ADO context + download attachments + spawn dev + wait
    TesterStep(),              # spawn tester + wait role:ready
    PushToADOStep(),           # push branch to ADO + create PR  (from fivepoints_pipeline)
    WaitForADOMergeStep(),     # block until ADO PR merged        (from fivepoints_pipeline)
  )
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
    PushToADOStep,
    WaitForADOMergeStep,
)

from claire_fivepoints.ado_context_adapter import ADOContextAdapter

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
    ado_context: ADOContextAdapter
    local_path: Path
    ado_org: str
    ado_project: str


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _write_ado_context_summary(
    work_item: dict, attachment_paths: list[Path], dest_file: Path
) -> None:
    """Write a human-readable ADO context summary to *dest_file*."""
    fields = work_item.get("fields") or {}
    title = fields.get("System.Title", "")
    description = fields.get("System.Description", "")
    acceptance_criteria = fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", "")
    area = fields.get("System.AreaPath", "")
    state = fields.get("System.State", "")
    work_type = fields.get("System.WorkItemType", "")
    item_id = work_item.get("id", "")

    lines = [
        f"# ADO Work Item #{item_id} — {title}",
        "",
        f"**Area:** {area}",
        f"**State:** {state}",
        f"**Type:** {work_type}",
        "",
    ]

    if description:
        lines += ["## Description", "", description, ""]

    if acceptance_criteria:
        lines += ["## Acceptance Criteria", "", acceptance_criteria, ""]

    if attachment_paths:
        lines += ["## Attachments", ""]
        for path in attachment_paths:
            lines.append(f"- `{path.name}` → `{path}`")
        lines.append("")

    dest_file.write_text("\n".join(lines), encoding="utf-8")
    logger.info("ado_context.summary_written path=%s", dest_file)


class DevWithADOContextStep:
    """Fetch ADO context, download attachments, spawn dev session, wait for completion.

    On restart (ctx already has dev_done=True), the step is a no-op so the
    pipeline can resume at TesterStep without re-spawning the dev.
    """

    def __call__(
        self,
        task: FivepointsTask,
        ctx: dict[str, Any],
        adapters: FivepointsTfoneDevAdapters,
    ) -> StepResult:
        if ctx.get("dev_done"):
            logger.info(
                "tfone_dev.dev_with_ado_context.skipped",
                extra={"issue": task.issue, "repo": task.repo},
            )
            return StepResult(ok=True, data={})

        dest = adapters.local_path / ".claire" / "attachments" / f"issue-{task.issue}"

        work_item = adapters.ado_context.fetch_work_item(
            adapters.ado_org, adapters.ado_project, task.issue
        )
        logger.info(
            "tfone_dev.ado_context.fetched",
            extra={"issue": task.issue, "org": adapters.ado_org},
        )

        attachment_paths = adapters.ado_context.download_attachments(
            adapters.ado_org, adapters.ado_project, task.issue, dest
        )
        logger.info(
            "tfone_dev.ado_context.attachments_downloaded",
            extra={"issue": task.issue, "count": len(attachment_paths)},
        )

        context_file = dest / "ADO_CONTEXT.md"
        _write_ado_context_summary(work_item, attachment_paths, context_file)

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

    Skips if ctx already has tester_done=True (pipeline restart recovery).
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
    """dev-only variant: DevWithADOContextStep → TesterStep → ADO push → ADO merge.

    Usage::

        workflow = FivepointsTfoneDevWorkflow()
        result = workflow.run(task, adapters)   # adapters: FivepointsTfoneDevAdapters
    """

    def __init__(self) -> None:
        self._pipeline = pipe(
            DevWithADOContextStep(),
            TesterStep(),
            PushToADOStep(),
            WaitForADOMergeStep(),
        )

    def run(
        self, task: FivepointsTask, adapters: FivepointsTfoneDevAdapters
    ) -> StepResult:
        return self._pipeline(task, adapters)
