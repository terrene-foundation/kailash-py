# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring test for :class:`kailash_ml.automl.AutoMLEngine`.

Per ``rules/facade-manager-detection.md`` MUST Rule 1-2 every
manager-shape class exposed on the framework facade MUST have a
Tier 2 test that:

1. Imports the class through the framework facade
   (``from kailash_ml.automl import AutoMLEngine``).
2. Constructs a real ``ConnectionManager`` against real SQLite
   infrastructure.
3. Triggers a code path that ends up calling at least one method on the
   manager and actually writes audit rows.
4. Asserts the externally-observable effect (a row in
   ``_kml_automl_trials``).

Toy problem: 3 ParamSpec families × 3 trials per family. Each family
is a separate sweep run; we assert admission decisions are recorded
and trial rows are persisted. With no GovernanceEngine injected the
admission wire-through degrades to ``"skipped"`` — which itself is a
valid code path exercising the PACT bridge end-to-end.
"""
from __future__ import annotations

import tempfile
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def sqlite_conn(tmp_path: Path):
    """Real SQLite ConnectionManager — no mocks, per Tier 2 contract.

    Applies migration 0003 so the canonical 19-column ``_kml_automl_trials``
    schema is in place before any trial INSERT. Per W6-020 the engine
    no longer creates this table inline — operators MUST run the
    numbered migration ahead of every sweep
    (``rules/schema-migration.md`` MUST Rule 1).
    """
    import importlib

    from kailash_ml.tracking.tracker import _MigrationConnAdapter

    db_path = tmp_path / "automl_wiring.db"
    conn = ConnectionManager(f"sqlite:///{db_path}")
    await conn.initialize()
    # Apply migration 0003 — directly so this fixture does not depend on
    # the registry walking 0001/0002 first (the 0001/0002 path requires
    # additional schema fixtures that aren't in scope for AutoML wiring).
    # The migration helpers expect the (sql, params_tuple) call form so
    # we wrap the ConnectionManager via the same adapter that
    # ExperimentTracker.create() uses (W10 tracker bootstrap).
    mig_mod = importlib.import_module(
        "kailash.tracking.migrations.0003_automl_trials_schema_alignment"
    )
    await mig_mod.Migration().apply(_MigrationConnAdapter(conn))
    try:
        yield conn
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Toy trial function — three param-space families
# ---------------------------------------------------------------------------


async def _toy_trial(trial: Trial) -> TrialOutcome:
    """Deterministic metric: higher ``scale`` + categorical bonus.

    Supports all three families' keys (``"scale"``, ``"rate"``,
    ``"n"``) — absent keys default to 0.5 so the function works for
    every family without per-family branching.
    """
    scale = float(trial.params.get("scale", 0.5))
    rate = float(trial.params.get("rate", 0.5))
    n = float(trial.params.get("n", 5))
    bonus = 0.1 if trial.params.get("activation") == "relu" else 0.0
    metric = 0.2 + 0.3 * scale + 0.3 * rate + (n / 100.0) + bonus
    return TrialOutcome(
        trial_number=trial.trial_number,
        params=dict(trial.params),
        metric=min(0.99, metric),
        metric_name="accuracy",
        direction="maximize",
        duration_seconds=0.01,
        cost_microdollars=50_000,  # $0.05 per trial
    )


FAMILIES: list[tuple[str, list[ParamSpec]]] = [
    (
        "family_linear",
        [
            ParamSpec(name="scale", kind="float", low=0.0, high=1.0),
            ParamSpec(name="rate", kind="float", low=0.0, high=1.0),
        ],
    ),
    (
        "family_mixed",
        [
            ParamSpec(name="n", kind="int", low=1, high=100),
            ParamSpec(name="activation", kind="categorical", choices=("relu", "tanh")),
        ],
    ),
    (
        "family_logscale",
        [
            ParamSpec(name="rate", kind="log_float", low=1e-3, high=1.0),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Tier 2 tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAutoMLEngineWiring:
    async def test_construction_through_facade(
        self, sqlite_conn: ConnectionManager
    ) -> None:
        """AutoMLEngine is importable + constructable through kailash_ml.automl."""
        config = AutoMLConfig(
            search_strategy="random",
            max_trials=3,
            time_budget_seconds=60,
            seed=11,
            auto_approve=True,
        )
        engine = AutoMLEngine(
            config=config,
            tenant_id="tenant-wiring",
            actor_id="actor-wiring",
            connection=sqlite_conn,
        )
        assert engine.tenant_id == "tenant-wiring"
        assert engine.actor_id == "actor-wiring"
        assert engine.cost_tracker is not None

    async def test_three_families_three_trials_each_persists_audit_rows(
        self, sqlite_conn: ConnectionManager
    ) -> None:
        """Run 3 param-space families × 3 trials each; assert rows exist."""
        all_run_ids: list[str] = []
        for family_name, space in FAMILIES:
            config = AutoMLConfig(
                search_strategy="random",
                max_trials=3,
                time_budget_seconds=60,
                seed=7,
                auto_approve=True,
            )
            engine = AutoMLEngine(
                config=config,
                tenant_id="tenant-wiring",
                actor_id="actor-wiring",
                connection=sqlite_conn,
            )
            result = await engine.run(
                space=space,
                trial_fn=_toy_trial,
                run_id=f"run-{family_name}",
                source_tag="baseline",
            )
            all_run_ids.append(result.run_id)
            assert result.total_trials == 3, family_name
            assert result.completed_trials == 3, family_name
            assert result.best_trial is not None, family_name
            assert result.best_trial.metric_value is not None, family_name

        # External assertion: audit rows persisted per family
        rows = await sqlite_conn.fetch(
            "SELECT run_id, trial_number, status, metric_value, admission_decision "
            "FROM _kml_automl_trials WHERE tenant_id = ? ORDER BY run_id, trial_number",
            "tenant-wiring",
        )
        assert (
            len(rows) == 9
        ), f"expected 9 audit rows (3 families × 3 trials), got {len(rows)}"
        run_ids_in_audit = {row["run_id"] for row in rows}
        assert run_ids_in_audit == set(all_run_ids)
        # Every trial must be "completed" with an admission decision recorded
        for row in rows:
            assert row["status"] == "completed"
            # With no GovernanceEngine injected and no kailash_pact installed
            # the admission decision is "skipped" (degraded mode) per the spec
            assert row["admission_decision"] == "skipped"
            assert row["metric_value"] is not None

    async def test_tenant_isolation_in_audit_rows(
        self, sqlite_conn: ConnectionManager
    ) -> None:
        """Trials from different tenants MUST land under their own tenant_id."""
        for tenant_id, seed in (("tenant-a", 1), ("tenant-b", 2)):
            config = AutoMLConfig(
                search_strategy="random",
                max_trials=2,
                time_budget_seconds=60,
                seed=seed,
                auto_approve=True,
            )
            engine = AutoMLEngine(
                config=config,
                tenant_id=tenant_id,
                actor_id="actor-iso",
                connection=sqlite_conn,
            )
            await engine.run(space=FAMILIES[0][1], trial_fn=_toy_trial)
        rows_a = await sqlite_conn.fetch(
            "SELECT trial_number FROM _kml_automl_trials WHERE tenant_id = ?",
            "tenant-a",
        )
        rows_b = await sqlite_conn.fetch(
            "SELECT trial_number FROM _kml_automl_trials WHERE tenant_id = ?",
            "tenant-b",
        )
        assert len(rows_a) == 2
        assert len(rows_b) == 2

    async def test_admission_decision_id_recorded(
        self, sqlite_conn: ConnectionManager
    ) -> None:
        """Every trial row must carry a non-null admission_decision_id OR
        the special 'skipped'/'unimplemented' marker so forensic queries
        can split by decision class."""
        config = AutoMLConfig(
            search_strategy="grid",
            max_trials=100,
            time_budget_seconds=60,
            seed=3,
            auto_approve=True,
        )
        engine = AutoMLEngine(
            config=config,
            tenant_id="tenant-admission",
            actor_id="actor-admission",
            connection=sqlite_conn,
        )
        from kailash_ml.automl.strategies import GridSearchStrategy

        strategy = GridSearchStrategy(
            space=[ParamSpec(name="scale", kind="float", low=0.0, high=1.0)],
            grid_resolution=3,
        )
        result = await engine.run(
            space=[ParamSpec(name="scale", kind="float", low=0.0, high=1.0)],
            trial_fn=_toy_trial,
            strategy=strategy,
        )
        assert result.completed_trials == 3
        rows = await sqlite_conn.fetch(
            "SELECT admission_decision, admission_decision_id FROM _kml_automl_trials "
            "WHERE tenant_id = ?",
            "tenant-admission",
        )
        assert len(rows) == 3
        for row in rows:
            # decision is always recorded; decision_id populated even in skipped mode
            assert row["admission_decision"] in {
                "admitted",
                "denied",
                "skipped",
                "unimplemented",
            }
            assert row["admission_decision_id"] is not None

    async def test_cost_budget_early_stop_persists_partial_audit(
        self, sqlite_conn: ConnectionManager
    ) -> None:
        """Budget exhaustion early-stops the sweep but preserves partial audit."""
        config = AutoMLConfig(
            search_strategy="random",
            max_trials=10,
            time_budget_seconds=60,
            seed=0,
            auto_approve=True,
            total_budget_microdollars=120_000,  # $0.12, trial cost $0.05 each
        )
        engine = AutoMLEngine(
            config=config,
            tenant_id="tenant-budget",
            actor_id="actor-budget",
            connection=sqlite_conn,
        )
        result = await engine.run(
            space=FAMILIES[0][1],
            trial_fn=_toy_trial,
            estimate_trial_cost_microdollars=lambda t: 50_000,
        )
        assert result.early_stopped is True
        # Expect at most 3 completed trials (0.12 / 0.05 = 2.4)
        assert result.completed_trials <= 3
        rows = await sqlite_conn.fetch(
            "SELECT COUNT(*) AS n FROM _kml_automl_trials WHERE tenant_id = ?",
            "tenant-budget",
        )
        assert rows[0]["n"] == result.completed_trials
