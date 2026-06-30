"""Steps and workflow for fivepoints.tfone.dev — dev does everything, no analyst.

Pipeline shape:
  pipe(
    HydrateStateStep(),     # reads role label; populates ctx for restart recovery
    PrepareWorktreeStep(),  # idempotent worktree + feature/{pbi_id}-{slug} branch
    SpawnDevStep(),         # spawn dev terminal + wait for role:tester label
    TesterStep(),           # spawn tester + wait role:ready
    PushToADOStep(),        # push branch_name (from ctx) to ADO + create PR
    WaitForADOMergeStep(),  # block until ADO PR merged        (from fivepoints_pipeline)
  )

The dev agent reads the GitHub issue body (populated by the bridge) and downloads
ADO attachments itself — the workflow does not pre-fetch ADO context.

PushToADOStep is defined locally (not imported from claire_workflows.fivepoints_pipeline)
because it pushes the branch_name produced by PrepareWorktreeStep rather than deriving
issue-{N} from the issue number alone.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from claire_adapters.github import GhRunner, SubprocessGhRunner
from claire_core.logging_config import get_logger
from claire_core.pipeline import StepResult, pipe
from claire_workflows.fivepoints_pipeline import (
    FivepointsGitHubAdapter,
    FivepointsTask,
    FivepointsTerminalAdapter,
    HydrateStateStep,
    WaitForADOMergeStep,
)

from claire_fivepoints.ado_adapter import FivepointsADOAdapter
from claire_fivepoints.azure_issue_bridge.worktree import RealWorktreePrepare

logger = get_logger(__name__)

_LABEL_TESTER = "role:tester"
_LABEL_READY = "role:ready"

_META_TAG = "<!-- claire:meta -->"
_PBI_ID_PATTERN = re.compile(r"_workitems/edit/(\d+)")
_BRANCH_PATTERN = re.compile(r"\*\*Branch:\*\* `([^`]+)`")
_BRANCH_NAME_PATTERN = re.compile(r"^feature/\d+-[a-z0-9-]+$")
_SLUG_MAX_LEN = 50


# ---------------------------------------------------------------------------
# Branch naming helpers
# ---------------------------------------------------------------------------


def _slugify(title: str, max_len: int = _SLUG_MAX_LEN) -> str:
    """Derive a branch-safe slug from an issue title.

    "PBI: Case Face Sheet - Enhancement" -> "case-face-sheet-enhancement"
    """
    text = re.sub(r"^PBI:\s*", "", title, flags=re.IGNORECASE)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].rstrip("-")


def _extract_pbi_id(body: str) -> str:
    match = _PBI_ID_PATTERN.search(body)
    if not match:
        raise RuntimeError(
            "Could not extract pbi_id from issue body — "
            "no ADO _workitems/edit/<id> link found"
        )
    return match.group(1)


def _is_valid_branch_name(branch_name: str) -> bool:
    """Guard against forged/malformed branch names before they reach `git push`.

    Anchored to the feature/{pbi_id}-{slug} shape this step itself produces — a
    value recovered from an (unauthenticated) issue comment that doesn't match
    can never start with '-' and can't smuggle extra git CLI flags/arguments
    through the `{branch}:{branch}` refspec.
    """
    return bool(_BRANCH_NAME_PATTERN.match(branch_name))


# ---------------------------------------------------------------------------
# GhIssueMetaAdapter — reads the issue, reads/posts the claire:meta comment
# ---------------------------------------------------------------------------


@runtime_checkable
class GhIssueMetaAdapter(Protocol):
    """Reads the GitHub issue and reads/writes the claire:meta tracking comment."""

    def get_issue(self, repo: str, issue: int) -> dict[str, Any]: ...
    def find_meta_comment(self, repo: str, issue: int) -> str | None: ...
    def post_comment(self, repo: str, issue: int, body: str) -> None: ...


@dataclass
class GhCliIssueMetaAdapter:
    """Concrete GhIssueMetaAdapter — delegates to the shared GhRunner abstraction
    (claire_adapters.github.SubprocessGhRunner), the same gh CLI wrapper already
    used by GhProjectAdapter / FivepointsGhAdapter elsewhere in this plugin.
    """

    runner: GhRunner = field(default_factory=SubprocessGhRunner)

    def get_issue(self, repo: str, issue: int) -> dict[str, Any]:
        output = self.runner.run(
            "issue", "view", str(issue), "--repo", repo, "--json", "body,title",
        )
        data: dict[str, Any] = json.loads(output)
        return data

    def find_meta_comment(self, repo: str, issue: int) -> str | None:
        try:
            output = self.runner.run(
                "issue", "view", str(issue), "--repo", repo, "--json", "comments",
            )
        except Exception as exc:
            logger.debug(
                "tfone_dev.find_meta_comment.failed",
                extra={"issue": issue, "repo": repo, "error": str(exc)},
            )
            return None
        data = json.loads(output or "{}")
        for comment in data.get("comments", []):
            body = comment.get("body", "")
            if body.startswith(_META_TAG):
                return body
        return None

    def post_comment(self, repo: str, issue: int, body: str) -> None:
        self.runner.run("issue", "comment", str(issue), "--repo", repo, "--body", body)


# ---------------------------------------------------------------------------
# Adapters dataclass
# ---------------------------------------------------------------------------


@dataclass
class FivepointsTfoneDevAdapters:
    """Adapters required by FivepointsTfoneDevWorkflow."""

    github: FivepointsGitHubAdapter
    terminal: FivepointsTerminalAdapter
    ado: FivepointsADOAdapter
    meta: GhIssueMetaAdapter
    local_path: Path
    ado_org: str
    ado_project: str


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


class PrepareWorktreeStep:
    """Create the dev worktree on a FivePoints-convention branch, idempotently.

    Branch name: feature/{pbi_id}-{slug} — pbi_id is parsed from the ADO
    _workitems/edit/<id> link in the issue body, slug is derived from the issue
    title. The chosen branch name is persisted as a <!-- claire:meta --> comment
    on the issue so a restarted pipeline recovers it without recreating the
    worktree or re-deriving the branch name.
    """

    def __call__(
        self,
        task: FivepointsTask,
        ctx: dict[str, Any],
        adapters: FivepointsTfoneDevAdapters,
    ) -> StepResult:
        worktree_path = adapters.local_path / ".claire" / "worktrees" / f"issue-{task.issue}"

        if worktree_path.exists():
            meta_body = adapters.meta.find_meta_comment(task.repo, task.issue)
            match = _BRANCH_PATTERN.search(meta_body) if meta_body else None
            if match and _is_valid_branch_name(match.group(1)):
                branch_name = match.group(1)
                logger.info(
                    "tfone_dev.prepare_worktree.skipped",
                    extra={
                        "issue": task.issue,
                        "repo": task.repo,
                        "branch_name": branch_name,
                    },
                )
                return StepResult(
                    ok=True,
                    data={
                        "worktree_ready": True,
                        "branch_name": branch_name,
                        "worktree_path": str(worktree_path),
                    },
                )
            if match:
                # Anyone able to comment on the issue can post a forged claire:meta
                # comment — never trust a branch_name that doesn't match the
                # convention this step itself produces. Fall through and re-derive.
                logger.warning(
                    "tfone_dev.prepare_worktree.meta_comment_rejected",
                    extra={
                        "issue": task.issue,
                        "repo": task.repo,
                        "rejected_branch_name": match.group(1),
                    },
                )

        issue_data = adapters.meta.get_issue(task.repo, task.issue)
        pbi_id = _extract_pbi_id(issue_data.get("body", "") or "")
        slug = _slugify(issue_data.get("title", "") or "")
        branch_name = f"feature/{pbi_id}-{slug}"
        if not _is_valid_branch_name(branch_name):
            raise RuntimeError(
                f"Derived branch name {branch_name!r} failed validation against "
                f"{_BRANCH_NAME_PATTERN.pattern!r} — check the issue title/body"
            )

        worktree_path_str = RealWorktreePrepare(local_path=adapters.local_path).prepare(
            repo=task.repo,
            issue=task.issue,
            base_branch="develop",
            branch_name=branch_name,
        )

        comment_body = (
            f"{_META_TAG}\n"
            f"**Branch:** `{branch_name}`\n"
            f"**Worktree:** `{worktree_path_str}`"
        )
        adapters.meta.post_comment(task.repo, task.issue, comment_body)

        logger.info(
            "tfone_dev.prepare_worktree.done",
            extra={"issue": task.issue, "repo": task.repo, "branch_name": branch_name},
        )
        return StepResult(
            ok=True,
            data={
                "worktree_ready": True,
                "branch_name": branch_name,
                "worktree_path": worktree_path_str,
            },
        )


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


class PushToADOStep:
    """Push the feature branch to ADO and create a PR.

    Reads branch_name from ctx (set by PrepareWorktreeStep) instead of deriving
    issue-{N} from the issue number, so the branch pushed to ADO matches the
    FivePoints feature/{pbi_id}-{slug} convention.
    """

    def __call__(
        self,
        task: FivepointsTask,
        ctx: dict[str, Any],
        adapters: FivepointsTfoneDevAdapters,
    ) -> StepResult:
        branch_name = ctx["branch_name"]
        ado_pr_id = adapters.ado.push_branch_and_create_pr(task.issue, branch_name)
        logger.info(
            "tfone_dev.push_to_ado.done",
            extra={
                "issue": task.issue,
                "repo": task.repo,
                "branch_name": branch_name,
                "ado_pr_id": ado_pr_id,
            },
        )
        return StepResult(ok=True, data={"ado_pr_id": ado_pr_id})


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


class FivepointsTfoneDevWorkflow:
    """dev-only variant: HydrateState → PrepareWorktree → SpawnDev → Tester → ADO push → ADO merge.

    HydrateStateStep reads the current role label at startup and populates ctx
    so restart recovery works correctly:
      role:tester present  → dev_done=True  (skip SpawnDevStep)
      role:ready  present  → dev_done=True, tester_done=True (skip both)

    PrepareWorktreeStep is idempotent on its own (worktree-on-disk + claire:meta
    comment check) and always runs — it no-ops itself rather than relying on ctx.

    Usage::

        workflow = FivepointsTfoneDevWorkflow()
        result = workflow.run(task, adapters)   # adapters: FivepointsTfoneDevAdapters
    """

    def __init__(self) -> None:
        self._pipeline = pipe(
            HydrateStateStep(),
            PrepareWorktreeStep(),
            SpawnDevStep(),
            TesterStep(),
            PushToADOStep(),
            WaitForADOMergeStep(),
        )

    def run(
        self, task: FivepointsTask, adapters: FivepointsTfoneDevAdapters
    ) -> StepResult:
        return self._pipeline(task, adapters)
