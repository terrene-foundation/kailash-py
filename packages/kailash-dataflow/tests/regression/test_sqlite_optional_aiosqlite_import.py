# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test: the SQLite adapter MUST import without the optional
``aiosqlite`` driver (F-AIOSQLITE).

``aiosqlite`` is an OPT-IN driver declared under the ``kailash-dataflow[sqlite]``
extra — NOT a core dependency. Before the fix, ``adapters/sqlite.py`` did a
module-scope ``import aiosqlite`` that ``adapters/__init__.py`` eagerly pulls in
(``from .sqlite import SQLiteAdapter``). On a clean ``pip install kailash-dataflow``
without the ``[sqlite]`` extra, ``import dataflow.adapters`` — and any code that
imports the public ``SQLiteAdapter`` from ``dataflow.adapters.__all__`` — raised
``ModuleNotFoundError: No module named 'aiosqlite'``.

The fix mirrors the deferred-driver pattern the MongoDB / pgvector sibling
adapters use: the class object imports cleanly (a lazy stub is bound when the
driver is absent), and the descriptive ``ImportError`` surfaces at the connect
boundary via ``_require_aiosqlite()`` — the "loud failure at call site"
``rules/dependencies.md`` permits for optional extras.

Because ``aiosqlite`` IS installed in the dev/test environment, the clean-install
condition is reproduced faithfully in a subprocess that installs a ``meta_path``
finder rejecting the ``aiosqlite`` import — a boundary-injected fixture
(``user-flow-validation.md`` MUST-7) rather than a mock of the import machinery.
"""

import subprocess
import sys
import textwrap

import pytest

# Reproduces a clean install WITHOUT the [sqlite] extra: a meta_path finder that
# raises ImportError for aiosqlite, exactly as a missing package would.
_BLOCKER = textwrap.dedent(
    """
    import sys

    class _AiosqliteBlocker:
        def find_spec(self, name, path, target=None):
            # A genuinely-absent module raises ModuleNotFoundError (subclass of
            # ImportError). Match that exactly so the fixture reproduces a real
            # clean install, not a broken-but-installed package.
            if name == "aiosqlite" or name.startswith("aiosqlite."):
                raise ModuleNotFoundError("No module named 'aiosqlite' (simulated clean install)")
            return None

    sys.meta_path.insert(0, _AiosqliteBlocker())
    """
)


def _run(body: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", _BLOCKER + textwrap.dedent(body)],
        capture_output=True,
        text=True,
    )


@pytest.mark.regression
def test_dataflow_adapters_import_without_aiosqlite():
    """``import dataflow.adapters`` + public ``SQLiteAdapter`` import cleanly
    when aiosqlite is absent."""
    result = _run(
        """
        import dataflow.adapters
        from dataflow.adapters import SQLiteAdapter
        # Constructing the adapter must NOT require the driver either.
        SQLiteAdapter("sqlite:///:memory:")
        print("IMPORT_OK")
        """
    )
    assert result.returncode == 0, (
        f"import failed without aiosqlite:\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "IMPORT_OK" in result.stdout


@pytest.mark.regression
def test_sqlite_connect_fails_fast_without_aiosqlite():
    """``SQLiteAdapter.connect()`` raises a descriptive ImportError up front
    (not a swallowed pool warning, not a deferred first-query failure) when
    aiosqlite is absent."""
    result = _run(
        """
        import asyncio
        from dataflow.adapters import SQLiteAdapter

        adapter = SQLiteAdapter("sqlite:///:memory:")
        try:
            asyncio.run(adapter.connect())
        except ImportError as e:
            assert "aiosqlite" in str(e)
            assert "kailash-dataflow[sqlite]" in str(e)
            print("FAILED_FAST_OK")
        else:
            raise AssertionError("connect() did not fail fast without aiosqlite")
        """
    )
    assert result.returncode == 0, (
        f"connect() did not fail fast as expected:\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "FAILED_FAST_OK" in result.stdout
