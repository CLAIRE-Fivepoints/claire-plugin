"""azure_issue_bridge.steps — pure pipeline steps: fetch_emails, filter_pbi, create_issues."""
from __future__ import annotations

import logging
from email.message import EmailMessage

from claire_core.pipeline import StepResult
from claire_fivepoints.azure_issue_bridge.adapters import ADOAdapter, WorkItem
from claire_fivepoints.azure_issue_bridge.bridge import is_pbi_email, parse_pbi_id

logger = logging.getLogger(__name__)


def fetch_emails_step(task, ctx: dict, adapters) -> StepResult:
    """Fetch emails from Gmail via adapters.email."""
    try:
        emails = adapters.email.fetch(
            sender=task.sender,
            max_results=task.max_results,
        )
    except RuntimeError as exc:
        return StepResult(ok=False, error=str(exc))
    return StepResult(ok=True, data={"emails": emails})


def filter_pbi_step(task, ctx: dict, adapters) -> StepResult:
    """Keep only valid ADO PBI emails using is_pbi_email()."""
    pbi_emails = []
    for e in ctx["emails"]:
        msg = EmailMessage()
        msg["From"] = e.get("from_addr", "")
        msg["Subject"] = e.get("subject", "")
        if is_pbi_email(msg, sender=task.sender):
            pbi_emails.append(e)
    return StepResult(ok=True, data={"pbi_emails": pbi_emails})


def _build_issue_body(work_item: WorkItem, ado: ADOAdapter, received_date: str = "") -> str:
    """Build an enriched issue body from the ADO work item (state, area, type,
    parent PBI link + background) — falls back to source/thread when no PBI ID
    could be parsed from the email subject.
    """
    body = f"**Azure DevOps:** {ado.work_item_url(work_item.id)}\n"
    if received_date:
        body += f"**Received:** {received_date}\n"
    body += f"\n**State:** {work_item.state}\n**Area:** {work_item.area_path}"
    if work_item.work_item_type:
        body += f"\n**Type:** {work_item.work_item_type}"

    parent: WorkItem | None = None
    if work_item.parent_id:
        body += f"\n**Parent PBI:** {ado.work_item_url(work_item.parent_id)}"
        try:
            parent = ado.fetch_work_item(str(work_item.parent_id))
        except Exception as exc:
            logger.warning("Could not fetch parent PBI #%s: %s", work_item.parent_id, exc)

    if work_item.description:
        body += f"\n\n**Description:**\n{work_item.description}"
    if work_item.acceptance_criteria:
        body += f"\n\n**Acceptance Criteria:**\n{work_item.acceptance_criteria}"

    if parent and parent.description and parent.description != work_item.description:
        body += f"\n\n---\n**Parent PBI — Background:**\n{parent.description}"

    return body


def create_issues_step(task, ctx: dict, adapters) -> StepResult:
    """Create one GitHub issue per detected PBI. No-op when dry_run=True."""
    if not task.dry_run and not task.repo:
        return StepResult(ok=False, error="repo is required when dry_run=False")

    created = []
    for e in ctx["pbi_emails"]:
        if task.dry_run:
            created.append({"subject": e["subject"], "dry_run": True})
            continue

        pbi_id = parse_pbi_id(e["subject"])

        # Déduplication — skip si une issue ouverte existe déjà pour ce PBI
        if pbi_id is not None:
            existing = adapters.github.find_open_issue(task.repo, pbi_id)
            if existing is not None:
                logger.info("PBI %s already has open issue #%s — skipping", pbi_id, existing)
                created.append({"subject": e["subject"], "skipped": True, "existing_issue": existing})
                continue

        body = f"Source: {e['from_addr']}\nThread: {e['thread_id']}"
        if pbi_id is not None:
            try:
                work_item = adapters.ado.fetch_work_item(pbi_id)
            except Exception as exc:
                return StepResult(ok=False, error=f"fetch_work_item failed: {exc}")
            body = _build_issue_body(work_item, adapters.ado, received_date=e.get("received_date", ""))

        try:
            issue_number = adapters.github.create_issue(
                title=f"PBI: {e['subject']}",
                body=body,
                repo=task.repo,
            )
        except RuntimeError as exc:
            return StepResult(ok=False, error=str(exc))
        created.append({"subject": e["subject"], "issue": issue_number})

    return StepResult(ok=True, data={"created": created})


def sync_branch_step(task, ctx: dict, adapters) -> StepResult:
    """Sync source/develop → target/develop before worktree creation."""
    if task.dry_run:
        return StepResult(ok=True, data={"sync_skipped": True})
    try:
        adapters.branch_sync.sync_branch(
            source_repo=task.source_repo,
            source_branch="develop",
            target_repo=task.repo,
            target_branch="develop",
        )
    except Exception as exc:
        return StepResult(ok=False, error=f"sync_branch failed: {exc}")
    return StepResult(ok=True, data={"branch_synced": True})


def assign_step(task, ctx: dict, adapters) -> StepResult:
    """Assign each issue to the agent — ALWAYS LAST in the pipeline. Triggers session-monitor."""
    assigned = []
    for item in ctx.get("created", []):
        issue_number = item.get("issue")
        if issue_number is None:
            if task.dry_run:
                assigned.append({"assign_skipped": True, "agent": task.agent})
            continue

        if task.dry_run:
            assigned.append({"assign_skipped": True, "agent": task.agent, "issue": issue_number})
            continue

        try:
            adapters.assign.assign(task.repo, issue_number, task.agent)
        except Exception as exc:
            return StepResult(ok=False, error=f"assign failed: {exc}")
        assigned.append({"assigned_to": task.agent, "issue": issue_number})

    return StepResult(ok=True, data={"assigned": assigned})


def add_label_step(task, ctx: dict, adapters) -> StepResult:
    """Add role:{client}-dev label to each created issue."""
    label = f"role:{task.client}-dev"
    labeled = []
    for item in ctx.get("created", []):
        issue_number = item.get("issue")
        if issue_number is None:
            # dry_run item — log only
            labeled.append({"subject": item.get("subject"), "label": label, "dry_run": True})
            continue
        try:
            adapters.labels.add_label(task.repo, issue_number, label)
        except Exception as exc:
            return StepResult(ok=False, error=f"add_label failed: {exc}")
        labeled.append({"issue": issue_number, "label": label})
    return StepResult(ok=True, data={"labeled": labeled})


def prepare_worktree_step(task, ctx: dict, adapters) -> StepResult:
    """Create a pbi-{issue} worktree on develop before assignment."""
    branch_prefix = getattr(task, "branch_prefix", "pbi")
    prepared = []
    for item in ctx.get("created", []):
        issue_number = item.get("issue")
        branch_name = (
            f"{branch_prefix}-{issue_number}"
            if issue_number is not None
            else f"{branch_prefix}-dry"
        )

        if issue_number is None or task.dry_run:
            prepared.append(
                {
                    "subject": item.get("subject"),
                    "worktree_skipped": True,
                    "branch_name": branch_name,
                }
            )
            continue

        try:
            worktree_path = adapters.worktree.prepare(
                repo=task.repo,
                issue=issue_number,
                base_branch="develop",
                branch_name=branch_name,
            )
        except Exception as exc:
            return StepResult(ok=False, error=f"prepare_worktree failed: {exc}")
        prepared.append(
            {
                "issue": issue_number,
                "worktree_path": worktree_path,
                "branch_name": branch_name,
            }
        )

    return StepResult(ok=True, data={"prepared": prepared})
