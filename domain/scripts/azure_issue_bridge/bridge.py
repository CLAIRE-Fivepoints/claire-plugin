"""
azure_issue_bridge.bridge — Core pipeline logic.

Pipeline:
  1. Poll Gmail inbox for Azure DevOps PBI assignment emails
  2. Parse the PBI ID from the email subject
  3. TRIAGE: group emails by ADO work item ID, then:
     - Skip work items in terminal ADO state (Done, Closed, Removed, Resolved)
     - Skip parents whose children are in the same batch (same-batch detection)
     - Skip parents whose ADO children already have GitHub issues (cross-batch detection)
     - Skip PBIs that already have an open GitHub issue (dedup)
  4. Fetch the full work item from Azure DevOps REST API (create decisions only)
  5. Create a GitHub issue with the PBI link via gh CLI
  6. Archive the email and persist processed IDs to avoid re-processing
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

STATE_DIR = Path("~/.claire/azure-issue-bridge").expanduser()
STATE_FILE = STATE_DIR / "state.json"
PROCESSED_FILE = STATE_DIR / "processed.json"


def _load_json(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read %s: %s", path, e)
    return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_processed_ids() -> set[str]:
    """Return the set of already-processed email message IDs."""
    data = _load_json(PROCESSED_FILE, [])
    return set(data)


def save_processed_id(message_id: str) -> None:
    """Append a processed email message ID to the persistent list."""
    ids = load_processed_ids()
    ids.add(message_id)
    _save_json(PROCESSED_FILE, list(ids))


def archive_email(message_id: str) -> None:
    """Remove an email from the Gmail inbox (archive it).

    Calls the Gmail messages.modify API to remove the INBOX label.
    Logs a warning on failure but does not raise — archiving is best-effort.
    """
    from claire_py.email.auth import get_credentials

    creds = get_credentials()
    if not creds:
        logger.warning("Gmail not configured — cannot archive email %s", message_id)
        return

    try:
        from googleapiclient.discovery import build  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("google-api-python-client not installed — cannot archive email")
        return

    try:
        service = build("gmail", "v1", credentials=creds)
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["INBOX"]},
        ).execute()
        logger.info("Archived email %s (removed from inbox)", message_id)
    except Exception as exc:
        logger.warning("Failed to archive email %s: %s", message_id, exc)


def save_state(state: dict[str, Any]) -> None:
    _save_json(STATE_FILE, state)


def load_state() -> dict[str, Any]:
    return _load_json(STATE_FILE, {})


# ---------------------------------------------------------------------------
# Email parsing
# ---------------------------------------------------------------------------

# Subject patterns from Azure DevOps assignment notifications:
#   "Product Backlog Item 10847 - DEV - Client Mgmt - ..."
#   "Task 13644 was assigned to andre.perez dothelpllc.com"
_PBI_SUBJECT_RE = re.compile(
    r"(?:Product Backlog Item|Task|Bug|Feature|User Story)\s+(\d+)",
    re.IGNORECASE,
)

# Exact sender address used by Azure DevOps assignment notifications.
# Using a precise sender lets Gmail pre-filter at the API level
# (via the `from:` query operator), avoiding per-message inspection.
_ADO_SENDER = "azuredevops@microsoft.com"


def is_ado_assignment_email(subject: str) -> bool:
    """Return True if the subject matches an ADO work item assignment notification.

    Matches: Product Backlog Item, Task, Bug, Feature, User Story.
    Sender filtering is done upstream via the Gmail `from:` query.
    """
    return bool(_PBI_SUBJECT_RE.search(subject))


def parse_pbi_id(subject: str) -> str | None:
    """Extract work item ID from an ADO assignment email subject.

    Returns the numeric ID as a string, or None if not found.
    """
    m = _PBI_SUBJECT_RE.search(subject)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Azure DevOps work item fetch
# ---------------------------------------------------------------------------

_DEFAULT_ADO_ORG = "FivePointsTechnology"
_DEFAULT_ADO_PROJECT = "TFIOne"
_ADO_API_VERSION = "7.1"

# ADO work item states that indicate the work is already complete.
# Work items in these states are skipped during triage — no GitHub issue is created.
_TERMINAL_STATES: frozenset[str] = frozenset({"done", "closed", "removed", "resolved"})

# ADO work item states that represent active/in-progress work.
# Only these states trigger GitHub issue creation. Any other state (empty, unknown,
# or a value not in this set) is treated as "state unknown" and results in a
# fail-safe skip — we never create an issue when we cannot confirm active status.
_ACTIVE_STATES: frozenset[str] = frozenset({"to do"})


@dataclass
class WorkItem:
    id: int
    title: str
    description: str
    acceptance_criteria: str
    tags: list[str] = field(default_factory=list)
    area_path: str = ""
    state: str = ""
    assigned_to: str = ""
    parent_id: int | None = None  # System.Parent — set for Tasks under a PBI
    work_item_type: str = (
        ""  # System.WorkItemType (e.g. "Task", "Product Backlog Item")
    )


def _get_pat() -> str:
    """Resolve Azure DevOps PAT from environment or config file."""
    pat = os.environ.get("AZURE_DEVOPS_PAT", "")
    if pat:
        return pat

    config_env = Path("~/.config/claire/.env").expanduser()
    if config_env.exists():
        with open(config_env) as f:
            for line in f:
                line = line.strip()
                if line.startswith("AZURE_DEVOPS_PAT="):
                    value = line[len("AZURE_DEVOPS_PAT=") :]
                    if value:
                        return value

    raise RuntimeError(
        "AZURE_DEVOPS_PAT not found. "
        "Set it in the environment or in ~/.config/claire/.env"
    )


def _ado_auth_header(pat: str) -> str:
    encoded = base64.b64encode(f":{pat}".encode()).decode()
    return f"Basic {encoded}"


def fetch_work_item(pbi_id: str | int) -> WorkItem:
    """Fetch a work item from Azure DevOps and return a WorkItem instance."""
    pat = _get_pat()
    auth = _ado_auth_header(pat)

    org = os.environ.get("ADO_ORG", _DEFAULT_ADO_ORG)
    project = os.environ.get("ADO_PROJECT", _DEFAULT_ADO_PROJECT)

    url = (
        f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{pbi_id}"
        f"?$expand=all&api-version={_ADO_API_VERSION}"
    )

    result = subprocess.run(
        [
            "curl",
            "-s",
            "-H",
            f"Authorization: {auth}",
            "-H",
            "Content-Type: application/json",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON response from ADO: {e}") from e

    if "errorCode" in data or ("message" in data and "id" not in data):
        raise RuntimeError(f"ADO API error: {data.get('message', data)}")

    fields = data.get("fields", {})

    raw_description = fields.get("System.Description", "") or ""
    raw_ac = fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", "") or ""

    # Strip HTML tags from description and acceptance criteria
    description = _strip_html(raw_description)
    acceptance_criteria = _strip_html(raw_ac)

    raw_tags = fields.get("System.Tags", "") or ""
    tags = [t.strip() for t in raw_tags.split(";") if t.strip()]

    raw_parent = fields.get("System.Parent")

    return WorkItem(
        id=data["id"],
        title=fields.get("System.Title", f"PBI {pbi_id}"),
        description=description,
        acceptance_criteria=acceptance_criteria,
        tags=tags,
        area_path=fields.get("System.AreaPath", ""),
        state=fields.get("System.State", ""),
        assigned_to=fields.get("System.AssignedTo", {}).get("displayName", "")
        if isinstance(fields.get("System.AssignedTo"), dict)
        else str(fields.get("System.AssignedTo", "")),
        parent_id=int(raw_parent) if raw_parent else None,
        work_item_type=fields.get("System.WorkItemType", ""),
    )


def _strip_html(html: str) -> str:
    """Remove HTML tags, decode common entities, and normalise whitespace."""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def create_github_issue(work_item: WorkItem) -> str:
    """Create a GitHub issue from an ADO work item.

    For Tasks with a parent PBI, fetches the parent and includes its description
    and acceptance criteria so the issue contains full business context.
    Returns the GitHub issue URL.
    """
    repo = os.environ.get("ADO_BRIDGE_REPO", _DEFAULT_GH_REPO)
    org = os.environ.get("ADO_ORG", _DEFAULT_ADO_ORG)
    project = os.environ.get("ADO_PROJECT", _DEFAULT_ADO_PROJECT)

    ado_url = f"https://dev.azure.com/{org}/{project}/_workitems/edit/{work_item.id}"

    title = f"{work_item.title} (PBI #{work_item.id})"
    body = f"**Azure DevOps:** {ado_url}\n\n**State:** {work_item.state}\n**Area:** {work_item.area_path}"
    if work_item.work_item_type:
        body += f"\n**Type:** {work_item.work_item_type}"

    # For Tasks with a parent, fetch the parent and include its context
    parent: WorkItem | None = None
    if work_item.parent_id:
        parent_url = f"https://dev.azure.com/{org}/{project}/_workitems/edit/{work_item.parent_id}"
        body += f"\n**Parent PBI:** {parent_url}"
        try:
            parent = fetch_work_item(work_item.parent_id)
            logger.info("Fetched parent PBI #%s for context", work_item.parent_id)
        except Exception as exc:
            logger.warning(
                "Could not fetch parent PBI #%s: %s", work_item.parent_id, exc
            )

    if work_item.description:
        body += f"\n\n**Description:**\n{work_item.description}"
    if work_item.acceptance_criteria:
        body += f"\n\n**Acceptance Criteria:**\n{work_item.acceptance_criteria}"

    # Append parent description as business background only.
    # Isolation guarantee: only this Task's own fields (description, AC) and the
    # parent PBI's description are included. Parent AC is excluded because it
    # covers all child tasks and would mix context for other developers. Sibling
    # tasks are never fetched — no sibling data can appear in this issue body.
    if parent and parent.description and parent.description != work_item.description:
        body += f"\n\n---\n**Parent PBI — Background:**\n{parent.description}"

    result = subprocess.run(
        [
            "gh",
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            title,
            "--body",
            body,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh issue create failed: {result.stderr.strip()}")

    issue_url = result.stdout.strip()
    logger.info("Created GitHub issue for PBI #%s: %s", work_item.id, issue_url)
    return issue_url


# ---------------------------------------------------------------------------
# Target repo configuration
# ---------------------------------------------------------------------------

# Default: fivepoints-test (safe). Override: ADO_BRIDGE_REPO=claire-labs/fivepoints
_DEFAULT_GH_REPO = os.environ.get("ADO_BRIDGE_REPO", "claire-labs/fivepoints-test")


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


@dataclass
class TriageDecision:
    """Result of grouping emails by ADO work item ID and checking for existing issues."""

    pbi_id: str
    action: Literal["create", "skip"]
    emails: list[Any]  # email objects from list_unread_replies
    existing_issue_url: str | None = None  # populated when skip_reason == "duplicate"
    skip_reason: (
        Literal[
            "duplicate",
            "parent_has_children",
            "non_task_type",
            "terminal_state",
            "state_unknown",
        ]
        | None
    ) = None


@dataclass
class ProcessingResult:
    message_id: str
    email_subject: str
    pbi_id: str
    work_item: WorkItem | None = None
    github_issue_url: str | None = None
    error: str | None = None
    skipped: bool = False  # True when triage decided to skip this PBI
    skip_reason: (
        Literal[
            "duplicate",
            "parent_has_children",
            "non_task_type",
            "terminal_state",
            "state_unknown",
        ]
        | None
    ) = None

    @property
    def success(self) -> bool:
        return self.error is None and self.github_issue_url is not None


def fetch_work_item_metadata(pbi_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch work item type and parent ID for multiple work items in one API call.

    Uses the ADO batch endpoint to retrieve only ``System.WorkItemType`` and
    ``System.Parent`` — lightweight enough to run during triage without slowing
    the pipeline.

    Returns ``{pbi_id: {"type": str, "parent_id": str | None}}``.
    On any error, returns an empty dict so triage continues without hierarchy info.
    """
    if not pbi_ids:
        return {}

    pat = _get_pat()
    auth = _ado_auth_header(pat)
    org = os.environ.get("ADO_ORG", _DEFAULT_ADO_ORG)
    project = os.environ.get("ADO_PROJECT", _DEFAULT_ADO_PROJECT)

    ids_param = ",".join(pbi_ids)
    url = (
        f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems"
        f"?ids={ids_param}&fields=System.WorkItemType,System.Parent,System.State&api-version={_ADO_API_VERSION}"
    )

    result = subprocess.run(
        [
            "curl",
            "-s",
            "-H",
            f"Authorization: {auth}",
            "-H",
            "Content-Type: application/json",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        logger.warning("fetch_work_item_metadata failed: %s", result.stderr.strip())
        return {}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.warning(
            "fetch_work_item_metadata: failed to JSON-decode ADO response (%s) — raw: %r",
            exc,
            result.stdout[:500],
        )
        return {}

    metadata: dict[str, dict[str, Any]] = {}
    for item in data.get("value", []):
        item_id = str(item.get("id", ""))
        if not item_id:
            continue
        fields = item.get("fields", {})
        raw_parent = fields.get("System.Parent")
        metadata[item_id] = {
            "type": fields.get("System.WorkItemType", ""),
            "parent_id": str(raw_parent) if raw_parent else None,
            "state": fields.get("System.State", ""),
        }

    return metadata


def fetch_ado_child_ids(pbi_id: str) -> list[str]:
    """Return ADO IDs of direct children (Hierarchy-Forward relations) of a work item.

    Used during triage: if a non-Task work item has any ADO children, it is always
    skipped — the Task is the canonical GitHub issue. This covers both orderings:
    parent email arrives before or after its children are processed.

    Returns an empty list on API error so triage continues without blocking.
    """
    pat = _get_pat()
    auth = _ado_auth_header(pat)
    org = os.environ.get("ADO_ORG", _DEFAULT_ADO_ORG)
    project = os.environ.get("ADO_PROJECT", _DEFAULT_ADO_PROJECT)

    url = (
        f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{pbi_id}"
        f"?$expand=relations&api-version={_ADO_API_VERSION}"
    )

    result = subprocess.run(
        [
            "curl",
            "-s",
            "-H",
            f"Authorization: {auth}",
            "-H",
            "Content-Type: application/json",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        logger.warning(
            "fetch_ado_child_ids failed for #%s: %s", pbi_id, result.stderr.strip()
        )
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    child_ids = []
    for relation in data.get("relations", []):
        if relation.get("rel") == "System.LinkTypes.Hierarchy-Forward":
            rel_url = relation.get("url", "")
            m = re.search(r"/workitems/(\d+)$", rel_url)
            if m:
                child_ids.append(m.group(1))

    return child_ids


def find_existing_github_issue(pbi_id: str) -> str | None:
    """Return the URL of an existing open GitHub issue for this ADO work item, or None.

    Searches the target repo for open issues whose title contains ``PBI #{pbi_id}``.
    Only open issues are checked (``gh issue list`` default). A closed issue for
    PBI #N does not prevent re-creation: closed = done, re-assignment = new work.
    """
    repo = os.environ.get("ADO_BRIDGE_REPO", _DEFAULT_GH_REPO)
    search_query = f"PBI #{pbi_id}"

    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--search",
            search_query,
            "--json",
            "url,title",
            "--limit",
            "10",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        logger.warning(
            "gh issue list failed while checking for PBI #%s: %s",
            pbi_id,
            result.stderr.strip(),
        )
        return None

    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    for issue in issues:
        if f"PBI #{pbi_id}" in issue.get("title", ""):
            return issue["url"]

    return None


def triage_emails(emails: list[Any]) -> list[TriageDecision]:
    """Group emails by ADO work item ID and decide create vs. skip for each.

    Groups all pending emails by PBI ID extracted from the subject.
    Applies three skip rules (in priority order):

    1. **Terminal state** — if the ADO work item state is Done, Closed, Removed,
       or Resolved, skip it. The work is already complete; no GitHub issue needed.

    2. **Parent has children** — if a non-Task work item has any ADO children,
       skip it. The Task is always the canonical GitHub issue. Two detection modes:
       - Same-batch: a child is also in the current batch (batch metadata call)
       - Any children in ADO: fetching Hierarchy-Forward relations; if any exist,
         parent is skipped regardless of whether children are already processed

    3. **Duplicate** — the work item already has an open GitHub issue.

    Returns one TriageDecision per unique PBI ID.
    Emails that cannot be mapped to a PBI ID are logged and dropped.
    """
    # Group emails by PBI ID
    groups: dict[str, list[Any]] = {}
    for email in emails:
        pbi_id = parse_pbi_id(email.subject)
        if pbi_id:
            groups.setdefault(pbi_id, []).append(email)
        else:
            logger.warning(
                "Could not parse PBI ID from subject: %r — skipping", email.subject
            )

    if not groups:
        return []

    # Fetch work item type + parent for all IDs in one batch call
    metadata = fetch_work_item_metadata(list(groups.keys()))

    # Identify parent IDs that have at least one child also in the batch.
    # These parents are skipped: children carry all necessary context.
    parents_with_children_in_batch: set[str] = {
        meta["parent_id"]
        for meta in metadata.values()
        if meta.get("parent_id") and meta["parent_id"] in groups
    }

    if parents_with_children_in_batch:
        logger.info(
            "Parent work items skipped (children present in batch): %s",
            ", ".join(f"#{p}" for p in sorted(parents_with_children_in_batch)),
        )

    decisions: list[TriageDecision] = []
    for pbi_id, group_emails in groups.items():
        if len(group_emails) > 1:
            logger.info(
                "PBI #%s: %d email(s) grouped (deduped to 1 work item)",
                pbi_id,
                len(group_emails),
            )

        skipped = False

        # Rule 0: skip work items whose state is terminal or cannot be determined.
        #
        # Fail-safe policy: we only create a GitHub issue when we KNOW the work item
        # is in an active state. Any ambiguity → skip:
        #   - pbi_id absent from metadata → API call failed entirely → state_unknown
        #   - state field empty or None  → state not returned by API → state_unknown
        #   - state.lower() in _TERMINAL_STATES → completed work → terminal_state
        #   - state not in _ACTIVE_STATES → unrecognised value → state_unknown
        if pbi_id not in metadata:
            logger.warning(
                "PBI #%s — state unknown: metadata not returned by ADO API "
                "(see prior warnings for fetch error), skipping",
                pbi_id,
            )
            decisions.append(
                TriageDecision(
                    pbi_id=pbi_id,
                    action="skip",
                    emails=group_emails,
                    skip_reason="state_unknown",
                )
            )
            skipped = True
        else:
            ado_state: str = metadata[pbi_id].get("state") or ""
            if not ado_state:
                logger.warning(
                    "PBI #%s — state field empty (state=%r, metadata=%s), skipping",
                    pbi_id,
                    ado_state,
                    metadata[pbi_id],
                )
                decisions.append(
                    TriageDecision(
                        pbi_id=pbi_id,
                        action="skip",
                        emails=group_emails,
                        skip_reason="state_unknown",
                    )
                )
                skipped = True
            elif ado_state.lower() in _TERMINAL_STATES:
                logger.info("Skipping PBI #%s — state: %s", pbi_id, ado_state)
                decisions.append(
                    TriageDecision(
                        pbi_id=pbi_id,
                        action="skip",
                        emails=group_emails,
                        skip_reason="terminal_state",
                    )
                )
                skipped = True
            elif ado_state.lower() not in _ACTIVE_STATES:
                logger.warning(
                    "PBI #%s — unexpected state %r (not a known active state), skipping",
                    pbi_id,
                    ado_state,
                )
                decisions.append(
                    TriageDecision(
                        pbi_id=pbi_id,
                        action="skip",
                        emails=group_emails,
                        skip_reason="state_unknown",
                    )
                )
                skipped = True

        # Rule 1a: skip parents whose children are also in this batch
        if not skipped and pbi_id in parents_with_children_in_batch:
            logger.info(
                "PBI #%s: skipped — parent of child(ren) in batch", pbi_id
            )
            decisions.append(
                TriageDecision(
                    pbi_id=pbi_id,
                    action="skip",
                    emails=group_emails,
                    skip_reason="parent_has_children",
                )
            )
            skipped = True

        # Rule 1b: Unconditional type gate — only Tasks create GitHub issues.
        # Any work item whose type is not "Task" (PBI, Feature, User Story, Bug, etc.)
        # is rejected immediately, without fetching ADO children. A non-Task item must
        # never become a GitHub issue, regardless of whether it has children in ADO.
        if not skipped:
            pbi_type = metadata.get(pbi_id, {}).get("type", "")
            if (
                pbi_type.lower() != "task"
            ):  # empty string != "task" → skipped (fail-safe)
                logger.info(
                    "PBI #%s: skipped — type is %r (only Tasks create GitHub issues)",
                    pbi_id,
                    pbi_type,
                )
                decisions.append(
                    TriageDecision(
                        pbi_id=pbi_id,
                        action="skip",
                        emails=group_emails,
                        skip_reason="non_task_type",
                    )
                )
                skipped = True

        # Rule 2: skip if an open GitHub issue already exists for this work item
        if not skipped:
            existing_url = find_existing_github_issue(pbi_id)
            if existing_url:
                logger.info(
                    "PBI #%s already has GitHub issue %s — skip", pbi_id, existing_url
                )
                decisions.append(
                    TriageDecision(
                        pbi_id=pbi_id,
                        action="skip",
                        emails=group_emails,
                        existing_issue_url=existing_url,
                        skip_reason="duplicate",
                    )
                )
                skipped = True

        if not skipped:
            decisions.append(
                TriageDecision(
                    pbi_id=pbi_id,
                    action="create",
                    emails=group_emails,
                )
            )

    return decisions


def process_emails(
    max_results: int = 20,
    dry_run: bool = False,
    max_process: int | None = None,
    lookback_days: int | None = None,
) -> list[ProcessingResult]:
    """Scan Gmail inbox for ADO assignment emails and process each one.

    Includes a triage phase that groups emails by ADO work item ID and skips
    PBIs that already have a GitHub issue — preventing duplicate issues when
    multiple notifications arrive for the same work item.

    Args:
        max_results: Max emails to fetch from Gmail inbox (scan window).
        dry_run: If True, log what would be created without touching GitHub or archiving.
        max_process: If set, limit the number of new work items created.
        lookback_days: If set, only scan emails from the last N days (Gmail newer_than filter).

    Returns a list of ProcessingResult for each unique ADO work item found.
    """
    from claire_py.email.watcher import list_unread_replies

    processed_ids = load_processed_ids()
    results: list[ProcessingResult] = []

    logger.info("Scanning Gmail inbox for ADO assignment emails...")
    emails = list_unread_replies(
        sender_filter=_ADO_SENDER,
        subject_filter=None,  # pre-filtered by sender; secondary regex handles type matching
        max_results=max_results,
        unread_only=False,
        lookback_days=lookback_days,
    )

    # Secondary filter: subject pattern + dedup guard (email-level)
    candidates = [
        e
        for e in emails
        if e.message_id not in processed_ids and is_ado_assignment_email(e.subject)
    ]

    logger.info("Found %d new ADO assignment email(s).", len(candidates))

    if not candidates:
        save_state(
            {
                "last_run": datetime.now().isoformat(),
                "emails_scanned": len(emails),
                "emails_processed": 0,
                "successes": 0,
                "skipped_duplicate": 0,
                "skipped_parent": 0,
                "skipped_terminal": 0,
                "skipped_state_unknown": 0,
                "failures": 0,
            }
        )
        return results

    # TRIAGE PHASE: group by PBI ID, check for existing GitHub issues
    logger.info("Triaging %d email(s) by ADO work item ID...", len(candidates))
    triage_decisions = triage_emails(candidates)

    to_create = [d for d in triage_decisions if d.action == "create"]
    to_skip = [d for d in triage_decisions if d.action == "skip"]

    logger.info(
        "Triage result: %d to create, %d to skip (already have GitHub issues)",
        len(to_create),
        len(to_skip),
    )

    # Handle skipped PBIs — mark all their emails as processed
    for decision in to_skip:
        result = ProcessingResult(
            message_id=decision.emails[0].message_id,
            email_subject=decision.emails[0].subject,
            pbi_id=decision.pbi_id,
            github_issue_url=decision.existing_issue_url,
            skipped=True,
            skip_reason=decision.skip_reason,
        )
        if not dry_run:
            for email in decision.emails:
                save_processed_id(email.message_id)
                archive_email(email.message_id)
        results.append(result)

    # Apply max_process cap to create decisions only
    if max_process is not None:
        to_create = to_create[:max_process]

    # Handle create decisions
    for decision in to_create:
        pbi_id = decision.pbi_id
        representative_email = decision.emails[0]

        result = ProcessingResult(
            message_id=representative_email.message_id,
            email_subject=representative_email.subject,
            pbi_id=pbi_id,
        )

        try:
            logger.info(
                "Processing PBI #%s (%d email(s))", pbi_id, len(decision.emails)
            )

            # Step 1: Fetch work item from ADO
            work_item = fetch_work_item(pbi_id)
            result.work_item = work_item
            logger.info("Fetched PBI #%s: %s", pbi_id, work_item.title)

            if dry_run:
                title = f"{work_item.title} (PBI #{work_item.id})"
                logger.info("[dry-run] Would create issue: %s", title)
                result.github_issue_url = "(dry-run)"
            else:
                # Step 2: Pre-creation duplicate guard — re-check GitHub right before
                # creating the issue. Triage already checked, but a concurrent bridge
                # run (daemon + manual) could have created the issue in the meantime.
                existing_url = find_existing_github_issue(pbi_id)
                if existing_url:
                    logger.info(
                        "PBI #%s — issue already exists at %s (created by concurrent run) — skipping",
                        pbi_id,
                        existing_url,
                    )
                    result.skipped = True
                    result.skip_reason = "duplicate"
                    result.github_issue_url = existing_url
                    for email in decision.emails:
                        save_processed_id(email.message_id)
                        archive_email(email.message_id)
                else:
                    # Step 3: Create GitHub issue
                    issue_url = create_github_issue(work_item)
                    result.github_issue_url = issue_url

                    # Mark ALL emails for this PBI as processed and archive them
                    for email in decision.emails:
                        save_processed_id(email.message_id)
                        archive_email(email.message_id)

        except Exception as exc:
            result.error = str(exc)
            logger.error("Failed to process PBI #%s: %s", pbi_id, exc)

        results.append(result)

    # Persist last run state
    save_state(
        {
            "last_run": datetime.now().isoformat(),
            "emails_scanned": len(emails),
            "emails_processed": len(results),
            "successes": sum(1 for r in results if r.success and not r.skipped),
            "skipped_duplicate": sum(
                1 for r in results if r.skipped and r.skip_reason == "duplicate"
            ),
            "skipped_parent": sum(
                1
                for r in results
                if r.skipped
                and r.skip_reason in ("parent_has_children", "non_task_type")
            ),
            "skipped_terminal": sum(
                1 for r in results if r.skipped and r.skip_reason == "terminal_state"
            ),
            "skipped_state_unknown": sum(
                1 for r in results if r.skipped and r.skip_reason == "state_unknown"
            ),
            "failures": sum(1 for r in results if not r.success and not r.skipped),
        }
    )

    return results
