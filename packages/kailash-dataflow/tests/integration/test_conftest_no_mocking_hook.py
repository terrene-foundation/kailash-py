# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the integration-tier NO-MOCKING hook.

The hook (``packages/kailash-dataflow/tests/integration/conftest.py::
_module_imports_unittest_mock``) was over-broad in its first cut — it
treated ANY ``unittest.mock`` import as a mocking primitive, which
flagged real-infrastructure tests that import ``ANY`` (the
argument-equality sentinel, NOT a mocking primitive). The hook was
refined per issue #979 S3 Finding C to whitelist non-primitive exports
of ``unittest.mock``.

These tests exercise the hook directly across the import shapes that
matter: pure-ANY imports PASS (false-positive class closed); primitive
imports FAIL (real mocking is still blocked); module-level rebinds
FAIL (downstream primitive use unauditable).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tests.integration.conftest import _module_imports_unittest_mock

# pytest-collectstart skips conftest path checks for tests collected
# elsewhere; these tests run as standard tier-2 collection by calling
# the helper directly with synthetic source files.


@pytest.fixture
def write_source(tmp_path: Path):
    """Return a helper that writes a synthetic .py file under tmp_path."""

    def _write(name: str, body: str) -> Path:
        path = tmp_path / name
        path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
        return path

    return _write


# ---------------------------------------------------------------------------
# WHITELIST — non-primitive imports MUST pass (the false-positive class)
# ---------------------------------------------------------------------------


def test_any_only_import_passes(write_source):
    """`from unittest.mock import ANY` is legal real-infra usage."""
    path = write_source(
        "test_any_only.py",
        """
        from unittest.mock import ANY

        def test_something():
            assert {"x": 1} == {"x": ANY}
        """,
    )
    assert _module_imports_unittest_mock(path) is False


def test_sentinel_only_import_passes(write_source):
    """`from unittest.mock import sentinel` is legal real-infra usage."""
    path = write_source(
        "test_sentinel_only.py",
        """
        from unittest.mock import sentinel

        UNSET = sentinel.UNSET
        """,
    )
    assert _module_imports_unittest_mock(path) is False


def test_call_only_import_passes(write_source):
    """`from unittest.mock import call` for partial-call matching is legal."""
    path = write_source(
        "test_call_only.py",
        """
        from unittest.mock import call
        """,
    )
    assert _module_imports_unittest_mock(path) is False


def test_multi_non_primitive_import_passes(write_source):
    """Multiple non-primitives in one import statement all pass."""
    path = write_source(
        "test_multi_any.py",
        """
        from unittest.mock import ANY, sentinel, call, DEFAULT
        """,
    )
    assert _module_imports_unittest_mock(path) is False


# ---------------------------------------------------------------------------
# BLOCKLIST — primitive imports MUST fail (real mocking still blocked)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "primitive",
    [
        "Mock",
        "MagicMock",
        "AsyncMock",
        "NonCallableMock",
        "NonCallableMagicMock",
        "patch",
        "PropertyMock",
        "seal",
        "create_autospec",
    ],
)
def test_primitive_import_blocks(write_source, primitive):
    """Each primitive triggers the gate when imported from unittest.mock."""
    path = write_source(
        f"test_{primitive.lower()}.py",
        f"""
        from unittest.mock import {primitive}
        """,
    )
    assert _module_imports_unittest_mock(path) is True


def test_mixed_primitive_and_non_primitive_blocks(write_source):
    """One primitive in a mixed-import block triggers the gate."""
    path = write_source(
        "test_mixed.py",
        """
        from unittest.mock import ANY, MagicMock, sentinel
        """,
    )
    assert _module_imports_unittest_mock(path) is True


def test_wildcard_import_blocks(write_source):
    """`from unittest.mock import *` pulls primitives — must block."""
    path = write_source(
        "test_wildcard.py",
        """
        from unittest.mock import *
        """,
    )
    assert _module_imports_unittest_mock(path) is True


# ---------------------------------------------------------------------------
# MODULE REBIND — bare-module imports MUST fail (unauditable primitive use)
# ---------------------------------------------------------------------------


def test_from_unittest_import_mock_blocks(write_source):
    """`from unittest import mock` makes downstream mock.MagicMock unauditable."""
    path = write_source(
        "test_unittest_mock_rebind.py",
        """
        from unittest import mock

        def test_something():
            m = mock.MagicMock()  # primitive use is invisible to AST gate
            assert m is not None
        """,
    )
    assert _module_imports_unittest_mock(path) is True


def test_import_unittest_mock_as_alias_blocks(write_source):
    """`import unittest.mock as m` — same rebind class."""
    path = write_source(
        "test_unittest_mock_alias.py",
        """
        import unittest.mock as m
        """,
    )
    assert _module_imports_unittest_mock(path) is True


def test_bare_import_unittest_mock_blocks(write_source):
    """`import unittest.mock` — bare-module rebind."""
    path = write_source(
        "test_unittest_mock_bare.py",
        """
        import unittest.mock
        """,
    )
    assert _module_imports_unittest_mock(path) is True


# ---------------------------------------------------------------------------
# FALSE-POSITIVE GUARDS — strings and comments MUST NOT trigger
# ---------------------------------------------------------------------------


def test_docstring_mention_passes(write_source):
    """Docstrings mentioning unittest.mock do not trigger the gate."""
    path = write_source(
        "test_docstring.py",
        '''
        """Tests for real-infrastructure boundaries.

        This module does NOT import unittest.mock primitives. The string
        ``from unittest.mock import MagicMock`` appears only here in the
        docstring as a counter-example.
        """
        ''',
    )
    assert _module_imports_unittest_mock(path) is False


def test_comment_mention_passes(write_source):
    """Comments mentioning unittest.mock do not trigger the gate."""
    path = write_source(
        "test_comment.py",
        """
        # Reminder: from unittest.mock import MagicMock is forbidden here.
        import pytest
        """,
    )
    assert _module_imports_unittest_mock(path) is False


def test_no_mock_imports_passes(write_source):
    """Files with zero unittest.mock content pass trivially."""
    path = write_source(
        "test_clean.py",
        """
        import pytest

        def test_something():
            assert 1 + 1 == 2
        """,
    )
    assert _module_imports_unittest_mock(path) is False


# ---------------------------------------------------------------------------
# ROBUSTNESS — file errors do not raise, return False (fail-open on read)
# ---------------------------------------------------------------------------


def test_unreadable_path_returns_false(tmp_path: Path):
    """Non-existent paths return False (no crash)."""
    bogus = tmp_path / "does_not_exist.py"
    assert _module_imports_unittest_mock(bogus) is False


def test_syntax_error_returns_false(write_source):
    """Syntactically invalid files return False (no crash)."""
    path = write_source(
        "test_syntax_broken.py",
        """
        from unittest.mock import (((  # syntax error
        """,
    )
    assert _module_imports_unittest_mock(path) is False
