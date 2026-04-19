"""Streaming MD5 helper for docx files.

Named ``cache_comparator`` for historical reasons — when the plugin cached FDS
docx files in git, this module compared the live PBI attachment against the
cached copy. The cache-in-git model is gone (issue #51 — fetch-on-use); only
``md5_file`` remains, now used to produce the ``docx_md5`` field of the manifest
and to dedupe re-extraction when the staging copy already matches the live docx.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

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
