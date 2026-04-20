"""Unit tests for ado_agent enrichment helpers (issue #86).

Pure-function tests — no network, no ADO calls. Covers the parsing and body
assembly that carries FDS Verification + MP4 attachment info into the ADO PR
description (reviewers on ADO cannot access the GitHub mirror).
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from ado_agent import (  # noqa: E402
    ADO_ATTACHMENT_SIZE_LIMIT,
    FDS_SENTINEL,
    attach_mp4_and_get_link,
    build_pr_body,
    extract_fds_verification,
    extract_mp4_path,
)


# ---------------------------------------------------------------------------
# extract_mp4_path — mirrors check_proof_gate's matcher so the gate and
# the attachment code agree on what counts as a proof.
# ---------------------------------------------------------------------------


class TestExtractMp4Path:
    def test_matches_mp4_prefix(self):
        assert extract_mp4_path(["MP4: /tmp/proof.mp4"]) == "/tmp/proof.mp4"

    def test_matches_proof_prefix(self):
        assert extract_mp4_path(["Proof: /tmp/a.mp4"]) == "/tmp/a.mp4"

    def test_matches_recording_prefix(self):
        assert extract_mp4_path(["Recording: /tmp/r.mp4"]) == "/tmp/r.mp4"

    def test_matches_video_prefix(self):
        assert extract_mp4_path(["Video: /tmp/v.mp4"]) == "/tmp/v.mp4"

    def test_case_insensitive(self):
        assert extract_mp4_path(["video: /tmp/v.mp4"]) == "/tmp/v.mp4"
        assert extract_mp4_path(["PROOF: /tmp/p.mp4"]) == "/tmp/p.mp4"

    def test_returns_first_match_across_comments(self):
        # The first MP4 reference wins — matches how dev checklist expects
        # the [8/11] comment to be posted once per issue.
        assert extract_mp4_path(
            ["chit-chat", "Proof: /tmp/first.mp4", "Video: /tmp/second.mp4"]
        ) == "/tmp/first.mp4"

    def test_rejects_prose_mentioning_mp4(self):
        # Guard against false positives: discussion comments may mention
        # `.mp4` without intending it as a proof reference.
        assert (
            extract_mp4_path(
                ["Don't use ffmpeg — use the Playwright .mp4 recording instead."]
            )
            is None
        )

    def test_rejects_inline_backtick_reference(self):
        assert (
            extract_mp4_path(["See the `MP4:` line in the checklist for syntax."])
            is None
        )

    def test_returns_none_on_no_comments(self):
        assert extract_mp4_path([]) is None


# ---------------------------------------------------------------------------
# extract_fds_verification
# ---------------------------------------------------------------------------


class TestExtractFdsVerification:
    def test_returns_body_when_starts_with_sentinel(self):
        body = f"{FDS_SENTINEL}\n- Screen X: pass"
        assert extract_fds_verification([body]) == body

    def test_returns_none_when_sentinel_is_inline(self):
        # Guard against false positives: a discussion comment quoting the
        # sentinel in backticks must not satisfy the verification slot.
        body = f"Looking for `{FDS_SENTINEL}` headers in the issue."
        assert extract_fds_verification([body]) is None

    def test_returns_first_sentinel_match(self):
        b1 = f"{FDS_SENTINEL}\n- first"
        b2 = f"{FDS_SENTINEL}\n- second"
        assert extract_fds_verification(["intro", b1, b2]) == b1

    def test_returns_none_on_empty(self):
        assert extract_fds_verification([]) is None


# ---------------------------------------------------------------------------
# build_pr_body — the contract with ADO reviewers.
# ---------------------------------------------------------------------------


class TestBuildPrBody:
    def test_embeds_fds_verification_verbatim(self):
        fds = f"{FDS_SENTINEL}\n- Screen A: pass\n- Screen B: pass"
        body = build_pr_body(
            "feature/71-x",
            71,
            fds_verification=fds,
            mp4_attachment_url=None,
            mp4_skip_reason=None,
        )
        # The whole FDS block must appear inside the PR body so reviewers
        # see the checklist without accessing GitHub.
        assert fds in body

    def test_embeds_mp4_attachment_link_when_url_provided(self):
        body = build_pr_body(
            "feature/71-x",
            71,
            fds_verification=None,
            mp4_attachment_url="https://ado/x.mp4",
            mp4_skip_reason=None,
        )
        assert "[Download MP4 proof](https://ado/x.mp4)" in body

    def test_surfaces_skip_reason_when_mp4_not_attached(self):
        body = build_pr_body(
            "feature/71-x",
            71,
            fds_verification=None,
            mp4_attachment_url=None,
            mp4_skip_reason="MP4 too large (50 MB)",
        )
        # A missing/skipped proof must be visible to the reviewer, not
        # silently dropped — otherwise they trust a PR that lacks proof.
        assert "⚠️" in body
        assert "MP4 too large" in body

    def test_skips_mp4_and_fds_sections_when_neither_present(self):
        body = build_pr_body(
            "feature/71-x",
            71,
            fds_verification=None,
            mp4_attachment_url=None,
            mp4_skip_reason=None,
        )
        assert "MP4 Proof" not in body
        assert "FDS Verification" not in body

    def test_prefers_attachment_over_skip_reason(self):
        # If both are somehow supplied, the URL wins (truthy attachment).
        body = build_pr_body(
            "feature/71-x",
            71,
            fds_verification=None,
            mp4_attachment_url="https://ado/x.mp4",
            mp4_skip_reason="should be ignored",
        )
        assert "Download MP4 proof" in body
        assert "should be ignored" not in body

    def test_always_includes_branch_and_issue(self):
        body = build_pr_body(
            "feature/9999-abc",
            9999,
            fds_verification=None,
            mp4_attachment_url=None,
            mp4_skip_reason=None,
        )
        assert "feature/9999-abc" in body
        assert "#9999" in body


# ---------------------------------------------------------------------------
# attach_mp4_and_get_link — the guard paths that don't need network.
# ---------------------------------------------------------------------------


class TestAttachMp4AndGetLink:
    def test_returns_skip_reason_when_mp4_path_is_none(self):
        url, reason = attach_mp4_and_get_link(123, None, pat="unused")
        assert url is None
        assert reason is not None and "No MP4 line" in reason

    def test_returns_skip_reason_when_file_missing(self):
        url, reason = attach_mp4_and_get_link(
            123, "/nonexistent/path/proof.mp4", pat="unused"
        )
        assert url is None
        assert reason is not None and "not on disk" in reason

    def test_returns_skip_reason_when_file_too_large(self, tmp_path):
        # Sparse file of size > ADO_ATTACHMENT_SIZE_LIMIT — no real bytes
        # are written, just the size metadata, so the test is fast.
        big = tmp_path / "big.mp4"
        with open(big, "wb") as fh:
            fh.seek(ADO_ATTACHMENT_SIZE_LIMIT + 1)
            fh.write(b"\0")

        url, reason = attach_mp4_and_get_link(123, str(big), pat="unused")
        assert url is None
        assert reason is not None and "too large" in reason
