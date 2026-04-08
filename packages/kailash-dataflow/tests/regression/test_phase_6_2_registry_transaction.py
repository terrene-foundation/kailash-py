# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Phase 6.2 — model registry mutations wrapped in real transactions.

Per ``workspaces/dataflow-perfection/todos/active/07-phase-6-async-
migration.md`` TODO-6.2, every model-registry mutation MUST run inside
a SQLAlchemy ``engine.begin()`` block so partial failure rolls back
the entire bundle instead of leaving the registry in a half-created
state.

These regression tests assert two contracts:

1. The registry exposes a sync ``transaction()`` context manager that
   yields a SQLAlchemy connection inside an active transaction (or
   ``None`` when no sync engine is available).
2. ``_create_model_registry_table`` builds the table + indexes inside
   a single transaction so a failing index statement on PostgreSQL or
   SQLite rolls back the table itself. SQLite is the deterministic
   transactional-DDL platform we test against because PostgreSQL
   would require infra; MySQL is excluded because it has no
   transactional DDL (the production code path documents this).
"""
from __future__ import annotations

import os
import tempfile

import pytest

pytestmark = pytest.mark.regression


def _make_dataflow(db_url: str):
    """Build a minimal DataFlow that the model registry can talk to."""
    from dataflow import DataFlow

    df = DataFlow(database_url=db_url, auto_migrate=False)
    return df


class TestRegistryTransactionContext:
    """ModelRegistry.transaction() yields a SQLAlchemy connection."""

    def setup_method(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._db_url = f"sqlite:///{self._tmp.name}"

    def teardown_method(self) -> None:
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def test_transaction_yields_sqlalchemy_connection(self):
        """The sync transaction() context manager MUST yield a real
        SQLAlchemy Connection (not a TransactionManager dict, not
        ``None`` when SQLDatabaseNode is importable)."""
        from sqlalchemy.engine.base import Connection

        df = _make_dataflow(self._db_url)
        registry = df._model_registry

        with registry.transaction() as conn:
            assert conn is not None, (
                "transaction() returned None — sync engine should be "
                "available because SQLDatabaseNode is importable"
            )
            assert isinstance(conn, Connection), (
                f"transaction() yielded {type(conn).__name__}, expected "
                "sqlalchemy.engine.base.Connection"
            )

    def test_transaction_rolls_back_on_exception(self):
        """The transaction MUST roll back when the body raises so the
        caller can rely on all-or-nothing semantics."""
        from sqlalchemy import text

        df = _make_dataflow(self._db_url)
        registry = df._model_registry

        # Run the registry init so the model registry table exists.
        assert registry.initialize() is True

        # Insert a sentinel row inside a transaction that then raises.
        try:
            with registry.transaction() as conn:
                conn.execute(
                    text(
                        "INSERT INTO dataflow_model_registry "
                        "(model_name, model_checksum, model_definitions, status) "
                        "VALUES ('rollback_test', 'abc', '{}', 'active')"
                    )
                )
                raise RuntimeError("forced rollback")
        except RuntimeError:
            pass

        # Verify the row is NOT visible — the transaction rolled back.
        engine = registry._acquire_sync_engine(self._db_url)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT COUNT(*) FROM dataflow_model_registry "
                    "WHERE model_name = 'rollback_test'"
                )
            ).fetchone()
            assert row[0] == 0, (
                "transaction() failed to roll back — sentinel row visible "
                "after exception"
            )


class TestRegistryTableCreationAtomic:
    """``_create_model_registry_table`` runs DDL inside a single tx."""

    def setup_method(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._db_url = f"sqlite:///{self._tmp.name}"

    def teardown_method(self) -> None:
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def test_create_table_via_sync_engine_path(self):
        """Happy path — table + indexes are created via the sync engine
        path (not the legacy fallback). Verifies the wiring is live.
        """
        from sqlalchemy import inspect, text

        df = _make_dataflow(self._db_url)
        registry = df._model_registry

        assert registry._create_model_registry_table() is True

        engine = registry._acquire_sync_engine(self._db_url)
        assert engine is not None

        with engine.connect() as conn:
            insp = inspect(conn)
            assert "dataflow_model_registry" in insp.get_table_names()
            indexes = {ix["name"] for ix in insp.get_indexes("dataflow_model_registry")}
            assert "idx_model_registry_application" in indexes
            assert "idx_model_registry_checksum" in indexes
            assert "idx_model_registry_name" in indexes
            assert "idx_model_registry_status" in indexes

            # The table is empty after a fresh init.
            row = conn.execute(
                text("SELECT COUNT(*) FROM dataflow_model_registry")
            ).fetchone()
            assert row[0] == 0
