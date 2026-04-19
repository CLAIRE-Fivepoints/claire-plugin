"""Unit tests for reset_pbi — guardrails, plan building, state mutation."""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

import pytest

# Allow tests to import the single-file module from its sibling directory.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from reset_pbi import (  # noqa: E402  (import after sys.path mutation)
    AGENT_LOGINS,
    Context,
    Plan,
    build_plan,
    check_pr_merged,
    execute_plan,
    is_agent_comment,
    parse_pbi_from_title,
    purge_state,
    state_contains_issue,
    verify_pbi_matches_issue,
)


# ---------------------------------------------------------------------------
# parse_pbi_from_title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,expected",
    [
        ("1 - Code Gen (PBI #18839)", "18839"),
        ("feat: something PBI#12345", "12345"),
        ("(PBI #1)", "1"),
        ("pbi # 987 lowercase and spaces", "987"),
        ("nothing interesting", None),
        ("", None),
    ],
)
def test_parse_pbi_from_title(title: str, expected: str | None) -> None:
    assert parse_pbi_from_title(title) == expected


# ---------------------------------------------------------------------------
# verify_pbi_matches_issue
# ---------------------------------------------------------------------------


def test_verify_pbi_matches_issue_match() -> None:
    ok, detected = verify_pbi_matches_issue("18839", "1 - Code Gen (PBI #18839)")
    assert ok is True
    assert detected == "18839"


def test_verify_pbi_matches_issue_mismatch() -> None:
    ok, detected = verify_pbi_matches_issue("18839", "Something (PBI #99)")
    assert ok is False
    assert detected == "99"


def test_verify_pbi_matches_issue_no_reference() -> None:
    ok, detected = verify_pbi_matches_issue("18839", "plain title no reference")
    assert ok is False
    assert detected is None


# ---------------------------------------------------------------------------
# check_pr_merged
# ---------------------------------------------------------------------------


def test_check_pr_merged_true_when_merged_flag() -> None:
    assert check_pr_merged(pr_state="OPEN", merged=True) is True


def test_check_pr_merged_true_when_state_merged() -> None:
    assert check_pr_merged(pr_state="MERGED", merged=False) is True


def test_check_pr_merged_false_when_open() -> None:
    assert check_pr_merged(pr_state="OPEN", merged=False) is False


def test_check_pr_merged_false_when_closed_not_merged() -> None:
    assert check_pr_merged(pr_state="CLOSED", merged=False) is False


# ---------------------------------------------------------------------------
# is_agent_comment
# ---------------------------------------------------------------------------


def test_is_agent_comment_known_agents() -> None:
    for login in AGENT_LOGINS:
        assert is_agent_comment(login) is True


def test_is_agent_comment_human_login() -> None:
    assert is_agent_comment("andreoperez") is False


# ---------------------------------------------------------------------------
# build_plan
# ---------------------------------------------------------------------------


def _mk_ctx(**overrides: object) -> Context:
    defaults = {
        "pbi_id": "18839",
        "issue_number": 71,
        "repo": "CLAIRE-Fivepoints/fivepoints",
        "issue_title": "1 - Code Gen (PBI #18839)",
        "issue_state": "OPEN",
        "issue_labels": ["role:analyst"],
        "pr_number": None,
        "pr_state": None,
        "pr_merged": False,
        "comments": [],
        "release_assets": [],
        "state_file": Path("/tmp/nonexistent_state.json"),
        "state_has_issue": False,
    }
    defaults.update(overrides)
    return Context(**defaults)  # type: ignore[arg-type]


def test_build_plan_empty_when_clean() -> None:
    ctx = _mk_ctx()
    plan = build_plan(ctx)
    assert plan.actions == []


def test_build_plan_deletes_agent_comments_only() -> None:
    ctx = _mk_ctx(
        comments=[
            {"id": 1, "user": {"login": "claire-test-ai"}, "body": "hi"},
            {"id": 2, "user": {"login": "human-reviewer"}, "body": "lgtm"},
            {"id": 3, "user": {"login": "claire-plugin-gatekeeper-ai"}, "body": "ok"},
        ]
    )
    plan = build_plan(ctx)
    comment_actions = [a for a in plan.actions if a.kind == "gh:comment"]
    comment_ids = {a.payload["comment_id"] for a in comment_actions}
    assert comment_ids == {1, 3}, "only agent-authored comments should be scheduled"


def test_build_plan_resets_labels_when_not_analyst() -> None:
    ctx = _mk_ctx(issue_labels=["role:dev", "role:dev:in-progress", "priority:high"])
    plan = build_plan(ctx)
    label_actions = [a for a in plan.actions if a.kind == "gh:labels"]
    assert len(label_actions) == 1
    assert label_actions[0].payload["labels"] == ["role:analyst"]


def test_build_plan_skips_label_action_when_already_analyst_only() -> None:
    ctx = _mk_ctx(issue_labels=["role:analyst"])
    plan = build_plan(ctx)
    assert [a.kind for a in plan.actions] == []


def test_build_plan_reopens_closed_issue() -> None:
    ctx = _mk_ctx(issue_state="CLOSED")
    plan = build_plan(ctx)
    assert any(a.kind == "gh:reopen" for a in plan.actions)


def test_build_plan_deletes_release_assets() -> None:
    ctx = _mk_ctx(
        release_assets=[
            {"id": 100, "name": "proof-issue-71-swagger.mp4", "release_tag": "v1"},
            {"id": 101, "name": "BEFORE_issue-71.png", "release_tag": "v1"},
        ]
    )
    plan = build_plan(ctx)
    asset_actions = [a for a in plan.actions if a.kind == "gh:asset"]
    assert {a.payload["asset_id"] for a in asset_actions} == {100, 101}


def test_build_plan_purges_state_when_present() -> None:
    ctx = _mk_ctx(state_has_issue=True)
    plan = build_plan(ctx)
    assert any(a.kind == "state:purge" for a in plan.actions)


def test_build_plan_skips_state_purge_when_absent() -> None:
    ctx = _mk_ctx(state_has_issue=False)
    plan = build_plan(ctx)
    assert not any(a.kind == "state:purge" for a in plan.actions)


# ---------------------------------------------------------------------------
# purge_state / state_contains_issue
# ---------------------------------------------------------------------------


def _write_state(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2))


def test_state_contains_issue_true_in_processed(tmp_path: Path) -> None:
    f = tmp_path / "state.json"
    _write_state(f, {"processed_issues": {"71": "2026-04-16T00:00:00"}})
    assert state_contains_issue(f, 71) is True


def test_state_contains_issue_true_in_assignees_only(tmp_path: Path) -> None:
    f = tmp_path / "state.json"
    _write_state(f, {"issue_assignees": {"71": ["claire-test-ai"]}})
    assert state_contains_issue(f, 71) is True


def test_state_contains_issue_false_when_missing_file(tmp_path: Path) -> None:
    assert state_contains_issue(tmp_path / "absent.json", 71) is False


def test_state_contains_issue_false_when_unrelated(tmp_path: Path) -> None:
    f = tmp_path / "state.json"
    _write_state(f, {"processed_issues": {"99": "x"}})
    assert state_contains_issue(f, 71) is False


def test_purge_state_removes_entries(tmp_path: Path) -> None:
    f = tmp_path / "state.json"
    _write_state(
        f,
        {
            "processed_issues": {"71": "t1", "72": "t2"},
            "issue_assignees": {"71": ["claire-test-ai"], "72": ["bot"]},
            "last_updated": "old",
        },
    )
    changed = purge_state(f, 71)
    assert changed is True
    data = json.loads(f.read_text())
    assert "71" not in data["processed_issues"]
    assert "71" not in data["issue_assignees"]
    # Untouched entries survive.
    assert data["processed_issues"]["72"] == "t2"
    assert data["issue_assignees"]["72"] == ["bot"]
    # last_updated is refreshed.
    assert data["last_updated"] != "old"


def test_purge_state_returns_false_when_absent(tmp_path: Path) -> None:
    f = tmp_path / "state.json"
    _write_state(f, {"processed_issues": {"99": "t"}})
    assert purge_state(f, 71) is False


# ---------------------------------------------------------------------------
# execute_plan — idempotent 404 handling on delete actions (issue #60)
# ---------------------------------------------------------------------------


class _FakeClient:
    """Test double for GitHubClient. Each method can be wired to raise."""

    def __init__(self, raise_code: int | None = None, raise_on: set[str] | None = None):
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

    def delete_release_asset(self, asset_id: int) -> None:
        self.calls.append(("delete_release_asset", (asset_id,)))
        self._maybe_raise("delete_release_asset")

    def delete_issue_comment(self, comment_id: int) -> None:
        self.calls.append(("delete_issue_comment", (comment_id,)))
        self._maybe_raise("delete_issue_comment")

    def set_issue_labels(self, issue_number: int, labels: list[str]) -> None:
        self.calls.append(("set_issue_labels", (issue_number, labels)))
        self._maybe_raise("set_issue_labels")

    def reopen_issue(self, issue_number: int) -> None:
        self.calls.append(("reopen_issue", (issue_number,)))
        self._maybe_raise("reopen_issue")


def _asset_plan() -> Plan:
    plan = Plan()
    plan.add(
        "gh:asset",
        "delete release asset 'proof-issue-71.mp4' from proof-issue-71-...",
        asset_id=42,
    )
    return plan


def _comment_plan() -> Plan:
    plan = Plan()
    plan.add(
        "gh:comment",
        "delete comment #12345 by claire-test-ai: 'hello'",
        comment_id=12345,
    )
    return plan


def test_execute_plan_404_on_asset_delete_is_skip() -> None:
    """Idempotent asset delete: 404 = already gone = SKIP, not FAIL."""
    client = _FakeClient(raise_code=404, raise_on={"delete_release_asset"})
    ctx = _mk_ctx()
    results = execute_plan(_asset_plan(), client, ctx)
    assert len(results) == 1
    assert results[0].startswith("SKIP "), f"expected SKIP, got: {results[0]}"
    assert "already absent" in results[0] or "404" in results[0]


def test_execute_plan_404_on_comment_delete_is_skip() -> None:
    """Idempotent comment delete: 404 = already deleted = SKIP, not FAIL."""
    client = _FakeClient(raise_code=404, raise_on={"delete_issue_comment"})
    ctx = _mk_ctx()
    results = execute_plan(_comment_plan(), client, ctx)
    assert len(results) == 1
    assert results[0].startswith("SKIP "), f"expected SKIP, got: {results[0]}"


def test_execute_plan_non_404_asset_delete_still_fails() -> None:
    """A 500 on asset delete is a real error and must stay FAIL."""
    client = _FakeClient(raise_code=500, raise_on={"delete_release_asset"})
    ctx = _mk_ctx()
    results = execute_plan(_asset_plan(), client, ctx)
    assert len(results) == 1
    assert results[0].startswith("FAIL "), f"expected FAIL, got: {results[0]}"
    assert "500" in results[0]


def test_execute_plan_404_on_reopen_still_fails() -> None:
    """Non-delete 404s (e.g. reopen on a vanished issue) stay FAIL — a 404
    there means the target itself is gone, which is a real problem."""
    plan = Plan()
    plan.add("gh:reopen", "reopen issue #71")
    client = _FakeClient(raise_code=404, raise_on={"reopen_issue"})
    ctx = _mk_ctx(issue_state="CLOSED")
    results = execute_plan(plan, client, ctx)
    assert len(results) == 1
    assert results[0].startswith("FAIL "), f"expected FAIL, got: {results[0]}"
