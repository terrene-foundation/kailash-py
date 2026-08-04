# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-1 guards for the TrustPlane MCP server's optional-``mcp`` boundary (#1996).

``mcp`` is an OPTIONAL extra. Before #1996 this module did
``from mcp.server import FastMCP`` at module scope and built ``FastMCP(...)`` at
import time, so a bare ``pip install kailash`` made the module un-importable with
a bare, unactionable ``ImportError``.

These tests simulate the dependency being absent WITHOUT uninstalling it, by
poisoning ``sys.modules`` (an entry set to ``None`` makes ``import`` raise), and
assert both halves of the contract: the module still imports, and the typed,
actionable error is raised at USE time.
"""

import importlib
import sys
from contextlib import contextmanager
from unittest import mock

import pytest

from kailash.mcp_compat import FASTMCP_IMPORT_ERROR_MESSAGE

MODULE = "kailash.trust.plane.mcp_server"


@contextmanager
def mcp_package_absent():
    """Make every ``mcp`` import raise ImportError, then restore ``sys.modules``.

    ``mock.patch.dict(sys.modules)`` snapshots and restores the whole mapping, so
    the real ``mcp`` package (and any module re-imported under the poisoned
    state) is fully restored on exit.
    """
    with mock.patch.dict(sys.modules):
        for name in list(sys.modules):
            if name == "mcp" or name.startswith("mcp."):
                sys.modules[name] = None
        sys.modules["mcp"] = None
        sys.modules["mcp.server"] = None
        yield


@contextmanager
def freshly_imported_without_mcp():
    """Re-import the trust-plane MCP server from scratch with ``mcp`` absent."""
    with mcp_package_absent():
        sys.modules.pop(MODULE, None)
        yield importlib.import_module(MODULE)


class TestImportSucceedsWithoutMcp:
    """AC: module import no longer executes ``FastMCP(...)`` when ``mcp`` is absent."""

    def test_module_imports_when_mcp_is_absent(self):
        with freshly_imported_without_mcp() as mod:
            assert mod.__name__ == MODULE

    def test_import_does_not_build_the_server(self):
        with freshly_imported_without_mcp() as mod:
            assert mod._server is None, (
                "importing the module built the FastMCP server; construction "
                "must be deferred to first use"
            )

    def test_tool_functions_are_importable_without_mcp(self):
        """The tool coroutines are plain functions — no decorator, no dependency."""
        with freshly_imported_without_mcp() as mod:
            for _func, name, _description in mod.TOOL_SPECS:
                assert callable(getattr(mod, name))


class TestTypedErrorWhenMcpAbsent:
    """AC: a guarded accessor raises a typed, actionable ImportError."""

    def test_get_server_raises_actionable_import_error(self):
        with freshly_imported_without_mcp() as mod:
            with pytest.raises(ImportError) as excinfo:
                mod.get_server()
            assert str(excinfo.value) == FASTMCP_IMPORT_ERROR_MESSAGE

    def test_error_names_the_package_and_the_install_command(self):
        """The message must be ACTIONABLE, not merely typed."""
        with freshly_imported_without_mcp() as mod:
            with pytest.raises(ImportError) as excinfo:
                mod.get_server()
            message = str(excinfo.value)
            assert "mcp" in message
            assert "pip install" in message

    def test_original_import_error_is_chained_as_cause(self):
        """`raise ... from exc` keeps the real failure available for debugging."""
        with freshly_imported_without_mcp() as mod:
            with pytest.raises(ImportError) as excinfo:
                mod.get_server()
            assert isinstance(excinfo.value.__cause__, ImportError)

    def test_lazy_mcp_attribute_raises_the_same_error(self):
        """The historical ``mcp_server.mcp`` surface fails the same actionable way."""
        with freshly_imported_without_mcp() as mod:
            with pytest.raises(ImportError) as excinfo:
                mod.mcp
            assert str(excinfo.value) == FASTMCP_IMPORT_ERROR_MESSAGE

    def test_failed_build_does_not_cache_a_broken_server(self):
        with freshly_imported_without_mcp() as mod:
            with pytest.raises(ImportError):
                mod.get_server()
            assert mod._server is None


class TestCompatAccessorDirectly:
    def test_get_fastmcp_class_raises_actionable_error(self):
        from kailash.mcp_compat import get_fastmcp_class

        with mcp_package_absent():
            with pytest.raises(ImportError) as excinfo:
                get_fastmcp_class()
            assert str(excinfo.value) == FASTMCP_IMPORT_ERROR_MESSAGE

    def test_get_fastmcp_class_returns_the_class_when_present(self):
        from mcp.server import FastMCP

        from kailash.mcp_compat import get_fastmcp_class

        assert get_fastmcp_class() is FastMCP


class TestServerBuildsWhenMcpPresent:
    """The deferral must not have lost any registration."""

    def test_get_server_registers_every_tool_spec(self):
        import kailash.trust.plane.mcp_server as mod

        server = mod.get_server()
        registered = set(server._tool_manager._tools)
        expected = {name for _func, name, _description in mod.TOOL_SPECS}

        assert expected == {
            "trust_check",
            "trust_record",
            "trust_envelope",
            "trust_status",
            "trust_verify",
        }
        assert registered == expected

    def test_registered_descriptions_match_the_specs(self):
        import kailash.trust.plane.mcp_server as mod

        tools = mod.get_server()._tool_manager._tools
        for _func, name, description in mod.TOOL_SPECS:
            assert tools[name].description == description

    def test_get_server_is_a_singleton(self):
        import kailash.trust.plane.mcp_server as mod

        assert mod.get_server() is mod.get_server()
        assert mod.mcp is mod.get_server()

    def test_unknown_attribute_still_raises_attribute_error(self):
        """PEP 562 ``__getattr__`` must not swallow genuine typos."""
        import kailash.trust.plane.mcp_server as mod

        with pytest.raises(AttributeError):
            mod.definitely_not_an_attribute
