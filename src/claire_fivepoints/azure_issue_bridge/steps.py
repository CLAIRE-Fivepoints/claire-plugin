"""azure_issue_bridge.steps — pure pipeline steps: fetch_emails, filter_pbi, create_issues."""
from __future__ import annotations

from email.message import EmailMessage

from claire_core.pipeline import StepResult
from claire_fivepoints.azure_issue_bridge.bridge import is_pbi_email


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


def create_issues_step(task, ctx: dict, adapters) -> StepResult:
    """Create one GitHub issue per detected PBI. No-op when dry_run=True."""
    if not task.dry_run and not task.repo:
        return StepResult(ok=False, error="repo is required when dry_run=False")

    created = []
    for e in ctx["pbi_emails"]:
        if task.dry_run:
            created.append({"subject": e["subject"], "dry_run": True})
            continue
        try:
            issue_number = adapters.github.create_issue(
                title=f"PBI: {e['subject']}",
                body=f"Source: {e['from_addr']}\nThread: {e['thread_id']}",
                repo=task.repo,
            )
        except RuntimeError as exc:
            return StepResult(ok=False, error=str(exc))
        created.append({"subject": e["subject"], "issue": issue_number})

    return StepResult(ok=True, data={"created": created})


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
