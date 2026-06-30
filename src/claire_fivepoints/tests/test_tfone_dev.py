"""Tests for DevWithADOContextStep, TesterStep and FivepointsTfoneDevWorkflow.

Level 1 — unit tests for each step in isolation.
Level 2 — scenario tests for the full FivepointsTfoneDevWorkflow (including restart recovery).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claire_core.pipeline import StepResult
from claire_fivepoints.ado_context_adapter import MockADOContextAdapter
from claire_fivepoints.tfone_dev_steps import (
    DevWithADOContextStep,
    FivepointsTfoneDevAdapters,
    FivepointsTfoneDevWorkflow,
    TesterStep,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapters(
    tmp_path: Path,
    *,
    closed: bool = False,
    role_label: str | None = None,
    pr_number: int | None = 10,
    work_item: dict | None = None,
    attachment_paths: list[Path] | None = None,
) -> FivepointsTfoneDevAdapters:
    gh = MagicMock()
    gh.is_issue_closed.return_value = closed
    gh.get_role_label.return_value = role_label
    gh.wait_for_label.return_value = None
    gh.find_pr_for_issue.return_value = pr_number

    terminal = MagicMock()
    ado = MagicMock()
    ado.push_branch_and_create_pr.return_value = 42
    ado.wait_for_merge.return_value = None

    mock_ado_context = MockADOContextAdapter(
        work_item=work_item or {"id": 1, "fields": {"System.Title": "Test"}},
        attachments=attachment_paths or [],
    )

    return FivepointsTfoneDevAdapters(
        github=gh,
        terminal=terminal,
        ado=ado,
        ado_context=mock_ado_context,
        local_path=tmp_path,
        ado_org="TestOrg",
        ado_project="TestProject",
    )


def _make_task(issue: int = 42, repo: str = "org/repo"):
    from claire_workflows.fivepoints_pipeline import FivepointsTask
    return FivepointsTask(issue=issue, repo=repo)


# ---------------------------------------------------------------------------
# MockADOContextAdapter
# ---------------------------------------------------------------------------


class TestMockADOContextAdapter:
    def test_fetch_work_item_returns_fixture(self) -> None:
        adapter = MockADOContextAdapter(work_item={"id": 99}, attachments=[])
        result = adapter.fetch_work_item("org", "proj", 99)
        assert result == {"id": 99}

    def test_download_attachments_creates_dest_and_returns_paths(
        self, tmp_path: Path
    ) -> None:
        fake_path = tmp_path / "fixture.docx"
        adapter = MockADOContextAdapter(work_item={}, attachments=[fake_path])
        dest = tmp_path / "attachments"
        paths = adapter.download_attachments("org", "proj", {}, dest)
        assert paths == [fake_path]
        assert dest.is_dir()

    def test_download_attachments_empty(self, tmp_path: Path) -> None:
        adapter = MockADOContextAdapter(work_item={}, attachments=[])
        paths = adapter.download_attachments("org", "proj", {}, tmp_path / "out")
        assert paths == []


# ---------------------------------------------------------------------------
# DevWithADOContextStep
# ---------------------------------------------------------------------------


class TestDevWithADOContextStep:
    def test_skips_when_dev_done_in_ctx(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path)
        task = _make_task()
        result = DevWithADOContextStep()(task, {"dev_done": True}, adapters)
        assert result.ok
        adapters.terminal.spawn_dev.assert_not_called()
        adapters.github.wait_for_label.assert_not_called()

    def test_fetches_work_item_and_downloads_attachments(self, tmp_path: Path) -> None:
        adapters = _make_adapters(
            tmp_path,
            work_item={
                "id": 42,
                "fields": {
                    "System.Title": "My Feature",
                    "System.Description": "Desc",
                    "Microsoft.VSTS.Common.AcceptanceCriteria": "AC",
                    "System.AreaPath": "Area\\Path",
                    "System.State": "Active",
                    "System.WorkItemType": "User Story",
                },
            },
        )
        task = _make_task(issue=42)
        result = DevWithADOContextStep()(task, {}, adapters)
        assert result.ok
        dest = tmp_path / ".claire" / "attachments" / "issue-42"
        assert dest.is_dir()
        context_file = dest / "ADO_CONTEXT.md"
        assert context_file.is_file()
        content = context_file.read_text()
        assert "My Feature" in content
        assert "Desc" in content
        assert "AC" in content

    def test_single_ado_fetch_per_run(self, tmp_path: Path) -> None:
        """download_attachments receives the already-fetched work_item — no double fetch."""
        from unittest.mock import patch

        adapters = _make_adapters(tmp_path)
        task = _make_task(issue=5)

        fetch_calls: list = []
        orig_fetch = adapters.ado_context.fetch_work_item

        def tracking_fetch(org, project, item_id):
            fetch_calls.append((org, project, item_id))
            return orig_fetch(org, project, item_id)

        adapters.ado_context.fetch_work_item = tracking_fetch
        DevWithADOContextStep()(task, {}, adapters)
        assert len(fetch_calls) == 1, "fetch_work_item must be called exactly once"

    def test_writes_attachments_list_in_context_file(self, tmp_path: Path) -> None:
        fake = tmp_path / "spec.docx"
        fake.write_bytes(b"fake")
        adapters = _make_adapters(tmp_path, attachment_paths=[fake])
        task = _make_task(issue=7)
        DevWithADOContextStep()(task, {}, adapters)
        context_file = tmp_path / ".claire" / "attachments" / "issue-7" / "ADO_CONTEXT.md"
        assert "spec.docx" in context_file.read_text()

    def test_spawns_dev_and_waits_for_label(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path)
        task = _make_task(issue=5)
        result = DevWithADOContextStep()(task, {}, adapters)
        assert result.ok
        adapters.terminal.spawn_dev.assert_called_once_with(5, "org/repo")
        adapters.github.wait_for_label.assert_called_once_with(
            "org/repo", 5, "role:tester"
        )

    def test_returns_dev_done_and_pr_number(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path, pr_number=99)
        task = _make_task()
        result = DevWithADOContextStep()(task, {}, adapters)
        assert result.ok
        assert result.data["dev_done"] is True
        assert result.data["pr_number"] == 99

    def test_context_file_created_even_without_attachments(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path, attachment_paths=[])
        task = _make_task(issue=3)
        DevWithADOContextStep()(task, {}, adapters)
        context_file = tmp_path / ".claire" / "attachments" / "issue-3" / "ADO_CONTEXT.md"
        assert context_file.is_file()


# ---------------------------------------------------------------------------
# TesterStep
# ---------------------------------------------------------------------------


class TestTesterStep:
    def test_skips_when_tester_done_in_ctx(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path)
        task = _make_task()
        result = TesterStep()(task, {"tester_done": True}, adapters)
        assert result.ok
        adapters.terminal.spawn_tester.assert_not_called()

    def test_spawns_tester_and_waits(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path)
        task = _make_task(issue=8)
        result = TesterStep()(task, {}, adapters)
        assert result.ok
        adapters.terminal.spawn_tester.assert_called_once_with(8, "org/repo")
        adapters.github.wait_for_label.assert_called_once_with(
            "org/repo", 8, "role:ready"
        )

    def test_returns_tester_done(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path)
        result = TesterStep()(_make_task(), {}, adapters)
        assert result.ok
        assert result.data["tester_done"] is True


# ---------------------------------------------------------------------------
# FivepointsTfoneDevWorkflow — scenario tests (including restart recovery)
# ---------------------------------------------------------------------------


class TestFivepointsTfoneDevWorkflow:
    def test_full_happy_path_fresh_start(self, tmp_path: Path) -> None:
        """No label present → HydrateState returns {} → all steps run."""
        adapters = _make_adapters(tmp_path, role_label=None, pr_number=20)
        task = _make_task(issue=42)
        result = FivepointsTfoneDevWorkflow().run(task, adapters)
        assert result.ok
        adapters.terminal.spawn_dev.assert_called_once()
        adapters.terminal.spawn_tester.assert_called_once()
        adapters.ado.push_branch_and_create_pr.assert_called_once_with(42)
        adapters.ado.wait_for_merge.assert_called_once_with(42)

    def test_restart_with_role_tester_skips_dev(self, tmp_path: Path) -> None:
        """role:tester present → HydrateState sets dev_done=True → DevStep skipped."""
        adapters = _make_adapters(tmp_path, role_label="role:tester", pr_number=5)
        task = _make_task()
        result = FivepointsTfoneDevWorkflow().run(task, adapters)
        assert result.ok
        adapters.terminal.spawn_dev.assert_not_called()
        adapters.terminal.spawn_tester.assert_called_once()

    def test_restart_with_role_ready_skips_dev_and_tester(self, tmp_path: Path) -> None:
        """role:ready present → HydrateState sets dev_done+tester_done → both skipped."""
        adapters = _make_adapters(tmp_path, role_label="role:ready", pr_number=7)
        task = _make_task()
        result = FivepointsTfoneDevWorkflow().run(task, adapters)
        assert result.ok
        adapters.terminal.spawn_dev.assert_not_called()
        adapters.terminal.spawn_tester.assert_not_called()
        adapters.ado.push_branch_and_create_pr.assert_called_once()

    def test_issue_closed_exits_cleanly(self, tmp_path: Path) -> None:
        """Closed issue → HydrateState returns ok=False → pipeline exits."""
        adapters = _make_adapters(tmp_path, closed=True)
        task = _make_task()
        result = FivepointsTfoneDevWorkflow().run(task, adapters)
        assert not result.ok
        adapters.terminal.spawn_dev.assert_not_called()
        adapters.ado.push_branch_and_create_pr.assert_not_called()

    def test_ado_merge_failure_propagates(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path, role_label=None)
        adapters.ado.push_branch_and_create_pr.return_value = 99
        adapters.ado.wait_for_merge.side_effect = RuntimeError("ADO PR abandoned")
        task = _make_task()
        with pytest.raises(RuntimeError, match="ADO PR abandoned"):
            FivepointsTfoneDevWorkflow().run(task, adapters)


# ---------------------------------------------------------------------------
# run_fivepoints_tfone_dev_for_issue — entry point smoke test
# ---------------------------------------------------------------------------


class TestRunFivepointsTfoneDevForIssue:
    def test_entry_point_wires_adapters_and_calls_workflow(
        self, tmp_path: Path
    ) -> None:
        from unittest.mock import patch

        from claire_core.pipeline import StepResult as _SR
        from claire_fivepoints.workflows import run_fivepoints_tfone_dev_for_issue

        mock_workflow_instance = MagicMock()
        mock_workflow_instance.run.return_value = _SR(ok=True, data={"ado_merged": True})

        mock_ado_cls = MagicMock()
        mock_ado_cls.for_repo.return_value = MagicMock()
        mock_ado_ctx_cls = MagicMock()
        mock_ado_ctx_cls.for_repo.return_value = MagicMock()
        mock_workflow_cls = MagicMock(return_value=mock_workflow_instance)

        with (
            patch(
                "claire_fivepoints.workflows.FivepointsGhAdapter.default",
                return_value=MagicMock(),
            ),
            patch(
                "claire_fivepoints.workflows.FivepointsOsascriptTerminalAdapter.with_role_tokens",
                return_value=MagicMock(),
            ),
            patch(
                "claire_fivepoints.workflows.load_local_path",
                return_value=str(tmp_path),
            ),
            patch(
                "claire_fivepoints.workflows.find_repo_entry",
                return_value={"ado_org": "Org", "ado_project": "Proj"},
            ),
            patch("claire_fivepoints.workflows.FivepointsConcreteADOAdapter", mock_ado_cls),
            patch("claire_fivepoints.workflows.RealADOContextAdapter", mock_ado_ctx_cls),
            patch("claire_fivepoints.workflows.FivepointsTfoneDevWorkflow", mock_workflow_cls),
        ):
            result = run_fivepoints_tfone_dev_for_issue(42, "org/repo")

        assert result.ok
        mock_workflow_instance.run.assert_called_once()
        call_args = mock_workflow_instance.run.call_args
        task = call_args[0][0]
        assert task.issue == 42
        assert task.repo == "org/repo"
