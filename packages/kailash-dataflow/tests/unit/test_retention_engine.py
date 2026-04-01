# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for TSG-106: RetentionEngine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dataflow.features.retention import (
    DataFlowConfigError,
    RetentionEngine,
    RetentionPolicy,
    RetentionResult,
    _validate_table_name,
)


# ---------------------------------------------------------------------------
# Table name validation
# ---------------------------------------------------------------------------


class TestTableNameValidation:
    def test_valid_names(self):
        _validate_table_name("users")
        _validate_table_name("User")
        _validate_table_name("_private_table")
        _validate_table_name("table123")

    def test_invalid_names(self):
        with pytest.raises(ValueError, match="Invalid table name"):
            _validate_table_name("users; DROP TABLE")
        with pytest.raises(ValueError, match="Invalid table name"):
            _validate_table_name("123starts_with_number")
        with pytest.raises(ValueError, match="Invalid table name"):
            _validate_table_name("has spaces")
        with pytest.raises(ValueError, match="Invalid table name"):
            _validate_table_name("")


# ---------------------------------------------------------------------------
# RetentionPolicy
# ---------------------------------------------------------------------------


class TestRetentionPolicy:
    def test_default_values(self):
        p = RetentionPolicy(
            model_name="User",
            table_name="users",
            policy="delete",
            after_days=90,
        )
        assert p.cutoff_field == "created_at"
        assert p.archive_table is None
        assert p.last_run is None

    def test_custom_values(self):
        p = RetentionPolicy(
            model_name="Order",
            table_name="orders",
            policy="archive",
            after_days=365,
            archive_table="old_orders",
            cutoff_field="order_date",
        )
        assert p.archive_table == "old_orders"
        assert p.cutoff_field == "order_date"


# ---------------------------------------------------------------------------
# RetentionEngine registration
# ---------------------------------------------------------------------------


class TestRetentionEngineRegistration:
    def test_register_valid_policy(self):
        engine = RetentionEngine(dataflow_instance=None)
        policy = RetentionPolicy(
            model_name="User",
            table_name="users",
            policy="delete",
            after_days=90,
        )
        engine.register(policy)
        assert "User" in engine._policies

    def test_register_invalid_table_name(self):
        engine = RetentionEngine(dataflow_instance=None)
        policy = RetentionPolicy(
            model_name="User",
            table_name="users; DROP TABLE",
            policy="delete",
            after_days=90,
        )
        with pytest.raises(ValueError, match="Invalid table name"):
            engine.register(policy)

    def test_register_invalid_archive_table(self):
        engine = RetentionEngine(dataflow_instance=None)
        policy = RetentionPolicy(
            model_name="User",
            table_name="users",
            policy="archive",
            after_days=365,
            archive_table="bad name",
        )
        with pytest.raises(ValueError, match="Invalid table name"):
            engine.register(policy)


# ---------------------------------------------------------------------------
# Archive table name generation
# ---------------------------------------------------------------------------


class TestArchiveTableName:
    def test_default_archive_table(self):
        p = RetentionPolicy(
            model_name="User",
            table_name="users",
            policy="archive",
            after_days=365,
        )
        expected = f"{p.table_name}_archive"
        assert expected == "users_archive"

    def test_custom_archive_table(self):
        p = RetentionPolicy(
            model_name="Order",
            table_name="orders",
            policy="archive",
            after_days=365,
            archive_table="old_orders",
        )
        assert p.archive_table == "old_orders"


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestRetentionStatus:
    def test_status_empty(self):
        engine = RetentionEngine(dataflow_instance=None)
        assert engine.status() == {}

    def test_status_with_policies(self):
        engine = RetentionEngine(dataflow_instance=None)
        engine.register(
            RetentionPolicy(
                model_name="User",
                table_name="users",
                policy="delete",
                after_days=90,
            )
        )
        engine.register(
            RetentionPolicy(
                model_name="Order",
                table_name="orders",
                policy="archive",
                after_days=365,
                archive_table="old_orders",
            )
        )

        status = engine.status()
        assert len(status) == 2
        assert status["User"]["policy"] == "delete"
        assert status["User"]["after_days"] == 90
        assert status["User"]["last_run"] is None
        assert status["Order"]["policy"] == "archive"
        assert status["Order"]["archive_table"] == "old_orders"


# ---------------------------------------------------------------------------
# Dry run result structure
# ---------------------------------------------------------------------------


class TestRetentionResult:
    def test_result_defaults(self):
        r = RetentionResult(
            model_name="User",
            policy="delete",
            affected_rows=42,
        )
        assert r.archived_rows == 0
        assert r.deleted_rows == 0
        assert r.dry_run is False
        assert r.error is None

    def test_dry_run_result(self):
        r = RetentionResult(
            model_name="User",
            policy="delete",
            affected_rows=42,
            dry_run=True,
        )
        assert r.dry_run is True

    def test_error_result(self):
        r = RetentionResult(
            model_name="User",
            policy="partition",
            affected_rows=0,
            error="PostgreSQL required",
        )
        assert r.error == "PostgreSQL required"


# ---------------------------------------------------------------------------
# Partition policy validation
# ---------------------------------------------------------------------------


class TestPartitionPolicyValidation:
    @pytest.mark.asyncio
    async def test_partition_non_postgresql_raises(self):
        """Partition policy should raise DataFlowConfigError on non-PG."""

        class MockConfig:
            class database:
                url = "sqlite:///test.db"

        class MockDB:
            config = MockConfig()
            _connection_manager = None

        engine = RetentionEngine(dataflow_instance=MockDB())
        engine.register(
            RetentionPolicy(
                model_name="Event",
                table_name="events",
                policy="partition",
                after_days=365,
            )
        )

        results = await engine.run()
        assert results["Event"].error is not None
        assert (
            "PostgreSQL" in results["Event"].error
            or "not yet implemented" in results["Event"].error
        )
