"""claire fivepoints — plugin CLI sub-group.

Registered via the claire.commands entry point so that `claire fivepoints`
becomes a top-level sub-command without coupling the core CLI to the plugin.
"""
from __future__ import annotations

import importlib.resources

import typer
from rich.console import Console

app = typer.Typer(help="Fivepoints plugin commands.")
step_app = typer.Typer(help="Run individual fivepoints pipeline steps standalone.")
bridge_app = typer.Typer(help="Azure DevOps PBI email bridge.")
app.add_typer(step_app, name="step")
app.add_typer(bridge_app, name="azure-issue-bridge")

_console = Console()
_err = Console(stderr=True)

_AGENT_HELP = """\
# claire fivepoints

> Fivepoints plugin commands.

## Sub-commands

  claire fivepoints step ado-push  --issue N --repo owner/name
  claire fivepoints step ado-watch --pr N --ado-pr ADO_ID --repo owner/name
  claire fivepoints azure-issue-bridge run [--dry-run]

## Notes

- ado-push runs PushToADOStep (pushes branch to ADO, creates ADO PR)
- ado-watch runs WaitForADOMergeStep (blocks until ADO PR is merged)
- azure-issue-bridge scans Gmail for ADO PBI assignment emails (sender via --from, default: azuredevops@microsoft.com)
- Exits 0 on success, 1 on step failure
"""

_BRIDGE_AGENT_HELP = """\
# claire fivepoints azure-issue-bridge

> Watch Gmail for ADO PBI assignment emails and create GitHub issues.

## Commands

  claire fivepoints azure-issue-bridge run [--from SENDER] [--repo owner/name] [--dry-run] [--max-results N]

## Options

  --from TEXT       Sender email filter (default: azuredevops@microsoft.com)
  --repo TEXT       Target GitHub repo (default: claire-labs/fivepoints-test)
  --dry-run         Show detected emails without creating issues
  --max-results N   Max inbox emails to scan (default: 20)

## Subject format

  Product Backlog Item {ID} - {area} - {title}

## Example

  fivepoints azure-issue-bridge run --from andreoperez@gmail.com --dry-run
  fivepoints azure-issue-bridge run --repo claire-labs/fivepoints-test
"""

_STEP_AGENT_HELP = """\
# claire fivepoints step

> Run individual fivepoints pipeline steps standalone.

## Commands

  claire fivepoints step list                                List all available fivepoints steps
  claire fivepoints step ado-push  --issue N --repo owner/name
  claire fivepoints step ado-watch --pr N --ado-pr ADO_ID --repo owner/name

## Options

  --issue INT      GitHub issue number (ado-push only)
  --pr    INT      GitHub PR number
  --ado-pr INT     ADO PR ID (from ado-push output, ado-watch only)
  --repo  TEXT     Repo in owner/name format (required)

## Example

  claire fivepoints step list
  claire fivepoints step ado-push  --issue 42 --repo CLAIRE-Fivepoints/fivepoints
  claire fivepoints step ado-watch --pr 12 --ado-pr 789 --repo CLAIRE-Fivepoints/fivepoints
"""


def _agent_help_callback(value: bool) -> None:
    if value:
        typer.echo(_AGENT_HELP)
        raise typer.Exit()


def _step_agent_help_callback(value: bool) -> None:
    if value:
        typer.echo(_STEP_AGENT_HELP)
        raise typer.Exit()


def _bridge_agent_help_callback(value: bool) -> None:
    if value:
        typer.echo(_BRIDGE_AGENT_HELP)
        raise typer.Exit()


@app.callback()
def _root(
    agent_help: bool = typer.Option(
        False, "--agent-help", callback=_agent_help_callback,
        is_eager=True, hidden=True,
    ),
) -> None:
    """Fivepoints plugin commands."""


@step_app.callback()
def _step_root(
    agent_help: bool = typer.Option(
        False, "--agent-help", callback=_step_agent_help_callback,
        is_eager=True, hidden=True,
    ),
) -> None:
    """Run individual fivepoints pipeline steps standalone."""


def _load_plugin_steps() -> list[dict]:
    """Read steps from plugin.yaml bundled with the package."""
    import yaml

    try:
        yaml_bytes = importlib.resources.files("claire_fivepoints").joinpath("plugin.yaml").read_bytes()
        data = yaml.safe_load(yaml_bytes) or {}
    except (FileNotFoundError, yaml.YAMLError) as exc:
        _err.print(f"[red]failed to load plugin.yaml:[/red] {exc}")
        return []
    return data.get("steps", [])


def _build_fivepoints_full_adapters(repo: str):
    """Build FivepointsFullAdapters for standalone step execution."""
    from claire_fivepoints.ado_adapter import FivepointsConcreteADOAdapter
    from claire_fivepoints.adapters import FivepointsGhAdapter, FivepointsOsascriptTerminalAdapter
    from claire_workflows.fivepoints_pipeline import FivepointsFullAdapters

    return FivepointsFullAdapters(
        github=FivepointsGhAdapter.default(repo=repo),
        terminal=FivepointsOsascriptTerminalAdapter.with_role_tokens(repo),
        ado=FivepointsConcreteADOAdapter.for_repo(repo),
    )


@step_app.command("list")
def step_list_cmd() -> None:
    """List all available fivepoints plugin steps."""
    steps = _load_plugin_steps()
    typer.echo("Available steps (fivepoints plugin):\n")
    if not steps:
        typer.echo("  (no steps defined)")
        return
    name_w = max(len(s["name"]) for s in steps)
    flags_w = max(len(", ".join(s.get("flags", []))) for s in steps)
    for step in steps:
        flags = ", ".join(step.get("flags", []))
        desc = step.get("description", "")
        typer.echo(f"  {step['name']:<{name_w}}  {flags:<{flags_w}}  {desc}")


@step_app.command("ado-push")
def ado_push_cmd(
    issue: int = typer.Option(..., "--issue", "-i", help="Issue number."),
    repo: str = typer.Option(..., "--repo", "-r", help="Target repo (owner/name)."),
    agent_help: bool = typer.Option(
        False, "--agent-help", callback=_step_agent_help_callback,
        is_eager=True, hidden=True,
    ),
) -> None:
    """Run PushToADOStep standalone — push branch to ADO and create ADO PR."""
    from claire_workflows.fivepoints_pipeline import FivepointsTask, PushToADOStep

    task = FivepointsTask(issue=issue, repo=repo)
    adapters = _build_fivepoints_full_adapters(repo)
    result = PushToADOStep()(task, {}, adapters)
    if not result.ok:
        _err.print(f"[red]✗[/red] ado-push failed: {result.error}")
        raise typer.Exit(code=1)
    _console.print(f"[green]✓[/green] ADO PR created: {result.data.get('ado_pr_id')}")


@step_app.command("ado-watch")
def ado_watch_cmd(
    pr: int = typer.Option(..., "--pr", "-p", help="GitHub PR number."),
    ado_pr: int = typer.Option(..., "--ado-pr", help="ADO PR ID (from ado-push output)."),
    repo: str = typer.Option(..., "--repo", "-r", help="Target repo (owner/name)."),
    agent_help: bool = typer.Option(
        False, "--agent-help", callback=_step_agent_help_callback,
        is_eager=True, hidden=True,
    ),
) -> None:
    """Run WaitForADOMergeStep standalone — block until ADO PR is merged."""
    from claire_workflows.fivepoints_pipeline import FivepointsTask, WaitForADOMergeStep

    task = FivepointsTask(issue=0, repo=repo)
    adapters = _build_fivepoints_full_adapters(repo)
    result = WaitForADOMergeStep()(task, {"ado_pr_id": ado_pr}, adapters)
    if not result.ok:
        _err.print(f"[red]✗[/red] ado-watch failed: {result.error}")
        raise typer.Exit(code=1)
    _console.print(f"[green]✓[/green] ADO PR #{ado_pr} merged")


@step_app.command("improvement-cycle", hidden=True)
def improvement_cycle_cmd(
    pr: int = typer.Option(..., "--pr", "-p", help="GitHub PR number."),
    repo: str = typer.Option(..., "--repo", "-r", help="Target repo (owner/name)."),
    agent_help: bool = typer.Option(
        False, "--agent-help", callback=_step_agent_help_callback,
        is_eager=True, hidden=True,
    ),
) -> None:
    """Run improvement-cycle step standalone (ADO comment review + fix cycle)."""
    _err.print("[yellow]⚠[/yellow] improvement-cycle is not yet implemented as a standalone step.")
    raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# azure-issue-bridge sub-group
# ---------------------------------------------------------------------------


class _GhCliAdapter:
    """Calls `gh issue create` via subprocess and returns the new issue number."""

    def create_issue(self, title: str, body: str, repo: str) -> int:
        import subprocess

        cmd = [
            "gh", "issue", "create",
            "--title", title,
            "--body", body,
            "--repo", repo,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"gh issue create failed: {result.stderr.strip()}")
        # gh outputs the issue URL, e.g. https://github.com/owner/repo/issues/42
        url = result.stdout.strip().rstrip("/")
        return int(url.split("/")[-1])


@bridge_app.callback()
def _bridge_root(
    agent_help: bool = typer.Option(
        False, "--agent-help", callback=_bridge_agent_help_callback,
        is_eager=True, hidden=True,
    ),
) -> None:
    """Azure DevOps PBI email bridge."""


@bridge_app.command("run")
def bridge_run_cmd(
    sender: str = typer.Option(
        "azuredevops@microsoft.com", "--from",
        help="Sender email filter (ADO default).",
    ),
    repo: str = typer.Option(
        "claire-labs/fivepoints-test", "--repo",
        help="Target GitHub repo (owner/name).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show detected emails without creating issues."),
    max_results: int = typer.Option(20, "--max-results", help="Max inbox emails to scan."),
    agent_help: bool = typer.Option(
        False, "--agent-help", callback=_bridge_agent_help_callback,
        is_eager=True, hidden=True,
    ),
) -> None:
    """Scan Gmail for ADO PBI assignment emails and create GitHub issues."""
    from claire_fivepoints.azure_issue_bridge.adapters import BridgeAdapters, GmailApiAdapter
    from claire_fivepoints.azure_issue_bridge.pipeline import BridgeTask, bridge_pipeline

    _console.print(f"[dim]Sender:[/dim] {sender}")
    if dry_run:
        _console.print("[dim]Mode:[/dim] dry-run — no issues will be created")

    task = BridgeTask(sender=sender, max_results=max_results, dry_run=dry_run, repo=repo)
    adapters = BridgeAdapters(
        email=GmailApiAdapter(),
        github=_GhCliAdapter(),
    )
    result = bridge_pipeline(task, adapters)
    if not result.ok:
        _err.print(f"[red]✗[/red] bridge failed: {result.error}")
        raise typer.Exit(code=1)

    created = result.data.get("created", [])
    if not created:
        _console.print("No PBI assignment emails found.")
        return

    _console.print(f"\n[bold]{'Detected' if dry_run else 'Created'} {len(created)} PBI email(s):[/bold]")
    for item in created:
        subject = item.get("subject", "(no subject)")
        if item.get("dry_run"):
            _console.print(f"  [dim][dry-run][/dim] [green]✓[/green] {subject}")
        else:
            _console.print(f"  [green]✓[/green] {subject} → #{item.get('issue')}")
