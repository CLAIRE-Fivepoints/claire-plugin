"""Tests for fivepoints entry point functions.

Covers:
  - run_fivepoints_tfone_github_for_issue: builds adapters and calls FivepointsGitHubWorkflow
  - run_fivepoints_tfone_full_for_issue: builds adapters and calls FivepointsFullWorkflow
  - FivepointsGhAdapter.get_role_label: parses gh output, returns None when absent
  - FivepointsGhAdapter.wait_for_label: polls until label or later label found
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from claire_core.pipeline import StepResult
from claire_fivepoints.adapters import FivepointsGhAdapter, FivepointsOsascriptTerminalAdapter
from claire_fivepoints.workflows import (
    run_fivepoints_tfone_full_for_issue,
    run_fivepoints_tfone_github_for_issue,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_gh_adapter(label: str | None = None, pr: int | None = None, closed: bool = False):
    gh = MagicMock()
    gh.is_issue_closed.return_value = closed
    gh.find_pr_for_issue.return_value = pr
    return gh


def _mock_terminal():
    t = MagicMock()
    t.spawn_analyst = MagicMock()
    t.spawn_dev = MagicMock()
    t.spawn_tester = MagicMock()
    return t


# ---------------------------------------------------------------------------
# FivepointsGhAdapter unit tests
# ---------------------------------------------------------------------------


class TestFivepointsGhAdapter:
    def test_get_role_label_returns_label(self) -> None:
        gh = MagicMock()
        gh.runner.run.return_value = "role:dev\n"
        adapter = FivepointsGhAdapter(_gh=gh)
        assert adapter.get_role_label("org/repo", 42) == "role:dev"

    def test_get_role_label_returns_none_when_empty(self) -> None:
        gh = MagicMock()
        gh.runner.run.return_value = "\n"
        adapter = FivepointsGhAdapter(_gh=gh)
        assert adapter.get_role_label("org/repo", 42) is None

    def test_get_role_label_strips_whitespace(self) -> None:
        gh = MagicMock()
        gh.runner.run.return_value = "  role:tester  \n"
        adapter = FivepointsGhAdapter(_gh=gh)
        assert adapter.get_role_label("org/repo", 42) == "role:tester"

    def test_wait_for_label_returns_immediately_when_label_present(self) -> None:
        gh = MagicMock()
        gh.runner.run.return_value = "role:dev\n"
        adapter = FivepointsGhAdapter(_gh=gh, poll_interval=0.0)
        adapter.wait_for_label("org/repo", 42, "role:dev")

    def test_wait_for_label_returns_when_later_label_found(self) -> None:
        """Waiting for role:dev should return immediately if role:tester is present."""
        gh = MagicMock()
        gh.runner.run.return_value = "role:tester\n"
        adapter = FivepointsGhAdapter(_gh=gh, poll_interval=0.0)
        adapter.wait_for_label("org/repo", 42, "role:dev")

    def test_wait_for_label_polls_until_found(self) -> None:
        gh = MagicMock()
        gh.runner.run.side_effect = ["\n", "\n", "role:dev\n"]
        adapter = FivepointsGhAdapter(_gh=gh, poll_interval=0.0)
        adapter.wait_for_label("org/repo", 42, "role:dev")
        assert gh.runner.run.call_count == 3

    def test_is_issue_closed_delegates_to_gh(self) -> None:
        gh = MagicMock()
        gh.is_issue_closed.return_value = True
        adapter = FivepointsGhAdapter(_gh=gh)
        assert adapter.is_issue_closed("org/repo", 42) is True

    def test_find_pr_for_issue_delegates_to_gh(self) -> None:
        gh = MagicMock()
        gh.find_pr_for_issue.return_value = 99
        adapter = FivepointsGhAdapter(_gh=gh)
        assert adapter.find_pr_for_issue("org/repo", 42) == 99


# ---------------------------------------------------------------------------
# run_fivepoints_tfone_github_for_issue
# ---------------------------------------------------------------------------


class TestRunFivepointsTfoneGithub:
    def test_github_workflow_called_with_correct_adapters(self) -> None:
        run_calls: list[tuple] = []

        class _FakeWorkflow:
            def __init__(self):
                pass

            def run(self, task, adapters):
                run_calls.append((task, adapters))
                return StepResult(ok=True, data={"merged_pr": 10})

        mock_gh = MagicMock()
        mock_terminal = MagicMock()

        with (
            patch(
                "claire_fivepoints.workflows.FivepointsGhAdapter.default",
                return_value=mock_gh,
            ),
            patch(
                "claire_fivepoints.workflows.FivepointsOsascriptTerminalAdapter.with_role_tokens",
                return_value=mock_terminal,
            ),
            patch(
                "claire_fivepoints.workflows.FivepointsGitHubWorkflow",
                return_value=_FakeWorkflow(),
            ),
        ):
            result = run_fivepoints_tfone_github_for_issue(42, "org/repo")

        assert result.ok
        assert len(run_calls) == 1
        task, adapters = run_calls[0]
        assert task.issue == 42
        assert task.repo == "org/repo"
        assert adapters.github is mock_gh
        assert adapters.terminal is mock_terminal

    def test_poll_interval_passed_to_gh_adapter(self) -> None:
        with (
            patch(
                "claire_fivepoints.workflows.FivepointsGhAdapter.default"
            ) as mock_default,
            patch(
                "claire_fivepoints.workflows.FivepointsOsascriptTerminalAdapter.with_role_tokens",
                return_value=MagicMock(),
            ),
            patch(
                "claire_fivepoints.workflows.FivepointsGitHubWorkflow",
                return_value=MagicMock(
                    run=MagicMock(return_value=StepResult(ok=True, data={"merged_pr": 1}))
                ),
            ),
        ):
            run_fivepoints_tfone_github_for_issue(1, "org/repo", poll_interval=60.0)

        mock_default.assert_called_once_with(repo="org/repo", poll_interval=60.0)


# ---------------------------------------------------------------------------
# run_fivepoints_tfone_full_for_issue
# ---------------------------------------------------------------------------


class TestRunFivepointsTfoneFull:
    def test_full_workflow_called_with_ado_adapter(self) -> None:
        run_calls: list[tuple] = []

        class _FakeWorkflow:
            def __init__(self):
                pass

            def run(self, task, adapters):
                run_calls.append((task, adapters))
                return StepResult(ok=True, data={"merged_pr": 20})

        mock_gh = MagicMock()
        mock_terminal = MagicMock()
        mock_ado = MagicMock()

        with (
            patch(
                "claire_fivepoints.workflows.FivepointsGhAdapter.default",
                return_value=mock_gh,
            ),
            patch(
                "claire_fivepoints.workflows.FivepointsOsascriptTerminalAdapter.with_role_tokens",
                return_value=mock_terminal,
            ),
            patch(
                "claire_fivepoints.ado_adapter.FivepointsConcreteADOAdapter.for_repo",
                return_value=mock_ado,
            ),
            patch(
                "claire_fivepoints.workflows.FivepointsFullWorkflow",
                return_value=_FakeWorkflow(),
            ),
        ):
            result = run_fivepoints_tfone_full_for_issue(7, "org/repo")

        assert result.ok
        assert len(run_calls) == 1
        task, adapters = run_calls[0]
        assert task.issue == 7
        assert adapters.github is mock_gh
        assert adapters.terminal is mock_terminal
        assert adapters.ado is mock_ado


# ---------------------------------------------------------------------------
# FivepointsConcreteADOAdapter unit tests
# ---------------------------------------------------------------------------


class TestFivepointsConcreteADOAdapter:
    def test_push_branch_uses_git_runner(self) -> None:
        from claire_fivepoints.ado_adapter import FivepointsConcreteADOAdapter

        push_calls: list[tuple] = []

        class _FakeGit:
            def push(self, remote: str, refspec: str) -> None:
                push_calls.append((remote, refspec))

        mock_ado = MagicMock()
        mock_ado.find_pr_for_branch.return_value = {"pullRequestId": 42}

        adapter = FivepointsConcreteADOAdapter(ado=mock_ado, git=_FakeGit())
        pr_id = adapter.push_branch_and_create_pr(99, "feature/123-my-feature")

        assert pr_id == 42
        assert push_calls == [
            ("ado", "feature/123-my-feature:feature/123-my-feature")
        ]

    def test_push_branch_falls_back_to_issue_branch_when_name_omitted(self) -> None:
        """fivepoints.tfone.full still calls push_branch_and_create_pr(issue) with no
        branch_name (core's single-arg PushToADOStep) — must keep working unchanged."""
        from claire_fivepoints.ado_adapter import FivepointsConcreteADOAdapter

        push_calls: list[tuple] = []

        class _FakeGit:
            def push(self, remote: str, refspec: str) -> None:
                push_calls.append((remote, refspec))

        mock_ado = MagicMock()
        mock_ado.find_pr_for_branch.return_value = {"pullRequestId": 7}

        adapter = FivepointsConcreteADOAdapter(ado=mock_ado, git=_FakeGit())
        pr_id = adapter.push_branch_and_create_pr(99)

        assert pr_id == 7
        assert push_calls == [("ado", "issue-99:issue-99")]
        mock_ado.find_pr_for_branch.assert_called_once_with("issue-99")

    def test_wait_for_merge_returns_on_completed(self) -> None:
        from claire_fivepoints.ado_adapter import FivepointsConcreteADOAdapter

        mock_ado = MagicMock()
        mock_ado.get_pr_status.return_value = "completed"

        adapter = FivepointsConcreteADOAdapter(ado=mock_ado, git=MagicMock())
        adapter.wait_for_merge(7)

        mock_ado.get_pr_status.assert_called_once_with(7)

    def test_wait_for_merge_raises_on_abandoned(self) -> None:
        from claire_fivepoints.ado_adapter import FivepointsConcreteADOAdapter

        mock_ado = MagicMock()
        mock_ado.get_pr_status.return_value = "abandoned"

        adapter = FivepointsConcreteADOAdapter(ado=mock_ado, git=MagicMock())
        with pytest.raises(RuntimeError, match="abandoned"):
            adapter.wait_for_merge(7)

    def test_subprocess_git_runner_passes_cwd_to_git_push(self) -> None:
        from claire_fivepoints.ado_adapter import SubprocessGitRunner

        with patch("subprocess.run") as mock_run:
            runner = SubprocessGitRunner(cwd="/some/repo")
            runner.push("ado", "feature/1-foo:feature/1-foo")

        mock_run.assert_called_once_with(
            ["git", "push", "ado", "feature/1-foo:feature/1-foo"],
            check=True,
            cwd="/some/repo",
        )

    def test_subprocess_git_runner_defaults_cwd_to_none(self) -> None:
        from claire_fivepoints.ado_adapter import SubprocessGitRunner

        with patch("subprocess.run") as mock_run:
            SubprocessGitRunner().push("ado", "develop:develop")

        assert mock_run.call_args.kwargs["cwd"] is None

    def test_for_repo_wires_local_path_into_git_runner_cwd(self) -> None:
        from claire_fivepoints.ado_adapter import FivepointsConcreteADOAdapter

        with (
            patch(
                "claire_fivepoints.ado_adapter.find_repo_entry",
                return_value={
                    "ado_org": "Org",
                    "ado_project": "Proj",
                    "ado_repo": "TFIOneGit",
                },
            ),
            patch(
                "claire_fivepoints.ado_adapter.parse_env_file",
                return_value={"AZURE_DEVOPS_PAT": "fake-pat"},
            ),
            patch(
                "claire_fivepoints.ado_adapter.load_local_path",
                return_value="/Users/andreperez/projects/fivepoints",
            ),
        ):
            adapter = FivepointsConcreteADOAdapter.for_repo("CLAIRE-Fivepoints/fivepoints")

        assert adapter.git._cwd == "/Users/andreperez/projects/fivepoints"
