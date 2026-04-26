# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 regression tests for W6-020 — _kml_automl_trials migration discipline.

Two scenarios per the todo's Acceptance gate:

1. Fresh DB without migration 0003 applied → ``AutoMLEngine.run`` MUST
   raise typed :class:`MigrationRequiredError` with grep-able context.
2. After migration 0003 applied → engine writes a trial row, the row is
   readable through the canonical 19-column schema, and tenant_id is
   persisted on the row.

Per ``rules/testing.md`` § Tier 2 — real SQLite database via
``kailash.db.connection.ConnectionManager``; no mocks. Per
``rules/schema-migration.md`` MUST Rule 5 — migration tests run
against the production schema dialect.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from kailash.db.connection import ConnectionManager

from kailash_ml.automl import (
    AutoMLConfig,
    AutoMLEngine,
    ParamSpec,
    Trial,
    TrialOutcome,
)
from kailash_ml.errors import MigrationRequiredError


# ---------------------------------------------------------------------------
# Migration module — imported via importlib because the filename starts
# with a digit (NNNN_<name>.py per the registry's filename pattern).
# ---------------------------------------------------------------------------


_MIGRATION_MOD = importlib.import_module(
    "kailash.tracking.migrations.0003_automl_trials_schema_alignment"
)
Migration = _MIGRATION_MOD.Migration
PlaceholderTablePopulatedError = _MIGRATION_MOD.PlaceholderTablePopulatedError
DowngradeRefusedError = _MIGRATION_MOD.DowngradeRefusedError


# Migration helpers expect ``conn.execute(sql, params_tuple)`` shape;
# ConnectionManager uses varargs ``execute(sql, *args)``. Wrap via the
# same private adapter ExperimentTracker.create() uses (mirrors W10
# tracker bootstrap).
from kailash_ml.tracking.tracker import _MigrationConnAdapter


def _adapt(conn: ConnectionManager) -> Any:
    return _MigrationConnAdapter(conn)


# Late import to satisfy ``Any`` annotation above without polluting
# the module-level import block.
from typing import Any  # noqa: E402


# ---------------------------------------------------------------------------
# Toy trial — minimal so the test focuses on schema discipline, not
# search behavior.
# ---------------------------------------------------------------------------


async def _toy_trial(trial: Trial) -> TrialOutcome:
    return TrialOutcome(
        trial_number=trial.trial_number,
        params=dict(trial.params),
        metric=0.5,
        metric_name="accuracy",
        direction="maximize",
        duration_seconds=0.001,
        cost_microdollars=10_000,
    )


_PARAM_SPACE = [ParamSpec(name="scale", kind="float", low=0.0, high=1.0)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def fresh_conn(tmp_path: Path):
    """Real SQLite ConnectionManager with NO migrations applied."""
    db_path = tmp_path / "automl_migration.db"
    conn = ConnectionManager(f"sqlite:///{db_path}")
    await conn.initialize()
    try:
        yield conn
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Scenario 1 — fresh DB without migration → typed MigrationRequiredError
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.regression
class TestEngineRaisesWhenMigrationMissing:
    async def test_run_raises_migration_required_error(
        self, fresh_conn: ConnectionManager
    ) -> None:
        """Engine MUST refuse to write to a DB whose schema is not aligned."""
        config = AutoMLConfig(
            search_strategy="random",
            max_trials=2,
            time_budget_seconds=30,
            seed=1,
            auto_approve=True,
        )
        engine = AutoMLEngine(
            config=config,
            tenant_id="tenant-fresh",
            actor_id="actor-fresh",
            connection=fresh_conn,
        )
        with pytest.raises(MigrationRequiredError) as exc_info:
            await engine.run(space=_PARAM_SPACE, trial_fn=_toy_trial)
        # Typed-error contract — grep-able fields per
        # rules/observability.md Rule 5 (log triage).
        err = exc_info.value
        assert err.tenant_id == "tenant-fresh"
        assert err.actor_id == "actor-fresh"
        assert err.resource_id == "_kml_automl_trials"
        assert (
            err.context.get("migration_module")
            == "kailash.tracking.migrations.0003_automl_trials_schema_alignment"
        )
        assert err.context.get("table_present") is False

    async def test_engine_emits_no_create_table_ddl(
        self, fresh_conn: ConnectionManager
    ) -> None:
        """Failed run leaves the DB exactly as it was — no inline DDL."""
        config = AutoMLConfig(
            search_strategy="random",
            max_trials=1,
            time_budget_seconds=30,
            seed=1,
            auto_approve=True,
        )
        engine = AutoMLEngine(
            config=config,
            tenant_id="tenant-no-ddl",
            actor_id="actor-no-ddl",
            connection=fresh_conn,
        )
        with pytest.raises(MigrationRequiredError):
            await engine.run(space=_PARAM_SPACE, trial_fn=_toy_trial)
        # Audit table MUST NOT have been created by the failed engine.
        rows = await fresh_conn.fetch(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='_kml_automl_trials'"
        )
        assert rows == [], (
            "engine must NOT emit CREATE TABLE inline; rows on a fresh DB "
            "indicate the lazy DDL path is still wired"
        )


# ---------------------------------------------------------------------------
# Scenario 2 — migration applied → engine writes + reads canonical rows
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.regression
class TestEngineWritesAfterMigrationApplied:
    async def test_apply_then_run_persists_audit_row(
        self, fresh_conn: ConnectionManager
    ) -> None:
        """Apply migration → engine runs → audit row visible on read-back."""
        # Apply the migration.
        result = await Migration().apply(_adapt(fresh_conn))
        assert result.direction == "upgrade"
        assert "canonical _kml_automl_trials" in result.notes

        # Construct + run engine.
        config = AutoMLConfig(
            search_strategy="random",
            max_trials=1,
            time_budget_seconds=30,
            seed=2,
            auto_approve=True,
        )
        engine = AutoMLEngine(
            config=config,
            tenant_id="tenant-applied",
            actor_id="actor-applied",
            connection=fresh_conn,
        )
        sweep = await engine.run(space=_PARAM_SPACE, trial_fn=_toy_trial)
        assert sweep.completed_trials == 1

        # Read-back through the canonical 19-column schema. State
        # persistence verification per rules/testing.md § "State
        # Persistence Verification (Tiers 2-3)".
        rows = await fresh_conn.fetch(
            "SELECT trial_id, run_id, tenant_id, actor_id, trial_number, "
            "strategy, params_json, metric_name, metric_value, "
            "cost_microdollars, started_at, status, source, fidelity, rung "
            "FROM _kml_automl_trials WHERE tenant_id = ?",
            "tenant-applied",
        )
        assert len(rows) == 1, f"expected 1 audit row, got {len(rows)}"
        row = rows[0]
        assert row["tenant_id"] == "tenant-applied"
        assert row["actor_id"] == "actor-applied"
        assert row["status"] == "completed"
        assert row["metric_value"] == pytest.approx(0.5)

    async def test_verify_returns_true_after_apply(
        self, fresh_conn: ConnectionManager
    ) -> None:
        """Migration.verify must report True once apply has run."""
        assert await Migration().verify(_adapt(fresh_conn)) is False
        await Migration().apply(_adapt(fresh_conn))
        assert await Migration().verify(_adapt(fresh_conn)) is True

    async def test_apply_is_idempotent(self, fresh_conn: ConnectionManager) -> None:
        """Re-running apply on an already-migrated DB is a no-op."""
        first = await Migration().apply(_adapt(fresh_conn))
        second = await Migration().apply(_adapt(fresh_conn))
        assert "no-op" in second.notes
        # First apply records 0 rows migrated (no placeholder existed)
        # second apply records 0 too.
        assert first.rows_migrated == 0
        assert second.rows_migrated == 0


# ---------------------------------------------------------------------------
# Scenario 3 — placeholder table present (covers the 0002 → 0003 path)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.regression
class TestPlaceholderHandling:
    async def test_empty_placeholder_dropped_and_replaced(
        self, fresh_conn: ConnectionManager
    ) -> None:
        """If 0002's empty placeholder is present, 0003 drops + recreates."""
        # Simulate the 0002 placeholder shape (subset of the columns that
        # 0002's TABLE_INVENTORY declared).
        await fresh_conn.execute(
            "CREATE TABLE _kml_automl_trials ("
            " tenant_id TEXT NOT NULL,"
            " trial_id TEXT NOT NULL,"
            " study_id TEXT NOT NULL,"
            " hyperparams TEXT NOT NULL,"
            " score REAL NOT NULL,"
            " status TEXT NOT NULL,"
            " created_at TEXT NOT NULL,"
            " PRIMARY KEY (tenant_id, trial_id))"
        )
        result = await Migration().apply(_adapt(fresh_conn))
        assert result.rows_migrated == 1
        assert "placeholder_dropped=True" in result.notes
        # Canonical sentinel column now present.
        cols = await fresh_conn.fetch("PRAGMA table_info(_kml_automl_trials)")
        names = {row["name"] for row in cols}
        assert "trial_number" in names
        assert "hyperparams" not in names

    async def test_populated_placeholder_raises(
        self, fresh_conn: ConnectionManager
    ) -> None:
        """If the placeholder has rows, 0003 refuses to drop it."""
        await fresh_conn.execute(
            "CREATE TABLE _kml_automl_trials ("
            " tenant_id TEXT NOT NULL,"
            " trial_id TEXT NOT NULL,"
            " study_id TEXT NOT NULL,"
            " hyperparams TEXT NOT NULL,"
            " score REAL NOT NULL,"
            " status TEXT NOT NULL,"
            " created_at TEXT NOT NULL,"
            " PRIMARY KEY (tenant_id, trial_id))"
        )
        await fresh_conn.execute(
            "INSERT INTO _kml_automl_trials VALUES "
            "('t1', 'tr1', 's1', '{}', 0.0, 'ok', '2026-04-27T00:00:00')"
        )
        with pytest.raises(PlaceholderTablePopulatedError) as exc:
            await Migration().apply(_adapt(fresh_conn))
        assert exc.value.context.get("rows_present") == 1


# ---------------------------------------------------------------------------
# Scenario 4 — rollback discipline
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.regression
class TestRollbackDiscipline:
    async def test_rollback_without_force_refuses(
        self, fresh_conn: ConnectionManager
    ) -> None:
        """Rollback MUST refuse without force_downgrade=True."""
        await Migration().apply(_adapt(fresh_conn))
        with pytest.raises(DowngradeRefusedError):
            await Migration().rollback(_adapt(fresh_conn))

    async def test_rollback_with_force_drops_table(
        self, fresh_conn: ConnectionManager
    ) -> None:
        """force_downgrade=True drops the canonical table cleanly."""
        await Migration().apply(_adapt(fresh_conn))
        result = await Migration().rollback(_adapt(fresh_conn), force_downgrade=True)
        assert result.direction == "downgrade"
        rows = await fresh_conn.fetch(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='_kml_automl_trials'"
        )
        assert rows == []
