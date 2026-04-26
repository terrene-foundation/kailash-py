# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring — ``dataflow.ml_feature_source`` round-trip.

Per ``rules/facade-manager-detection.md`` MUST Rule 2 and
``rules/orphan-detection.md`` MUST Rule 2, this test exercises
``dataflow.ml_feature_source`` end-to-end against a real SQLite-backed
DataFlow instance and asserts the externally-observable contract:

* ``materialize`` on a FeatureGroup implementation returns a
  ``polars.LazyFrame``.
* Multi-tenant groups without ``tenant_id`` raise
  ``TenantRequiredError`` with the exact message shape the
  ``rules/tenant-isolation.md`` § 2 contract mandates.
* Write-then-read persistence is verified end-to-end: rows written to
  the DataFlow table through ``db.express`` are retrievable through a
  ``FeatureGroup`` that reads from the same table.

This test uses a deterministic in-memory ``FeatureGroup``-shaped adapter
(not ``MagicMock``) — see ``rules/testing.md`` § "Protocol-Satisfying
Deterministic Adapters Are Not Mocks" — so the test runs without
kailash-ml installed while still exercising the real Express read path
and the real classification-metadata propagation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import polars as pl
import pytest

from dataflow import DataFlow
from dataflow.ml import (
    TenantRequiredError,
    ml_feature_source,
    transform,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Deterministic FeatureGroup test-double (real class, not a mock).
# ---------------------------------------------------------------------------


class DataFlowTableFeatureGroup:
    """Real FeatureGroup-shaped adapter that reads from a DataFlow table.

    Satisfies the shape ``dataflow.ml_feature_source`` expects:

    * ``.name`` — non-empty string
    * ``.multi_tenant`` — bool
    * ``.classification`` — optional dict
    * ``.materialize(...)`` — callable returning a polars LazyFrame

    This is NOT a mock. The ``materialize`` method runs a real query
    against the real DataFlow instance and constructs a real polars
    frame from the real rows. See ``rules/testing.md`` § Tier 2 exception.
    """

    def __init__(
        self,
        *,
        db: DataFlow,
        model_name: str,
        multi_tenant: bool = False,
        classification: Optional[dict] = None,
    ) -> None:
        self._db = db
        self.name = f"feature_group_{model_name.lower()}"
        self._model_name = model_name
        self.multi_tenant = multi_tenant
        self.classification = classification or {}
        self._materialize_calls: list[dict] = []

    def materialize(
        self,
        *,
        tenant_id: Optional[str] = None,
        point_in_time: Any = None,
        since: Any = None,
        until: Any = None,
        limit: Optional[int] = None,
    ) -> "pl.LazyFrame":
        self._materialize_calls.append(
            {
                "tenant_id": tenant_id,
                "point_in_time": point_in_time,
                "since": since,
                "until": until,
                "limit": limit,
            }
        )
        filter_spec: dict = {}
        if tenant_id is not None and self.multi_tenant:
            filter_spec["tenant_id"] = tenant_id
        list_kwargs: dict = {}
        if limit is not None:
            list_kwargs["limit"] = limit
        rows = self._db.express_sync.list(self._model_name, filter_spec, **list_kwargs)
        if rows:
            frame = pl.DataFrame(rows)
        else:
            frame = pl.DataFrame()
        return frame.lazy()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def single_tenant_db(tmp_path: Path):
    """Build a single-tenant DataFlow with a simple "Measurement" model."""
    # File-backed SQLite so express_sync (sync callers) uses a durable store
    # rather than an :memory: instance that may be swapped between
    # threads by the runtime.
    db_path = tmp_path / "ml_source.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

    @df.model
    class Measurement:
        id: str
        name: str
        value: float

    # Trigger lazy connection so express_sync is ready on first use.
    df._ensure_connected()
    try:
        yield df
    finally:
        try:
            df.close()
        except Exception:
            pass


@pytest.fixture
def multi_tenant_db(tmp_path: Path):
    """Build a multi-tenant DataFlow for TenantRequiredError coverage."""
    db_path = tmp_path / "ml_mt_source.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True, multi_tenant=True)
    df._ensure_connected()
    try:
        yield df
    finally:
        try:
            df.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ml_feature_source_returns_lazyframe(single_tenant_db: DataFlow):
    """Happy path — materialize returns a polars LazyFrame usable with transform."""
    db = single_tenant_db

    db.express_sync.create("Measurement", {"id": "m1", "name": "a", "value": 1.5})
    db.express_sync.create("Measurement", {"id": "m2", "name": "b", "value": 2.5})
    db.express_sync.create("Measurement", {"id": "m3", "name": "c", "value": 3.5})

    group = DataFlowTableFeatureGroup(db=db, model_name="Measurement")
    source = ml_feature_source(group)

    assert isinstance(source, pl.LazyFrame)
    collected = source.collect()
    assert collected.height == 3
    values = sorted(collected["value"].to_list())
    assert values == [1.5, 2.5, 3.5]


def test_ml_feature_source_write_then_read_persistence(
    single_tenant_db: DataFlow,
):
    """State persistence verification — write via express, read via ml_feature_source."""
    db = single_tenant_db

    # Write
    db.express_sync.create(
        "Measurement", {"id": "persist-1", "name": "alpha", "value": 100.0}
    )

    # Read back via ml_feature_source
    group = DataFlowTableFeatureGroup(db=db, model_name="Measurement")
    df = ml_feature_source(group).collect()

    names = df["name"].to_list()
    assert "alpha" in names, f"persisted row not visible: {names}"


def test_ml_feature_source_feeds_transform(single_tenant_db: DataFlow):
    """End-to-end — ml_feature_source output accepted by dataflow.transform."""
    db = single_tenant_db

    db.express_sync.create("Measurement", {"id": "t1", "name": "x", "value": 10.0})
    db.express_sync.create("Measurement", {"id": "t2", "name": "y", "value": 20.0})

    group = DataFlowTableFeatureGroup(db=db, model_name="Measurement")
    source = ml_feature_source(group)

    result = transform(pl.col("value") * 2, source, name="doubled", tenant_id=None)
    collected = result.collect()
    doubled = sorted(collected["doubled"].to_list())
    assert doubled == [20.0, 40.0]

    # Transform metadata must be present on the lazy result
    meta = getattr(result, "_kailash_ml_metadata", {})
    assert meta.get("kailash_ml.transform") == "doubled"


def test_ml_feature_source_multi_tenant_without_tenant_id_raises(
    multi_tenant_db: DataFlow,
):
    """rules/tenant-isolation.md § 2 — multi_tenant=True requires tenant_id."""
    db = multi_tenant_db

    group = DataFlowTableFeatureGroup(db=db, model_name="SomeModel", multi_tenant=True)

    with pytest.raises(TenantRequiredError, match="tenant_id is required"):
        ml_feature_source(group)  # no tenant_id


def test_ml_feature_source_propagates_classification_metadata(
    single_tenant_db: DataFlow,
):
    """spec § 2.5 — classification metadata surfaces on returned LazyFrame."""
    db = single_tenant_db

    db.express_sync.create("Measurement", {"id": "c1", "name": "d", "value": 5.0})

    group = DataFlowTableFeatureGroup(
        db=db,
        model_name="Measurement",
        classification={"name": "pii", "value": "public"},
    )
    source = ml_feature_source(group)

    meta = getattr(source, "_kailash_ml_metadata", {})
    assert "kailash_ml.classification" in meta
    assert meta["kailash_ml.classification"] == {
        "name": "pii",
        "value": "public",
    }


def test_ml_feature_source_forwards_limit(single_tenant_db: DataFlow):
    """spec § 2.2 — limit is forwarded to the FeatureGroup's materialize."""
    db = single_tenant_db

    for i in range(5):
        db.express_sync.create(
            "Measurement",
            {"id": f"lim-{i}", "name": f"n{i}", "value": float(i)},
        )

    group = DataFlowTableFeatureGroup(db=db, model_name="Measurement")
    source = ml_feature_source(group, limit=2)
    collected = source.collect()

    assert collected.height == 2
    # Verify the group actually saw the limit kwarg (not just polars post-filter)
    assert group._materialize_calls[-1]["limit"] == 2


def test_ml_feature_source_lineage_hash_stable_across_calls(
    single_tenant_db: DataFlow,
):
    """dataset_hash of a feature source is stable for the same underlying rows."""
    from dataflow.ml import hash as df_hash

    db = single_tenant_db

    db.express_sync.create("Measurement", {"id": "h1", "name": "p", "value": 1.0})
    db.express_sync.create("Measurement", {"id": "h2", "name": "q", "value": 2.0})

    group = DataFlowTableFeatureGroup(db=db, model_name="Measurement")
    frame_a = ml_feature_source(group).collect()
    frame_b = ml_feature_source(group).collect()

    assert df_hash(frame_a) == df_hash(frame_b)
