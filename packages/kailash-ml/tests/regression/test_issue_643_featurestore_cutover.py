# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression — issue #643 step 3: the 2.0.0 FeatureStore canonical cutover.

Two contracts are pinned here:

1. **Top-level resolution flip (structural).** After the 2.0.0 cutover,
   ``from kailash_ml import FeatureStore`` MUST resolve to the canonical
   read surface ``kailash_ml.features.FeatureStore`` (NOT the legacy
   ``kailash_ml.engines.feature_store.FeatureStore``) AND MUST NOT emit a
   ``DeprecationWarning`` on access (the 1.7.2 bridge shim was removed at
   cutover). The legacy class MUST remain importable via its explicit
   module path — the non-deprecated home for write-path callers
   (``packages/kailash-ml/MIGRATION.md``). These are structural assertions
   (object identity + warning capture), not lexical greps, per
   ``rules/probe-driven-verification.md`` Rule 3.

2. **Write-via-DataFlow-model → read-via-canonical-get_features round-trip
   (Tier-2, real infra).** This is the migration story the cutover depends
   on: the canonical 1.0+ FeatureStore is read-only (spec § 1.2); writers
   move feature materialisation to a ``@db.model`` + ``express.create`` and
   read back through ``FeatureStore.get_features``. Before this test the
   suite only asserted ``get_features`` returns a ``DataFrame`` against an
   *unseeded* table — it never proved a seeded write is actually
   retrievable, nor that latest-per-entity / as-of semantics hold. This
   test seeds real rows in file-backed SQLite (real infrastructure per
   ``rules/testing.md`` Tier 2 — NO mocks) and asserts the read-back, the
   latest-per-entity dedup, and point-in-time correctness.

Cross-references:

* ``specs/ml-feature-store.md`` § 1.2 (read-only surface), § 4.1
  (get_features contract), § 11 (legacy write ops deferred to M2).
* ``rules/facade-manager-detection.md`` MUST 1 — companion of
  ``test_feature_store_wiring.py``.
* ``rules/testing.md`` § "State Persistence Verification" — every write
  verified with a read-back.
"""
from __future__ import annotations

import warnings
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Contract 1 — top-level resolution flip (structural; no DataFlow needed)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_top_level_featurestore_resolves_to_canonical() -> None:
    """``from kailash_ml import FeatureStore`` IS the canonical surface."""
    import kailash_ml
    import kailash_ml.features as features_pkg

    assert kailash_ml.FeatureStore is features_pkg.FeatureStore, (
        "issue #643 2.0.0 cutover: top-level FeatureStore must resolve to "
        "kailash_ml.features.FeatureStore (the canonical read surface)"
    )
    assert (
        kailash_ml.FeatureStore.__module__ == "kailash_ml.features.store"
    ), kailash_ml.FeatureStore.__module__


@pytest.mark.regression
def test_top_level_featurestore_access_emits_no_deprecation_warning() -> None:
    """The 1.7.2 bridge DeprecationWarning is removed at the 2.0.0 cutover."""
    import importlib

    import kailash_ml

    # Re-import fresh so module-scope side effects are excluded; the access
    # itself routes through __getattr__ which is where the old shim lived.
    importlib.reload(kailash_ml)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _ = kailash_ml.FeatureStore
    feature_store_deprecations = [
        w
        for w in caught
        if issubclass(w.category, DeprecationWarning)
        and "FeatureStore" in str(w.message)
    ]
    assert not feature_store_deprecations, [
        str(w.message) for w in feature_store_deprecations
    ]


@pytest.mark.regression
def test_legacy_featurestore_still_importable_via_explicit_path() -> None:
    """The legacy write-capable surface remains importable (non-deprecated
    home for write-path callers per MIGRATION.md); it is a DISTINCT class
    from the canonical surface (different constructor contract)."""
    import kailash_ml
    from kailash_ml.engines.feature_store import FeatureStore as LegacyFeatureStore

    assert LegacyFeatureStore.__module__ == "kailash_ml.engines.feature_store"
    assert kailash_ml.FeatureStore is not LegacyFeatureStore


# ---------------------------------------------------------------------------
# Contract 2 — write-then-read round-trip (Tier-2, real file-backed SQLite)
# ---------------------------------------------------------------------------

# Skip cleanly if the dataflow.ml_feature_source binding FeatureStore consumes
# is unavailable — never silently no-op (Tier-2 contract).
try:
    import polars as pl  # noqa: F401
except ImportError as exc:  # pragma: no cover — manifest dep
    pytest.skip(f"polars not installed: {exc}", allow_module_level=True)

from kailash_ml.features.store import _import_ml_feature_source  # noqa: E402

try:
    _import_ml_feature_source()
except ImportError as exc:
    pytest.skip(
        f"dataflow.ml_feature_source binding unavailable "
        f"(FeatureStore.get_features consumes it): {exc}",
        allow_module_level=True,
    )

from kailash_ml.features import (  # noqa: E402
    CANONICAL_SINGLE_TENANT_SENTINEL,
    FeatureField,
    FeatureSchema,
    FeatureStore,
)

from dataflow import DataFlow  # noqa: E402

_T1 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
_T2 = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)  # one week later


@pytest.fixture
def seeded_db(tmp_path: Path):
    """Single-tenant file-backed SQLite DataFlow with a feature table named
    after the schema, seeded with two observations for ``u1`` (different
    event times) and one for ``u2`` — so latest-per-entity dedup and as-of
    semantics are OBSERVABLE (single-row-per-entity tables hide both)."""
    db_path = tmp_path / "feat_643.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

    # schema.name MUST equal the DataFlow model name (the canonical
    # read adapter reads express_sync.list(schema.name)).
    @df.model
    class UserChurnFeatures:
        id: str
        user_id: str
        event_time: datetime
        login_count_7d: int
        purchase_amount_30d: float

    df._ensure_connected()

    # The canonical write path: materialise features as DataFlow model rows.
    df.express_sync.create(
        "UserChurnFeatures",
        {
            "id": "r1",
            "user_id": "u1",
            "event_time": _T1,
            "login_count_7d": 3,
            "purchase_amount_30d": 10.0,
        },
    )
    df.express_sync.create(
        "UserChurnFeatures",
        {
            "id": "r2",
            "user_id": "u1",
            "event_time": _T2,  # newer — latest-per-entity must pick this
            "login_count_7d": 7,
            "purchase_amount_30d": 25.0,
        },
    )
    df.express_sync.create(
        "UserChurnFeatures",
        {
            "id": "r3",
            "user_id": "u2",
            "event_time": _T1,
            "login_count_7d": 1,
            "purchase_amount_30d": 5.0,
        },
    )
    try:
        yield df
    finally:
        try:
            df.close()
        except Exception:
            pass


@pytest.fixture
def churn_schema() -> FeatureSchema:
    return FeatureSchema(
        name="UserChurnFeatures",
        version=1,
        fields=(
            FeatureField(name="login_count_7d", dtype="int64"),
            FeatureField(name="purchase_amount_30d", dtype="float64"),
        ),
        entity_id_column="user_id",
        timestamp_column="event_time",
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_cutover_write_via_model_read_via_canonical_get_features(
    seeded_db: DataFlow,
    churn_schema: FeatureSchema,
) -> None:
    """Migration-story validation: features written through a DataFlow model
    are retrievable through the canonical ``FeatureStore.get_features`` — and
    with no timestamp, the LATEST row per entity is returned (not every
    historical row)."""
    fs = FeatureStore(seeded_db, default_tenant_id=CANONICAL_SINGLE_TENANT_SENTINEL)
    result = await fs.get_features(churn_schema)

    assert isinstance(result, pl.DataFrame)
    # entity_id + declared field columns project through.
    assert set(result.columns) == {"user_id", "login_count_7d", "purchase_amount_30d"}
    # latest-per-entity: one row per entity, u1's NEWER (_T2) observation wins.
    by_user = {row["user_id"]: row for row in result.to_dicts()}
    assert set(by_user) == {"u1", "u2"}, by_user
    assert by_user["u1"]["login_count_7d"] == 7, "u1 must reflect the _T2 row"
    assert by_user["u1"]["purchase_amount_30d"] == 25.0
    assert by_user["u2"]["login_count_7d"] == 1


@pytest.mark.regression
@pytest.mark.asyncio
async def test_cutover_get_features_point_in_time_as_of(
    seeded_db: DataFlow,
    churn_schema: FeatureSchema,
) -> None:
    """Point-in-time correctness: as of ``_T1`` (before u1's second
    observation), u1's feature value is the _T1 row (login=3), not the
    later _T2 row (login=7)."""
    fs = FeatureStore(seeded_db, default_tenant_id=CANONICAL_SINGLE_TENANT_SENTINEL)
    result = await fs.get_features(churn_schema, timestamp=_T1)

    by_user = {row["user_id"]: row for row in result.to_dicts()}
    assert by_user["u1"]["login_count_7d"] == 3, (
        "as-of _T1 must return u1's _T1 value (3), not the post-_T1 value (7) "
        "— point-in-time correctness per spec § 6.2 MUST 1"
    )
    assert by_user["u2"]["login_count_7d"] == 1
