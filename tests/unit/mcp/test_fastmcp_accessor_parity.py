# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""The two FastMCP accessors MUST agree on path and message (#1996).

``kailash.mcp_compat.get_fastmcp_class`` (core) and
``kailash_mcp.platform_server._get_fastmcp_class`` (the kailash-mcp platform
server) both resolve the SAME third-party class. They are deliberately two
functions rather than one shared helper — ``kailash-mcp`` declares
``kailash>=2.56.0``, and importing a core module added after that floor would
break every install within the declared range.

Two copies drift. These tests are the tripwire that makes drift loud: they pin
the import PATH structurally (via AST, so a refactor that moves the import is
still checked) and the error MESSAGE byte-for-byte.

Why ``mcp.server`` is the agreed path: on ``mcp`` 1.x both ``mcp.server`` and
``mcp.server.fastmcp`` resolve to the same class, but ``mcp`` 2.0.0 deletes the
``mcp.server.fastmcp`` submodule outright while ``mcp/server/__init__.py``
survives with an explicit ``__all__``.
"""

import ast
import inspect
import textwrap

import pytest

from kailash import mcp_compat

platform_server = pytest.importorskip(
    "kailash_mcp.platform_server",
    reason="kailash-mcp package required for accessor-parity tests",
)

#: The one import path both accessors must use.
AGREED_IMPORT_MODULE = "mcp.server"
AGREED_IMPORT_NAME = "FastMCP"


def _fastmcp_import_paths(func) -> list[tuple[str, tuple[str, ...]]]:
    """Return every ``from X import Y`` inside ``func`` that imports FastMCP."""
    # textwrap.dedent, NOT inspect.cleandoc — cleandoc strips the indentation of
    # every line after the first, which corrupts a function body into an
    # IndentationError.
    source = textwrap.dedent(inspect.getsource(func))
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = tuple(alias.name for alias in node.names)
            if AGREED_IMPORT_NAME in names:
                found.append((node.module or "", names))
    return found


class TestImportPathParity:
    def test_core_accessor_imports_from_the_agreed_path(self):
        paths = _fastmcp_import_paths(mcp_compat.get_fastmcp_class)
        assert paths == [(AGREED_IMPORT_MODULE, (AGREED_IMPORT_NAME,))]

    def test_platform_server_accessor_imports_from_the_agreed_path(self):
        paths = _fastmcp_import_paths(platform_server._get_fastmcp_class)
        assert paths == [(AGREED_IMPORT_MODULE, (AGREED_IMPORT_NAME,))]

    def test_neither_accessor_uses_the_deleted_2x_submodule(self):
        """``mcp.server.fastmcp`` does not exist in mcp 2.x — it must not appear."""
        for func in (
            mcp_compat.get_fastmcp_class,
            platform_server._get_fastmcp_class,
        ):
            for module, _names in _fastmcp_import_paths(func):
                assert module != "mcp.server.fastmcp", (
                    f"{func.__qualname__} imports FastMCP from the "
                    f"mcp.server.fastmcp submodule, which mcp 2.x deletes"
                )


class TestErrorMessageParity:
    def test_messages_are_byte_identical(self):
        assert (
            platform_server.FASTMCP_IMPORT_ERROR_MESSAGE
            == mcp_compat.FASTMCP_IMPORT_ERROR_MESSAGE
        )

    def test_message_is_actionable(self):
        message = mcp_compat.FASTMCP_IMPORT_ERROR_MESSAGE
        assert "mcp" in message
        assert "pip install" in message


class TestResolvedClassParity:
    def test_both_accessors_return_the_same_class(self):
        assert platform_server._get_fastmcp_class() is mcp_compat.get_fastmcp_class()
