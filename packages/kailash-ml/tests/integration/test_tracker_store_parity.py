# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W14b Tier-2 integration — cross-backend parity for the tracker store.

Per ``specs/ml-tracking.md`` §6 :class:`SqliteTrackerStore` and
:class:`PostgresTrackerStore` MUST produce byte-identical
``list_runs`` / ``list_metrics`` / ``list_artifacts`` / ``list_tags``
/ ``list_experiments_summary`` output for the same scripted run
history. Drift between the two is BLOCKED — downstream analysis code
(polars query primitives, RunDiff) must not care which backend it
reads from.

The test scripts one representative run through each backend:

1. ``insert_run`` with the W14a-extended column set.
2. ``append_metric`` × 3 (keyed + stepped).
3. ``append_metrics_batch`` × 2 more rows.
4. ``insert_artifact`` × 2 (second one dedupes on the same SHA).
5. ``upsert_tags`` × 2 keys, then ``upsert_tag`` replacing one.
6. ``update_run`` FINISHED + ``wall_clock_end``.
7. Read back via ``list_runs`` / ``list_metrics`` / ``list_artifacts``
   / ``list_tags`` / ``list_experiments_summary``.

Then assert the read-back dicts are equal across backends. PostgreSQL
leg is skipped per ``rules/testing.md`` ACCEPTABLE-tier when
``POSTGRES_TEST_URL`` is absent from the environment.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from kailash_ml.tracking import PostgresTrackerStore, SqliteTrackerStore
from kailash_ml.tracking.storage.base import AbstractTrackerStore

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


_POSTGRES_URL = os.environ.get("POSTGRES_TEST_URL")


def _make_run_row(run_id: str, experiment: str) -> dict:
    """Canonical run-row fixture — every backend stores these fields."""
    return {
        "run_id": run_id,
        "experiment": experiment,
        "parent_run_id": None,
        "status": "RUNNING",
        "host": "parity-host",
        "python_version": "3.13.7",
        "kailash_ml_version": "1.0.0",
        "lightning_version": "2.5.2",
        "torch_version": "2.7.0",
        "cuda_version": None,
        "git_sha": "deadbeef",
        "git_branch": "feat/parity",
        "git_dirty": False,
        "wall_clock_start": "2026-04-22T01:02:03+00:00",
        "wall_clock_end": None,
        "duration_seconds": None,
        "tenant_id": "acme",
        "device_used": "cpu",
        "accelerator": "cpu",
        "precision": "fp32",
        "device_family": "cpu",
        "device_backend": "torch",
        "device_fallback_reason": None,
        "device_array_api": True,
        "params": {"lr": 0.01, "batch_size": 32},
        "error_type": None,
        "error_message": None,
    }


async def _script_run_history(store: AbstractTrackerStore, run_id: str) -> None:
    """Execute the canonical W14b parity script against ``store``."""
    experiment = "parity-exp"

    await store.insert_run(_make_run_row(run_id, experiment))

    await store.append_metric(
        run_id, "loss", 1.25, step=0, timestamp="2026-04-22T01:02:10+00:00"
    )
    await store.append_metric(
        run_id, "loss", 0.75, step=1, timestamp="2026-04-22T01:02:20+00:00"
    )
    await store.append_metric(
        run_id, "accuracy", 0.92, step=1, timestamp="2026-04-22T01:02:21+00:00"
    )

    await store.append_metrics_batch(
        run_id,
        [
            ("loss", 0.50, 2, "2026-04-22T01:02:30+00:00"),
            ("accuracy", 0.95, 2, "2026-04-22T01:02:31+00:00"),
        ],
    )

    first_insert = await store.insert_artifact(
        run_id,
        "model.onnx",
        "sha-abc",
        "application/octet-stream",
        1024,
        "/tmp/model.onnx",
        "2026-04-22T01:02:40+00:00",
    )
    assert first_insert is True
    # Second insert with identical (run_id, name, sha) MUST be idempotent.
    second_insert = await store.insert_artifact(
        run_id,
        "model.onnx",
        "sha-abc",
        "application/octet-stream",
        1024,
        "/tmp/model.onnx",
        "2026-04-22T01:02:41+00:00",
    )
    assert second_insert is False

    await store.upsert_tags(run_id, {"env": "dev", "owner": "alice"})
    # Overwrite one tag via single-key upsert.
    await store.upsert_tag(run_id, "env", "prod")

    await store.update_run(
        run_id,
        {
            "status": "FINISHED",
            "wall_clock_end": "2026-04-22T01:05:00+00:00",
            "duration_seconds": 177.0,
        },
    )


async def _collect_read_surface(
    store: AbstractTrackerStore, run_id: str, experiment: str
) -> dict:
    """Gather every read-side public return into one dict for equality."""
    run = await store.get_run(run_id)
    runs = await store.list_runs(experiment=experiment)
    queried = await store.query_runs(
        experiment=experiment, tenant_id="acme", status="FINISHED", limit=10
    )
    metrics = await store.list_metrics(run_id)
    artifacts = await store.list_artifacts(run_id)
    tags = await store.list_tags(run_id)
    summary = await store.list_experiments_summary(tenant_id="acme")
    return {
        "run": run,
        "runs": runs,
        "queried": queried,
        "metrics": metrics,
        "artifacts": artifacts,
        "tags": tags,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# SQLite-only leg (always runs).
# ---------------------------------------------------------------------------


async def test_sqlite_script_round_trip(tmp_path: Path) -> None:
    """SQLite backend round-trips the canonical W14b history cleanly.

    This is the lower bound on the parity contract — if the SQLite
    leg is wrong, the Postgres leg cannot agree with anything stable.
    """
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    store = SqliteTrackerStore(tmp_path / "parity.db")
    try:
        await _script_run_history(store, run_id)
        surface = await _collect_read_surface(store, run_id, "parity-exp")
    finally:
        await store.close()

    assert surface["run"] is not None
    assert surface["run"]["status"] == "FINISHED"
    assert surface["run"]["params"] == {"lr": 0.01, "batch_size": 32}
    assert surface["run"]["device_array_api"] is True
    assert surface["run"]["git_dirty"] is False

    assert len(surface["runs"]) == 1
    assert len(surface["queried"]) == 1

    # Metrics come back ordered by (key, step, id).
    assert [(m["key"], m["step"], m["value"]) for m in surface["metrics"]] == [
        ("accuracy", 1, 0.92),
        ("accuracy", 2, 0.95),
        ("loss", 0, 1.25),
        ("loss", 1, 0.75),
        ("loss", 2, 0.50),
    ]

    assert len(surface["artifacts"]) == 1
    assert surface["artifacts"][0]["sha256"] == "sha-abc"

    assert surface["tags"] == {"env": "prod", "owner": "alice"}

    assert len(surface["summary"]) == 1
    assert surface["summary"][0]["experiment"] == "parity-exp"
    assert surface["summary"][0]["run_count"] == 1
    assert surface["summary"][0]["finished_count"] == 1


# ---------------------------------------------------------------------------
# SQLite ↔ PostgreSQL parity leg.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    _POSTGRES_URL is None,
    reason="requires POSTGRES_TEST_URL env var for the Postgres parity leg",
)
async def test_sqlite_postgres_read_surface_parity(tmp_path: Path) -> None:
    """SQLite + PostgreSQL MUST return byte-identical read surfaces.

    The surfaces compared: :meth:`get_run`, :meth:`list_runs`,
    :meth:`query_runs`, :meth:`list_metrics`, :meth:`list_artifacts`,
    :meth:`list_tags`, :meth:`list_experiments_summary`.

    A single `_kml_*` schema unification wave later in the 34-wave
    plan will re-home the tables; until then the two backends share
    the ``experiment_*`` shape so this test can hold the parity
    invariant at the dict level.
    """
    run_id = f"run-{uuid.uuid4().hex[:8]}"

    sqlite_store = SqliteTrackerStore(tmp_path / "parity-sqlite.db")
    pg_store = PostgresTrackerStore(
        _POSTGRES_URL,  # noqa: S105 — test-only env var
        artifact_root=tmp_path / "parity-pg-artifacts",
    )
    try:
        # Fresh schema for the PG leg — drop the parity tables if a
        # prior test run left rows behind. Uses the store's own
        # connection manager so identifiers stay validated.
        await pg_store.initialize()
        for table in (
            "experiment_model_versions",
            "experiment_tags",
            "experiment_artifacts",
            "experiment_metrics",
            "experiment_runs",
        ):
            await pg_store._conn.execute(f"DELETE FROM {table}")

        await _script_run_history(sqlite_store, run_id)
        await _script_run_history(pg_store, run_id)

        sqlite_surface = await _collect_read_surface(sqlite_store, run_id, "parity-exp")
        pg_surface = await _collect_read_surface(pg_store, run_id, "parity-exp")
    finally:
        await sqlite_store.close()
        await pg_store.close()

    # Compare every surface piece — if the dicts drift, the assertion
    # message surfaces the first mismatching key.
    assert sqlite_surface["run"] == pg_surface["run"], (
        f"get_run drift — sqlite={sqlite_surface['run']} "
        f"postgres={pg_surface['run']}"
    )
    assert sqlite_surface["runs"] == pg_surface["runs"]
    assert sqlite_surface["queried"] == pg_surface["queried"]
    assert sqlite_surface["metrics"] == pg_surface["metrics"]
    assert sqlite_surface["artifacts"] == pg_surface["artifacts"]
    assert sqlite_surface["tags"] == pg_surface["tags"]
    assert sqlite_surface["summary"] == pg_surface["summary"]
