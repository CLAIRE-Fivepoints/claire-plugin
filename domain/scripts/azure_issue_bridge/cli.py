"""
azure_issue_bridge.cli — Command-line interface.

Subcommands:
  run     One-shot: scan inbox and process any pending ADO assignment emails
  start   Polling loop: run repeatedly on a configurable interval
  status  Show the last run state
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azure_issue_bridge.bridge import ProcessingResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

# Business hours window: only poll during these hours (local time)
_HOUR_START = int(os.environ.get("ADO_BRIDGE_HOUR_START", "8"))
_HOUR_END = int(os.environ.get("ADO_BRIDGE_HOUR_END", "17"))


def _is_business_hours() -> bool:
    """Return True if the current local hour is within the polling window."""
    hour = datetime.datetime.now().hour
    return _HOUR_START <= hour < _HOUR_END


def _print_skipped(r: ProcessingResult) -> None:
    """Print a consistent skip line based on the skip_reason."""
    if r.skip_reason in ("parent_has_children", "non_task_type"):
        print(f"~ PBI #{r.pbi_id}: parent — children will create issues")
    else:
        print(f"~ PBI #{r.pbi_id}: already has GitHub issue — skipped")
        if r.github_issue_url:
            print(f"  → {r.github_issue_url}")


def _parse_lookback(value: str) -> int:
    """Parse a lookback string like '30d' or '7d' and return the number of days.

    Accepts bare integers ('30') or day-suffixed strings ('30d').
    Raises argparse.ArgumentTypeError on invalid input.
    """
    s = value.strip().lower().rstrip("d")
    try:
        days = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid --lookback value {value!r}: expected a number of days (e.g. '30d' or '30')"
        ) from None
    if days <= 0:
        raise argparse.ArgumentTypeError(
            f"Invalid --lookback value {value!r}: must be a positive number of days"
        )
    return days


def cmd_run(args: argparse.Namespace) -> int:
    from azure_issue_bridge.bridge import process_emails

    lookback_days = _parse_lookback(args.lookback) if args.lookback else None
    results = process_emails(
        max_results=args.max_results,
        dry_run=args.dry_run,
        lookback_days=lookback_days,
    )

    if not results:
        print("No new ADO assignment emails found.")
        return 0

    for r in results:
        if r.skipped:
            _print_skipped(r)
        elif r.success:
            print(f"✓ PBI #{r.pbi_id}: {r.work_item.title if r.work_item else ''}")
            print(f"  → {r.github_issue_url}")
        else:
            print(f"✗ PBI #{r.pbi_id}: {r.error}")

    failures = [r for r in results if not r.success and not r.skipped]
    return 1 if failures else 0


def cmd_start(args: argparse.Namespace) -> int:
    """Polling loop — run every `interval` minutes."""
    from azure_issue_bridge.bridge import process_emails

    interval_seconds = args.interval * 60
    lookback_days = _parse_lookback(args.lookback) if args.lookback else None

    print(f"Starting azure-issue-bridge polling loop (interval: {args.interval}m)")
    print("Press Ctrl+C to stop.\n")

    print(f"Business hours: {_HOUR_START:02d}:00 - {_HOUR_END:02d}:00 local time\n")

    while True:
        try:
            if not _is_business_hours():
                logger.info(
                    "Outside business hours (%02d:00-%02d:00). Skipping poll. Next check in %dm.",
                    _HOUR_START,
                    _HOUR_END,
                    args.interval,
                )
                time.sleep(interval_seconds)
                continue

            logger.info("--- Polling inbox ---")
            results = process_emails(
                max_results=args.max_results,
                dry_run=args.dry_run,
                lookback_days=lookback_days,
            )

            if results:
                for r in results:
                    if r.skipped:
                        _print_skipped(r)
                    elif r.success:
                        print(f"✓ PBI #{r.pbi_id} → {r.github_issue_url}")
                    else:
                        print(f"✗ PBI #{r.pbi_id}: {r.error}")
            else:
                logger.info("No new emails. Next poll in %dm.", args.interval)

            time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print("\nStopped.")
            return 0
        except Exception as exc:
            logger.error("Unexpected error: %s", exc)
            logger.info("Retrying in %dm...", args.interval)
            time.sleep(interval_seconds)


def cmd_test(args: argparse.Namespace) -> int:
    """Test run: reset processed IDs, process 1 PBI, close created issue."""
    from azure_issue_bridge.bridge import (
        PROCESSED_FILE,
        process_emails,
    )

    # Reset dedup state so already-processed emails are retried
    if PROCESSED_FILE.exists():
        PROCESSED_FILE.write_text("[]")
        print("✓ Reset processed.json")

    print(f"Running pipeline (max {args.max_results} PBI)...\n")
    # Scan up to 50 inbox emails but process at most max_results work items
    results = process_emails(
        max_results=50, dry_run=args.dry_run, max_process=args.max_results
    )

    if not results:
        print(
            "✗ No ADO assignment emails found — check Gmail auth and AZURE_DEVOPS_PAT."
        )
        return 1

    for r in results:
        if r.skipped:
            _print_skipped(r)
        elif r.success:
            print(f"✓ PBI #{r.pbi_id}: {r.work_item.title if r.work_item else ''}")
            print(f"  → {r.github_issue_url}")
        else:
            print(f"✗ PBI #{r.pbi_id}: {r.error}")

    failures = [r for r in results if not r.success and not r.skipped]
    return 1 if failures else 0


def cmd_restore_inbox(_args: argparse.Namespace) -> int:
    """Restore archived ADO assignment emails back to the Gmail inbox.

    Searches Gmail for Azure DevOps assignment emails that are no longer in the
    inbox (archived by a previous bridge run) and adds the INBOX label back.
    Also resets processed.json so those emails will be re-triaged on the next run.

    Use this to re-run the bridge from scratch on previously-processed emails.
    """
    from azure_issue_bridge.bridge import PROCESSED_FILE
    from claire_py.email.auth import get_credentials

    try:
        from googleapiclient import discovery
    except ImportError:
        print(
            "✗ google-api-python-client not installed — run: pip install google-api-python-client"
        )
        return 1

    creds = get_credentials()
    if not creds:
        print("✗ Gmail not configured. Run: claire email auth")
        return 1

    service = discovery.build("gmail", "v1", credentials=creds)

    results = (
        service.users()
        .messages()
        .list(
            userId="me",
            q="from:azuredevops@microsoft.com -in:inbox",
            maxResults=100,
        )
        .execute()
    )

    messages = results.get("messages", [])
    if len(messages) == 100:
        logger.warning(
            "restore-inbox: retrieved maximum 100 emails — there may be more archived ADO "
            "emails not restored. Run again if needed."
        )
    if not messages:
        print("No archived ADO emails found.")
    else:
        restored = 0
        for msg in messages:
            detail = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["Subject"],
                )
                .execute()
            )
            subject = next(
                (
                    h["value"]
                    for h in detail.get("payload", {}).get("headers", [])
                    if h["name"] == "Subject"
                ),
                "",
            )
            if any(
                kw in subject
                for kw in [
                    "Product Backlog Item",
                    "Task",
                    "Bug",
                    "Feature",
                    "User Story",
                ]
            ):
                service.users().messages().modify(
                    userId="me",
                    id=msg["id"],
                    body={"addLabelIds": ["INBOX"]},
                ).execute()
                print(f"✓ Restored: {subject}")
                restored += 1

        print(f"\nRestored {restored} email(s) to inbox")

    # Reset processed.json so restored emails are re-triaged
    if PROCESSED_FILE.exists():
        PROCESSED_FILE.write_text("[]")
        print("✓ Reset processed.json")

    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    from azure_issue_bridge.bridge import (
        STATE_FILE,
        load_processed_ids,
        load_state,
    )

    state = load_state()
    processed = load_processed_ids()

    if not state:
        print("No runs recorded yet. Run: claire azure-issue-bridge run")
        return 0

    print("Azure DevOps Email Bridge — Last Run Status")
    print("-------------------------------------------")
    print(f"Last run:         {state.get('last_run', 'unknown')}")
    print(f"Emails scanned:   {state.get('emails_scanned', 0)}")
    print(f"Emails processed: {state.get('emails_processed', 0)}")
    print(f"Issues created:   {state.get('successes', 0)}")
    print(f"Skipped (dedup):  {state.get('skipped_duplicate', 0)}")
    print(f"Skipped (parent): {state.get('skipped_parent', 0)}")
    print(f"Failures:         {state.get('failures', 0)}")
    print(f"Total processed:  {len(processed)} emails (all-time)")
    print(f"State file:       {STATE_FILE}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claire azure-issue-bridge",
        description="Watch Gmail for ADO PBI assignment emails → create GitHub issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run 'claire azure-issue-bridge --agent-help' for LLM-optimized help",
    )

    sub = parser.add_subparsers(dest="subcommand")

    # run
    run_p = sub.add_parser(
        "run", help="One-shot: scan inbox and process pending emails"
    )
    run_p.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Max number of inbox emails to scan (default: 20)",
    )
    run_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and format issues but do NOT spawn analyst session",
    )
    run_p.add_argument(
        "--lookback",
        default=None,
        metavar="DAYS",
        help="Limit email scan to the last N days (e.g. '30d' or '30'). No limit by default.",
    )

    # start
    start_p = sub.add_parser(
        "start", help="Polling loop (runs during business hours: 8AM-5PM local time)"
    )
    start_p.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Poll interval in minutes (default: 15)",
    )
    start_p.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Max inbox emails to scan per poll (default: 20)",
    )
    start_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and format issues but do NOT spawn analyst session",
    )
    start_p.add_argument(
        "--lookback",
        default=None,
        metavar="DAYS",
        help="Limit email scan to the last N days (e.g. '30d' or '30'). No limit by default.",
    )

    # test
    test_p = sub.add_parser(
        "test", help="Test run: reset processed IDs and process 1 PBI"
    )
    test_p.add_argument(
        "--max-results",
        type=int,
        default=1,
        help="Max PBIs to process (default: 1)",
    )
    test_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Format only, do NOT spawn analyst session",
    )

    # restore-inbox
    sub.add_parser(
        "restore-inbox",
        help="Restore archived ADO emails to Gmail inbox + reset processed.json",
    )

    # status
    sub.add_parser("status", help="Show last run state")

    return parser


def main() -> None:
    # Handle --agent-help before argparse (avoid subcommand requirement)
    if "--agent-help" in sys.argv:
        print(_AGENT_HELP)
        sys.exit(0)

    parser = build_parser()
    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "run": cmd_run,
        "start": cmd_start,
        "test": cmd_test,
        "restore-inbox": cmd_restore_inbox,
        "status": cmd_status,
    }

    fn = dispatch.get(args.subcommand)
    if fn is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(fn(args))


_AGENT_HELP = """\
# azure-issue-bridge: ADO PBI Assignment → GitHub Issue Pipeline

## Purpose
Polls Gmail for Azure DevOps assignment notification emails, groups them by
ADO work item ID, and creates one GitHub issue per unique work item.
Includes a triage phase that prevents duplicate issues when multiple
notifications arrive for the same PBI.

## Subcommands

### run — one-shot execution
  claire azure-issue-bridge run [--dry-run] [--max-results N] [--lookback DAYS]

  Scans inbox, triages pending emails, creates GitHub issues, exits.
  Use for manual runs or cron jobs.

  --dry-run         Fetch + format but do NOT create GitHub issues or archive emails
  --lookback DAYS   Limit scan to emails from the last N days (e.g. '30d' or '30').
                    Prevents the bridge from picking up very old archived emails.
                    No limit by default.

### start — continuous polling loop
  claire azure-issue-bridge start [--interval N] [--dry-run] [--lookback DAYS]

  Runs in foreground, polling inbox every N minutes (default: 15).
  Use for always-on daemon. Pair with a process manager or cron.

### restore-inbox — restore archived ADO emails for re-processing
  claire azure-issue-bridge restore-inbox

  Finds ADO assignment emails that were archived by a previous bridge run and
  restores the INBOX label so they appear in the inbox again. Also resets
  processed.json. Use before a test run to re-process previously-handled emails.

### status — show last run
  claire azure-issue-bridge status

  Prints last run timestamp, issue counts (created / skipped / failed),
  and processed email registry location.

## Email Filter
- Sender: azuredevops@microsoft.com
- Subject: must match "Product Backlog Item {ID}" or similar ADO work item patterns

## Pipeline
  Gmail inbox
    → filter ADO assignment emails (not yet processed)
    → TRIAGE: group emails by ADO work item ID (see Triage Phase below)
    → fetch work item from ADO REST API (create decisions only)
    → create GitHub issue via gh CLI
        - body includes: Task description, Task AC, Parent PBI link + background description
        - parent description fetched from ADO when parent_id present (not parent AC —
          parent AC covers all child tasks and would mix sibling developer context)
    → archive all emails for this PBI in Gmail (remove INBOX label)
    → persist email IDs to ~/.claire/azure-issue-bridge/processed.json

## Triage Phase
The triage step groups emails by work item ID and applies two skip rules (in priority order):

  1. **Parent has children** — if a non-Task work item has any ADO children, skip it.
     The Task is always the canonical GitHub issue (one issue per piece of work).
     - Same-batch: a child is also in the current batch (ADO batch metadata call)
     - Any batch: ADO Hierarchy-Forward relations fetched for all non-Task items;
       if any children exist, the parent is skipped regardless of processing order

  2. **Duplicate** — the work item already has an open GitHub issue.
     (Only open issues are checked: closed = done, re-assignment = new work.)

Output symbols:
  ✓  Issue created
  ~  Skipped (parent — children will create issues)
  ~  Skipped (duplicate — existing issue found)
  ✗  Error

## Required Credentials
  AZURE_DEVOPS_PAT    — ADO REST API auth (read from env or ~/.config/claire/.env)
  Gmail OAuth2        — configured via: claire email auth

## State Files
  ~/.claire/azure-issue-bridge/state.json     — last run metadata
    Keys: successes, skipped_duplicate, skipped_parent, failures
  ~/.claire/azure-issue-bridge/processed.json — processed email IDs (dedup)

## Cron Setup (every 15 min)
  claire cron enable azure-issue-bridge

  Add to ~/.config/claire/cron_jobs.yaml:
  jobs:
    - name: azure-issue-bridge
      schedule: "*/15 * * * *"
      command: "claire azure-issue-bridge run"
      log_file: "~/.claire/logs/azure-issue-bridge.log"
      description: "Watch ADO assignment emails and create GitHub issues"

## Environment Variables
  AZURE_DEVOPS_PAT    Azure DevOps PAT (read from env or ~/.config/claire/.env)
  ADO_ORG             Azure DevOps org (default: FivePointsTechnology)
  ADO_PROJECT         Azure DevOps project (default: TFIOne)
  ADO_BRIDGE_REPO     Target GitHub repo (default: claire-labs/fivepoints-test)
                      Set to claire-labs/fivepoints to go live
"""


if __name__ == "__main__":
    main()
