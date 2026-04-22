# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W14b Tier-1 unit tests — :class:`AbstractTrackerStore` Protocol conformance.

Per ``specs/ml-tracking.md`` §6 the SQLite + PostgreSQL backends MUST
be interchangeable; that promise is cashed as ``isinstance(x,
AbstractTrackerStore) is True`` for both implementations. These tests
are deliberately lightweight — no DB connections, no fixtures — so
the Protocol contract itself is the gate.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from kailash_ml.tracking import (
    AbstractTrackerStore,
    PostgresTrackerStore,
    SqliteTrackerStore,
)


def test_sqlite_store_satisfies_protocol(tmp_path: Path) -> None:
    """A constructed SQLite store MUST pass the runtime Protocol check."""
    store = SqliteTrackerStore(tmp_path / "tracker.db")
    assert isinstance(store, AbstractTrackerStore), (
        "SqliteTrackerStore no longer satisfies AbstractTrackerStore — "
        "a method was likely removed or renamed; re-derive the Protocol "
        "from storage/base.py and restore parity."
    )


def test_postgres_store_satisfies_protocol(tmp_path: Path) -> None:
    """A constructed Postgres store MUST pass the runtime Protocol check.

    The store is NOT initialised here (no network access in Tier 1);
    the Protocol check inspects the method surface only.
    """
    store = PostgresTrackerStore(
        "postgresql://user:pass@localhost:5432/_not_used_",
        artifact_root=tmp_path / "artifacts",
    )
    assert isinstance(store, AbstractTrackerStore), (
        "PostgresTrackerStore no longer satisfies AbstractTrackerStore — "
        "a method was likely removed or renamed; re-derive the Protocol "
        "from storage/base.py and restore parity."
    )


def test_sqlite_artifact_root_resolves_to_directory(tmp_path: Path) -> None:
    """``SqliteTrackerStore.artifact_root`` MUST return a directory path
    — the runner's ``_hash_and_materialise_artifact`` treats it as one.
    """
    store = SqliteTrackerStore(tmp_path / "tracker.db")
    root = store.artifact_root
    assert root is not None
    assert Path(root).name == "artifacts"


def test_postgres_artifact_root_is_explicit(tmp_path: Path) -> None:
    """``PostgresTrackerStore.artifact_root`` MUST echo the path the
    caller supplied — the Postgres backend has no natural on-disk
    counterpart to a SQLite DB file."""
    root_dir = tmp_path / "pg-artifacts"
    store = PostgresTrackerStore(
        "postgresql://user:pass@localhost:5432/_not_used_",
        artifact_root=root_dir,
    )
    assert store.artifact_root == str(root_dir)
    assert root_dir.is_dir(), "constructor MUST create the artifact root"


def test_postgres_empty_url_is_blocked() -> None:
    """An empty URL MUST raise at construction time."""
    with pytest.raises(ValueError, match="non-empty URL"):
        PostgresTrackerStore("", artifact_root="/tmp/_unused")
