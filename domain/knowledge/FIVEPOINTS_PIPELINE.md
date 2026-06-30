---
domain: claire
category: knowledge
name: FIVEPOINTS_PIPELINE
title: "Fivepoints Pipeline — issue-to-merge V2 workflow"
keywords: [fivepoints, pipeline, workflow, analyst, dev, tester, ado, role, HydrateStateStep, SpawnAnalystStep, WaitForAnalystDoneStep, SpawnDevStep, WaitForDevDoneStep, SpawnTesterStep, WaitForTesterDoneStep, PushToADOStep, WaitForADOMergeStep, FivepointsGitHubWorkflow, FivepointsFullWorkflow, FivepointsTfoneDevWorkflow, DevWithADOContextStep, TesterStep, ADOContextAdapter, role:dev, role:tester, role:ready, ctx-aware, restart-recovery, pipe, fivepoints.tfone.dev]
updated: 2026-06-30
---

# Fivepoints Pipeline — issue-to-merge V2 workflow

V2 `pipe()`-based implementation of the fivepoints issue-to-merge orchestration.
Replaces the Bash scripts in the plugin with Python functional composition.

## Source

`packages/workflows/src/claire_workflows/fivepoints_pipeline.py`

## Pipeline shape

```
HydrateStateStep()         ← reads role label; populates ctx for restart recovery
SpawnAnalystStep()         ← ctx-aware: skip if analyst_done
WaitForAnalystDoneStep()   ← polls for role:dev label
SpawnDevStep()             ← ctx-aware: skip if dev_done
WaitForDevDoneStep()       ← polls for role:tester label + finds PR number
SpawnTesterStep()          ← ctx-aware: skip if tester_done
WaitForTesterDoneStep()    ← polls for role:ready label
[ PushToADOStep() ]        ← full workflow only
[ WaitForADOMergeStep() ]  ← full workflow only
```

## Workflow classes

Three variants, selected at the call site. Adapter dataclasses enforce correctness at the type level.

```python
class FivepointsGitHubWorkflow:
    """analyst → dev → tester — manual merge on GitHub. No ADO."""
    def __init__(self): self._pipeline = pipe(*_core_steps())

class FivepointsFullWorkflow:
    """analyst → dev → tester → ADO push → ADO merge."""
    def __init__(self): self._pipeline = pipe(*_core_steps(), PushToADOStep(), WaitForADOMergeStep())

class FivepointsTfoneDevWorkflow:           # claire_fivepoints.tfone_dev_steps
    """dev reads ADO context → tester → ADO push → ADO merge. No analyst."""
    def __init__(self): self._pipeline = pipe(
        HydrateStateStep(),
        DevWithADOContextStep(),   # fetch ADO work item + attachments → spawn dev → wait role:tester
        TesterStep(),              # spawn tester → wait role:ready
        PushToADOStep(),
        WaitForADOMergeStep(),
    )
```

`FivepointsTfoneDevWorkflow` is registered as entry point `fivepoints.tfone.dev` and uses
`FivepointsTfoneDevAdapters` (adds `ado_context: ADOContextAdapter`, `local_path`, `ado_org`,
`ado_project` on top of the standard fields). Restart recovery uses the same `HydrateStateStep`
label mapping — `role:tester` → `dev_done=True`, `role:ready` → `dev_done+tester_done=True`.

## Adapter protocols

```python
class FivepointsGitHubAdapter(Protocol):
    def is_issue_closed(self, repo, issue) -> bool: ...
    def get_role_label(self, repo, issue) -> str | None: ...
    def wait_for_label(self, repo, issue, label) -> None: ...
    def find_pr_for_issue(self, repo, issue) -> int | None: ...

class FivepointsTerminalAdapter(Protocol):
    def spawn_analyst(self, issue, repo) -> None: ...
    def spawn_dev(self, issue, repo) -> None: ...
    def spawn_tester(self, issue, repo) -> None: ...

class FivepointsADOAdapter(Protocol):   # FivepointsFullWorkflow only
    def push_branch_and_create_pr(self, issue) -> int: ...
    def wait_for_merge(self, ado_pr_id) -> None: ...
```

## Adapter dataclasses

```python
@dataclass
class FivepointsGitHubAdapters:
    github: FivepointsGitHubAdapter
    terminal: FivepointsTerminalAdapter

@dataclass
class FivepointsFullAdapters:
    github: FivepointsGitHubAdapter
    terminal: FivepointsTerminalAdapter
    ado: FivepointsADOAdapter   # required, not Optional

@dataclass
class FivepointsTfoneDevAdapters:           # claire_fivepoints.tfone_dev_steps
    github: FivepointsGitHubAdapter
    terminal: FivepointsTerminalAdapter
    ado: FivepointsADOAdapter
    ado_context: ADOContextAdapter          # claire_fivepoints.ado_context_adapter
    local_path: Path                        # root of the repo checkout; attachments go under .claire/attachments/issue-{N}/
    ado_org: str
    ado_project: str
```

`ADOContextAdapter` Protocol (in `claire_fivepoints.ado_context_adapter`):

```python
class ADOContextAdapter(Protocol):
    def fetch_work_item(self, org: str, project: str, item_id: int) -> dict: ...
    def download_attachments(self, org: str, project: str, work_item: dict, dest: Path) -> list[Path]: ...
```

Concrete implementation: `RealADOContextAdapter` — reads `AZURE_DEVOPS_PAT` from
`~/.config/claire/github_manager.env`, `~/.config/claire/.env`, or the environment.
Test double: `MockADOContextAdapter(work_item={...}, attachments=[...])`.

`download_attachments` takes the already-fetched `work_item` dict to avoid a redundant
REST round-trip (the caller fetches once via `fetch_work_item` and passes it in).

## Restart recovery (HydrateStateStep)

`HydrateStateStep` reads the current GitHub role label on startup and pre-populates
ctx so the pipeline resumes at the correct step without re-spawning agents:

| Role label present | ctx populated |
|---|---|
| issue closed | ok=False — clean exit |
| `role:ready` | analyst_done, dev_done, tester_done, pr_number |
| `role:tester` | analyst_done, dev_done, pr_number |
| `role:dev` | analyst_done |
| none / other | {} (fresh start) |

Each step checks its done-flag before acting:

```python
class SpawnAnalystStep:
    def __call__(self, task, ctx, adapters) -> StepResult:
        if ctx.get("analyst_done"):          # set by Hydrate or WaitForAnalystDoneStep
            return StepResult(ok=True, data={})
        adapters.terminal.spawn_analyst(task.issue, task.repo)
        return StepResult(ok=True, data={})
```

## Usage

```python
from claire_workflows.fivepoints_pipeline import (
    FivepointsTask,
    FivepointsGitHubAdapters,
    FivepointsGitHubWorkflow,
    FivepointsFullAdapters,
    FivepointsFullWorkflow,
)

# GitHub-only variant
task = FivepointsTask(issue=42, repo="CLAIRE-Fivepoints/fivepoints")
adapters = FivepointsGitHubAdapters(github=..., terminal=...)
result = FivepointsGitHubWorkflow().run(task, adapters)

# Full variant (with ADO)
adapters_full = FivepointsFullAdapters(github=..., terminal=..., ado=...)
result = FivepointsFullWorkflow().run(task, adapters_full)

# Dev-only variant (no analyst, reads ADO context)
from claire_fivepoints.tfone_dev_steps import FivepointsTfoneDevAdapters, FivepointsTfoneDevWorkflow
from claire_fivepoints.ado_context_adapter import RealADOContextAdapter
adapters_dev = FivepointsTfoneDevAdapters(
    github=..., terminal=..., ado=...,
    ado_context=RealADOContextAdapter.for_repo(repo),
    local_path=Path("/path/to/repo"),
    ado_org="MyOrg", ado_project="MyProject",
)
result = FivepointsTfoneDevWorkflow().run(task, adapters_dev)
```

## Tests

`packages/workflows/src/claire_workflows/tests/test_fivepoints_pipeline.py`
`src/claire_fivepoints/tests/test_tfone_dev.py`

- **Level 1** (unit): each step in isolation with `MockAdapters` / `MockADOContextAdapter`
- **Level 2** (scenario): full end-to-end for all workflow classes including restart recovery

## See also

- `claire domain read claire knowledge RUN_PIPELINE` — CLI entry point for e2e pipelines
- `claire domain read core knowledge WORKFLOW_AUTHORING` — authoring guide for V2 workflows
- Issue #478 — feat(workflows): add FivepointsPipeline
- Issue #172 — feat(pipeline): fivepoints.tfone.dev — dev does everything, no analyst
