"""Regression prevention tests for SQLite concurrency invariants (TODO-024).

Static analysis tests that catch regressions:
1. Query routing correctness
2. No bare aiosqlite.connect() calls outside pool (IS-5)

Async pool tests (WAL mode, shared-cache, bounded concurrency, stress) moved to
tests/tier2_integration/runtime/test_sqlite_invariants_async.py.
"""

import re
from pathlib import Path

import pytest

from kailash.core.pool.sqlite_pool import (
    _is_read_query,
)


class TestQueryRoutingInvariants:
    """Verify query routing doesn't regress."""

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("SELECT 1", True),
            ("select * from t", True),
            ("WITH cte AS (SELECT 1) SELECT * FROM cte", True),
            ("EXPLAIN SELECT 1", True),
            ("PRAGMA table_info(t)", True),
            ("PRAGMA journal_mode = WAL", False),
            ("INSERT INTO t VALUES (1)", False),
            ("UPDATE t SET x = 1", False),
            ("DELETE FROM t", False),
            ("CREATE TABLE t (id INT)", False),
            ("DROP TABLE t", False),
            ("ALTER TABLE t ADD COLUMN x INT", False),
            ("BEGIN", False),
            ("COMMIT", False),
            ("ROLLBACK", False),
            ("-- comment\nSELECT 1", True),
            ("/* block */ SELECT 1", True),
            ("", False),
        ],
    )
    def test_query_routing(self, query, expected):
        assert _is_read_query(query) is expected


class TestNoDirectAiosqliteConnect:
    """Static analysis: no bare aiosqlite.connect() outside the pool (IS-5).

    The pool is the single sanctioned entry point for SQLite connections.
    Direct aiosqlite.connect() calls bypass concurrency controls and cause
    'database is locked' errors.
    """

    # Directories that MUST route through the pool
    _SCAN_DIRS = [
        "src/kailash/nodes/data",
        "packages/kailash-dataflow/src/dataflow/adapters",
    ]

    # Files that are ALLOWED to call aiosqlite.connect() directly
    _ALLOWED_FILES = {
        "sqlite_pool.py",  # The pool itself
        "persistent_tiers.py",  # Kaizen memory tiers (standalone DBs)
        "async_sql.py",  # SQLiteAdapter base class (connection factory)
        "async_connection.py",  # Connection utilities
        "sqlite.py",  # DataFlow SQLite adapter (wraps connections)
        "sqlite_enterprise.py",  # DataFlow enterprise adapter (wraps connections)
    }

    # Pattern for bare aiosqlite.connect() calls
    _PATTERN = re.compile(r"aiosqlite\.connect\s*\(")

    def _find_repo_root(self) -> Path:
        """Walk up from this test file to find the repo root."""
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "src").is_dir() and (parent / "packages").is_dir():
                return parent
        pytest.skip("Cannot locate repo root")

    def test_no_bare_aiosqlite_connect(self):
        """No bare aiosqlite.connect() in adapter/node code outside allowed files."""
        root = self._find_repo_root()
        violations = []

        for scan_dir in self._SCAN_DIRS:
            dir_path = root / scan_dir
            if not dir_path.is_dir():
                continue
            for py_file in dir_path.rglob("*.py"):
                if py_file.name in self._ALLOWED_FILES:
                    continue
                content = py_file.read_text()
                matches = list(self._PATTERN.finditer(content))
                if matches:
                    for m in matches:
                        line_no = content[: m.start()].count("\n") + 1
                        violations.append(f"{py_file.relative_to(root)}:{line_no}")

        assert (
            violations == []
        ), f"Found bare aiosqlite.connect() calls outside pool:\n" + "\n".join(
            f"  - {v}" for v in violations
        )
