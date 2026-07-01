"""Unit tests for RealWorktreePrepare — mocks subprocess.run directly (no mocking
of RealWorktreePrepare itself), so the actual git command sequence is exercised:
ado-remote sync (git fetch ado dev + git branch -f) and the detached-HEAD vs
named-branch worktree add paths.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from claire_fivepoints.azure_issue_bridge.worktree import RealWorktreePrepare


class TestRealWorktreePrepareSync:
    def test_returns_existing_worktree_without_git_call(self, tmp_path) -> None:
        worktree_path = tmp_path / ".claire" / "worktrees" / "issue-5"
        worktree_path.mkdir(parents=True)
        prepare = RealWorktreePrepare(local_path=str(tmp_path))

        with patch("subprocess.run") as mock_run:
            result = prepare.prepare(repo="org/repo", issue=5, base_branch="develop")

        mock_run.assert_not_called()
        assert result == str(worktree_path)

    def test_fetches_ado_dev_and_force_updates_develop(self, tmp_path) -> None:
        prepare = RealWorktreePrepare(local_path=str(tmp_path))

        with patch(
            "subprocess.run", return_value=MagicMock(returncode=0, stderr="")
        ) as mock_run:
            prepare.prepare(repo="org/repo", issue=7, base_branch="develop")

        commands = [call.args[0] for call in mock_run.call_args_list]
        assert ["git", "-C", str(tmp_path), "fetch", "ado", "dev"] in commands
        assert [
            "git", "-C", str(tmp_path), "branch", "-f", "develop", "ado/dev",
        ] in commands

    def test_rejects_base_branch_other_than_develop(self, tmp_path) -> None:
        prepare = RealWorktreePrepare(local_path=str(tmp_path))

        with patch("subprocess.run") as mock_run:
            with pytest.raises(ValueError, match="develop"):
                prepare.prepare(repo="org/repo", issue=1, base_branch="main")

        mock_run.assert_not_called()

    def test_raises_when_git_fetch_fails(self, tmp_path) -> None:
        prepare = RealWorktreePrepare(local_path=str(tmp_path))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="fatal: error")
            with pytest.raises(RuntimeError, match="git command failed"):
                prepare.prepare(repo="org/repo", issue=1, base_branch="develop")


class TestRealWorktreePrepareDetachedHead:
    """No branch_name — the new default path for PrepareWorktreeStep (issue #184)."""

    def test_worktree_add_uses_detach_no_named_branch(self, tmp_path) -> None:
        prepare = RealWorktreePrepare(local_path=str(tmp_path))
        expected_path = tmp_path / ".claire" / "worktrees" / "issue-9"

        with patch(
            "subprocess.run", return_value=MagicMock(returncode=0, stderr="")
        ) as mock_run:
            result = prepare.prepare(repo="org/repo", issue=9, base_branch="develop")

        assert result == str(expected_path)
        worktree_cmd = mock_run.call_args_list[-1].args[0]
        assert worktree_cmd == [
            "git", "-C", str(tmp_path), "worktree", "add", "--detach",
            str(expected_path), "develop",
        ]

    def test_raises_when_git_worktree_add_fails(self, tmp_path) -> None:
        prepare = RealWorktreePrepare(local_path=str(tmp_path))

        def run_side_effect(cmd, **kwargs):
            if "fetch" in cmd or "branch" in cmd:
                return MagicMock(returncode=0, stderr="", stdout="")
            return MagicMock(returncode=128, stderr="fatal: worktree add failed")

        with patch("subprocess.run", side_effect=run_side_effect):
            with pytest.raises(RuntimeError, match="git command failed"):
                prepare.prepare(repo="org/repo", issue=10, base_branch="develop")


class TestRealWorktreePrepareNamedBranch:
    """branch_name provided — legacy path kept for the (unwired) bridge step."""

    def test_worktree_add_creates_named_branch_from_develop(self, tmp_path) -> None:
        prepare = RealWorktreePrepare(local_path=str(tmp_path))
        expected_path = tmp_path / ".claire" / "worktrees" / "issue-11"

        with patch(
            "subprocess.run", return_value=MagicMock(returncode=0, stderr="")
        ) as mock_run:
            result = prepare.prepare(
                repo="org/repo", issue=11, base_branch="develop", branch_name="pbi-11",
            )

        assert result == str(expected_path)
        worktree_cmd = mock_run.call_args_list[-1].args[0]
        assert worktree_cmd == [
            "git", "-C", str(tmp_path), "worktree", "add", "--track", "-b",
            "pbi-11", str(expected_path), "develop",
        ]
