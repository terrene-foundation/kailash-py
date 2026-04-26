# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring test for the canonical 1.0+ ``kailash_ml.features.FeatureStore``.

Per ``rules/facade-manager-detection.md`` MUST 1 every ``*Store`` manager
exposed via the public surface MUST have a Tier-2 wiring test imported
through the framework facade. MUST 2 mandates the file name
``test_<lowercase_manager_name>_wiring.py`` so the absence is grep-able.

Spec source: ``specs/ml-feature-store.md`` § 7.2 + § 10. The fifteen
conformance assertions in § 10 are exercised here against a real
``DataFlow(...)`` instance backed by file-based SQLite (real
infrastructure per ``rules/testing.md`` Tier 2 — NO mocks). The legacy
sibling test ``test_feature_store.py`` exercises the 0.x engine surface
(``kailash_ml.engines.feature_store``) and is intentionally untouched.

Conformance assertions covered (15 from § 10 of ml-feature-store.md):

1. ``kailash_ml.features.__all__`` lists exactly the six § 2.1 symbols,
   each with a corresponding eager import.
2. ``FeatureStore.__init__(dataflow, *, default_tenant_id=None)``
   matches § 2.2 exactly.
3. ``FeatureStore(None)`` raises ``TypeError`` with the actionable
   message at ``store.py:104-109``.
4. ``default_tenant_id`` is eager-validated at construction via
   ``validate_tenant_id``.
5. ``fs.dataflow`` and ``fs.default_tenant_id`` are read-only
   properties.
6. ``FeatureSchema.content_hash`` is sha256 first-16-hex of the
   canonical payload, deterministic across processes.
7. ``FeatureField.dtype`` rejects non-allowlist values at construction.
8. ``get_features`` signature matches § 4.1 exactly.
9. ``get_features`` re-raises ``TenantRequiredError`` and ``ImportError``
   unchanged; wraps every other ``Exception`` as ``FeatureStoreError``.
10. Cache key shape matches
    ``kailash_ml:v1:{tenant_id}:feature:{schema_name}:{version}:{row_key}``.
11. ``validate_tenant_id`` rejects ``None``, non-``str``, the three
    forbidden sentinels, and tenant_id failing the regex.
12. ``make_feature_group_wildcard`` emits ``v*`` so a future keyspace
    bump does not strand legacy keys.
13. ``_import_ml_feature_source`` raises a loud ``ImportError`` whose
    message points to ``dataflow-ml-integration.md §1.1``.
14. Three structured INFO/EXCEPTION lines emitted on every
    ``get_features`` call (``feature_store.get_features.{start,ok,error}``).
15. No column names from ``FeatureSchema.fields`` appear at INFO+ log
    level (``rules/observability.md`` Rule 8).
"""
from __future__ import annotations

import inspect
import logging
from pathlib import Path

import kailash_ml.features as features_pkg
import pytest
from kailash_ml.errors import FeatureStoreError, TenantRequiredError
from kailash_ml.features import (
    CANONICAL_SINGLE_TENANT_SENTINEL,
    FeatureField,
    FeatureSchema,
    FeatureStore,
    make_feature_cache_key,
    make_feature_group_wildcard,
)
from kailash_ml.features.cache_keys import (
    FEATURE_KEY_VERSION,
    FORBIDDEN_TENANT_SENTINELS,
    validate_tenant_id,
)
from kailash_ml.features.store import _import_ml_feature_source

from dataflow import DataFlow

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Real-infrastructure fixtures (file-backed SQLite via DataFlow)
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path):
    """Build a real ``DataFlow`` against file-backed SQLite.

    Mirrors the kailash-dataflow convention used in
    ``test_dataflow_ml_event_wiring.py`` — file-backed SQLite is
    real infrastructure for kailash-ml's Tier 2 contract (no mocks).
    """
    db_path = tmp_path / "feature_store_wiring.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    df._ensure_connected()
    try:
        yield df
    finally:
        try:
            df.close()
        except Exception:
            pass


@pytest.fixture
def churn_schema() -> FeatureSchema:
    """A representative multi-field FeatureSchema."""
    return FeatureSchema(
        name="user_churn",
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
# Conformance § 10 #1 — `__all__` exports six symbols, all eagerly imported
# ---------------------------------------------------------------------------


def test_assertion_01_features_pkg_exports_six_symbols_eagerly() -> None:
    """``kailash_ml.features.__all__`` lists exactly the six § 2.1 symbols
    each with an eager (module-scope) import bound on the package.
    """
    expected = {
        "CANONICAL_SINGLE_TENANT_SENTINEL",
        "FeatureField",
        "FeatureSchema",
        "FeatureStore",
        "make_feature_cache_key",
        "make_feature_group_wildcard",
    }
    assert set(features_pkg.__all__) == expected, (
        f"features.__all__ drift: got {set(features_pkg.__all__)}, "
        f"expected {expected}"
    )
    # Eager-import binding — every entry resolvable as a package attribute
    # WITHOUT triggering ``__getattr__`` lazy resolution. Per
    # ``rules/orphan-detection.md`` MUST 6.
    for symbol in expected:
        assert hasattr(features_pkg, symbol), (
            f"{symbol} declared in __all__ but not bound at module scope "
            f"— violates rules/orphan-detection.md MUST 6"
        )


# ---------------------------------------------------------------------------
# Conformance § 10 #2 — Constructor signature
# ---------------------------------------------------------------------------


def test_assertion_02_constructor_signature_matches_spec() -> None:
    """``FeatureStore.__init__(dataflow, *, default_tenant_id=None)``
    matches § 2.2 exactly.
    """
    sig = inspect.signature(FeatureStore.__init__)
    params = list(sig.parameters.values())
    # self, dataflow (positional-or-keyword), *, default_tenant_id (keyword-only)
    assert params[0].name == "self"
    assert params[1].name == "dataflow"
    assert params[1].kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.POSITIONAL_ONLY,
    )
    assert params[2].name == "default_tenant_id"
    assert params[2].kind == inspect.Parameter.KEYWORD_ONLY
    assert params[2].default is None
    # Exactly three params (self + dataflow + default_tenant_id) — no extras
    assert len(params) == 3, f"unexpected extra params: {params}"


# ---------------------------------------------------------------------------
# Conformance § 10 #3 — FeatureStore(None) raises actionable TypeError
# ---------------------------------------------------------------------------


def test_assertion_03_none_dataflow_raises_actionable_typeerror() -> None:
    """``FeatureStore(None)`` raises ``TypeError`` with the actionable
    message at ``store.py:104-109`` citing
    ``rules/facade-manager-detection.md`` Rule 3.
    """
    with pytest.raises(TypeError) as exc_info:
        FeatureStore(None)  # type: ignore[arg-type]
    msg = str(exc_info.value)
    assert "FeatureStore(dataflow=...) is required" in msg
    assert "facade-manager-detection.md" in msg
    assert "Rule 3" in msg


# ---------------------------------------------------------------------------
# Conformance § 10 #4 — default_tenant_id eager-validated
# ---------------------------------------------------------------------------


def test_assertion_04_default_tenant_id_eager_validated_at_construction(
    db: DataFlow,
) -> None:
    """``default_tenant_id`` MUST be eagerly validated at construction
    via ``validate_tenant_id`` so a forbidden sentinel fails before
    any method call.
    """
    # Forbidden sentinel rejected
    with pytest.raises(TenantRequiredError):
        FeatureStore(db, default_tenant_id="default")
    with pytest.raises(TenantRequiredError):
        FeatureStore(db, default_tenant_id="global")
    with pytest.raises(TenantRequiredError):
        FeatureStore(db, default_tenant_id="")

    # Canonical single-tenant sentinel accepted
    fs = FeatureStore(db, default_tenant_id=CANONICAL_SINGLE_TENANT_SENTINEL)
    assert fs.default_tenant_id == CANONICAL_SINGLE_TENANT_SENTINEL


# ---------------------------------------------------------------------------
# Conformance § 10 #5 — fs.dataflow / fs.default_tenant_id are read-only
# ---------------------------------------------------------------------------


def test_assertion_05_properties_are_read_only(db: DataFlow) -> None:
    """``fs.dataflow`` and ``fs.default_tenant_id`` are read-only
    properties — assignment raises ``AttributeError``.
    """
    fs = FeatureStore(db, default_tenant_id="acme")
    assert fs.dataflow is db  # exact same instance
    assert fs.default_tenant_id == "acme"

    # Properties have no setter — assignment raises AttributeError
    with pytest.raises(AttributeError):
        fs.dataflow = None  # type: ignore[misc]
    with pytest.raises(AttributeError):
        fs.default_tenant_id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Conformance § 10 #6 — FeatureSchema.content_hash determinism
# ---------------------------------------------------------------------------


def test_assertion_06_content_hash_is_sha256_first_16_hex_deterministic() -> None:
    """``FeatureSchema.content_hash`` is sha256 first-16-hex of the
    canonical payload, deterministic across constructions.
    """
    fields = (
        FeatureField(name="x", dtype="int64"),
        FeatureField(name="y", dtype="float64"),
    )
    s1 = FeatureSchema(name="demo", version=1, fields=fields)
    s2 = FeatureSchema(name="demo", version=1, fields=fields)
    assert s1.content_hash == s2.content_hash, "non-deterministic content_hash"
    # 16-hex shape (sha256 truncated to first 16 chars)
    assert len(s1.content_hash) == 16
    assert all(
        c in "0123456789abcdef" for c in s1.content_hash
    ), f"content_hash {s1.content_hash!r} is not lowercase hex"
    # Different fields produce different hash
    s_alt = FeatureSchema(
        name="demo",
        version=1,
        fields=(FeatureField(name="x", dtype="int64"),),
    )
    assert s_alt.content_hash != s1.content_hash


# ---------------------------------------------------------------------------
# Conformance § 10 #7 — FeatureField.dtype rejects non-allowlist values
# ---------------------------------------------------------------------------


def test_assertion_07_feature_field_rejects_non_allowlist_dtype() -> None:
    """``FeatureField.dtype`` rejects values outside ``ALLOWED_DTYPES``
    at construction.
    """
    # Bogus dtype rejected
    with pytest.raises(ValueError, match="not a polars-native dtype"):
        FeatureField(name="x", dtype="not_a_real_dtype")
    # Synonym path accepted
    f = FeatureField(name="x", dtype="float")  # synonym for float64
    assert f.dtype == "float64"
    # Canonical path accepted
    f2 = FeatureField(name="y", dtype="int64")
    assert f2.dtype == "int64"


# ---------------------------------------------------------------------------
# Conformance § 10 #8 — get_features signature
# ---------------------------------------------------------------------------


def test_assertion_08_get_features_signature_matches_spec() -> None:
    """``get_features(schema, timestamp=None, *, tenant_id=None,
    entity_ids=None) -> pl.DataFrame`` matches § 4.1.
    """
    sig = inspect.signature(FeatureStore.get_features)
    params = list(sig.parameters.values())
    # self, schema, timestamp, *, tenant_id, entity_ids
    names = [p.name for p in params]
    assert names == [
        "self",
        "schema",
        "timestamp",
        "tenant_id",
        "entity_ids",
    ], f"signature drift: {names}"
    # timestamp default is None
    assert params[2].default is None
    # tenant_id and entity_ids are keyword-only
    assert params[3].kind == inspect.Parameter.KEYWORD_ONLY
    assert params[3].default is None
    assert params[4].kind == inspect.Parameter.KEYWORD_ONLY
    assert params[4].default is None


# ---------------------------------------------------------------------------
# Conformance § 10 #9 — error pass-through (TenantRequiredError + ImportError)
#                       + FeatureStoreError reclassification on other errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assertion_09a_get_features_passes_through_tenant_required_error(
    db: DataFlow, churn_schema: FeatureSchema
) -> None:
    """``get_features`` re-raises ``TenantRequiredError`` unchanged.

    Constructed without ``default_tenant_id`` AND called without
    ``tenant_id=`` — the validator raises and the wrapper MUST NOT
    reclassify as ``FeatureStoreError``.
    """
    fs = FeatureStore(db)  # no default_tenant_id
    with pytest.raises(TenantRequiredError):
        await fs.get_features(churn_schema)  # tenant_id omitted


@pytest.mark.asyncio
async def test_assertion_09b_get_features_wraps_other_exceptions_as_feature_store_error(
    db: DataFlow, churn_schema: FeatureSchema
) -> None:
    """``get_features`` wraps every non-Tenant/non-Import exception as
    ``FeatureStoreError(reason=..., tenant_id=...)`` with ``__cause__``
    chained to the original.

    The 1.0+ canonical surface delegates to ``dataflow.ml_feature_source``
    which duck-types on ``.materialize`` — ``FeatureSchema`` does not
    expose ``.materialize`` so the binding raises a wrapped error
    that get_features reclassifies as ``FeatureStoreError``.
    """
    fs = FeatureStore(db, default_tenant_id="acme")
    with pytest.raises(FeatureStoreError) as exc_info:
        await fs.get_features(churn_schema)
    err = exc_info.value
    # Tenant context propagated for forensic correlation
    assert err.tenant_id == "acme"
    assert "get_features failed" in err.reason
    # Original cause chained — operators can drill into the binding-layer
    # error without losing the FeatureStore context
    assert err.__cause__ is not None


# ---------------------------------------------------------------------------
# Conformance § 10 #10 — Cache key shape
# ---------------------------------------------------------------------------


def test_assertion_10_cache_key_shape_matches_canonical_form(db: DataFlow) -> None:
    """Cache key shape matches
    ``kailash_ml:v1:{tenant_id}:feature:{schema_name}:{version}:{row_key}``
    when emitted via ``FeatureStore.cache_key_for_row``.
    """
    fs = FeatureStore(db)
    schema = FeatureSchema(
        name="user_churn",
        version=2,
        fields=(FeatureField(name="x", dtype="int64"),),
    )
    key = fs.cache_key_for_row(schema, row_key="u1", tenant_id="acme")
    assert key == "kailash_ml:v1:acme:feature:user_churn:2:u1"

    # Version segment in the key MUST be the canonical FEATURE_KEY_VERSION
    assert FEATURE_KEY_VERSION == "v1"
    # Direct helper produces identical bytes — the wrapper does not drift
    direct = make_feature_cache_key(
        tenant_id="acme",
        schema_name="user_churn",
        version=2,
        row_key="u1",
    )
    assert direct == key

    # default_tenant_id resolves when caller omits tenant_id=
    fs_default = FeatureStore(db, default_tenant_id=CANONICAL_SINGLE_TENANT_SENTINEL)
    default_key = fs_default.cache_key_for_row(schema, row_key="u1")
    assert default_key == (
        f"kailash_ml:v1:{CANONICAL_SINGLE_TENANT_SENTINEL}:feature:user_churn:2:u1"
    )


# ---------------------------------------------------------------------------
# Conformance § 10 #11 — validate_tenant_id rejects None, non-str, sentinels, regex
# ---------------------------------------------------------------------------


def test_assertion_11_validate_tenant_id_rejects_invalid_inputs() -> None:
    """``validate_tenant_id`` rejects ``None``, non-``str``, the three
    forbidden sentinels, and tenant_id failing
    ``^[A-Za-z_][A-Za-z0-9_\\-]*$``.
    """
    op = "feature_store.test"
    # None
    with pytest.raises(TenantRequiredError):
        validate_tenant_id(None, operation=op)
    # Non-str (int)
    with pytest.raises(TenantRequiredError):
        validate_tenant_id(42, operation=op)  # type: ignore[arg-type]
    # Three forbidden sentinels — exhaustive enumeration so a future
    # additive change to FORBIDDEN_TENANT_SENTINELS surfaces here.
    assert FORBIDDEN_TENANT_SENTINELS == frozenset({"default", "global", ""})
    for forbidden in FORBIDDEN_TENANT_SENTINELS:
        with pytest.raises(TenantRequiredError):
            validate_tenant_id(forbidden, operation=op)
    # Regex failure: leading digit
    with pytest.raises(TenantRequiredError):
        validate_tenant_id("1tenant", operation=op)
    # Regex failure: contains a colon (would split key)
    with pytest.raises(TenantRequiredError):
        validate_tenant_id("ten:ant", operation=op)
    # Regex failure: whitespace
    with pytest.raises(TenantRequiredError):
        validate_tenant_id("ten ant", operation=op)
    # Valid forms: single-tenant sentinel + alphanumeric + dash
    assert validate_tenant_id("acme", operation=op) == "acme"
    assert validate_tenant_id("acme-corp", operation=op) == "acme-corp"
    assert validate_tenant_id(CANONICAL_SINGLE_TENANT_SENTINEL, operation=op) == (
        CANONICAL_SINGLE_TENANT_SENTINEL
    )


# ---------------------------------------------------------------------------
# Conformance § 10 #12 — make_feature_group_wildcard emits v* for keyspace bumps
# ---------------------------------------------------------------------------


def test_assertion_12_invalidation_wildcard_uses_keyspace_version_wildcard(
    db: DataFlow,
) -> None:
    """``make_feature_group_wildcard`` MUST emit ``v*`` per
    ``rules/tenant-isolation.md`` Rule 3a so a future
    ``FEATURE_KEY_VERSION`` bump does not strand legacy keys.
    """
    schema = FeatureSchema(
        name="user_churn",
        version=3,
        fields=(FeatureField(name="x", dtype="int64"),),
    )
    fs = FeatureStore(db)
    # Version-pinned form — v* in keyspace position
    pattern = fs.invalidation_pattern(schema, tenant_id="acme")
    assert pattern == "kailash_ml:v*:acme:feature:user_churn:3:*"
    # all_versions form — v* in keyspace AND * in version position
    pattern_all = fs.invalidation_pattern(schema, tenant_id="acme", all_versions=True)
    assert pattern_all == "kailash_ml:v*:acme:feature:user_churn:*"
    # Direct helper drifts identically
    direct = make_feature_group_wildcard(
        tenant_id="acme",
        schema_name="user_churn",
        version=3,
    )
    assert direct == pattern


# ---------------------------------------------------------------------------
# Conformance § 10 #13 — Loud ImportError on missing dataflow.ml_feature_source
# ---------------------------------------------------------------------------


def test_assertion_13_import_helper_resolves_or_loud_failure() -> None:
    """``_import_ml_feature_source`` either resolves the real binding
    (DataFlow ≥ 2.1) or raises a loud ``ImportError`` whose message
    points to ``dataflow-ml-integration.md §1.1``.
    """
    try:
        binding = _import_ml_feature_source()
    except ImportError as exc:
        msg = str(exc)
        # Loud, actionable, cites the canonical sibling spec.
        assert "ml_feature_source" in msg
        assert "dataflow-ml-integration.md" in msg
    else:
        # Live binding — confirm it is callable per the contract.
        assert callable(binding), "ml_feature_source MUST be callable"


# ---------------------------------------------------------------------------
# Conformance § 10 #14 + #15 —
#   #14: get_features emits start/ok/error structured log lines
#   #15: schema field NAMES never appear at INFO+ level
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assertion_14_15_get_features_emits_structured_logs_no_field_names_at_info(
    db: DataFlow, churn_schema: FeatureSchema, caplog: pytest.LogCaptureFixture
) -> None:
    """``get_features`` emits ``feature_store.get_features.start`` and
    either ``.ok`` or ``.error`` per call; field NAMES from
    ``FeatureSchema.fields`` MUST NOT appear at INFO+ log level
    (``rules/observability.md`` Rule 8).
    """
    fs = FeatureStore(db, default_tenant_id="acme")
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="kailash_ml.features.store"):
        with pytest.raises(FeatureStoreError):
            # FeatureSchema lacks .materialize → binding raises →
            # FeatureStore wraps as FeatureStoreError. Path emits
            # start + error log lines.
            await fs.get_features(churn_schema)

    messages = [r.message for r in caplog.records]
    levels_at_start_or_above = [
        r.levelno for r in caplog.records if r.levelno >= logging.INFO
    ]

    # #14 — start line emitted at INFO
    assert (
        "feature_store.get_features.start" in messages
    ), f"missing start log line; got messages={messages}"
    # #14 — error line emitted (logger.exception logs at ERROR)
    assert (
        "feature_store.get_features.error" in messages
    ), f"missing error log line; got messages={messages}"
    # Sanity: at least one INFO-or-higher record — confirms the path
    # actually emitted at the level the spec mandates.
    assert levels_at_start_or_above, "no INFO+ log records captured"

    # #15 — schema FIELD names never appear at INFO+ log level
    field_names = [f.name for f in churn_schema.fields]
    assert field_names == ["login_count_7d", "purchase_amount_30d", "is_premium"]
    for record in caplog.records:
        if record.levelno < logging.INFO:
            continue
        # Fields are stored on the LogRecord via `extra=`; we check both
        # the formatted message AND the raw __dict__ of the LogRecord
        # so a future regression that interpolates field names into the
        # message string OR adds them as extra= kwargs is caught.
        rendered = record.getMessage()
        for fname in field_names:
            assert fname not in rendered, (
                f"field name {fname!r} leaked into INFO+ log message: "
                f"{rendered!r} (rules/observability.md Rule 8 violation)"
            )
        # Extra attributes attached to the record
        for key, value in record.__dict__.items():
            if key in {
                "args",
                "msg",
                "message",
                "name",
                "exc_info",
                "exc_text",
                "stack_info",
                "pathname",
                "filename",
                "module",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "taskName",
            }:
                # Standard LogRecord internals — not user payload.
                continue
            for fname in field_names:
                assert fname not in str(value), (
                    f"field name {fname!r} leaked into INFO+ log extra "
                    f"{key}={value!r} (rules/observability.md Rule 8 violation)"
                )

    # Schema NAME ('user_churn') is permitted at INFO; only FIELD names
    # are schema-revealing per Rule 8. Confirm at least one INFO record
    # carried schema='user_churn' to prove the structured payload is
    # actually populated.
    saw_schema_name = any(
        getattr(r, "schema", None) == churn_schema.name
        for r in caplog.records
        if r.levelno >= logging.INFO
    )
    assert (
        saw_schema_name
    ), "expected schema='user_churn' in at least one INFO log record"
