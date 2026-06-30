"""Tests for tfone_dev_steps — PrepareWorktreeStep, SpawnDevStep, TesterStep,
PushToADOStep, GhCliIssueMetaAdapter, and FivepointsTfoneDevWorkflow.

Level 1 — unit tests for each step / adapter in isolation.
Level 2 — scenario tests for the full FivepointsTfoneDevWorkflow (including restart recovery).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claire_fivepoints.tfone_dev_steps import (
    FivepointsTfoneDevAdapters,
    FivepointsTfoneDevWorkflow,
    GhCliIssueMetaAdapter,
    PrepareWorktreeStep,
    PushToADOStep,
    SpawnDevStep,
    TesterStep,
    _extract_pbi_id,
    _is_valid_branch_name,
    _slugify,
)

_DEFAULT_BODY = "ADO: https://dev.azure.com/Org/Proj/_workitems/edit/18840"
_DEFAULT_TITLE = "PBI: Case Face Sheet - Enhancement"
_DEFAULT_BRANCH = "feature/18840-case-face-sheet-enhancement"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapters(
    tmp_path: Path,
    *,
    closed: bool = False,
    role_label: str | None = None,
    pr_number: int | None = 10,
    issue_body: str = _DEFAULT_BODY,
    issue_title: str = _DEFAULT_TITLE,
    meta_comment: str | None = None,
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

    meta = MagicMock()
    meta.get_issue.return_value = {"body": issue_body, "title": issue_title}
    meta.find_meta_comment.return_value = meta_comment

    return FivepointsTfoneDevAdapters(
        github=gh,
        terminal=terminal,
        ado=ado,
        meta=meta,
        local_path=tmp_path,
        ado_org="TestOrg",
        ado_project="TestProject",
    )


def _make_task(issue: int = 42, repo: str = "org/repo"):
    from claire_workflows.fivepoints_pipeline import FivepointsTask
    return FivepointsTask(issue=issue, repo=repo)


def _patch_worktree_prepare(worktree_path: str = "/mock/worktrees/issue-42"):
    return patch("claire_fivepoints.tfone_dev_steps.RealWorktreePrepare")


# ---------------------------------------------------------------------------
# _slugify / _extract_pbi_id
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_strips_pbi_prefix_and_lowercases(self) -> None:
        assert _slugify("PBI: Case Face Sheet - Enhancement") == "case-face-sheet-enhancement"

    def test_no_pbi_prefix(self) -> None:
        assert _slugify("Client Management Test") == "client-management-test"

    def test_truncates_to_max_len(self) -> None:
        title = "PBI: " + "word " * 30
        slug = _slugify(title)
        assert len(slug) <= 50

    def test_collapses_non_alnum_runs(self) -> None:
        assert _slugify("PBI: A/B  &  C!!!") == "a-b-c"


class TestExtractPbiId:
    def test_extracts_id_from_workitems_link(self) -> None:
        body = "See https://dev.azure.com/Org/Proj/_workitems/edit/18840 for details"
        assert _extract_pbi_id(body) == "18840"

    def test_raises_when_no_link_present(self) -> None:
        with pytest.raises(RuntimeError, match="pbi_id"):
            _extract_pbi_id("no ado link here")


class TestIsValidBranchName:
    def test_accepts_convention_shaped_branch(self) -> None:
        assert _is_valid_branch_name("feature/18840-case-face-sheet-enhancement")

    def test_rejects_leading_dash_injection_attempt(self) -> None:
        assert not _is_valid_branch_name("--upload-pack=evil")

    def test_rejects_legacy_issue_branch_name(self) -> None:
        assert not _is_valid_branch_name("issue-42")

    def test_rejects_uppercase_or_invalid_chars(self) -> None:
        assert not _is_valid_branch_name("feature/18840-Has Spaces")

    def test_rejects_missing_pbi_id(self) -> None:
        assert not _is_valid_branch_name("feature/-no-id")


# ---------------------------------------------------------------------------
# GhCliIssueMetaAdapter — delegates to the shared GhRunner abstraction
# ---------------------------------------------------------------------------


class TestGhCliIssueMetaAdapter:
    def test_get_issue_parses_json(self) -> None:
        runner = MagicMock()
        runner.run.return_value = json.dumps({"body": "b", "title": "t"})
        adapter = GhCliIssueMetaAdapter(runner=runner)

        data = adapter.get_issue("org/repo", 5)

        assert data == {"body": "b", "title": "t"}
        runner.run.assert_called_once_with(
            "issue", "view", "5", "--repo", "org/repo", "--json", "body,title",
        )

    def test_get_issue_propagates_runner_failure(self) -> None:
        runner = MagicMock()
        runner.run.side_effect = RuntimeError("boom")
        adapter = GhCliIssueMetaAdapter(runner=runner)

        with pytest.raises(RuntimeError, match="boom"):
            adapter.get_issue("org/repo", 5)

    def test_find_meta_comment_returns_matching_comment(self) -> None:
        runner = MagicMock()
        comments = {"comments": [{"body": "unrelated"}, {"body": "<!-- claire:meta -->\nstuff"}]}
        runner.run.return_value = json.dumps(comments)
        adapter = GhCliIssueMetaAdapter(runner=runner)

        result = adapter.find_meta_comment("org/repo", 5)

        assert result == "<!-- claire:meta -->\nstuff"

    def test_find_meta_comment_returns_none_when_absent(self) -> None:
        runner = MagicMock()
        runner.run.return_value = json.dumps({"comments": [{"body": "unrelated"}]})
        adapter = GhCliIssueMetaAdapter(runner=runner)

        result = adapter.find_meta_comment("org/repo", 5)

        assert result is None

    def test_find_meta_comment_returns_none_on_runner_failure(self) -> None:
        runner = MagicMock()
        runner.run.side_effect = RuntimeError("boom")
        adapter = GhCliIssueMetaAdapter(runner=runner)

        result = adapter.find_meta_comment("org/repo", 5)

        assert result is None

    def test_post_comment_calls_runner(self) -> None:
        runner = MagicMock()
        adapter = GhCliIssueMetaAdapter(runner=runner)

        adapter.post_comment("org/repo", 5, "hello")

        runner.run.assert_called_once_with(
            "issue", "comment", "5", "--repo", "org/repo", "--body", "hello",
        )

    def test_post_comment_propagates_runner_failure(self) -> None:
        runner = MagicMock()
        runner.run.side_effect = RuntimeError("boom")
        adapter = GhCliIssueMetaAdapter(runner=runner)

        with pytest.raises(RuntimeError, match="boom"):
            adapter.post_comment("org/repo", 5, "hello")

    def test_default_runner_is_subprocess_gh_runner(self) -> None:
        from claire_adapters.github import SubprocessGhRunner

        adapter = GhCliIssueMetaAdapter()
        assert isinstance(adapter.runner, SubprocessGhRunner)


# ---------------------------------------------------------------------------
# PrepareWorktreeStep
# ---------------------------------------------------------------------------


class TestPrepareWorktreeStep:
    def test_fresh_start_creates_worktree_and_posts_comment(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path, meta_comment=None)
        task = _make_task(issue=18842, repo="org/repo")
        worktree_path = str(tmp_path / ".claire" / "worktrees" / "issue-18842")

        with _patch_worktree_prepare() as mock_cls:
            mock_cls.return_value.prepare.return_value = worktree_path
            result = PrepareWorktreeStep()(task, {}, adapters)

        assert result.ok
        assert result.data["worktree_ready"] is True
        assert result.data["branch_name"] == _DEFAULT_BRANCH
        assert result.data["worktree_path"] == worktree_path

        mock_cls.assert_called_once_with(local_path=tmp_path)
        mock_cls.return_value.prepare.assert_called_once_with(
            repo="org/repo",
            issue=18842,
            base_branch="develop",
            branch_name=_DEFAULT_BRANCH,
        )

        adapters.meta.post_comment.assert_called_once()
        posted_repo, posted_issue, posted_body = adapters.meta.post_comment.call_args[0]
        assert posted_repo == "org/repo"
        assert posted_issue == 18842
        assert "<!-- claire:meta -->" in posted_body
        assert f"`{_DEFAULT_BRANCH}`" in posted_body
        assert worktree_path in posted_body

    def test_idempotent_when_worktree_exists_and_meta_comment_found(self, tmp_path: Path) -> None:
        worktree_dir = tmp_path / ".claire" / "worktrees" / "issue-7"
        worktree_dir.mkdir(parents=True)
        meta_comment = (
            "<!-- claire:meta -->\n"
            "**Branch:** `feature/100-existing-branch`\n"
            "**Worktree:** `/some/path`"
        )
        adapters = _make_adapters(tmp_path, meta_comment=meta_comment)
        task = _make_task(issue=7)

        with _patch_worktree_prepare() as mock_cls:
            result = PrepareWorktreeStep()(task, {}, adapters)

        assert result.ok
        assert result.data["branch_name"] == "feature/100-existing-branch"
        mock_cls.assert_not_called()
        adapters.meta.get_issue.assert_not_called()
        adapters.meta.post_comment.assert_not_called()

    def test_falls_through_when_worktree_exists_but_no_meta_comment(self, tmp_path: Path) -> None:
        worktree_dir = tmp_path / ".claire" / "worktrees" / "issue-7"
        worktree_dir.mkdir(parents=True)
        adapters = _make_adapters(tmp_path, meta_comment=None)
        task = _make_task(issue=7)

        with _patch_worktree_prepare() as mock_cls:
            mock_cls.return_value.prepare.return_value = str(worktree_dir)
            result = PrepareWorktreeStep()(task, {}, adapters)

        assert result.ok
        mock_cls.return_value.prepare.assert_called_once()
        adapters.meta.post_comment.assert_called_once()

    def test_missing_pbi_id_raises(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path, issue_body="no ado link here", meta_comment=None)
        task = _make_task(issue=9)
        with pytest.raises(RuntimeError, match="pbi_id"):
            PrepareWorktreeStep()(task, {}, adapters)

    def test_rejects_forged_meta_comment_and_re_derives(self, tmp_path: Path) -> None:
        """A branch_name that doesn't match feature/{pbi_id}-{slug} — e.g. posted by an
        attacker able to comment on the issue, or a stale/malformed comment — must never
        be trusted as-is. Falls through to deriving + recreating instead."""
        worktree_dir = tmp_path / ".claire" / "worktrees" / "issue-7"
        worktree_dir.mkdir(parents=True)
        forged_comment = (
            "<!-- claire:meta -->\n"
            "**Branch:** `--upload-pack=evil`\n"
            "**Worktree:** `/some/path`"
        )
        adapters = _make_adapters(tmp_path, meta_comment=forged_comment)
        task = _make_task(issue=7)

        with _patch_worktree_prepare() as mock_cls:
            mock_cls.return_value.prepare.return_value = str(worktree_dir)
            result = PrepareWorktreeStep()(task, {}, adapters)

        assert result.ok
        assert result.data["branch_name"] == _DEFAULT_BRANCH
        mock_cls.return_value.prepare.assert_called_once()
        adapters.meta.post_comment.assert_called_once()


# ---------------------------------------------------------------------------
# SpawnDevStep
# ---------------------------------------------------------------------------


class TestSpawnDevStep:
    def test_skips_when_dev_done_in_ctx(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path)
        task = _make_task()
        result = SpawnDevStep()(task, {"dev_done": True}, adapters)
        assert result.ok
        adapters.terminal.spawn_dev.assert_not_called()
        adapters.github.wait_for_label.assert_not_called()

    def test_spawns_dev_and_waits_for_label(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path)
        task = _make_task(issue=5)
        result = SpawnDevStep()(task, {}, adapters)
        assert result.ok
        adapters.terminal.spawn_dev.assert_called_once_with(5, "org/repo")
        adapters.github.wait_for_label.assert_called_once_with(
            "org/repo", 5, "role:tester"
        )

    def test_returns_dev_done_and_pr_number(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path, pr_number=99)
        task = _make_task()
        result = SpawnDevStep()(task, {}, adapters)
        assert result.ok
        assert result.data["dev_done"] is True
        assert result.data["pr_number"] == 99


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
# PushToADOStep
# ---------------------------------------------------------------------------


class TestPushToADOStep:
    def test_reads_branch_name_from_ctx_and_calls_adapter(self, tmp_path: Path) -> None:
        adapters = _make_adapters(tmp_path)
        adapters.ado.push_branch_and_create_pr.return_value = 77
        task = _make_task(issue=5)
        result = PushToADOStep()(task, {"branch_name": "feature/1-foo"}, adapters)
        assert result.ok
        assert result.data["ado_pr_id"] == 77
        adapters.ado.push_branch_and_create_pr.assert_called_once_with(5, "feature/1-foo")


# ---------------------------------------------------------------------------
# FivepointsTfoneDevWorkflow — scenario tests (including restart recovery)
# ---------------------------------------------------------------------------


class TestFivepointsTfoneDevWorkflow:
    def test_full_happy_path_fresh_start(self, tmp_path: Path) -> None:
        """No label present → HydrateState returns {} → all steps run."""
        adapters = _make_adapters(tmp_path, role_label=None, pr_number=20)
        task = _make_task(issue=42)
        with _patch_worktree_prepare() as mock_cls:
            mock_cls.return_value.prepare.return_value = str(tmp_path / ".claire/worktrees/issue-42")
            result = FivepointsTfoneDevWorkflow().run(task, adapters)
        assert result.ok
        adapters.terminal.spawn_dev.assert_called_once()
        adapters.terminal.spawn_tester.assert_called_once()
        adapters.ado.push_branch_and_create_pr.assert_called_once_with(42, _DEFAULT_BRANCH)
        adapters.ado.wait_for_merge.assert_called_once_with(42)

    def test_restart_with_role_tester_skips_dev(self, tmp_path: Path) -> None:
        """role:tester present → HydrateState sets dev_done=True → DevStep skipped."""
        adapters = _make_adapters(tmp_path, role_label="role:tester", pr_number=5)
        task = _make_task()
        with _patch_worktree_prepare() as mock_cls:
            mock_cls.return_value.prepare.return_value = "/mock/worktree"
            result = FivepointsTfoneDevWorkflow().run(task, adapters)
        assert result.ok
        adapters.terminal.spawn_dev.assert_not_called()
        adapters.terminal.spawn_tester.assert_called_once()

    def test_restart_with_role_ready_skips_dev_and_tester(self, tmp_path: Path) -> None:
        """role:ready present → HydrateState sets dev_done+tester_done → both skipped."""
        adapters = _make_adapters(tmp_path, role_label="role:ready", pr_number=7)
        task = _make_task()
        with _patch_worktree_prepare() as mock_cls:
            mock_cls.return_value.prepare.return_value = "/mock/worktree"
            result = FivepointsTfoneDevWorkflow().run(task, adapters)
        assert result.ok
        adapters.terminal.spawn_dev.assert_not_called()
        adapters.terminal.spawn_tester.assert_not_called()
        adapters.ado.push_branch_and_create_pr.assert_called_once()

    def test_restart_with_existing_worktree_reuses_branch_from_meta_comment(
        self, tmp_path: Path
    ) -> None:
        """PrepareWorktreeStep recovers branch_name from the claire:meta comment — no re-derivation, no worktree recreation."""
        worktree_dir = tmp_path / ".claire" / "worktrees" / "issue-42"
        worktree_dir.mkdir(parents=True)
        meta_comment = (
            "<!-- claire:meta -->\n"
            "**Branch:** `feature/999-recovered-branch`\n"
            "**Worktree:** `/some/path`"
        )
        adapters = _make_adapters(
            tmp_path, role_label="role:ready", pr_number=7, meta_comment=meta_comment
        )
        task = _make_task(issue=42)
        with _patch_worktree_prepare() as mock_cls:
            result = FivepointsTfoneDevWorkflow().run(task, adapters)
        assert result.ok
        mock_cls.assert_not_called()
        adapters.ado.push_branch_and_create_pr.assert_called_once_with(
            42, "feature/999-recovered-branch"
        )

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
        with _patch_worktree_prepare() as mock_cls:
            mock_cls.return_value.prepare.return_value = "/mock/worktree"
            with pytest.raises(RuntimeError, match="ADO PR abandoned"):
                FivepointsTfoneDevWorkflow().run(task, adapters)


# ---------------------------------------------------------------------------
# run_fivepoints_tfone_dev_for_issue — entry point smoke test
# ---------------------------------------------------------------------------


class TestRunFivepointsTfoneDevForIssue:
    def test_entry_point_wires_adapters_and_calls_workflow(
        self, tmp_path: Path
    ) -> None:
        from claire_core.pipeline import StepResult as _SR
        from claire_fivepoints.workflows import run_fivepoints_tfone_dev_for_issue

        mock_workflow_instance = MagicMock()
        mock_workflow_instance.run.return_value = _SR(ok=True, data={"ado_merged": True})

        mock_ado_cls = MagicMock()
        mock_ado_cls.for_repo.return_value = MagicMock()
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
            patch("claire_fivepoints.workflows.FivepointsTfoneDevWorkflow", mock_workflow_cls),
        ):
            result = run_fivepoints_tfone_dev_for_issue(42, "org/repo")

        assert result.ok
        mock_workflow_instance.run.assert_called_once()
        call_args = mock_workflow_instance.run.call_args
        task = call_args[0][0]
        adapters = call_args[0][1]
        assert task.issue == 42
        assert task.repo == "org/repo"
        assert isinstance(adapters.meta, GhCliIssueMetaAdapter)
