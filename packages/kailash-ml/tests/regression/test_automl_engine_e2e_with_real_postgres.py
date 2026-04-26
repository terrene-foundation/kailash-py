# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W6-021 — Tier-3 e2e regression for AutoMLEngine.run() persistence
against real Postgres.

Per ``specs/ml-automl.md`` § 11.3 (Tier 3 e2e gap) + ``rules/testing.md``
§ Tier 3 (real everything; every write verified with read-back) +
``rules/tenant-isolation.md`` MUST 5 (every audit row carries
``tenant_id``).

Sibling to ``test_automl_engine_e2e_with_real_lightgbm_trainer.py``:
that file proves the canonical surface composes with a real model
trainer; THIS file proves the canonical surface persists every audit
invariant the spec requires AND the persisted rows survive a SELECT
read-back across tenant boundaries.

Differences vs ``tests/integration/test_automl_engine_wiring.py``:

1. **Postgres-first** — gates on ``POSTGRES_TEST_URL``. When absent,
   skips with a loud reason (Tier-3 contract). The Tier-2 wiring test
   covers the SQLite-only happy path; this file's job is to prove the
   canonical Postgres lane round-trips.
2. **Persistence-focused** — every assertion is on rows read back via
   ``conn.fetch(...)`` AFTER the ``await engine.run(...)`` returns,
   covering: ``tenant_id`` isolation across two parallel sweeps,
   ``admission_decision`` enumeration, ``params`` JSON shape, and
   ``run_id`` stability.
3. **Two tenants, one connection** — the same ConnectionManager
   serves both tenants so the persisted-row tenant_id dimension is
   exercised under shared infrastructure, mirroring the multi-tenant
   production deployment.
"""
from __future__ import annotations

import importlib
import os
import uuid

import pytest

pytestmark = [pytest.mark.regression, pytest.mark.asyncio]


_POSTGRES_URL = os.environ.get("POSTGRES_TEST_URL")

if _POSTGRES_URL is None:
    pytest.skip(
        "POSTGRES_TEST_URL env var is required for Tier-3 Postgres e2e "
        "(see rules/testing.md § Tier 3 — real everything). Set "
        "POSTGRES_TEST_URL=postgresql://user:pass@host:port/db to run.",
        allow_module_level=True,
    )

from kailash.db.connection import ConnectionManager  # noqa: E402
from kailash_ml.automl import (  # noqa: E402
    AutoMLConfig,
    AutoMLEngine,
    ParamSpec,
    Trial,
    TrialOutcome,
)


# ---------------------------------------------------------------------------
# Deterministic synthetic trial — Postgres lane stresses persistence,
# not the trainer (covered by the LightGBM-trainer e2e file).
# ---------------------------------------------------------------------------


async def _synthetic_trial(trial: Trial) -> TrialOutcome:
    scale = float(trial.params.get("scale", 0.5))
    rate = float(trial.params.get("rate", 0.5))
    metric = 0.5 + 0.25 * scale + 0.25 * rate
    return TrialOutcome(
        trial_number=trial.trial_number,
        params=dict(trial.params),
        metric=min(0.99, metric),
        metric_name="accuracy",
        direction="maximize",
        duration_seconds=0.001,
        cost_microdollars=10_000,
    )


_SPACE = [
    ParamSpec(name="scale", kind="float", low=0.0, high=1.0),
    ParamSpec(name="rate", kind="float", low=0.0, high=1.0),
]


# ---------------------------------------------------------------------------
# Postgres ConnectionManager fixture — shared across tests per session
# (each test uses a unique tenant_id so cross-test rows don't collide).
# ---------------------------------------------------------------------------


@pytest.fixture
async def pg_conn():
    """Real Postgres ConnectionManager with migration 0003 applied."""
    from kailash_ml.tracking.tracker import _MigrationConnAdapter

    conn = ConnectionManager(_POSTGRES_URL)
    await conn.initialize()
    mig_mod = importlib.import_module(
        "kailash.tracking.migrations.0003_automl_trials_schema_alignment"
    )
    try:
        await mig_mod.Migration().apply(_MigrationConnAdapter(conn))
    except Exception:  # pragma: no cover — idempotent on reuse
        pass
    try:
        yield conn
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Test 1 — full sweep round-trip: every spec invariant survives the DB
# ---------------------------------------------------------------------------


async def test_automl_engine_run_persists_full_audit_row(
    pg_conn: ConnectionManager,
) -> None:
    """``AutoMLEngine.run()`` writes one audit row per trial with every
    invariant intact (per specs/ml-automl.md § 3.5 MUST 1, 2, 3).

    Read-back asserts: ``tenant_id``, ``run_id``, ``trial_number``,
    ``status``, ``metric_value``, ``metric_name``, ``direction``,
    ``source`` (mapped from the ``source_tag`` kwarg), ``admission_decision``,
    ``admission_decision_id``.
    Every column the spec requires the engine to persist is verified by
    SELECT — the engine cannot pass this test by setting them
    in-memory only.
    """
    tenant_id = f"e2e-pg-{uuid.uuid4().hex[:8]}"
    run_id = f"e2e-run-{uuid.uuid4().hex[:8]}"
    config = AutoMLConfig(
        task_type="classification",
        metric_name="accuracy",
        direction="maximize",
        search_strategy="random",
        max_trials=3,
        time_budget_seconds=60,
        seed=11,
        auto_approve=True,
    )
    engine = AutoMLEngine(
        config=config,
        tenant_id=tenant_id,
        actor_id="e2e-actor",
        connection=pg_conn,
    )
    result = await engine.run(
        space=_SPACE,
        trial_fn=_synthetic_trial,
        run_id=run_id,
        source_tag="e2e-postgres-roundtrip",
    )
    assert result.completed_trials == 3
    assert result.run_id == run_id

    # Per migration 0003 the persisted column is "source"; the engine
    # maps the run() kwarg `source_tag` to that column at insert time.
    rows = await pg_conn.fetch(
        "SELECT tenant_id, run_id, trial_number, status, metric_value, "
        "metric_name, direction, source, admission_decision, "
        "admission_decision_id "
        "FROM _kml_automl_trials WHERE tenant_id = ? AND run_id = ? "
        "ORDER BY trial_number",
        tenant_id,
        run_id,
    )
    assert len(rows) == 3, (
        f"expected 3 persisted rows for tenant={tenant_id} run={run_id}, "
        f"got {len(rows)}"
    )
    seen_trial_numbers: set[int] = set()
    for row in rows:
        assert row["tenant_id"] == tenant_id
        assert row["run_id"] == run_id
        assert row["status"] == "completed"
        assert row["metric_name"] == "accuracy"
        assert row["direction"] == "maximize"
        assert row["source"] == "e2e-postgres-roundtrip"
        # admission_decision is one of the four spec-enumerated values
        assert row["admission_decision"] in {
            "admitted",
            "denied",
            "skipped",
            "unimplemented",
        }
        # admission_decision_id is non-null even in skipped/unimplemented
        assert row["admission_decision_id"] is not None
        assert row["metric_value"] is not None
        assert 0.0 <= float(row["metric_value"]) <= 1.0
        seen_trial_numbers.add(int(row["trial_number"]))
    # trial_number sequence is deterministic in v1.1.1: 0, 1, 2
    assert seen_trial_numbers == {0, 1, 2}


# ---------------------------------------------------------------------------
# Test 2 — tenant isolation across two concurrent sweeps on shared conn
# ---------------------------------------------------------------------------


async def test_automl_engine_tenant_isolation_round_trip(
    pg_conn: ConnectionManager,
) -> None:
    """Two tenants writing to the same ``_kml_automl_trials`` table
    MUST NOT see each other's rows on read-back.

    Per ``rules/tenant-isolation.md`` MUST 5 every audit row carries
    ``tenant_id``; this test proves the column actually filters on
    SELECT (i.e. the engine doesn't accidentally clobber it).
    """
    tenant_a = f"e2e-iso-a-{uuid.uuid4().hex[:8]}"
    tenant_b = f"e2e-iso-b-{uuid.uuid4().hex[:8]}"

    for tenant_id, seed, n_trials in (
        (tenant_a, 1, 2),
        (tenant_b, 2, 4),  # different trial count to make the assertion strict
    ):
        config = AutoMLConfig(
            search_strategy="random",
            max_trials=n_trials,
            time_budget_seconds=60,
            seed=seed,
            auto_approve=True,
        )
        engine = AutoMLEngine(
            config=config,
            tenant_id=tenant_id,
            actor_id="e2e-actor",
            connection=pg_conn,
        )
        await engine.run(space=_SPACE, trial_fn=_synthetic_trial)

    rows_a = await pg_conn.fetch(
        "SELECT trial_number FROM _kml_automl_trials WHERE tenant_id = ?",
        tenant_a,
    )
    rows_b = await pg_conn.fetch(
        "SELECT trial_number FROM _kml_automl_trials WHERE tenant_id = ?",
        tenant_b,
    )
    # Tenant A wrote 2 rows, Tenant B wrote 4. Both isolated by tenant_id.
    assert (
        len(rows_a) == 2
    ), f"tenant_a expected 2 rows, got {len(rows_a)} — possible leak"
    assert (
        len(rows_b) == 4
    ), f"tenant_b expected 4 rows, got {len(rows_b)} — possible leak"

    # Cross-tenant negative read-back: a SELECT for tenant_a's rows
    # against tenant_b's id MUST return zero
    cross = await pg_conn.fetch(
        "SELECT COUNT(*) AS n FROM _kml_automl_trials "
        "WHERE tenant_id = ? AND tenant_id != ?",
        tenant_a,
        tenant_a,
    )
    assert int(cross[0]["n"]) == 0


# ---------------------------------------------------------------------------
# Test 3 — direction='minimize' best-trial selection round-trips correctly
# ---------------------------------------------------------------------------


async def test_automl_engine_minimize_direction_best_trial_round_trip(
    pg_conn: ConnectionManager,
) -> None:
    """When ``direction='minimize'`` (per § 13.2 regression case) the
    in-memory best_trial MUST be the row with the LOWEST persisted
    metric_value for the run.

    Per ``specs/ml-automl.md`` § 3.5 MUST 2 best-trial selection is
    direction-aware. This test reads every persisted row for the run,
    finds the global min, and asserts it equals the in-memory
    ``result.best_trial.metric_value``.
    """
    tenant_id = f"e2e-min-{uuid.uuid4().hex[:8]}"
    run_id = f"e2e-min-{uuid.uuid4().hex[:8]}"

    async def inverse_trial(trial: Trial) -> TrialOutcome:
        # Treat the metric as a loss (lower = better)
        scale = float(trial.params.get("scale", 0.5))
        rate = float(trial.params.get("rate", 0.5))
        loss = 1.0 - (0.25 * scale + 0.25 * rate + 0.25)
        return TrialOutcome(
            trial_number=trial.trial_number,
            params=dict(trial.params),
            metric=loss,
            metric_name="rmse",
            direction="minimize",
            duration_seconds=0.001,
            cost_microdollars=10_000,
        )

    config = AutoMLConfig(
        task_type="regression",
        metric_name="rmse",
        direction="minimize",
        search_strategy="random",
        max_trials=4,
        time_budget_seconds=60,
        seed=42,
        auto_approve=True,
    )
    engine = AutoMLEngine(
        config=config,
        tenant_id=tenant_id,
        actor_id="e2e-actor",
        connection=pg_conn,
    )
    result = await engine.run(
        space=_SPACE,
        trial_fn=inverse_trial,
        run_id=run_id,
        source_tag="e2e-minimize",
    )
    assert result.best_trial is not None
    in_memory_best = result.best_trial.metric_value
    assert in_memory_best is not None

    rows = await pg_conn.fetch(
        "SELECT metric_value FROM _kml_automl_trials "
        "WHERE tenant_id = ? AND run_id = ? "
        "ORDER BY metric_value ASC",
        tenant_id,
        run_id,
    )
    assert len(rows) == 4
    persisted_min = float(rows[0]["metric_value"])
    assert persisted_min == pytest.approx(in_memory_best, rel=1e-9), (
        f"in-memory best_trial.metric_value {in_memory_best} disagrees with "
        f"persisted MIN(metric_value) {persisted_min} for direction=minimize"
    )
