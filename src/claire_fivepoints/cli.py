"""claire fivepoints — plugin CLI sub-group.

Registered via the claire.commands entry point so that `claire fivepoints`
becomes a top-level sub-command without coupling the core CLI to the plugin.
"""
from __future__ import annotations

import argparse
import importlib.resources
import os
from types import SimpleNamespace

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

  claire fivepoints azure-issue-bridge run [--from SENDER] [--repo owner/name] [--dry-run] [--max-results N] [--client SLUG] [--source-repo OWNER/REPO]
  claire fivepoints azure-issue-bridge inject --from ADDRESS --subject SUBJECT [--dry-run] [--repo OWNER/NAME] [--agent USERNAME]

## Options (run)

  --from TEXT       Sender email filter (default: azuredevops@microsoft.com)
  --repo TEXT       Target GitHub repo (default: claire-labs/fivepoints-test)
  --dry-run         Show detected emails without creating issues
  --max-results N   Max inbox emails to scan (default: 20)
  --client SLUG        Client slug for the role:{client}-dev label (default: fivepoints)
  --source-repo TEXT   Source repo for branch sync (default: CLAIRE-Fivepoints/fivepoints-test, envvar: ADO_BRIDGE_SYNC_SOURCE)

## Options (inject)

  --from ADDRESS    Sender address (e.g. azuredevops@microsoft.com)
  --subject SUBJECT Email subject matching the ADO PBI pattern
  --dry-run         Print parsed result without any side effects
  --repo OWNER/NAME Target GitHub repo override
  --agent USERNAME  GitHub assignee override

## Subject format

  Product Backlog Item {ID} - {area} - {title}

## Example

  fivepoints azure-issue-bridge run --from andreoperez@gmail.com --dry-run
  fivepoints azure-issue-bridge run --repo claire-labs/fivepoints-test
  fivepoints azure-issue-bridge inject --from azuredevops@microsoft.com \\
    --subject "Product Backlog Item 12345 - DEV - Client Management test" --dry-run
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


class _RealLabelAdapter:
    """Calls `gh issue edit --add-label` via subprocess. Creates the label if absent."""

    def add_label(self, repo: str, issue: int, label: str) -> None:
        import subprocess

        result = subprocess.run(
            ["gh", "issue", "edit", str(issue), "--repo", repo, "--add-label", label],
            check=False, capture_output=True, text=True,
        )
        if result.returncode != 0:
            create_result = subprocess.run(
                ["gh", "label", "create", label, "--repo", repo, "--color", "0075ca"],
                check=False, capture_output=True, text=True,
            )
            retry = subprocess.run(
                ["gh", "issue", "edit", str(issue), "--repo", repo, "--add-label", label],
                check=False, capture_output=True, text=True,
            )
            if retry.returncode != 0:
                label_stderr = create_result.stderr.strip()
                issue_stderr = retry.stderr.strip()
                context = f"label create: {label_stderr or '(no stderr)'} | issue edit: {issue_stderr}"
                raise RuntimeError(f"gh add-label failed: {context}")


class _RealAssignAdapter:
    """Calls `gh issue edit --add-assignee` via subprocess. Triggers the session-monitor."""

    def assign(self, repo: str, issue: int, agent: str) -> None:
        import subprocess

        result = subprocess.run(
            ["gh", "issue", "edit", str(issue), "--repo", repo, "--add-assignee", agent],
            check=False, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh assign failed: {result.stderr.strip()}")


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
    client: str = typer.Option(
        "fivepoints", "--client", envvar="ADO_BRIDGE_CLIENT",
        help="Client slug for the role:{client}-dev label.",
    ),
    source_repo: str = typer.Option(
        "CLAIRE-Fivepoints/fivepoints-test", "--source-repo", envvar="ADO_BRIDGE_SYNC_SOURCE",
        help="Source repo for branch sync (develop → target/develop).",
    ),
    agent: str = typer.Option(
        "claire-test-ai", "--agent",
        help="GitHub login of the agent to assign (triggers session-monitor).",
    ),
    agent_help: bool = typer.Option(
        False, "--agent-help", callback=_bridge_agent_help_callback,
        is_eager=True, hidden=True,
    ),
) -> None:
    """Scan Gmail for ADO PBI assignment emails and create GitHub issues."""
    from claire_fivepoints.azure_issue_bridge.adapters import BridgeAdapters, GmailApiAdapter, RealBranchSync, RealWorktreePrepare
    from claire_fivepoints.azure_issue_bridge.pipeline import BridgeTask, bridge_pipeline

    _console.print(f"[dim]Sender:[/dim] {sender}")
    if dry_run:
        _console.print("[dim]Mode:[/dim] dry-run — no issues will be created")

    task = BridgeTask(
        sender=sender, max_results=max_results, dry_run=dry_run,
        repo=repo, client=client, source_repo=source_repo, agent=agent,
    )
    adapters = BridgeAdapters(
        email=GmailApiAdapter(),
        github=_GhCliAdapter(),
        labels=_RealLabelAdapter(),
        branch_sync=RealBranchSync(),
        worktree=RealWorktreePrepare(),
        assign=_RealAssignAdapter(),
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


def _cmd_inject(args: argparse.Namespace) -> int:
    """Feed a synthetic email into the bridge pipeline without Gmail or ADO auth.

    Runs the full pipeline: create_issue → add_label → sync_branch → assign.
    No cleanup is performed — use the displayed commands to clean up manually.
    """
    from azure_issue_bridge.bridge import (
        WorkItem,
        add_issue_label,
        assign_github_issue,
        create_github_issue,
        is_pbi_email,
        load_bridge_config,
        parse_pbi_id,
        parse_subject_parts,
    )
    from azure_issue_bridge.sync import RealBranchSync

    msg = SimpleNamespace(subject=args.subject, message_id="inject")
    if not is_pbi_email(msg):
        print(f"✗ Subject does not match ADO PBI pattern: {args.subject!r}")
        return 1

    pbi_id = parse_pbi_id(args.subject)
    if not pbi_id:
        print("✗ Could not parse PBI ID from subject")
        return 1

    area, title = parse_subject_parts(args.subject)
    if not title:
        title = f"PBI {pbi_id}"

    work_item = WorkItem(
        id=int(pbi_id),
        title=title,
        description="",
        acceptance_criteria="",
        area_path=area,
        state="To Do",
        work_item_type="Task",
    )

    config = load_bridge_config()
    repo = args.repo or config.target_repo
    agent = args.agent or config.agent
    label = f"role:{config.client}-dev"
    sync_branch = config.sync_branch

    if args.dry_run:
        ado_org = os.environ.get("ADO_ORG", "FivePointsTechnology")
        ado_project = os.environ.get("ADO_PROJECT", "TFIOne")
        ado_url = (
            f"https://dev.azure.com/{ado_org}/{ado_project}"
            f"/_workitems/edit/{pbi_id}"
        )
        print(f"[dry-run] Parsed PBI #{pbi_id}")
        print(f"  from:    {args.from_addr}")
        print(f"  title:   {work_item.title} (PBI #{pbi_id})")
        print(f"  area:    {work_item.area_path or '(none)'}")
        print(f"  repo:    {repo}")
        print()
        print("[dry-run] Issue body preview:")
        print(f"  **Azure DevOps:** {ado_url}")
        print(f"  **State:** {work_item.state}")
        print(f"  **Area:** {work_item.area_path}")
        print(f"  **Type:** {work_item.work_item_type}")
        print()
        print("[dry-run] Pipeline steps:")
        print(f"  1. create_issue   → {work_item.title} (PBI #{pbi_id}) in {repo}")
        print(f"  2. add_label      → {label}")
        print(
            f"  3. sync_branch    → {config.source_repo}/{sync_branch} → {repo}/{sync_branch}"
        )
        print(f"  4. assign         → {agent}")
        return 0

    _prev_repo = os.environ.get("ADO_BRIDGE_REPO")
    os.environ["ADO_BRIDGE_REPO"] = repo
    try:
        issue = create_github_issue(work_item)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1
    finally:
        if _prev_repo is None:
            os.environ.pop("ADO_BRIDGE_REPO", None)
        else:
            os.environ["ADO_BRIDGE_REPO"] = _prev_repo

    try:
        add_issue_label(repo, issue.number, label)
    except RuntimeError as exc:
        print(f"✗ add_label failed: {exc}")
        return 1

    branch_sync = RealBranchSync()
    try:
        branch_sync.sync_branch(config.source_repo, sync_branch, repo, sync_branch)
    except RuntimeError as exc:
        print(f"✗ sync_branch failed: {exc}")
        return 1

    try:
        assign_github_issue(repo, issue.number, agent)
    except RuntimeError as exc:
        print(f"✗ assign failed: {exc}")
        return 1

    print(f"\n✓ Pipeline complet\n")
    print(f"Issue créée   : {issue.url}")
    print(f"Label         : {label}")
    print(
        f"Branch sync   : {config.source_repo}/{sync_branch} → {repo}/{sync_branch}"
    )
    print(f"Assigné à     : {agent}")
    print(f"\nPour nettoyer :")
    print(f"  gh issue close {issue.number} --repo {repo}")
    return 0


@bridge_app.command("inject")
def bridge_inject_cmd(
    from_addr: str = typer.Option(..., "--from", help="Sender address (e.g. azuredevops@microsoft.com)."),
    subject: str = typer.Option(..., "--subject", help="Email subject matching the ADO PBI pattern."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print parsed result without any side effects."),
    repo: str = typer.Option(None, "--repo", help="Target GitHub repo (owner/name)."),
    agent: str = typer.Option(None, "--agent", help="GitHub assignee override."),
    agent_help: bool = typer.Option(
        False, "--agent-help", callback=_bridge_agent_help_callback,
        is_eager=True, hidden=True,
    ),
) -> None:
    """Feed a synthetic email into the bridge pipeline (no Gmail or ADO auth required)."""
    args = argparse.Namespace(
        from_addr=from_addr,
        subject=subject,
        dry_run=dry_run,
        repo=repo,
        agent=agent,
    )
    rc = _cmd_inject(args)
    if rc != 0:
        raise typer.Exit(code=rc)
