#!/usr/bin/env python3
"""
domain/scripts/ado_agent.py — ADO build verification agent.

Called by ado-transition.sh after the branch is pushed to ADO.
Creates ADO PR, monitors build pipeline, reports results to GitHub issue.

Python = Logic (API calls, build status parsing, pass/fail decisions).
Bash orchestration (git push, remote setup) lives in ado-transition.sh.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# ADO configuration (TFI One)
ADO_ORG = "FivePointsTechnology"
ADO_PROJECT = "TFIOne"
ADO_REPO = "TFIOneGit"
ADO_BASE_URL = f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis"

GH_REPO = os.environ.get("CLAIRE_WAIT_REPO", "CLAIRE-Fivepoints/fivepoints-test")
GH_API_BASE = f"https://api.github.com/repos/{GH_REPO}"

POLL_INTERVAL = 60  # seconds between build checks
MAX_WAIT = 7200  # 2 hours max

# ADO PR attachment limit. Actual server cap is ~30 MB; we stay under to leave
# headroom for the JSON envelope and avoid a 413 that would abort the push.
ADO_ATTACHMENT_SIZE_LIMIT = 25 * 1024 * 1024

MP4_LINE_RE = re.compile(
    r"^(?:MP4|Proof|Recording|Video)\s*[: ]\s*(\S+\.mp4)\b",
    re.IGNORECASE | re.MULTILINE,
)
FDS_SENTINEL = "**FDS Verification (screenshot + AI)**"


# ─────────────────────────────────────────────
# ADO API helpers
# ─────────────────────────────────────────────


def _ado_headers(pat: str) -> dict[str, str]:
    token = base64.b64encode(f":{pat}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def ado_get(path: str, pat: str) -> Any:
    url = f"{ADO_BASE_URL}{path}"
    req = urllib.request.Request(url, headers=_ado_headers(pat))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def ado_post(path: str, body: dict[str, Any], pat: str) -> Any:
    url = f"{ADO_BASE_URL}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers=_ado_headers(pat), method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


# ─────────────────────────────────────────────
# ADO PR operations
# ─────────────────────────────────────────────


def extract_mp4_path(comment_bodies: list[str]) -> str | None:
    """Find the first MP4 path in an issue's comments.

    Matches the dev-checklist convention: a line starting with
    `MP4:` / `Proof:` / `Recording:` / `Video:` (case-insensitive)
    followed by a token ending in `.mp4`. Intentionally tighter than
    "any `.mp4` in prose" — mirrors the `check_proof_gate` matcher so
    the gate and the attachment code agree on what counts as a proof.
    """
    for body in comment_bodies:
        match = MP4_LINE_RE.search(body)
        if match:
            return match.group(1)
    return None


def extract_fds_verification(comment_bodies: list[str]) -> str | None:
    """Return the first comment body that STARTS with the FDS sentinel.

    The whole comment body is returned verbatim so it can be copied into
    the ADO PR description — reviewers on ADO (where GitHub is private)
    see the FDS checklist inline without following a link they can't open.
    """
    for body in comment_bodies:
        if body.startswith(FDS_SENTINEL):
            return body
    return None


def build_pr_body(
    branch: str,
    issue: int,
    fds_verification: str | None,
    mp4_attachment_url: str | None,
    mp4_skip_reason: str | None,
) -> str:
    """Assemble the ADO PR description from the pieces gathered on GitHub.

    ADO reviewers cannot access the (private) GitHub issue, so the PR body
    carries the proofs directly: the FDS Verification checklist verbatim and
    an attachment link to the MP4. When the MP4 can't be attached (too big,
    not found on disk), the body surfaces the skip reason instead of silently
    dropping it — a reviewer must see that a proof was expected.
    """
    sections: list[str] = [
        f"## GitHub Issue\n{GH_REPO}#{issue}",
        f"## Branch\n`{branch}`",
    ]

    if mp4_attachment_url:
        sections.append(
            "## MP4 Proof\n"
            f"[Download MP4 proof]({mp4_attachment_url})"
        )
    elif mp4_skip_reason:
        sections.append(f"## MP4 Proof\n⚠️ {mp4_skip_reason}")

    if fds_verification:
        sections.append(
            "## FDS Verification\n"
            "_Copied verbatim from the GitHub issue comment so ADO reviewers "
            "see the FDS checklist inline._\n\n"
            f"{fds_verification}"
        )

    sections.append("---\nCreated by C.L.A.I.R.E. pipeline")
    return "\n\n".join(sections)


def gh_list_issue_comment_bodies(issue: int) -> list[str]:
    """Return raw body strings for every comment on a GitHub issue."""
    url = f"{GH_API_BASE}/issues/{issue}/comments?per_page=100"
    req = urllib.request.Request(url, headers=_gh_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    return [str(item.get("body", "")) for item in payload]


def ado_upload_pr_attachment(
    pr_id: int, file_path: str, file_name: str, pat: str
) -> str | None:
    """Upload a local file as an ADO PR attachment. Return the attachment URL, or None on failure.

    Uses the ADO REST attachments endpoint:
      PUT /git/repositories/{repo}/pullRequests/{pr_id}/attachments/{name}?api-version=7.1
    Body = raw bytes, Content-Type = application/octet-stream. The response
    JSON carries a `url` field the reviewer's browser can fetch with their
    ADO session — no GitHub access needed.
    """
    try:
        with open(file_path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print(f"[agent] Could not read {file_path}: {exc}", file=sys.stderr)
        return None

    encoded_name = urllib.parse.quote(file_name, safe="")
    url = (
        f"{ADO_BASE_URL}/git/repositories/{ADO_REPO}"
        f"/pullRequests/{pr_id}/attachments/{encoded_name}?api-version=7.1"
    )
    headers = _ado_headers(pat)
    headers["Content-Type"] = "application/octet-stream"

    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            response = json.loads(resp.read().decode())
        return str(response.get("url") or "") or None
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"[agent] Attachment upload failed for {file_name}: {exc}", file=sys.stderr)
        return None


def ado_patch_pr_description(pr_id: int, description: str, pat: str) -> bool:
    """PATCH an existing ADO PR's description. Returns True on success."""
    url = (
        f"{ADO_BASE_URL}/git/repositories/{ADO_REPO}"
        f"/pullrequests/{pr_id}?api-version=7.1"
    )
    data = json.dumps({"description": description}).encode()
    req = urllib.request.Request(url, data=data, headers=_ado_headers(pat), method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=30):
            return True
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"[agent] PR description PATCH failed: {exc}", file=sys.stderr)
        return False


def attach_mp4_and_get_link(
    pr_id: int, mp4_path: str | None, pat: str
) -> tuple[str | None, str | None]:
    """Try to attach an MP4 to the PR. Returns (attachment_url, skip_reason).

    Exactly one of the two is populated. Skip reasons name what the reviewer
    needs to know (size limit breach, missing file) — never drop the proof
    silently.
    """
    if not mp4_path:
        return None, "No MP4 line found in the GitHub issue comments."

    if not os.path.exists(mp4_path):
        return None, f"MP4 referenced in issue but not on disk: `{mp4_path}`"

    size = os.path.getsize(mp4_path)
    if size > ADO_ATTACHMENT_SIZE_LIMIT:
        mb = size / (1024 * 1024)
        limit_mb = ADO_ATTACHMENT_SIZE_LIMIT / (1024 * 1024)
        return (
            None,
            f"MP4 too large for ADO attachments ({mb:.1f} MB > {limit_mb:.0f} MB): `{mp4_path}`",
        )

    file_name = os.path.basename(mp4_path)
    url = ado_upload_pr_attachment(pr_id, mp4_path, file_name, pat)
    if not url:
        return None, f"MP4 upload failed (see agent log): `{mp4_path}`"
    return url, None


def create_pr(branch: str, target: str, issue: int, pat: str) -> tuple[int, str]:
    """Create ADO PR enriched with proofs from the GitHub issue.

    Flow:
    1. Fetch issue comments; extract MP4 path + FDS Verification text.
    2. Create the PR with a skeleton body.
    3. Upload the MP4 as an ADO attachment when possible.
    4. PATCH the PR description with the final body (attachment link +
       FDS text verbatim). Reviewers on ADO see everything inline —
       GitHub is private and they can't click through.
    """
    pr_title = branch.removeprefix("feature/").removeprefix("bugfix/")

    try:
        comment_bodies = gh_list_issue_comment_bodies(issue)
    except Exception as exc:
        print(f"[agent] Could not fetch GitHub comments for enrichment: {exc}", file=sys.stderr)
        comment_bodies = []

    mp4_path = extract_mp4_path(comment_bodies)
    fds_text = extract_fds_verification(comment_bodies)

    # Skeleton body omits the MP4 section entirely. If the PATCH below fails,
    # the description is incomplete but accurate — the reviewer sees "no MP4
    # listed" instead of a misleading "Upload in progress..." stuck forever.
    skeleton_body = build_pr_body(
        branch,
        issue,
        fds_verification=fds_text,
        mp4_attachment_url=None,
        mp4_skip_reason=None,
    )

    response = ado_post(
        f"/git/repositories/{ADO_REPO}/pullrequests?api-version=7.1",
        {
            "sourceRefName": f"refs/heads/{branch}",
            "targetRefName": f"refs/heads/{target}",
            "title": pr_title,
            "description": skeleton_body,
        },
        pat,
    )
    pr_id: int = response["pullRequestId"]
    pr_url = (
        f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}"
        f"/_git/{ADO_REPO}/pullrequest/{pr_id}"
    )

    attachment_url, skip_reason = attach_mp4_and_get_link(pr_id, mp4_path, pat)
    final_body = build_pr_body(
        branch,
        issue,
        fds_verification=fds_text,
        mp4_attachment_url=attachment_url,
        mp4_skip_reason=skip_reason,
    )
    if final_body != skeleton_body:
        if not ado_patch_pr_description(pr_id, final_body, pat):
            # Attachment may already be uploaded to ADO (visible in the "Files"
            # tab), but the PR body won't reference it. Surface the mismatch
            # prominently so the dev can retry the PATCH or patch by hand.
            print(
                f"⚠️  ADO PR #{pr_id} description PATCH failed — body missing "
                f"MP4 link / FDS text. See agent stderr log; retry manually "
                f"if needed.",
                file=sys.stderr,
            )

    return pr_id, pr_url


def get_pr_status(pr_id: int, pat: str) -> str:
    """Return PR status: active | completed | abandoned."""
    data = ado_get(
        f"/git/repositories/{ADO_REPO}/pullrequests/{pr_id}?api-version=7.1", pat
    )
    return str(data.get("status", "active"))


def get_build_statuses(pr_id: int, pat: str) -> list[dict[str, Any]]:
    """Return PR policy/build statuses (empty list on error)."""
    try:
        data = ado_get(
            f"/git/repositories/{ADO_REPO}/pullRequests/{pr_id}/statuses?api-version=7.1",
            pat,
        )
        return list(data.get("value", []))
    except Exception:
        return []


def get_pr_threads(pr_id: int, pat: str) -> list[dict[str, Any]]:
    """Return active comment threads on the ADO PR (empty list on error)."""
    try:
        data = ado_get(
            f"/git/repositories/{ADO_REPO}/pullRequests/{pr_id}/threads?api-version=7.1",
            pat,
        )
        threads: list[dict[str, Any]] = data.get("value", [])
        # Filter to non-system, active threads only
        return [
            t
            for t in threads
            if not t.get("isDeleted", False) and t.get("status") != "closed"
        ]
    except Exception:
        return []


# ─────────────────────────────────────────────
# GitHub REST API helpers (no subprocess)
# ─────────────────────────────────────────────


def _gh_headers() -> dict[str, str]:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GH_TOKEN or GITHUB_TOKEN must be set for GitHub API calls")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }


def gh_comment(issue: int, body: str) -> None:
    """Post a comment on a GitHub issue."""
    url = f"{GH_API_BASE}/issues/{issue}/comments"
    data = json.dumps({"body": body}).encode()
    req = urllib.request.Request(url, data=data, headers=_gh_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=30):
        pass


def _gh_get_role_labels(issue: int) -> list[str]:
    """Return current role: labels on the issue."""
    url = f"{GH_API_BASE}/issues/{issue}/labels"
    req = urllib.request.Request(url, headers=_gh_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        labels: list[dict[str, Any]] = json.loads(resp.read().decode())
    return [str(lbl["name"]) for lbl in labels if str(lbl["name"]).startswith("role:")]


def _gh_remove_label(issue: int, label: str) -> None:
    """Remove a label from a GitHub issue (ignore 404)."""
    encoded = urllib.parse.quote(label, safe="")
    url = f"{GH_API_BASE}/issues/{issue}/labels/{encoded}"
    req = urllib.request.Request(url, headers=_gh_headers(), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=30):
            pass
    except urllib.error.HTTPError:
        pass  # already removed or never existed


def _gh_ensure_label(label: str) -> None:
    """Create label if it does not exist (ignore 422 = already exists)."""
    url = f"{GH_API_BASE}/labels"
    data = json.dumps(
        {
            "name": label,
            "color": "D93F0B",
            "description": "Pipeline: waiting for ADO review",
        }
    ).encode()
    req = urllib.request.Request(url, data=data, headers=_gh_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30):
            pass
    except urllib.error.HTTPError:
        pass  # already exists


def _gh_add_label(issue: int, label: str) -> None:
    """Add a label to a GitHub issue."""
    url = f"{GH_API_BASE}/issues/{issue}/labels"
    data = json.dumps({"labels": [label]}).encode()
    req = urllib.request.Request(url, data=data, headers=_gh_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=30):
        pass


def gh_label_switch(issue: int, new_label: str) -> None:
    """Remove all role: labels and apply new_label."""
    for label in _gh_get_role_labels(issue):
        _gh_remove_label(issue, label)
    _gh_ensure_label(new_label)
    _gh_add_label(issue, new_label)


def gh_close(issue: int, body: str) -> None:
    """Post a comment then close the GitHub issue."""
    gh_comment(issue, body)
    url = f"{GH_API_BASE}/issues/{issue}"
    data = json.dumps({"state": "closed"}).encode()
    req = urllib.request.Request(url, data=data, headers=_gh_headers(), method="PATCH")
    with urllib.request.urlopen(req, timeout=30):
        pass


# ─────────────────────────────────────────────
# Build verification agent
# ─────────────────────────────────────────────


def verify_build(
    pr_id: int, pr_url: str, issue: int, pat: str, poll_interval: int
) -> bool:
    """Poll ADO PR + build + comment threads. Return True on merge, False on failure/abandon.

    When reviewer comments arrive:
    - Post a task summary on the GitHub issue so the dev sees what needs to be addressed
    - NEVER reply on the ADO PR — agent is read-only on ADO
    """
    print(f"[agent] Monitoring ADO PR #{pr_id} (build + merge + review comments)...")
    elapsed = 0
    seen_thread_ids: set[int] = set()

    while elapsed < MAX_WAIT:
        pr_status = get_pr_status(pr_id, pat)

        if pr_status == "completed":
            print("✅ ADO PR merged!")
            gh_close(
                issue,
                f"**Pipeline complete.** ADO PR [#{pr_id}]({pr_url}) merged.\n\nClosing issue.",
            )
            return True

        if pr_status == "abandoned":
            print("⚠️  ADO PR abandoned")
            gh_comment(
                issue,
                f"**ADO PR [#{pr_id}]({pr_url}) was abandoned.**\n\nManual review needed.",
            )
            return False

        # Check build/policy statuses
        statuses = get_build_statuses(pr_id, pat)
        if statuses:
            latest = statuses[-1]
            state = str(latest.get("state", "pending"))
            desc = str(latest.get("description", ""))
            print(f"  [{elapsed}s] Build: {state} — {desc}")

            if state == "failed":
                gh_comment(
                    issue,
                    f"❌ **Build failed** on ADO PR [#{pr_id}]({pr_url}).\n\n> {desc}\n\n"
                    "Fix in feature branch → push update → re-run `fivepoints ado-transition`.",
                )
                return False
        else:
            print(f"  [{elapsed}s] PR status: {pr_status}, waiting for build...")

        # Check for new reviewer comment threads on ADO PR
        # Agent is READ-ONLY on ADO — never replies to the PR.
        # New threads are surfaced as GitHub issue tasks for the dev to address.
        threads = get_pr_threads(pr_id, pat)
        new_threads = [t for t in threads if t.get("id") not in seen_thread_ids]
        if new_threads:
            task_lines = []
            for thread in new_threads:
                seen_thread_ids.add(int(thread.get("id", 0)))
                comments = thread.get("comments", [])
                if not comments:
                    continue
                first = comments[0]
                author = first.get("author", {}).get("displayName", "Reviewer")
                text = str(first.get("content", "")).strip()
                if text:
                    task_lines.append(f"- [ ] **{author}:** {text}")

            if task_lines:
                body = (
                    f"**📋 ADO PR [#{pr_id}]({pr_url}) — new review comments to address:**\n\n"
                    + "\n".join(task_lines)
                    + "\n\nFix in feature branch → push → re-run `fivepoints ado-transition`."
                )
                gh_comment(issue, body)
                print(
                    f"  [{elapsed}s] Posted {len(task_lines)} new review thread(s) to GitHub issue."
                )

        time.sleep(poll_interval)
        elapsed += poll_interval

    print("⏰ Build monitoring timed out after 2 hours")
    return False


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ADO build verification agent — PR creation + build + merge monitoring"
    )
    parser.add_argument("--issue", required=True, type=int, help="GitHub issue number")
    parser.add_argument(
        "--branch", required=True, help="Feature branch (already pushed to ADO)"
    )
    parser.add_argument(
        "--target", default="dev", help="ADO PR target branch (default: dev)"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=POLL_INTERVAL,
        help="Build poll interval in seconds",
    )
    args = parser.parse_args()

    pat = os.environ.get("AZURE_DEVOPS_WRITE_PAT") or os.environ.get(
        "AZURE_DEVOPS_PAT", ""
    )
    if not pat:
        print("❌ AZURE_DEVOPS_WRITE_PAT must be set", file=sys.stderr)
        return 1

    print(f"[agent] Creating ADO PR: {args.branch} → {args.target}")

    try:
        pr_id, pr_url = create_pr(args.branch, args.target, args.issue, pat)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"❌ Failed to create ADO PR (HTTP {exc.code}): {body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"❌ Failed to create ADO PR: {exc}", file=sys.stderr)
        return 1

    print(f"✅ ADO PR created: #{pr_id}")
    print(f"   URL: {pr_url}")

    gh_comment(
        args.issue,
        f"**ADO PR created:** [PR #{pr_id}]({pr_url})\n\n"
        f"Branch `{args.branch}` → `{args.target}`\n\n"
        "Build pipeline started — monitoring...",
    )
    gh_label_switch(args.issue, "role:ado-review")

    success = verify_build(pr_id, pr_url, args.issue, pat, args.poll_interval)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
