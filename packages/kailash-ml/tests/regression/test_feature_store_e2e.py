# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W6-021 — Tier-3 e2e regression for canonical FeatureStore.

Per ``specs/ml-feature-store.md`` § 11.4 (Wave 6 follow-up: create a
Tier-2+ e2e exercising ``kailash_ml.features.FeatureStore`` via a real
``DataFlow(...)`` instance + real Postgres + the
``dataflow.ml_feature_source`` binding) and ``rules/testing.md``
§ "End-to-End Pipeline Regression".

DOCS-EXACT shape executed verbatim from ``specs/ml-feature-store.md``
§ 8.2 (Feature Retrieval — Multi-Tenant) — the only deviation from the
spec snippet is gating on real Postgres + binding availability.

Skip gates (Tier-3 contract — real everything; never silently no-op):

1. ``POSTGRES_TEST_URL`` env var MUST be set (else skip with reason).
2. ``dataflow.ml_feature_source`` binding MUST be importable through
   the same resolution path that ``FeatureStore.get_features()``
   uses internally (else skip with reason citing the spec § 11.4
   blocker — the binding lands at the location ``FeatureStore``
   searches, not at ``dataflow.ml.ml_feature_source``).

Cross-references:

* ``rules/facade-manager-detection.md`` MUST 1, 2, 3 — wiring contract
  for ``FeatureStore`` (companion ``test_feature_store_wiring.py``
  shipped as W6-022).
* ``rules/tenant-isolation.md`` MUST 1, 2 — tenant_id is the second
  cache-key dimension; missing tenant_id raises TenantRequiredError.
* ``rules/dependencies.md`` § "Optional Extras with Loud Failure" —
  binding absence raises an actionable ImportError; this test relies
  on that contract to gate cleanly.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

pytestmark = [pytest.mark.regression, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Hard skip gates — Tier-3 contract
# ---------------------------------------------------------------------------


_POSTGRES_URL = os.environ.get("POSTGRES_TEST_URL")
if _POSTGRES_URL is None:
    pytest.skip(
        "POSTGRES_TEST_URL env var is required for Tier-3 FeatureStore e2e "
        "(see rules/testing.md § Tier 3). Set "
        "POSTGRES_TEST_URL=postgresql://user:pass@host:port/db to run.",
        allow_module_level=True,
    )

try:
    import polars as pl  # noqa: F401
except ImportError as exc:  # pragma: no cover — manifest dep
    pytest.skip(
        f"polars not installed (kailash-ml dependency drift): {exc}",
        allow_module_level=True,
    )

# Gate on the binding the FeatureStore actually consumes — see
# kailash_ml/features/store.py::_import_ml_feature_source. The store
# searches ``dataflow.ml_feature_source`` then
# ``dataflow.ml_integration.ml_feature_source``; the binding currently
# lives at ``dataflow.ml.ml_feature_source`` (W31 31b cleanup pending).
from kailash_ml.features.store import _import_ml_feature_source  # noqa: E402

try:
    _import_ml_feature_source()
except ImportError as exc:
    pytest.skip(
        f"dataflow.ml_feature_source binding not yet wired at the path "
        f"FeatureStore.get_features() consumes (see specs/ml-feature-store.md "
        f"§ 11.4 — blocked on W31 31b). Skipping until the binding lands. "
        f"Underlying error: {exc}",
        allow_module_level=True,
    )

from dataflow import DataFlow  # noqa: E402
from kailash_ml.errors import FeatureStoreError, TenantRequiredError  # noqa: E402
from kailash_ml.features import (  # noqa: E402
    CANONICAL_SINGLE_TENANT_SENTINEL,
    FeatureField,
    FeatureSchema,
    FeatureStore,
)


# ---------------------------------------------------------------------------
# Fixtures — real DataFlow + real Postgres
# ---------------------------------------------------------------------------


@pytest.fixture
async def real_dataflow():
    """Construct a real DataFlow against ``POSTGRES_TEST_URL``.

    Per ``rules/dataflow-pool.md`` Rule 2 the constructor performs a
    SELECT 1 health check; a failed check raises and the test fails
    loud rather than silently degrading.
    """
    df = DataFlow(_POSTGRES_URL, multi_tenant=True)
    try:
        yield df
    finally:
        # DataFlow exposes close() / async-close lifecycle — best-effort.
        close = getattr(df, "close", None)
        if callable(close):
            try:
                await close()
            except TypeError:
                close()


@pytest.fixture
def churn_schema() -> FeatureSchema:
    """DOCS-EXACT FeatureSchema from specs/ml-feature-store.md § 8.1."""
    return FeatureSchema(
        name="user_churn_e2e",
        version=1,
        fields=(
            FeatureField(name="login_count_7d", dtype="int64"),
            FeatureField(name="purchase_amount_30d", dtype="float64"),
            FeatureField(name="is_premium", dtype="bool", nullable=False),
        ),
        entity_id_column="user_id",
        timestamp_column="event_time",
    )


# ---------------------------------------------------------------------------
# Test 1 — DOCS-EXACT § 8.2 multi-tenant retrieval round-trip
# ---------------------------------------------------------------------------


async def test_feature_store_get_features_multi_tenant_round_trip(
    real_dataflow: DataFlow,
    churn_schema: FeatureSchema,
) -> None:
    """DOCS-EXACT § 8.2 — multi-tenant retrieval against real Postgres.

    Verifies ``FeatureStore.get_features(schema, tenant_id="acme")``
    returns a polars.DataFrame (NOT a LazyFrame, per spec invariant
    #1) routed through the live ``dataflow.ml_feature_source`` binding.

    The binding's behaviour against an empty feature table is to
    return an empty polars.DataFrame whose schema matches
    ``FeatureSchema.fields`` — this is the read-back state-persistence
    contract: a get_features call that hits the binding and survives
    the type-check at the public API boundary.
    """
    tenant_id = f"e2e-fs-{uuid.uuid4().hex[:8]}"
    fs = FeatureStore(real_dataflow)
    assert fs.dataflow is real_dataflow

    df = await fs.get_features(churn_schema, tenant_id=tenant_id)
    assert isinstance(df, pl.DataFrame), (
        f"FeatureStore.get_features MUST return polars.DataFrame "
        f"(spec § 4.1 MUST 4); got {type(df).__name__}"
    )


# ---------------------------------------------------------------------------
# Test 2 — point-in-time-correct retrieval round-trips through binding
# ---------------------------------------------------------------------------


async def test_feature_store_get_features_point_in_time(
    real_dataflow: DataFlow,
    churn_schema: FeatureSchema,
) -> None:
    """DOCS-EXACT § 8.2 — point-in-time-correct retrieval.

    ``timestamp=`` MUST be respected end-to-end. The retrieval still
    routes through the binding; the test asserts shape, not content
    (content depends on a populated feature table that lives outside
    this test's scope per spec § 1.2 — FeatureStore does NOT own the
    materialisation DDL).
    """
    tenant_id = f"e2e-fs-pit-{uuid.uuid4().hex[:8]}"
    fs = FeatureStore(real_dataflow)
    as_of = datetime(2026, 4, 1, tzinfo=timezone.utc)
    df = await fs.get_features(
        churn_schema,
        timestamp=as_of,
        tenant_id=tenant_id,
        entity_ids=["u1", "u2", "u3"],
    )
    assert isinstance(df, pl.DataFrame)


# ---------------------------------------------------------------------------
# Test 3 — DOCS-EXACT § 8.3 single-tenant default sentinel
# ---------------------------------------------------------------------------


async def test_feature_store_single_tenant_default_round_trip(
    real_dataflow: DataFlow,
    churn_schema: FeatureSchema,
) -> None:
    """DOCS-EXACT § 8.3 — bind ``CANONICAL_SINGLE_TENANT_SENTINEL`` at
    construction; method calls may omit tenant_id thereafter.

    The default tenant_id is eager-validated at construction
    (FeatureStore.__init__) — passing the canonical sentinel MUST NOT
    raise; passing an invalid sentinel ('default', 'global', '')
    raises (covered by Tier-1 test_feature_store_unit.py).
    """
    fs = FeatureStore(real_dataflow, default_tenant_id=CANONICAL_SINGLE_TENANT_SENTINEL)
    assert fs.default_tenant_id == CANONICAL_SINGLE_TENANT_SENTINEL
    df = await fs.get_features(churn_schema)  # tenant_id omitted; default applies
    assert isinstance(df, pl.DataFrame)


# ---------------------------------------------------------------------------
# Test 4 — TenantRequiredError surfaces unchanged on missing tenant_id
# ---------------------------------------------------------------------------


async def test_feature_store_missing_tenant_raises_typed_error(
    real_dataflow: DataFlow,
    churn_schema: FeatureSchema,
) -> None:
    """Per ``rules/tenant-isolation.md`` Rule 2 + spec § 4.2, a
    multi-tenant FeatureStore call without a tenant_id MUST raise
    :class:`TenantRequiredError` (not FeatureStoreError, not
    ImportError, not silent default).

    This is the negative-path round-trip — the typed error is the
    user-visible contract for missing tenant; it MUST surface
    unchanged through ``FeatureStore.get_features`` even when
    everything else (DataFlow, binding) is real and live.
    """
    fs = FeatureStore(real_dataflow)  # no default_tenant_id
    with pytest.raises(TenantRequiredError):
        await fs.get_features(churn_schema)


# ---------------------------------------------------------------------------
# Test 5 — cache-key + invalidation pattern round-trip (read-back via
# the helper methods themselves; no external cache exercised, but the
# tenant + version + schema dimensions are asserted to survive the
# canonical key shape per spec § 8.4)
# ---------------------------------------------------------------------------


async def test_feature_store_cache_key_and_invalidation_round_trip(
    real_dataflow: DataFlow,
    churn_schema: FeatureSchema,
) -> None:
    """DOCS-EXACT § 8.4 — cache_key_for_row + invalidation_pattern.

    Read-back here is structural: every dimension the spec mandates
    (tenant_id, schema name, version, row_key) MUST survive into the
    rendered key. A regression that drops any dimension breaks both
    cache lookup AND the version-wildcard sweep contract (Rule 3a).
    """
    fs = FeatureStore(real_dataflow)
    key = fs.cache_key_for_row(churn_schema, row_key="u1", tenant_id="acme")
    # Spec § 8.4: 'kailash_ml:v1:acme:feature:user_churn:1:u1' — adapted
    # for our schema name.
    assert key == "kailash_ml:v1:acme:feature:user_churn_e2e:1:u1"

    pattern = fs.invalidation_pattern(churn_schema, tenant_id="acme")
    assert pattern == "kailash_ml:v*:acme:feature:user_churn_e2e:1:*"

    pattern_all = fs.invalidation_pattern(
        churn_schema, tenant_id="acme", all_versions=True
    )
    assert pattern_all == "kailash_ml:v*:acme:feature:user_churn_e2e:*"
