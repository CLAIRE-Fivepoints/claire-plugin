"""Azure DevOps REST client for attachment fetching.

PAT resolution mirrors the chain in `ado_common.sh`:
    AZURE_DEVOPS_WRITE_PAT → AZURE_DEVOPS_DEV_PAT → client config → .env → AZURE_DEVOPS_PAT

Read-only operations here need only the read-scoped PAT.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

_API_VERSION = "7.1"
_ENV_FILE = Path.home() / ".config" / "claire" / ".env"


@dataclass(frozen=True)
class AdoConfig:
    org: str
    project: str
    pat: str

    @property
    def base_url(self) -> str:
        return f"https://dev.azure.com/{self.org}/{self.project}/_apis"


@dataclass(frozen=True)
class Attachment:
    name: str
    url: str
    size: int | None = None


def _read_env_file(path: Path = _ENV_FILE) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    except OSError as e:
        logger.warning("Could not read env file %s: %s", path, e)
    return result


def resolve_pat(
    env: dict[str, str] | None = None,
    env_file: Path | None = None,
) -> str | None:
    """Resolve an Azure DevOps PAT following the documented priority chain.

    Priority (first non-empty wins):
      1. AZURE_DEVOPS_WRITE_PAT (env)
      2. AZURE_DEVOPS_DEV_PAT   (env)
      3. AZURE_DEVOPS_PAT       (env)
      4. AZURE_DEVOPS_WRITE_PAT / DEV_PAT / PAT in ~/.config/claire/.env
    """
    sources: list[dict[str, str]] = []
    sources.append(dict(os.environ) if env is None else dict(env))
    sources.append(_read_env_file(env_file or _ENV_FILE))

    keys = ("AZURE_DEVOPS_WRITE_PAT", "AZURE_DEVOPS_DEV_PAT", "AZURE_DEVOPS_PAT")
    for source in sources:
        for key in keys:
            value = source.get(key, "").strip()
            if value:
                return value
    return None


def fetch_work_item_relations(
    config: AdoConfig,
    pbi_id: int,
    session: requests.Session | None = None,
) -> list[dict]:
    """GET /_apis/wit/workitems/{id}?$expand=relations — returns relations[]."""
    url = f"{config.base_url}/wit/workitems/{pbi_id}"
    params = {"$expand": "relations", "api-version": _API_VERSION}
    http = session or requests.Session()
    response = http.get(url, params=params, auth=("", config.pat), timeout=30)
    response.raise_for_status()
    payload = response.json()
    return payload.get("relations") or []


def filter_attachments(relations: Iterable[dict]) -> list[Attachment]:
    """Keep only AttachedFile relations — strip the rest (parent links, PRs, etc.)."""
    attachments: list[Attachment] = []
    for rel in relations:
        if rel.get("rel") != "AttachedFile":
            continue
        url = rel.get("url")
        attrs = rel.get("attributes") or {}
        name = attrs.get("name") or "attachment"
        size = attrs.get("resourceSize")
        if not url:
            logger.warning("Attachment %r has no url, skipping", name)
            continue
        attachments.append(Attachment(name=name, url=url, size=size))
    return attachments


def download_attachment(
    attachment: Attachment,
    destination: Path,
    pat: str,
    session: requests.Session | None = None,
) -> Path:
    """Stream an attachment to disk and return the path written."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    http = session or requests.Session()
    with http.get(
        attachment.url,
        params={"api-version": _API_VERSION},
        auth=("", pat),
        stream=True,
        timeout=120,
    ) as response:
        response.raise_for_status()
        with destination.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    fh.write(chunk)
    return destination
