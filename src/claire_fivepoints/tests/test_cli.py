"""Tests for claire fivepoints step list command."""
from __future__ import annotations

from typer.testing import CliRunner

from claire_fivepoints.cli import app

runner = CliRunner()


class TestFivepointsStepList:
    """claire fivepoints step list — reads plugin.yaml and prints steps."""

    def test_list_exits_zero(self) -> None:
        result = runner.invoke(app, ["step", "list"])
        assert result.exit_code == 0, result.output

    def test_list_shows_ado_push(self) -> None:
        result = runner.invoke(app, ["step", "list"])
        assert "ado-push" in result.output

    def test_list_shows_ado_watch(self) -> None:
        result = runner.invoke(app, ["step", "list"])
        assert "ado-watch" in result.output

    def test_list_shows_improvement_cycle(self) -> None:
        result = runner.invoke(app, ["step", "list"])
        assert "improvement-cycle" in result.output

    def test_list_shows_flags(self) -> None:
        result = runner.invoke(app, ["step", "list"])
        assert "--issue" in result.output or "--pr" in result.output

    def test_list_shows_descriptions(self) -> None:
        result = runner.invoke(app, ["step", "list"])
        assert "ADO" in result.output

    def test_list_header(self) -> None:
        result = runner.invoke(app, ["step", "list"])
        assert "fivepoints plugin" in result.output

    def test_step_agent_help_mentions_list(self) -> None:
        from claire_fivepoints.cli import step_app

        result = runner.invoke(step_app, ["--agent-help"])
        assert "list" in result.output
