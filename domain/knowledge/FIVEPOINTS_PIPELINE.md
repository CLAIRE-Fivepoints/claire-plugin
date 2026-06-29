---
domain: claire
category: knowledge
name: FIVEPOINTS_PIPELINE
title: "Fivepoints Pipeline — issue-to-merge V2 workflow"
keywords: [fivepoints, pipeline, workflow, analyst, dev, tester, ado, role, HydrateStateStep, SpawnAnalystStep, WaitForAnalystDoneStep, SpawnDevStep, WaitForDevDoneStep, SpawnTesterStep, WaitForTesterDoneStep, PushToADOStep, WaitForADOMergeStep, FivepointsGitHubWorkflow, FivepointsFullWorkflow, role:dev, role:tester, role:ready, ctx-aware, restart-recovery, pipe]
updated: 2026-05-12
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

## Two workflow classes

```python
class FivepointsGitHubWorkflow:
    """analyst → dev → tester — manual merge on GitHub. No ADO."""
    def __init__(self): self._pipeline = pipe(*_core_steps())

class FivepointsFullWorkflow:
    """analyst → dev → tester → ADO push → ADO merge."""
    def __init__(self): self._pipeline = pipe(*_core_steps(), PushToADOStep(), WaitForADOMergeStep())
```

Select the class at the call site. Adapter dataclasses enforce correctness at the type level.

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
```

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
```

## Tests

`packages/workflows/src/claire_workflows/tests/test_fivepoints_pipeline.py`

- **Level 1** (unit): each step in isolation with `MockAdapters`
- **Level 2** (scenario): full end-to-end for both workflow classes including restart recovery

## See also

- `claire domain read claire knowledge RUN_PIPELINE` — CLI entry point for e2e pipelines
- `claire domain read core knowledge WORKFLOW_AUTHORING` — authoring guide for V2 workflows
- Issue #478 — feat(workflows): add FivepointsPipeline
