"""
reset_pbi — Per-PBI factory reset for the fivepoints pipeline.

Purpose:
    Reset a single PBI + its linked GitHub issue to a clean state so a fresh
    agent session can replay the full analyst -> dev -> tester flow from zero.
    Used to validate pipeline fixes (e.g. issues #27, #29, #30).

Scope (Python portion — HTTP + JSON only, no subprocess):
    * Verify the GitHub issue title references the given --pbi id
    * Refuse to proceed if the linked PR is already merged
    * Delete agent-authored comments on the issue
    * Reset labels to [role:analyst] (removing any other role:* labels)
    * Reopen the issue if closed
    * Remove the issue from the github-manager state JSON
    * Delete release assets whose name references the issue/PBI

Git operations (branch / worktree delete) are executed by the bash
orchestrator (domain/commands/reset-pbi.sh) — see DEV_RULES #2.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Authors whose comments are considered agent-authored and will be deleted.
AGENT_LOGINS = frozenset(
    {
        "claire-test-ai",
        "claire-plugin-gatekeeper-ai",
        "myclaire-ai",
        "claire-gatekeeper-ai",
    }
)

PBI_TITLE_RE = re.compile(r"PBI\s*#\s*(\d+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Plan representation
# ---------------------------------------------------------------------------


@dataclass
class Action:
    """One entry in the reset plan. ``kind`` names the bucket; ``describe`` is
    the one-line preview used by dry-run and the log file."""

    kind: str
    describe: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    actions: list[Action] = field(default_factory=list)

    def add(self, kind: str, describe: str, **payload: Any) -> None:
        self.actions.append(Action(kind=kind, describe=describe, payload=payload))

    def render(self) -> str:
        if not self.actions:
            return "  (no actions)"
        return "\n".join(f"  [{a.kind}] {a.describe}" for a in self.actions)


# ---------------------------------------------------------------------------
# Guardrail / validation helpers (pure logic, unit-tested)
# ---------------------------------------------------------------------------


def parse_pbi_from_title(title: str) -> str | None:
    """Return the PBI id referenced in an issue title, or None."""
    m = PBI_TITLE_RE.search(title or "")
    return m.group(1) if m else None


def verify_pbi_matches_issue(
    pbi_id: str, issue_title: str
) -> tuple[bool, str | None]:
    """Confirm the issue title references ``pbi_id``.

    Returns (True, None) on match. On mismatch returns (False, detected_pbi)
    where detected_pbi is what the title actually references (or None if the
    title has no PBI reference at all).
    """
    detected = parse_pbi_from_title(issue_title)
    if detected is None:
        return False, None
    return detected == str(pbi_id), detected


def check_pr_merged(pr_state: str | None, merged: bool) -> bool:
    """Return True if the PR blocks the reset (merged already)."""
    if merged:
        return True
    # gh reports state "MERGED" alongside merged=true, but guard both.
    return (pr_state or "").upper() == "MERGED"


def is_agent_comment(author_login: str) -> bool:
    return author_login in AGENT_LOGINS


# ---------------------------------------------------------------------------
# GitHub REST client (urllib-based — no requests, no subprocess)
# ---------------------------------------------------------------------------


class GitHubClient:
    """Minimal authenticated GitHub REST client."""

    def __init__(self, token: str, repo: str, *, base_url: str = "https://api.github.com"):
        if not token:
            raise ValueError("GitHub token is required")
        if "/" not in repo:
            raise ValueError(f"repo must be 'owner/name', got {repo!r}")
        self._token = token
        self._repo = repo
        self._base_url = base_url.rstrip("/")

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            raw = resp.read()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.decode(errors="replace")

    # ---- issue comments ----
    def list_issue_comments(self, issue_number: int) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            path = (
                f"/repos/{self._repo}/issues/{issue_number}/comments"
                f"?per_page=100&page={page}"
            )
            batch = self._request("GET", path) or []
            if not batch:
                break
            comments.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return comments

    def delete_issue_comment(self, comment_id: int) -> None:
        self._request("DELETE", f"/repos/{self._repo}/issues/comments/{comment_id}")

    # ---- issues ----
    def set_issue_labels(self, issue_number: int, labels: list[str]) -> None:
        self._request(
            "PUT",
            f"/repos/{self._repo}/issues/{issue_number}/labels",
            {"labels": labels},
        )

    def reopen_issue(self, issue_number: int) -> None:
        self._request(
            "PATCH",
            f"/repos/{self._repo}/issues/{issue_number}",
            {"state": "open"},
        )

    # ---- releases ----
    def delete_release_asset(self, asset_id: int) -> None:
        self._request(
            "DELETE", f"/repos/{self._repo}/releases/assets/{asset_id}"
        )


# ---------------------------------------------------------------------------
# Plan building
# ---------------------------------------------------------------------------


@dataclass
class Context:
    pbi_id: str
    issue_number: int
    repo: str
    issue_title: str
    issue_state: str
    issue_labels: list[str]
    pr_number: int | None
    pr_state: str | None
    pr_merged: bool
    comments: list[dict[str, Any]]
    release_assets: list[dict[str, Any]]  # each: {id, name, release_tag}
    state_file: Path
    state_has_issue: bool


def build_plan(ctx: Context) -> Plan:
    """Compute the ordered list of reset actions for ``ctx``."""
    plan = Plan()

    # 1. Comments (agent-authored only)
    agent_comments = [c for c in ctx.comments if is_agent_comment(c["user"]["login"])]
    for c in agent_comments:
        preview = (c.get("body") or "").splitlines()[0][:60]
        plan.add(
            "gh:comment",
            f"delete comment #{c['id']} by {c['user']['login']}: {preview!r}",
            comment_id=c["id"],
        )

    # 2. Labels — reset to exactly [role:analyst]
    current = sorted(ctx.issue_labels)
    desired = ["role:analyst"]
    if current != desired:
        plan.add(
            "gh:labels",
            f"set labels {current} -> {desired}",
            labels=desired,
        )

    # 3. Reopen if closed
    if (ctx.issue_state or "").upper() == "CLOSED":
        plan.add("gh:reopen", f"reopen issue #{ctx.issue_number}")

    # 4. Release assets
    for a in ctx.release_assets:
        plan.add(
            "gh:asset",
            f"delete release asset '{a['name']}' from {a.get('release_tag', '?')}",
            asset_id=a["id"],
        )

    # 5. Claire github-manager state
    if ctx.state_has_issue:
        plan.add(
            "state:purge",
            f"remove issue #{ctx.issue_number} from {ctx.state_file}",
        )

    return plan


# ---------------------------------------------------------------------------
# State-file mutation
# ---------------------------------------------------------------------------


def purge_state(state_file: Path, issue_number: int) -> bool:
    """Remove ``issue_number`` from the github-manager state JSON.

    Returns True if a change was written, False if the issue was not present.
    """
    if not state_file.exists():
        logger.warning("state file does not exist: %s", state_file)
        return False
    with open(state_file) as f:
        data = json.load(f)
    changed = False
    key = str(issue_number)
    processed = data.get("processed_issues", {})
    if key in processed:
        processed.pop(key)
        changed = True
    assignees = data.get("issue_assignees", {})
    if key in assignees:
        assignees.pop(key)
        changed = True
    if changed:
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(state_file, "w") as f:
            json.dump(data, f, indent=2)
    return changed


def state_contains_issue(state_file: Path, issue_number: int) -> bool:
    if not state_file.exists():
        return False
    try:
        with open(state_file) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("could not read state file %s: %s", state_file, exc)
        return False
    key = str(issue_number)
    return key in data.get("processed_issues", {}) or key in data.get(
        "issue_assignees", {}
    )


# ---------------------------------------------------------------------------
# Plan execution
# ---------------------------------------------------------------------------


def execute_plan(plan: Plan, client: GitHubClient, ctx: Context) -> list[str]:
    """Execute every action in ``plan``. Returns per-action result strings."""
    results: list[str] = []
    for action in plan.actions:
        try:
            if action.kind == "gh:comment":
                client.delete_issue_comment(action.payload["comment_id"])
            elif action.kind == "gh:labels":
                client.set_issue_labels(
                    ctx.issue_number, action.payload["labels"]
                )
            elif action.kind == "gh:reopen":
                client.reopen_issue(ctx.issue_number)
            elif action.kind == "gh:asset":
                client.delete_release_asset(action.payload["asset_id"])
            elif action.kind == "state:purge":
                purge_state(ctx.state_file, ctx.issue_number)
            else:
                logger.warning("unknown action kind: %s", action.kind)
                results.append(f"SKIP {action.kind}: unknown kind")
                continue
            results.append(f"OK   [{action.kind}] {action.describe}")
        except urllib.error.HTTPError as e:
            results.append(
                f"FAIL [{action.kind}] {action.describe}: HTTP {e.code} {e.reason}"
            )
            logger.warning("action failed: %s — HTTP %s", action.describe, e.code)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            results.append(
                f"FAIL [{action.kind}] {action.describe}: {type(e).__name__}: {e}"
            )
            logger.warning("action failed: %s — %s", action.describe, e)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_json_arg(value: str | None, label: str) -> Any:
    """Load JSON from ``value`` (either a literal or a path prefixed with @)."""
    if value is None:
        return None
    if value.startswith("@"):
        path = Path(value[1:])
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise SystemExit(f"could not read {label} JSON from {path}: {e}")
    if value.strip() == "":
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise SystemExit(f"invalid {label} JSON: {e}")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reset_pbi",
        description=(
            "Factory reset a PBI's GitHub issue + state so the pipeline can "
            "replay from zero. Called by domain/commands/reset-pbi.sh."
        ),
    )
    p.add_argument("--pbi", required=True, help="ADO PBI id (numeric)")
    p.add_argument(
        "--issue", required=True, type=int, help="GitHub issue number"
    )
    p.add_argument(
        "--repo", required=True, help="GitHub repo in owner/name form"
    )
    p.add_argument(
        "--state-file",
        required=True,
        type=Path,
        help="Path to github_manager_state_<owner>_<repo>.json",
    )
    p.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Path to the reset log file (written to)",
    )
    p.add_argument(
        "--issue-json",
        required=True,
        help='JSON blob or @path with {title,state,labels[]} for the issue',
    )
    p.add_argument(
        "--pr-json",
        default=None,
        help='JSON blob or @path with {number,state,merged} for the linked PR',
    )
    p.add_argument(
        "--comments-json",
        default=None,
        help="JSON blob or @path — if provided, skip the API fetch of comments",
    )
    p.add_argument(
        "--releases-json",
        default=None,
        help=(
            "JSON blob or @path — list of {id,name,release_tag} release assets "
            "pre-filtered by issue number"
        ),
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print plan and exit")
    mode.add_argument(
        "--confirm",
        action="store_true",
        help="Execute plan (destructive). Required for any real mutation.",
    )
    p.add_argument(
        "--keep-db",
        action="store_true",
        help="Reserved for future use — no-op today (state file is untouched by --keep-db)",
    )
    return p


def _write_log(log_file: Path, lines: list[str]) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a") as f:
        for line in lines:
            f.write(line + "\n")


def _collect_context(args: argparse.Namespace, client: GitHubClient) -> Context:
    issue = _load_json_arg(args.issue_json, "issue-json") or {}
    pr = _load_json_arg(args.pr_json, "pr-json")
    comments_payload = _load_json_arg(args.comments_json, "comments-json")
    releases_payload = _load_json_arg(args.releases_json, "releases-json") or []

    # If comments weren't pre-supplied, fetch via API.
    if comments_payload is None:
        comments = client.list_issue_comments(args.issue)
    else:
        comments = comments_payload

    pr_number: int | None = None
    pr_state: str | None = None
    pr_merged = False
    if pr:
        pr_number = pr.get("number")
        pr_state = pr.get("state")
        pr_merged = bool(pr.get("merged", False))

    state_file: Path = args.state_file
    state_has_issue = state_contains_issue(state_file, args.issue)

    return Context(
        pbi_id=str(args.pbi),
        issue_number=int(args.issue),
        repo=args.repo,
        issue_title=issue.get("title", ""),
        issue_state=issue.get("state", ""),
        issue_labels=[
            label["name"] if isinstance(label, dict) else str(label)
            for label in issue.get("labels", [])
        ],
        pr_number=pr_number,
        pr_state=pr_state,
        pr_merged=pr_merged,
        comments=comments,
        release_assets=releases_payload,
        state_file=state_file,
        state_has_issue=state_has_issue,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    args = _build_parser().parse_args(argv)

    log_lines: list[str] = [
        f"=== reset_pbi pbi={args.pbi} issue={args.issue} repo={args.repo} ==="
    ]

    # Guardrail 1: PBI must match issue title.
    issue_data = _load_json_arg(args.issue_json, "issue-json") or {}
    match, detected = verify_pbi_matches_issue(args.pbi, issue_data.get("title", ""))
    if not match:
        if detected is None:
            msg = (
                f"ERROR: issue #{args.issue} title does not reference any PBI — "
                f"got {issue_data.get('title', '')!r}"
            )
        else:
            msg = (
                f"ERROR: issue #{args.issue} is linked to PBI #{detected}, "
                f"not PBI #{args.pbi}"
            )
        print(msg, file=sys.stderr)
        if args.log_file:
            _write_log(args.log_file, log_lines + [msg])
        return 2

    # Guardrail 2: PR must not be merged.
    pr_data = _load_json_arg(args.pr_json, "pr-json") or {}
    if check_pr_merged(pr_data.get("state"), bool(pr_data.get("merged", False))):
        msg = (
            f"ERROR: PR #{pr_data.get('number')} on branch "
            f"{pr_data.get('headRefName', '<?>')} is already MERGED — refusing reset"
        )
        print(msg, file=sys.stderr)
        if args.log_file:
            _write_log(args.log_file, log_lines + [msg])
        return 3

    token = os.environ.get("GITHUB_TOKEN", "")
    # In dry-run without comments provided we'd still need a token to fetch.
    # Fall back to an empty-comment list if no token is available and nothing supplied.
    if not token and args.comments_json is None:
        print(
            "WARNING: GITHUB_TOKEN not set and no --comments-json supplied; "
            "dry-run will assume zero agent comments",
            file=sys.stderr,
        )
        # Inject an empty comments payload so _collect_context skips the API call.
        args.comments_json = "[]"

    client = GitHubClient(token or "unset", args.repo) if token else None

    # When no token, we need a dummy client for execute only if confirm.
    if args.confirm and not token:
        print(
            "ERROR: --confirm requires GITHUB_TOKEN in the environment",
            file=sys.stderr,
        )
        return 4

    ctx = _collect_context(
        args,
        client
        if client is not None
        else GitHubClient("dummy-token-for-dry-run", args.repo),
    )
    plan = build_plan(ctx)

    print(f"=== reset_pbi plan (pbi={ctx.pbi_id} issue=#{ctx.issue_number}) ===")
    print(plan.render())
    log_lines.append(f"[plan] {len(plan.actions)} action(s)")
    log_lines.extend(f"  {a.kind}: {a.describe}" for a in plan.actions)

    if args.dry_run:
        print("\n[dry-run] no changes applied")
        log_lines.append("mode: dry-run")
        if args.log_file:
            _write_log(args.log_file, log_lines)
        return 0

    print("\n[confirm] executing plan...")
    results = execute_plan(plan, client, ctx)  # type: ignore[arg-type]
    for r in results:
        print(r)
    log_lines.append("mode: confirm")
    log_lines.extend(results)
    if args.log_file:
        _write_log(args.log_file, log_lines)

    failures = [r for r in results if r.startswith("FAIL")]
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
