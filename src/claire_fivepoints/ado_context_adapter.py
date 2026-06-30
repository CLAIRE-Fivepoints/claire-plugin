"""ADO context adapter — fetch work item and download attachments for DevWithADOContextStep.

ADOContextAdapter  Protocol — interface the step depends on
RealADOContextAdapter — calls ADO REST API with AZURE_DEVOPS_PAT
MockADOContextAdapter — injects fixtures for tests
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from claire_adapters.token import CONFIG_DIR, find_repo_entry, parse_env_file
from claire_core.logging_config import get_logger

logger = get_logger(__name__)

_API_VERSION = "7.1"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ADOContextAdapter(Protocol):
    """Read ADO work item data and download its attachments."""

    def fetch_work_item(self, org: str, project: str, item_id: int) -> dict:
        """Return the full work item dict (fields, relations, …)."""
        ...

    def download_attachments(
        self, org: str, project: str, item_id: int, dest: Path
    ) -> list[Path]:
        """Download all AttachedFile relations to *dest*; return paths written."""
        ...


# ---------------------------------------------------------------------------
# Real adapter
# ---------------------------------------------------------------------------


@dataclass
class RealADOContextAdapter:
    """Calls the ADO REST API with AZURE_DEVOPS_PAT."""

    pat: str

    @classmethod
    def for_repo(
        cls, repo: str, config_dir: Path | None = None
    ) -> "RealADOContextAdapter":
        _config_dir = config_dir if config_dir is not None else CONFIG_DIR
        env = parse_env_file(_config_dir / "github_manager.env")
        shared_env = parse_env_file(_config_dir / ".env")
        pat = (
            env.get("AZURE_DEVOPS_PAT")
            or shared_env.get("AZURE_DEVOPS_PAT")
            or os.environ.get("AZURE_DEVOPS_PAT", "")
        )
        return cls(pat=pat)

    def fetch_work_item(self, org: str, project: str, item_id: int) -> dict:
        import requests

        url = (
            f"https://dev.azure.com/{org}/{project}"
            f"/_apis/wit/workitems/{item_id}"
        )
        params = {"$expand": "all", "api-version": _API_VERSION}
        response = requests.get(url, params=params, auth=("", self.pat), timeout=30)
        response.raise_for_status()
        result: dict = response.json()
        logger.info(
            "ado_context.fetch_work_item.done",
            extra={"org": org, "project": project, "item_id": item_id},
        )
        return result

    def download_attachments(
        self, org: str, project: str, item_id: int, dest: Path
    ) -> list[Path]:
        import re

        import requests

        work_item = self.fetch_work_item(org, project, item_id)
        relations = work_item.get("relations") or []

        dest.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for rel in relations:
            if rel.get("rel") != "AttachedFile":
                continue
            url = rel.get("url")
            attrs = rel.get("attributes") or {}
            name = attrs.get("name") or "attachment"
            if not url:
                logger.warning("ado_context.attachment.no_url name=%s", name)
                continue

            safe_name = re.sub(r"[^\w.\-]+", "_", name)
            file_path = dest / safe_name

            params = {"api-version": _API_VERSION}
            with requests.get(
                url, params=params, auth=("", self.pat), stream=True, timeout=120
            ) as resp:
                resp.raise_for_status()
                with file_path.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            fh.write(chunk)

            paths.append(file_path)
            logger.info(
                "ado_context.download.done",
                extra={"name": name, "path": str(file_path)},
            )

        return paths


# ---------------------------------------------------------------------------
# Mock adapter
# ---------------------------------------------------------------------------


@dataclass
class MockADOContextAdapter:
    """Injectable fixture for unit tests — no network calls."""

    work_item: dict = field(default_factory=dict)
    attachments: list[Path] = field(default_factory=list)

    def fetch_work_item(self, org: str, project: str, item_id: int) -> dict:
        return self.work_item

    def download_attachments(
        self, org: str, project: str, item_id: int, dest: Path
    ) -> list[Path]:
        dest.mkdir(parents=True, exist_ok=True)
        return list(self.attachments)
