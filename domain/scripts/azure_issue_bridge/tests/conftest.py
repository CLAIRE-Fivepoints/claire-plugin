"""
conftest.py — pytest bootstrap for azure_issue_bridge tests.

Installs minimal stubs for claire_py (a V1 library not available in this
environment) so that patch() can resolve "claire_py.email.watcher.*" without
requiring the full V1 install.
"""

from __future__ import annotations

import sys
import types


def _install_claire_py_stubs() -> None:
    if "claire_py" in sys.modules:
        return

    claire_py = types.ModuleType("claire_py")
    claire_py_email = types.ModuleType("claire_py.email")
    claire_py_email_watcher = types.ModuleType("claire_py.email.watcher")
    claire_py_email_auth = types.ModuleType("claire_py.email.auth")

    claire_py_email_watcher.list_unread_replies = lambda *a, **kw: []  # type: ignore[attr-defined]
    claire_py_email_auth.get_credentials = lambda *a, **kw: None  # type: ignore[attr-defined]

    claire_py.email = claire_py_email  # type: ignore[attr-defined]
    claire_py_email.watcher = claire_py_email_watcher  # type: ignore[attr-defined]
    claire_py_email.auth = claire_py_email_auth  # type: ignore[attr-defined]

    sys.modules["claire_py"] = claire_py
    sys.modules["claire_py.email"] = claire_py_email
    sys.modules["claire_py.email.watcher"] = claire_py_email_watcher
    sys.modules["claire_py.email.auth"] = claire_py_email_auth


_install_claire_py_stubs()
