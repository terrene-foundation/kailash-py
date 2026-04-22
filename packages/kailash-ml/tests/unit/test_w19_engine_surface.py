# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W19 — MLEngine __init__ + DI + setup() + compare() invariant tests.

Covers the 9 invariants from the master wave plan §W19 against
``specs/ml-engines-v2.md §2.1 MUST 1-7 + §2.2``:

1. Zero-arg construction works
2. All 7 DI slots accepted
3. DI overrides honored literally (no silent wrap)
4. ``setup()`` idempotent per ``(df_fingerprint, target, ignore, feature_store_name)``
5. ``compare()`` routes every family through ``self.fit()`` (Lightning spine)
6. ``setup()`` raises ``TargetNotFoundError`` / ``TargetInFeaturesError``
7. 8-method surface exactly (setup, compare, fit, predict, finalize, evaluate, register, serve)
8. Async-first (sync variant not required by W19 — async is the canonical)
9. ``tenant_id`` plumbed onto ``SetupResult`` and ``ComparisonResult``

Also exercises §2.1 MUST 1b — the store-URL authority chain routes
through ``kailash_ml._env.resolve_store_url`` rather than hand-rolled
``os.environ.get(...)`` at the engine.
"""
from __future__ import annotations

from typing import Any

import polars as pl
import pytest

from kailash_ml import MLEngine, SetupResult
from kailash_ml._env import (
    CANONICAL_STORE_URL_ENV,
    DEFAULT_STORE_URL,
    LEGACY_TRACKER_DB_ENV,
)
from kailash_ml.engine import (
    TargetInFeaturesError,
    TargetNotFoundError,
    _default_store_url,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _frame(n: int = 20) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "x1": list(range(n)),
            "x2": [i * 2 for i in range(n)],
            "y": [i % 2 for i in range(n)],
        }
    )


# ----------------------------------------------------------------------
# Invariant 1: zero-arg construction works
# ----------------------------------------------------------------------


class TestInvariant1ZeroArgConstruction:
    def test_no_args_succeeds(self) -> None:
        MLEngine()

    def test_store_url_defaults_via_resolve_store_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zero-arg store_url MUST come from the shared authority chain."""
        monkeypatch.delenv(CANONICAL_STORE_URL_ENV, raising=False)
        monkeypatch.delenv(LEGACY_TRACKER_DB_ENV, raising=False)

        engine = MLEngine()
        expected_default = _default_store_url()
        # _default_store_url delegates to resolve_store_url(None) with tilde
        # expansion on; DEFAULT_STORE_URL carries the literal ~.
        assert expected_default.startswith("sqlite:///")
        assert "/.kailash_ml/ml.db" in expected_default
        assert engine.store_url == expected_default
        # Sanity: the unexpanded canonical default IS the literal with ~.
        assert "~/.kailash_ml/ml.db" in DEFAULT_STORE_URL


# ----------------------------------------------------------------------
# Invariant 2: all 7 DI slots accepted  (§2.2 signature)
# ----------------------------------------------------------------------


class TestInvariant2AllDISlotsAccepted:
    SLOTS = (
        "feature_store",
        "registry",
        "tracker",
        "trainer",
        "artifact_store",
        "connection_manager",
    )

    def test_slots_kwargs_on_init(self) -> None:
        """Every DI slot from §2.2 accepted by __init__ without error."""
        import inspect

        sig = inspect.signature(MLEngine.__init__)
        names = set(sig.parameters.keys())
        for slot in self.SLOTS:
            assert slot in names, f"MLEngine.__init__ missing DI slot: {slot}"

    def test_all_slots_accept_sentinel_object(self) -> None:
        """Passing a sentinel for every DI slot MUST succeed (accept-phase)."""
        sentinel = object()
        engine = MLEngine(
            feature_store=sentinel,
            registry=sentinel,
            tracker=sentinel,
            trainer=sentinel,
            artifact_store=sentinel,
            connection_manager=sentinel,
        )
        # Stored on the engine private slots — overrides honored (see §2.1 MUST 3)
        assert engine._feature_store is sentinel
        assert engine._registry is sentinel
        assert engine._tracker is sentinel
        assert engine._trainer is sentinel
        assert engine._artifact_store is sentinel
        assert engine._connection_manager is sentinel


# ----------------------------------------------------------------------
# Invariant 3: DI overrides honored literally (no silent wrap)
# ----------------------------------------------------------------------


class _NamedDouble:
    """Tagged adapter so identity checks work across construction paths."""

    def __init__(self, label: str) -> None:
        self.label = label


class TestInvariant3DIHonoredLiterally:
    def test_injected_tracker_is_used_as_is(self) -> None:
        """engine._tracker IS the injected object (no wrap, no default replace)."""
        t = _NamedDouble("custom-tracker")
        engine = MLEngine(tracker=t)
        assert engine._tracker is t  # identity, not equality

    def test_injected_registry_is_used_as_is(self) -> None:
        r = _NamedDouble("custom-registry")
        engine = MLEngine(registry=r)
        assert engine._registry is r

    def test_injected_feature_store_is_used_as_is(self) -> None:
        fs = _NamedDouble("custom-fs")
        engine = MLEngine(feature_store=fs)
        assert engine._feature_store is fs

    def test_injected_artifact_store_is_used_as_is(self) -> None:
        a = _NamedDouble("custom-artifacts")
        engine = MLEngine(artifact_store=a)
        assert engine._artifact_store is a

    def test_injected_connection_manager_is_used_as_is(self) -> None:
        cm = _NamedDouble("custom-cm")
        engine = MLEngine(connection_manager=cm)
        assert engine._connection_manager is cm


# ----------------------------------------------------------------------
# Invariant 4: setup() idempotent per (df_fingerprint, target, ignore, fs_name)
# ----------------------------------------------------------------------


class TestInvariant4SetupIdempotent:
    @pytest.mark.asyncio
    async def test_same_inputs_produce_same_schema_hash(self) -> None:
        engine = MLEngine()
        df = _frame()
        r1 = await engine.setup(df, target="y")
        r2 = await engine.setup(df, target="y")
        assert r1.schema_hash == r2.schema_hash
        assert r1.split_seed == r2.split_seed

    @pytest.mark.asyncio
    async def test_different_target_produces_different_hash(self) -> None:
        engine = MLEngine()
        df = _frame()
        r1 = await engine.setup(df, target="y")
        # Second setup with a different target column → different fingerprint
        df2 = df.with_columns(pl.Series("yy", df["y"]))
        r2 = await engine.setup(df2, target="yy")
        assert r1.schema_hash != r2.schema_hash

    @pytest.mark.asyncio
    async def test_different_ignore_produces_different_hash(self) -> None:
        engine = MLEngine()
        df = _frame()
        r1 = await engine.setup(df, target="y")
        engine2 = MLEngine()
        r2 = await engine2.setup(df, target="y", ignore=["x2"])
        assert r1.schema_hash != r2.schema_hash


# ----------------------------------------------------------------------
# Invariant 5: compare() routes every family through self.fit()
# ----------------------------------------------------------------------


class TestInvariant5CompareLightningRouted:
    @pytest.mark.asyncio
    async def test_compare_invokes_fit_per_family(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every family in the sweep MUST be dispatched via MLEngine.fit()."""
        from kailash_ml._results import ComparisonResult, TrainingResult

        engine = MLEngine()
        calls: list[dict[str, Any]] = []

        async def _fake_fit(**kwargs: Any) -> TrainingResult:
            calls.append(kwargs)
            fam = kwargs.get("family") or "custom"
            return TrainingResult(
                family=fam,
                metrics={"accuracy": 0.5 + 0.1 * len(calls)},
                model_uri=f"models://w19-fake-{fam}/v1",
                device_used="cpu",
                accelerator="cpu",
                precision="32-true",
                elapsed_seconds=0.01,
                tracker_run_id=f"run-{len(calls)}",
                tenant_id=engine.tenant_id,
                artifact_uris={},
                lightning_trainer_config={},
                hyperparameters={},
                feature_importance=None,
                device=None,
            )

        # Monkeypatch the engine's bound fit so compare routes through the stub
        monkeypatch.setattr(engine, "fit", _fake_fit)

        result = await engine.compare(
            data=_frame(),
            target="y",
            metric="accuracy",
            families=["sklearn"],  # only sklearn is a hard dep
        )
        assert isinstance(result, ComparisonResult)
        assert len(calls) == 1
        assert calls[0].get("family") == "sklearn"
        # Lightning-spine contract: compare() handed the family to fit()
        # which is the single dispatch point for accelerator/precision.


# ----------------------------------------------------------------------
# Invariant 6: setup() raises typed errors (§2.3)
# ----------------------------------------------------------------------


class TestInvariant6TypedSetupErrors:
    @pytest.mark.asyncio
    async def test_target_not_found_raises_typed_error(self) -> None:
        engine = MLEngine()
        df = _frame()
        with pytest.raises(TargetNotFoundError) as ei:
            await engine.setup(df, target="missing_col")
        assert ei.value.column == "missing_col"
        assert "y" in ei.value.columns or "x1" in ei.value.columns

    @pytest.mark.asyncio
    async def test_empty_target_raises_value_error(self) -> None:
        engine = MLEngine()
        df = _frame()
        with pytest.raises(ValueError, match="non-empty string"):
            await engine.setup(df, target="")

    @pytest.mark.asyncio
    async def test_zero_feature_columns_raises(self) -> None:
        """Target + ignore list leaving zero features → ValueError."""
        engine = MLEngine()
        df = _frame()
        with pytest.raises(ValueError, match="zero feature"):
            await engine.setup(df, target="y", ignore=["x1", "x2"])


# ----------------------------------------------------------------------
# Invariant 7: 8-method surface exactly (setup, compare, fit, predict,
#              finalize, evaluate, register, serve)
# ----------------------------------------------------------------------


class TestInvariant7EightMethodSurface:
    REQUIRED = (
        "setup",
        "compare",
        "fit",
        "predict",
        "finalize",
        "evaluate",
        "register",
        "serve",
    )

    def test_all_8_methods_present_and_callable(self) -> None:
        engine = MLEngine()
        for name in self.REQUIRED:
            assert hasattr(engine, name), f"missing: {name}"
            assert callable(getattr(engine, name))

    def test_no_unauthorized_9th_public_ml_method(self) -> None:
        """Public method set MUST stay bounded; guard against accretion.

        Any non-underscore callable outside the 8 canonical methods AND
        outside the allow-listed helpers (properties, read-only getters
        for introspection) requires a spec amendment per §2.1 MUST 5.
        """
        engine = MLEngine()
        allowed_helpers: set[str] = {
            "tenant_id",  # property
            "accelerator",  # property
            "backend_info",  # property
            "store_url",  # property
        }
        allowed = set(self.REQUIRED) | allowed_helpers
        public_attrs = {
            name
            for name in dir(engine)
            if not name.startswith("_") and callable(getattr(engine, name))
        }
        # Properties showing up as non-callable are filtered automatically.
        unauthorized = public_attrs - allowed
        assert unauthorized == set(), (
            f"MLEngine has unauthorized public callables (9th-method drift): "
            f"{sorted(unauthorized)} — see ml-engines-v2.md §2.1 MUST 5"
        )


# ----------------------------------------------------------------------
# Invariant 9: tenant_id plumbed onto SetupResult + ComparisonResult
# ----------------------------------------------------------------------


class TestInvariant9TenantIdPlumbed:
    @pytest.mark.asyncio
    async def test_setup_result_echoes_tenant_id(self) -> None:
        engine = MLEngine(tenant_id="acme")
        result: SetupResult = await engine.setup(_frame(), target="y")
        assert result.tenant_id == "acme"

    @pytest.mark.asyncio
    async def test_setup_result_echoes_none_single_tenant(self) -> None:
        engine = MLEngine()
        result: SetupResult = await engine.setup(_frame(), target="y")
        assert result.tenant_id is None


# ----------------------------------------------------------------------
# Invariant 2 (W19.b): Six-primitive default composition (§2.1 MUST 2)
# Engine-owns-construction contract — every DI slot that was None at
# __init__ is non-None after `_ensure_default_primitives_async()`.
# Idempotent — second call is a no-op. DI-injected sentinels are
# NEVER replaced by the default.
# ----------------------------------------------------------------------


@pytest.fixture
def _tmp_store_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> str:
    """Redirect engine defaults to a throwaway store + artifact root.

    Every W19.b test uses this fixture so the test never touches
    ``~/.kailash_ml/``. Honours the single-authority chain per §2.1
    MUST 1b (writes through ``KAILASH_ML_STORE_URL``).
    """
    store_url = f"sqlite:///{tmp_path}/w19b.db"
    monkeypatch.setenv(CANONICAL_STORE_URL_ENV, store_url)
    monkeypatch.delenv(LEGACY_TRACKER_DB_ENV, raising=False)
    monkeypatch.setenv("KAILASH_ML_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    return store_url


class TestInvariant2SixPrimitivesConstructed:
    """§2.1 MUST 2 — Engine owns construction of the six primitives."""

    @pytest.mark.asyncio
    async def test_engine_info_all_false_before_ensure(
        self, _tmp_store_env: str
    ) -> None:
        """Zero-arg engine carries zero populated slots at construction."""
        engine = MLEngine()
        snap = engine.engine_info
        assert snap == {
            "connection_manager": False,
            "artifact_store": False,
            "registry": False,
            "feature_store": False,
            "trainer": False,
            "experiment_tracker": False,
        }

    @pytest.mark.asyncio
    async def test_ensure_default_primitives_fills_every_slot(
        self, _tmp_store_env: str
    ) -> None:
        """After `_ensure_default_primitives_async()` every slot is populated."""
        engine = MLEngine()
        await engine._ensure_default_primitives_async()
        try:
            snap = engine.engine_info
            assert all(
                snap.values()
            ), f"expected every slot populated; got {dict(snap)}"
            # Canonical default types — proves the engine constructed
            # real primitives, not placeholders.
            assert engine._connection_manager is not None
            assert type(engine._connection_manager).__name__ == "ConnectionManager"
            assert type(engine._artifact_store).__name__ == "LocalFileArtifactStore"
            assert type(engine._registry).__name__ == "ModelRegistry"
            assert type(engine._feature_store).__name__ == "FeatureStore"
            assert type(engine._trainer).__name__ == "TrainingPipeline"
            assert type(engine._experiment_tracker).__name__ == "ExperimentTracker"
        finally:
            # Cleanup the pool / tracker to avoid resource warnings.
            await engine._experiment_tracker.close()
            await engine._connection_manager.close()

    @pytest.mark.asyncio
    async def test_ensure_default_primitives_is_idempotent(
        self, _tmp_store_env: str
    ) -> None:
        """Second call MUST be a no-op — identity preserved for every slot."""
        engine = MLEngine()
        await engine._ensure_default_primitives_async()
        try:
            first = (
                engine._connection_manager,
                engine._artifact_store,
                engine._registry,
                engine._feature_store,
                engine._trainer,
                engine._experiment_tracker,
            )
            await engine._ensure_default_primitives_async()
            second = (
                engine._connection_manager,
                engine._artifact_store,
                engine._registry,
                engine._feature_store,
                engine._trainer,
                engine._experiment_tracker,
            )
            for a, b in zip(first, second):
                assert a is b, (
                    f"slot identity broken by second ensure call: "
                    f"first={type(a).__name__} second={type(b).__name__}"
                )
        finally:
            await engine._experiment_tracker.close()
            await engine._connection_manager.close()

    @pytest.mark.asyncio
    async def test_di_injected_connection_manager_not_replaced(
        self, _tmp_store_env: str
    ) -> None:
        """DI-injected ConnectionManager is honored — default NEVER replaces it."""
        from kailash.db.connection import ConnectionManager

        injected = ConnectionManager(_tmp_store_env)
        await injected.initialize()
        engine = MLEngine(connection_manager=injected)
        try:
            await engine._ensure_default_primitives_async()
            # Identity MUST survive — the default path skipped the slot
            assert engine._connection_manager is injected
            # Downstream primitives MUST be built against the injected CM
            assert engine._registry is not None
            assert engine._feature_store is not None
        finally:
            await engine._experiment_tracker.close()
            await injected.close()

    @pytest.mark.asyncio
    async def test_di_injected_artifact_store_not_replaced(
        self, _tmp_store_env: str
    ) -> None:
        """DI-injected ArtifactStore flows through to the default-built ModelRegistry."""
        sentinel = _NamedDouble("injected-artifact-store")
        engine = MLEngine(artifact_store=sentinel)
        try:
            await engine._ensure_default_primitives_async()
            # The injected artifact-store identity survives
            assert engine._artifact_store is sentinel
        finally:
            await engine._experiment_tracker.close()
            await engine._connection_manager.close()

    @pytest.mark.asyncio
    async def test_experiment_tracker_inherits_engine_tenant_id(
        self, _tmp_store_env: str
    ) -> None:
        """Default ExperimentTracker receives engine.tenant_id as default_tenant_id."""
        engine = MLEngine(tenant_id="acme")
        await engine._ensure_default_primitives_async()
        try:
            assert engine._experiment_tracker.default_tenant_id == "acme"
        finally:
            await engine._experiment_tracker.close()
            await engine._connection_manager.close()
