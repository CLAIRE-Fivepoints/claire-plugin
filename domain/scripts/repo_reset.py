"""
repo_reset — Whole-repo factory reset for the fivepoints test mirror.

Resets `CLAIRE-Fivepoints/fivepoints` (the TFI One GitHub mirror) to a clean
state derived from ADO/<ref>, without deleting the repo itself. Settings
(labels, branch protection, webhooks, Actions secrets, collaborators) are
preserved; content (issues, PRs, branches, tags, releases, workflow runs)
is wiped.

The bash orchestrator (domain/commands/repo-reset.sh) owns:
  * Force-pushing `main` to the ADO ref (via ~/TFIOneGit local clone)
  * Pre-fetching the JSON inventories (branches, tags, issues, PRs, releases,
    workflow runs) via `gh`
  * The `fivepoints_test_repo` guardrail from machine.yml

This Python module owns:
  * Plan building from the pre-fetched inventories
  * Plan execution via the REST + GraphQL clients (urllib only — no subprocess,
    per DEV_RULES #2)

PR deletion note: GitHub's API does not expose PR deletion (REST DELETE /pulls/N
returns 404; no GraphQL mutation exists). Instead we strip the title and body
into a `[archived-repo-reset-<iso>]` tombstone and close the PR, so agent
searches (`gh pr list --search "PBI #18839"`) return zero matches.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Shared with reset_pbi — authors whose PR/issue comments are considered
# agent-authored and deleted as part of the wipe.
AGENT_LOGINS = frozenset(
    {
        "claire-test-ai",
        "claire-plugin-gatekeeper-ai",
        "myclaire-ai",
        "claire-gatekeeper-ai",
    }
)

# 404 on any of these means the target is already gone — SKIP, not FAIL.
IDEMPOTENT_DELETE_KINDS = frozenset(
    {
        "gh:branch-delete",
        "gh:tag-delete",
        "gh:release-delete",
        "gh:run-delete",
        "gh:pr-comment-delete",
        "gh:issue-delete",
    }
)

TOMBSTONE_BODY = (
    "This PR was archived during a factory repo reset. "
    "Original content is no longer authoritative."
)


def tombstone_title(timestamp_iso: str) -> str:
    """Title for a strip+rename tombstone. Stable format — grepped by tests."""
    return f"[archived-repo-reset-{timestamp_iso}]"


# ---------------------------------------------------------------------------
# Plan representation (same shape as reset_pbi.Plan / Action)
# ---------------------------------------------------------------------------


@dataclass
class Action:
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
# GitHub client (REST + GraphQL, urllib-based)
# ---------------------------------------------------------------------------


class GitHubClient:
    """Authenticated REST + GraphQL client for repo-reset.

    One client per run; the caller supplies a token with `delete_repo` and
    `admin:org` scopes so the GraphQL `deleteIssue` mutation is authorized.
    """

    def __init__(
        self,
        token: str,
        repo: str,
        *,
        base_url: str = "https://api.github.com",
    ):
        if not token:
            raise ValueError("GitHub admin token is required")
        if "/" not in repo:
            raise ValueError(f"repo must be 'owner/name', got {repo!r}")
        self._token = token
        self._repo = repo
        self._owner, self._name = repo.split("/", 1)
        self._base_url = base_url.rstrip("/")

    # ---- low-level request helpers ----

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
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

    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}/graphql"
        body = json.dumps({"query": query, "variables": variables}).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            raw = resp.read()
        payload = json.loads(raw) if raw else {}
        if payload.get("errors"):
            # Surface GraphQL errors as HTTPError-like so the executor can
            # classify them alongside REST failures.
            messages = "; ".join(
                e.get("message", "?") for e in payload["errors"]
            )
            raise urllib.error.HTTPError(
                url=url,
                code=422,
                msg=f"GraphQL error: {messages}",
                hdrs=None,  # type: ignore[arg-type]
                fp=None,
            )
        return payload.get("data", {})

    # ---- refs (branches, tags) ----

    def delete_branch(self, name: str) -> None:
        # Ref name is URL-escaped only minimally; branches like feat/foo work
        # without extra escaping because GitHub accepts slashes in the path.
        self._request(
            "DELETE", f"/repos/{self._repo}/git/refs/heads/{name}"
        )

    def delete_tag(self, name: str) -> None:
        self._request(
            "DELETE", f"/repos/{self._repo}/git/refs/tags/{name}"
        )

    # ---- issues ----

    def delete_issue(self, node_id: str) -> None:
        """GraphQL deleteIssue — admin token required."""
        query = """
        mutation($id: ID!) {
            deleteIssue(input: {issueId: $id}) {
                clientMutationId
            }
        }
        """
        self._graphql(query, {"id": node_id})

    # ---- pulls ----

    def archive_pr(self, pr_number: int, title: str, body: str) -> None:
        """Strip-rename a PR into a tombstone and close it in a single call."""
        self._request(
            "PATCH",
            f"/repos/{self._repo}/pulls/{pr_number}",
            {"title": title, "body": body, "state": "closed"},
        )

    def delete_pr_issue_comment(self, comment_id: int) -> None:
        """Delete a PR issue-comment (PR discussion comment, not review comment)."""
        self._request(
            "DELETE", f"/repos/{self._repo}/issues/comments/{comment_id}"
        )

    # ---- releases ----

    def delete_release(self, release_id: int) -> None:
        self._request(
            "DELETE", f"/repos/{self._repo}/releases/{release_id}"
        )

    # ---- workflow runs ----

    def delete_workflow_run(self, run_id: int) -> None:
        self._request(
            "DELETE", f"/repos/{self._repo}/actions/runs/{run_id}"
        )


# ---------------------------------------------------------------------------
# Context + plan building
# ---------------------------------------------------------------------------


@dataclass
class Context:
    repo: str
    allowed_repo: str
    keep_prs: bool
    timestamp_iso: str
    branches: list[str]          # non-main branch names
    tags: list[str]              # tag names
    issues: list[dict[str, Any]] # each: {number, node_id, title}
    prs: list[dict[str, Any]]    # each: {number, state, title}
    releases: list[dict[str, Any]]  # each: {id, tag_name}
    workflow_runs: list[int]     # run ids
    pr_comments: list[dict[str, Any]]  # each: {id, pr_number, author_login}


def verify_repo_allowed(repo: str, allowed_repo: str) -> tuple[bool, str]:
    """Guardrail — refuse to operate on anything other than the configured repo.

    Returns (True, "") if allowed. On mismatch returns (False, reason).
    """
    if not allowed_repo:
        return False, (
            "machine.yml does not define 'fivepoints_test_repo' — "
            "refusing to operate (configure it before running repo-reset)"
        )
    if repo != allowed_repo:
        return False, (
            f"repo {repo!r} is not the configured test repo "
            f"(machine.yml:fivepoints_test_repo={allowed_repo!r}) — refusing"
        )
    return True, ""


def is_agent_author(login: str) -> bool:
    return login in AGENT_LOGINS


def build_plan(ctx: Context) -> Plan:
    """Compute the ordered reset plan for ``ctx``.

    Order is chosen so that downstream cleanup doesn't invalidate upstream
    references:
      1. PR archive (while head branches still exist)
      2. PR agent-comment cleanup
      3. Issue delete (GraphQL)
      4. Workflow run delete
      5. Release delete
      6. Tag delete
      7. Branch delete (non-main; main is already force-pushed by bash)
    """
    plan = Plan()

    # 1. PR strip + rename (unless --keep-prs)
    if not ctx.keep_prs:
        tombstone = tombstone_title(ctx.timestamp_iso)
        for pr in ctx.prs:
            plan.add(
                "gh:pr-archive",
                f"archive PR #{pr['number']} (was {pr.get('state', '?')}: "
                f"{(pr.get('title') or '')[:50]!r}) -> {tombstone}",
                pr_number=pr["number"],
                title=tombstone,
                body=TOMBSTONE_BODY,
            )

    # 2. PR agent-authored discussion comments (unless --keep-prs)
    if not ctx.keep_prs:
        for c in ctx.pr_comments:
            if not is_agent_author(c.get("author_login", "")):
                continue
            plan.add(
                "gh:pr-comment-delete",
                f"delete PR #{c.get('pr_number', '?')} comment #{c['id']} "
                f"by {c.get('author_login', '?')}",
                comment_id=c["id"],
            )

    # 3. Issues — all of them (GraphQL deleteIssue)
    for issue in ctx.issues:
        plan.add(
            "gh:issue-delete",
            f"delete issue #{issue['number']}: "
            f"{(issue.get('title') or '')[:60]!r}",
            node_id=issue["node_id"],
        )

    # 4. Workflow runs
    for run_id in ctx.workflow_runs:
        plan.add(
            "gh:run-delete",
            f"delete workflow run {run_id}",
            run_id=run_id,
        )

    # 5. Releases
    for r in ctx.releases:
        plan.add(
            "gh:release-delete",
            f"delete release '{r.get('tag_name', '?')}' (id={r['id']})",
            release_id=r["id"],
        )

    # 6. Tags
    for tag in ctx.tags:
        plan.add("gh:tag-delete", f"delete tag {tag}", tag=tag)

    # 7. Non-main branches
    for branch in ctx.branches:
        if branch == "main":
            continue
        plan.add(
            "gh:branch-delete", f"delete branch {branch}", branch=branch
        )

    return plan


# ---------------------------------------------------------------------------
# Plan execution
# ---------------------------------------------------------------------------


def execute_plan(
    plan: Plan, client: GitHubClient
) -> list[str]:
    """Execute every action. Returns per-action result strings.

    Delete actions get idempotent 404 -> SKIP treatment (same pattern as
    reset_pbi). Mutations (PR archive) do not — a 404 there means the target
    is gone, which is a real error worth surfacing.
    """
    results: list[str] = []
    for action in plan.actions:
        try:
            if action.kind == "gh:pr-archive":
                client.archive_pr(
                    action.payload["pr_number"],
                    action.payload["title"],
                    action.payload["body"],
                )
            elif action.kind == "gh:pr-comment-delete":
                client.delete_pr_issue_comment(action.payload["comment_id"])
            elif action.kind == "gh:issue-delete":
                client.delete_issue(action.payload["node_id"])
            elif action.kind == "gh:run-delete":
                client.delete_workflow_run(action.payload["run_id"])
            elif action.kind == "gh:release-delete":
                client.delete_release(action.payload["release_id"])
            elif action.kind == "gh:tag-delete":
                client.delete_tag(action.payload["tag"])
            elif action.kind == "gh:branch-delete":
                client.delete_branch(action.payload["branch"])
            else:
                logger.warning("unknown action kind: %s", action.kind)
                results.append(f"SKIP {action.kind}: unknown kind")
                continue
            results.append(f"OK   [{action.kind}] {action.describe}")
        except urllib.error.HTTPError as e:
            if e.code == 404 and action.kind in IDEMPOTENT_DELETE_KINDS:
                results.append(
                    f"SKIP [{action.kind}] {action.describe}: "
                    f"already absent (HTTP 404)"
                )
                logger.info("action skipped (already absent): %s", action.describe)
            else:
                results.append(
                    f"FAIL [{action.kind}] {action.describe}: "
                    f"HTTP {e.code} {e.reason}"
                )
                logger.warning(
                    "action failed: %s — HTTP %s", action.describe, e.code
                )
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            results.append(
                f"FAIL [{action.kind}] {action.describe}: "
                f"{type(e).__name__}: {e}"
            )
            logger.warning("action failed: %s — %s", action.describe, e)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_json_arg(value: str | None, label: str) -> Any:
    """Load JSON from ``value`` (literal string or '@path')."""
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
        prog="repo_reset",
        description=(
            "Whole-repo factory reset for the fivepoints test mirror. "
            "Called by domain/commands/repo-reset.sh."
        ),
    )
    p.add_argument(
        "--repo", required=True, help="GitHub repo in owner/name form"
    )
    p.add_argument(
        "--allowed-repo",
        required=True,
        help="Expected repo (from machine.yml:fivepoints_test_repo) — guardrail",
    )
    p.add_argument(
        "--log-file", type=Path, default=None, help="Path to reset log file"
    )
    p.add_argument(
        "--branches-json",
        default="[]",
        help="JSON list or @path of non-main branch names",
    )
    p.add_argument(
        "--tags-json", default="[]", help="JSON list or @path of tag names"
    )
    p.add_argument(
        "--issues-json",
        default="[]",
        help="JSON list or @path of {number, node_id, title}",
    )
    p.add_argument(
        "--prs-json",
        default="[]",
        help="JSON list or @path of {number, state, title}",
    )
    p.add_argument(
        "--releases-json",
        default="[]",
        help="JSON list or @path of {id, tag_name}",
    )
    p.add_argument(
        "--runs-json",
        default="[]",
        help="JSON list or @path of run ids (integers)",
    )
    p.add_argument(
        "--pr-comments-json",
        default="[]",
        help="JSON list or @path of {id, pr_number, author_login}",
    )
    p.add_argument(
        "--keep-prs",
        action="store_true",
        help="Skip PR strip+rename and PR comment cleanup",
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print plan and exit")
    mode.add_argument(
        "--confirm",
        action="store_true",
        help="Execute plan (destructive). Required for any real mutation.",
    )
    return p


def _write_log(log_file: Path, lines: list[str]) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a") as f:
        for line in lines:
            f.write(line + "\n")


def _collect_context(args: argparse.Namespace) -> Context:
    branches = _load_json_arg(args.branches_json, "branches-json") or []
    tags = _load_json_arg(args.tags_json, "tags-json") or []
    issues = _load_json_arg(args.issues_json, "issues-json") or []
    prs = _load_json_arg(args.prs_json, "prs-json") or []
    releases = _load_json_arg(args.releases_json, "releases-json") or []
    runs = _load_json_arg(args.runs_json, "runs-json") or []
    pr_comments = (
        _load_json_arg(args.pr_comments_json, "pr-comments-json") or []
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    return Context(
        repo=args.repo,
        allowed_repo=args.allowed_repo,
        keep_prs=args.keep_prs,
        timestamp_iso=ts,
        branches=[b for b in branches if b != "main"],
        tags=list(tags),
        issues=list(issues),
        prs=list(prs),
        releases=list(releases),
        workflow_runs=[int(r) for r in runs],
        pr_comments=list(pr_comments),
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    args = _build_parser().parse_args(argv)

    log_lines: list[str] = [
        f"=== repo_reset repo={args.repo} allowed={args.allowed_repo} ==="
    ]

    ok, reason = verify_repo_allowed(args.repo, args.allowed_repo)
    if not ok:
        print(f"ERROR: {reason}", file=sys.stderr)
        if args.log_file:
            _write_log(args.log_file, log_lines + [f"ERROR: {reason}"])
        return 2

    token = os.environ.get("GITHUB_ADMIN_TOKEN", "")
    if args.confirm and not token:
        print(
            "ERROR: --confirm requires GITHUB_ADMIN_TOKEN in the environment "
            "(token must have delete_repo + admin:org scopes)",
            file=sys.stderr,
        )
        return 4

    ctx = _collect_context(args)
    plan = build_plan(ctx)

    print(f"=== repo_reset plan ({args.repo}) ===")
    print(plan.render())
    log_lines.append(f"[plan] {len(plan.actions)} action(s)")
    log_lines.extend(f"  {a.kind}: {a.describe}" for a in plan.actions)

    if args.dry_run:
        print("\n[dry-run] no changes applied")
        log_lines.append("mode: dry-run")
        if args.log_file:
            _write_log(args.log_file, log_lines)
        return 0

    client = GitHubClient(token, args.repo)
    print("\n[confirm] executing plan...")
    results = execute_plan(plan, client)
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
