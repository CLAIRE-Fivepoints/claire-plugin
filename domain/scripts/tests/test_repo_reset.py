"""Unit tests for repo_reset — guardrails, plan building, execution."""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from repo_reset import (  # noqa: E402
    AGENT_LOGINS,
    TOMBSTONE_BODY,
    Context,
    GitHubClient,
    Plan,
    build_plan,
    execute_plan,
    is_agent_author,
    tombstone_title,
    verify_repo_allowed,
)


# ---------------------------------------------------------------------------
# verify_repo_allowed — guardrail
# ---------------------------------------------------------------------------


def test_verify_repo_allowed_match() -> None:
    ok, reason = verify_repo_allowed(
        "CLAIRE-Fivepoints/fivepoints", "CLAIRE-Fivepoints/fivepoints"
    )
    assert ok is True
    assert reason == ""


def test_verify_repo_allowed_mismatch_refuses() -> None:
    ok, reason = verify_repo_allowed(
        "CLAIRE-Fivepoints/fivepoints", "CLAIRE-Fivepoints/other-repo"
    )
    assert ok is False
    assert "not the configured test repo" in reason
    assert "other-repo" in reason


def test_verify_repo_allowed_empty_config_refuses() -> None:
    ok, reason = verify_repo_allowed("CLAIRE-Fivepoints/fivepoints", "")
    assert ok is False
    assert "fivepoints_test_repo" in reason


# ---------------------------------------------------------------------------
# tombstone format
# ---------------------------------------------------------------------------


def test_tombstone_title_format_is_stable() -> None:
    assert tombstone_title("20260419T235959Z") == (
        "[archived-repo-reset-20260419T235959Z]"
    )


def test_tombstone_title_starts_with_archive_marker() -> None:
    assert tombstone_title("whatever").startswith("[archived-repo-reset-")


def test_tombstone_body_is_non_empty_and_non_authoritative() -> None:
    # Agents searching for content won't match body tombstone text.
    assert TOMBSTONE_BODY
    assert "no longer authoritative" in TOMBSTONE_BODY


# ---------------------------------------------------------------------------
# is_agent_author — reuse of AGENT_LOGINS
# ---------------------------------------------------------------------------


def test_is_agent_author_known_agents() -> None:
    for login in AGENT_LOGINS:
        assert is_agent_author(login) is True


def test_is_agent_author_human() -> None:
    assert is_agent_author("andreoperez") is False
    assert is_agent_author("") is False


# ---------------------------------------------------------------------------
# build_plan
# ---------------------------------------------------------------------------


def _mk_ctx(**overrides: object) -> Context:
    defaults: dict[str, object] = {
        "repo": "CLAIRE-Fivepoints/fivepoints",
        "allowed_repo": "CLAIRE-Fivepoints/fivepoints",
        "keep_prs": False,
        "timestamp_iso": "20260419T235959Z",
        "branches": [],
        "tags": [],
        "issues": [],
        "prs": [],
        "releases": [],
        "workflow_runs": [],
        "pr_comments": [],
    }
    defaults.update(overrides)
    return Context(**defaults)  # type: ignore[arg-type]


def test_build_plan_empty_when_repo_is_clean() -> None:
    plan = build_plan(_mk_ctx())
    assert plan.actions == []


def test_build_plan_order_is_pr_comments_issues_runs_releases_tags_branches() -> None:
    """Order matters: archive PRs before their head branches are deleted."""
    ctx = _mk_ctx(
        branches=["feature/x", "main", "hotfix/y"],
        tags=["v1.0"],
        issues=[{"number": 42, "node_id": "I_kw1", "title": "bug"}],
        prs=[{"number": 10, "state": "OPEN", "title": "wip"}],
        releases=[{"id": 99, "tag_name": "v1.0"}],
        workflow_runs=[1001],
        pr_comments=[
            {"id": 555, "pr_number": 10, "author_login": "claire-test-ai"}
        ],
    )
    plan = build_plan(ctx)
    order = [a.kind for a in plan.actions]
    # Every major kind appears at least once.
    assert "gh:pr-archive" in order
    assert "gh:pr-comment-delete" in order
    assert "gh:issue-delete" in order
    assert "gh:run-delete" in order
    assert "gh:release-delete" in order
    assert "gh:tag-delete" in order
    assert "gh:branch-delete" in order
    # PR archive must precede branch delete (head refs still exist at rename).
    assert order.index("gh:pr-archive") < order.index("gh:branch-delete")
    # Issues deleted before branches too (unrelated but cheap to verify).
    assert order.index("gh:issue-delete") < order.index("gh:branch-delete")


def test_build_plan_archives_prs_with_tombstone_title_and_body() -> None:
    ctx = _mk_ctx(
        prs=[
            {"number": 7, "state": "OPEN", "title": "feat: codegen for PBI #18839"},
            {"number": 8, "state": "CLOSED", "title": "old hotfix"},
        ]
    )
    plan = build_plan(ctx)
    archive = [a for a in plan.actions if a.kind == "gh:pr-archive"]
    assert [a.payload["pr_number"] for a in archive] == [7, 8]
    for a in archive:
        assert a.payload["title"] == "[archived-repo-reset-20260419T235959Z]"
        assert a.payload["body"] == TOMBSTONE_BODY


def test_build_plan_keep_prs_skips_pr_archive_and_pr_comments() -> None:
    ctx = _mk_ctx(
        keep_prs=True,
        prs=[{"number": 7, "state": "OPEN", "title": "wip"}],
        pr_comments=[
            {"id": 555, "pr_number": 7, "author_login": "claire-test-ai"}
        ],
        # Unrelated buckets must still run.
        tags=["v1.0"],
    )
    plan = build_plan(ctx)
    kinds = [a.kind for a in plan.actions]
    assert "gh:pr-archive" not in kinds
    assert "gh:pr-comment-delete" not in kinds
    assert "gh:tag-delete" in kinds, "non-PR buckets still run under --keep-prs"


def test_build_plan_skips_main_from_branches() -> None:
    ctx = _mk_ctx(branches=["main", "feature/x", "main", "chore/y"])
    plan = build_plan(ctx)
    branch_actions = [a for a in plan.actions if a.kind == "gh:branch-delete"]
    branches = [a.payload["branch"] for a in branch_actions]
    assert "main" not in branches
    assert set(branches) == {"feature/x", "chore/y"}


def test_build_plan_filters_pr_comments_to_agent_authors_only() -> None:
    ctx = _mk_ctx(
        pr_comments=[
            {"id": 1, "pr_number": 7, "author_login": "claire-test-ai"},
            {"id": 2, "pr_number": 7, "author_login": "human-reviewer"},
            {"id": 3, "pr_number": 7, "author_login": "myclaire-ai"},
        ]
    )
    plan = build_plan(ctx)
    ids = {
        a.payload["comment_id"]
        for a in plan.actions
        if a.kind == "gh:pr-comment-delete"
    }
    assert ids == {1, 3}


def test_build_plan_issue_delete_uses_node_id() -> None:
    """GraphQL deleteIssue requires node_id, not the integer number."""
    ctx = _mk_ctx(
        issues=[
            {"number": 42, "node_id": "I_kw1ABCD", "title": "bug"},
            {"number": 43, "node_id": "I_kw1EFGH", "title": "feat"},
        ]
    )
    plan = build_plan(ctx)
    deletes = [a for a in plan.actions if a.kind == "gh:issue-delete"]
    assert [a.payload["node_id"] for a in deletes] == ["I_kw1ABCD", "I_kw1EFGH"]


# ---------------------------------------------------------------------------
# execute_plan — idempotent 404 handling
# ---------------------------------------------------------------------------


class _FakeClient:
    """Test double for GitHubClient. Each method can be wired to raise."""

    def __init__(
        self,
        raise_code: int | None = None,
        raise_on: set[str] | None = None,
    ):
        self.raise_code = raise_code
        self.raise_on = raise_on or set()
        self.calls: list[tuple[str, tuple]] = []

    def _maybe_raise(self, op: str) -> None:
        if self.raise_code is not None and op in self.raise_on:
            raise urllib.error.HTTPError(
                url="https://api.github.com/test",
                code=self.raise_code,
                msg="Not Found" if self.raise_code == 404 else "Server Error",
                hdrs=None,  # type: ignore[arg-type]
                fp=None,
            )

    def delete_branch(self, name: str) -> None:
        self.calls.append(("delete_branch", (name,)))
        self._maybe_raise("delete_branch")

    def delete_tag(self, name: str) -> None:
        self.calls.append(("delete_tag", (name,)))
        self._maybe_raise("delete_tag")

    def delete_issue(self, node_id: str) -> None:
        self.calls.append(("delete_issue", (node_id,)))
        self._maybe_raise("delete_issue")

    def archive_pr(self, pr_number: int, title: str, body: str) -> None:
        self.calls.append(("archive_pr", (pr_number, title, body)))
        self._maybe_raise("archive_pr")

    def delete_pr_issue_comment(self, comment_id: int) -> None:
        self.calls.append(("delete_pr_issue_comment", (comment_id,)))
        self._maybe_raise("delete_pr_issue_comment")

    def delete_release(self, release_id: int) -> None:
        self.calls.append(("delete_release", (release_id,)))
        self._maybe_raise("delete_release")

    def delete_workflow_run(self, run_id: int) -> None:
        self.calls.append(("delete_workflow_run", (run_id,)))
        self._maybe_raise("delete_workflow_run")


def _plan_with(kind: str, **payload: object) -> Plan:
    plan = Plan()
    plan.add(kind, f"test {kind}", **payload)
    return plan


@pytest.mark.parametrize(
    "kind,payload,method",
    [
        ("gh:branch-delete", {"branch": "feature/x"}, "delete_branch"),
        ("gh:tag-delete", {"tag": "v1.0"}, "delete_tag"),
        ("gh:issue-delete", {"node_id": "I_xyz"}, "delete_issue"),
        ("gh:run-delete", {"run_id": 100}, "delete_workflow_run"),
        ("gh:release-delete", {"release_id": 55}, "delete_release"),
        ("gh:pr-comment-delete", {"comment_id": 9}, "delete_pr_issue_comment"),
    ],
)
def test_execute_plan_404_on_idempotent_delete_is_skip(
    kind: str, payload: dict, method: str
) -> None:
    """All delete actions: 404 -> SKIP (idempotent rerun friendly)."""
    client = _FakeClient(raise_code=404, raise_on={method})
    results = execute_plan(_plan_with(kind, **payload), client)  # type: ignore[arg-type]
    assert len(results) == 1
    assert results[0].startswith("SKIP "), f"expected SKIP, got: {results[0]}"
    assert "already absent" in results[0] or "404" in results[0]


def test_execute_plan_500_on_branch_delete_stays_fail() -> None:
    client = _FakeClient(raise_code=500, raise_on={"delete_branch"})
    results = execute_plan(
        _plan_with("gh:branch-delete", branch="feature/x"), client  # type: ignore[arg-type]
    )
    assert len(results) == 1
    assert results[0].startswith("FAIL ")
    assert "500" in results[0]


def test_execute_plan_404_on_pr_archive_stays_fail() -> None:
    """PR archive is a mutation, not a delete — 404 means the PR vanished,
    which is a real problem worth surfacing."""
    plan = _plan_with(
        "gh:pr-archive",
        pr_number=7,
        title="[archived-repo-reset-x]",
        body=TOMBSTONE_BODY,
    )
    client = _FakeClient(raise_code=404, raise_on={"archive_pr"})
    results = execute_plan(plan, client)  # type: ignore[arg-type]
    assert len(results) == 1
    assert results[0].startswith("FAIL ")


def test_execute_plan_runs_every_action_in_order() -> None:
    client = _FakeClient()
    plan = Plan()
    plan.add("gh:pr-archive", "pr 7", pr_number=7, title="t", body="b")
    plan.add("gh:pr-comment-delete", "cmt 9", comment_id=9)
    plan.add("gh:issue-delete", "iss 42", node_id="I_x")
    plan.add("gh:run-delete", "run 1", run_id=1)
    plan.add("gh:release-delete", "rel 5", release_id=5)
    plan.add("gh:tag-delete", "tag v1", tag="v1")
    plan.add("gh:branch-delete", "br x", branch="feature/x")
    results = execute_plan(plan, client)  # type: ignore[arg-type]
    assert all(r.startswith("OK ") for r in results), results
    called = [c[0] for c in client.calls]
    assert called == [
        "archive_pr",
        "delete_pr_issue_comment",
        "delete_issue",
        "delete_workflow_run",
        "delete_release",
        "delete_tag",
        "delete_branch",
    ]


def test_execute_plan_unknown_kind_is_skip_not_fail() -> None:
    client = _FakeClient()
    plan = Plan()
    plan.add("gh:unknown", "bogus")
    results = execute_plan(plan, client)  # type: ignore[arg-type]
    assert results[0].startswith("SKIP ")
    assert "unknown kind" in results[0]


# ---------------------------------------------------------------------------
# GraphQL NOT_FOUND idempotency — issue delete path
#
# The _FakeClient path above proves the executor classifies 404 as SKIP, but
# it shortcuts past the real GitHubClient._graphql mapping. These tests
# drive the real _graphql with a urlopen stub so the NOT_FOUND -> 404
# contract is exercised end-to-end.
# ---------------------------------------------------------------------------


class _FakeUrlopen:
    """Context-manager stub for urllib.request.urlopen.

    Yields a response whose .read() returns the given body. The body is a
    pre-serialized JSON string so tests can simulate any GitHub response.
    """

    def __init__(self, body: str):
        self._body = body.encode()

    def __call__(self, req, timeout=None):  # noqa: ARG002
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _graphql_not_found_payload() -> str:
    """A GitHub GraphQL response for a node that no longer exists.

    Real shape from the API — `errors[].type == "NOT_FOUND"` and HTTP 200.
    """
    return json.dumps(
        {
            "data": None,
            "errors": [
                {
                    "type": "NOT_FOUND",
                    "path": ["deleteIssue"],
                    "message": "Could not resolve to a node with the global id of 'I_kwDOxxxxx'.",
                }
            ],
        }
    )


def _graphql_other_error_payload() -> str:
    """A GitHub GraphQL response for a non-idempotency error (e.g. bad scope)."""
    return json.dumps(
        {
            "errors": [
                {
                    "type": "FORBIDDEN",
                    "message": "Resource not accessible by integration",
                }
            ]
        }
    )


def test_graphql_maps_not_found_to_http_404() -> None:
    """NOT_FOUND -> HTTPError(404) so IDEMPOTENT_DELETE_KINDS catches it."""
    client = GitHubClient("test-token", "owner/repo")
    fake = _FakeUrlopen(_graphql_not_found_payload())
    with patch("urllib.request.urlopen", fake):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            client.delete_issue("I_kwDOxxxxx")
    assert exc_info.value.code == 404, (
        f"expected 404 (idempotent), got {exc_info.value.code}"
    )


def test_graphql_maps_other_errors_to_http_422() -> None:
    """Non-NOT_FOUND GraphQL errors stay as 422 (real failure)."""
    client = GitHubClient("test-token", "owner/repo")
    fake = _FakeUrlopen(_graphql_other_error_payload())
    with patch("urllib.request.urlopen", fake):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            client.delete_issue("I_kwDOxxxxx")
    assert exc_info.value.code == 422


def test_execute_plan_graphql_not_found_on_issue_delete_is_skip() -> None:
    """End-to-end: GraphQL NOT_FOUND on gh:issue-delete -> SKIP in execute_plan.

    This is the test that would have caught the gatekeeper-flagged bug: the
    _FakeClient version skipped the _graphql layer entirely.
    """
    client = GitHubClient("test-token", "owner/repo")
    fake = _FakeUrlopen(_graphql_not_found_payload())
    plan = Plan()
    plan.add(
        "gh:issue-delete",
        "delete issue #42: 'gone'",
        node_id="I_kwDOxxxxx",
    )
    with patch("urllib.request.urlopen", fake):
        results = execute_plan(plan, client)
    assert len(results) == 1
    assert results[0].startswith("SKIP "), (
        f"expected SKIP (idempotent rerun), got: {results[0]}"
    )


def test_execute_plan_graphql_forbidden_on_issue_delete_stays_fail() -> None:
    """End-to-end: GraphQL FORBIDDEN stays FAIL (not a delete-idempotency case)."""
    client = GitHubClient("test-token", "owner/repo")
    fake = _FakeUrlopen(_graphql_other_error_payload())
    plan = Plan()
    plan.add(
        "gh:issue-delete",
        "delete issue #42: 'scope error'",
        node_id="I_kwDOxxxxx",
    )
    with patch("urllib.request.urlopen", fake):
        results = execute_plan(plan, client)
    assert len(results) == 1
    assert results[0].startswith("FAIL "), (
        f"expected FAIL (real error), got: {results[0]}"
    )
