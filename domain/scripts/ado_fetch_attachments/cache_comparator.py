"""MD5-based cache drift detection and section-level text diff."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_CHUNK = 64 * 1024


def md5_file(path: Path) -> str:
    """Return the hex MD5 of a file, streaming to avoid loading large docx into memory."""
    digest = hashlib.md5()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class CacheComparison:
    cached_path: Path | None
    cached_md5: str | None
    fresh_path: Path
    fresh_md5: str
    match: bool

    @property
    def status(self) -> str:
        if self.cached_path is None:
            return "missing"
        return "match" if self.match else "drift"


def compare_to_cache(fresh: Path, cached: Path | None) -> CacheComparison:
    fresh_md5 = md5_file(fresh)
    if cached is None or not cached.is_file():
        return CacheComparison(
            cached_path=cached,
            cached_md5=None,
            fresh_path=fresh,
            fresh_md5=fresh_md5,
            match=False,
        )
    cached_md5 = md5_file(cached)
    return CacheComparison(
        cached_path=cached,
        cached_md5=cached_md5,
        fresh_path=fresh,
        fresh_md5=fresh_md5,
        match=cached_md5 == fresh_md5,
    )


def resolve_cache_path(cache_dir: Path, attachment_name: str) -> Path | None:
    """Map an attachment filename to the canonical domain cache path.

    Examples:
      '4 - Client Management(1).docx' -> FDS_CLIENT_MANAGEMENT.docx
      'Education.docx'                -> FDS_EDUCATION.docx

    Returns None if no cached counterpart exists.
    """
    stem = Path(attachment_name).stem
    stem = re.sub(r"\([^)]*\)", "", stem)
    stem = re.sub(r"^\s*\d+\s*[-_]\s*", "", stem)
    token = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_").upper()
    if not token:
        return None
    candidate = cache_dir / f"FDS_{token}.docx"
    if candidate.is_file():
        return candidate
    for path in cache_dir.glob("FDS_*.docx"):
        if token in path.stem.upper():
            return path
    return None


@dataclass
class SectionDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    common: list[str] = field(default_factory=list)

    def has_changes(self) -> bool:
        return bool(self.added or self.removed)


def diff_sections(cached_sections: list[str], fresh_sections: list[str]) -> SectionDiff:
    cached_set = set(cached_sections)
    fresh_set = set(fresh_sections)
    return SectionDiff(
        added=[s for s in fresh_sections if s not in cached_set],
        removed=[s for s in cached_sections if s not in fresh_set],
        common=[s for s in fresh_sections if s in cached_set],
    )
