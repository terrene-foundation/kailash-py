# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MLEngine — single-point entry for kailash-ml 2.0 (Phase 2 scaffold).

Implements the construction surface of `specs/ml-engines.md` §2:
zero-arg construction with production defaults (§2.1 MUST 1), owns
construction of the six primitives (§2.1 MUST 2), accepts DI overrides
for every primitive without silent wrap (§2.1 MUST 3), exposes exactly
the documented eight methods (§2.1 MUST 5).

The eight method bodies are Phase 2 scaffolds — they validate their
arguments against the MUST clauses in §2.1 / §2.3 (argument
conflicts, target-not-in-features, etc.) and then raise
`NotImplementedError` with a phase pointer. Phase 3-5 will fill in the
concrete training / prediction / serving bodies.

Phase 2 deliberately does NOT touch the existing engines under
`kailash_ml.engines.*`; the 2.0 cut (Phase F) relocates legacy
classes to `kailash_ml.legacy.*`. Phase 2 is additive.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import pickle
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Union

from kailash_ml._device import BackendInfo, detect_backend
from kailash_ml.engines import _engine_sql as _sql

logger = logging.getLogger(__name__)

__all__ = [
    "MLEngine",
    "Patience",
    "EngineNotSetUpError",
    "ConflictingArgumentsError",
    "TargetNotFoundError",
    "TargetInFeaturesError",
    "AcceleratorUnavailableError",
    "TenantRequiredError",
    "ModelNotFoundError",
    "OnnxExportError",
    "SchemaDriftError",
]


_PHASE_3 = (
    "Phase 3 will implement this method (Trainable adapters + Lightning "
    "Trainer integration)."
)
_PHASE_4 = "Phase 4 will implement this method (inference path + ONNX export)."
_PHASE_5 = (
    "Phase 5 will implement this method (InferenceServer + multi-channel " "serving)."
)


# ---------------------------------------------------------------------------
# Typed exceptions (ml-engines.md §2.3)
# ---------------------------------------------------------------------------


class _EngineError(RuntimeError):
    """Base for MLEngine-typed errors."""


class EngineNotSetUpError(_EngineError):
    """Raised when fit()/compare() is called before setup()."""


class ConflictingArgumentsError(_EngineError):
    """Raised when mutually-exclusive arguments are both supplied."""


class TargetNotFoundError(_EngineError):
    def __init__(self, column: str, columns: tuple[str, ...]) -> None:
        super().__init__(
            f"Target column '{column}' not found in DataFrame. "
            f"Columns: {list(columns)}."
        )
        self.column = column
        self.columns = columns


class TargetInFeaturesError(_EngineError):
    def __init__(self, column: str) -> None:
        super().__init__(
            f"Target column '{column}' appears in the feature set. "
            f"Remove it from features or add to ignore=[...]."
        )
        self.column = column


class AcceleratorUnavailableError(_EngineError):
    def __init__(self, requested: str, detected: tuple[str, ...]) -> None:
        super().__init__(
            f"Requested accelerator '{requested}' is not available. "
            f"Detected: {list(detected)}. Use accelerator='auto' to let "
            f"the resolver pick the best available backend."
        )
        self.requested = requested
        self.detected = detected


class TenantRequiredError(_EngineError):
    """Raised when a multi-tenant primitive is accessed without tenant_id."""


class ModelNotFoundError(_EngineError):
    def __init__(self, name: str, version: Optional[int] = None) -> None:
        if version is None:
            super().__init__(f"Model '{name}' not found in registry.")
        else:
            super().__init__(f"Model '{name}' version {version} not found in registry.")
        self.name = name
        self.version = version


class OnnxExportError(_EngineError):
    def __init__(self, framework: str, cause: str) -> None:
        super().__init__(
            f"ONNX export failed for framework '{framework}': {cause}. "
            f"Pass format='pickle' to opt out of ONNX requirement."
        )
        self.framework = framework
        self.cause = cause


class SchemaDriftError(_EngineError):
    def __init__(self, before: Any, after: Any) -> None:
        super().__init__(
            f"Schema drift detected between setup() and fit(): "
            f"before={before!r}, after={after!r}."
        )
        self.before = before
        self.after = after


# ---------------------------------------------------------------------------
# Support types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Patience:
    """Early-stopping patience spec.

    Minimal Phase 2 scaffold; Phase 3 widens with mode/min_delta as the
    Lightning EarlyStopping callback lands.
    """

    patience: int
    min_delta: float = 0.0
    mode: str = "min"


# ---------------------------------------------------------------------------
# Default store resolution
# ---------------------------------------------------------------------------


_DEFAULT_STORE_DIR = pathlib.Path.home() / ".kailash_ml"
_DEFAULT_DB_PATH = _DEFAULT_STORE_DIR / "ml.db"


def _default_store_url() -> str:
    """Return the default SQLite store URL, honoring an env override.

    `KAILASH_ML_STORE_URL` lets CI and test runs point the Engine at a
    throwaway location without patching the Engine itself.
    """
    override = os.environ.get("KAILASH_ML_STORE_URL")
    if override:
        return override
    return f"sqlite:///{_DEFAULT_DB_PATH}"


# ---------------------------------------------------------------------------
# Family → Trainable factory
# ---------------------------------------------------------------------------


_FAMILY_ALIASES = {
    "sklearn": "sklearn",
    "random_forest": "sklearn",
    "rf": "sklearn",
    "logreg": "sklearn",
    "logistic": "sklearn",
    "xgb": "xgboost",
    "xgboost": "xgboost",
    "lgbm": "lightgbm",
    "lightgbm": "lightgbm",
    "torch": "torch",
    "pytorch": "torch",
    "lightning": "lightning",
}


def _build_trainable_from_family(family: str, *, target: str) -> Any:
    """Resolve a family string to an initialized Trainable adapter.

    Per `specs/ml-engines.md` §2.1 MUST 8 the family name is an opaque
    registered identifier; the set of known names is maintained here.
    Unknown family names raise a typed error naming the known families.
    """
    # Lazy import so that `import kailash_ml` doesn't force lightning/xgboost
    # imports until the user actually calls fit(family=…).
    from kailash_ml import trainable as _tr

    canonical = _FAMILY_ALIASES.get(family.lower())
    if canonical is None:
        raise ValueError(
            f"Unknown family: '{family}'. Known families: "
            f"{sorted(set(_FAMILY_ALIASES.values()))}. "
            f"Aliases: {sorted(_FAMILY_ALIASES.keys())}."
        )

    if canonical == "sklearn":
        return _tr.SklearnTrainable(target=target)
    if canonical == "xgboost":
        return _tr.XGBoostTrainable(target=target)
    if canonical == "lightgbm":
        return _tr.LightGBMTrainable(target=target)
    if canonical == "torch":
        raise ValueError(
            "family='torch' requires `trainable=TorchTrainable(model=…, "
            "loss_fn=…)` — no zero-config default. Use family='sklearn' for "
            "the three-line hello world, or pass your own TorchTrainable."
        )
    if canonical == "lightning":
        raise ValueError(
            "family='lightning' requires `trainable=LightningTrainable"
            "(module=your_lightning_module)` — no zero-config default."
        )
    # Defensive — should be unreachable
    raise ValueError(f"Internal: unmapped family canonical '{canonical}'")


# ---------------------------------------------------------------------------
# MLEngine (ml-engines.md §2.1)
# ---------------------------------------------------------------------------


class MLEngine:
    """Single-point entry for the kailash-ml 2.0 lifecycle.

    Construction is zero-arg capable (§2.1 MUST 1) and owns the
    composition of the six primitives (§2.1 MUST 2). Every constructor
    override is honored as-is (§2.1 MUST 3) — no silent wrap. The
    public method surface is exactly the documented eight (§2.1 MUST 5).

    Phase 2 scaffolds the construction surface and method signatures;
    Phase 3-5 fill in the concrete bodies. See module docstring for the
    phase allocation.
    """

    # Fixed public method surface (§2.1 MUST 5): setup, compare, fit,
    # predict, finalize, evaluate, register, serve. Any addition is a
    # spec amendment.

    def __init__(
        self,
        store: Union[str, Any, None] = None,
        *,
        accelerator: str = "auto",
        precision: str = "auto",
        devices: Union[str, int, list] = "auto",
        tenant_id: Optional[str] = None,
        # DI overrides (any combination accepted; §2.1 MUST 3)
        feature_store: Any = None,
        registry: Any = None,
        tracker: Any = None,
        trainer: Any = None,
        artifact_store: Any = None,
        connection_manager: Any = None,
    ) -> None:
        # Validate simple arguments up-front so construction errors are
        # loud and typed.
        if not isinstance(accelerator, str):
            raise TypeError(
                f"accelerator must be a string; got {type(accelerator).__name__}."
            )
        if not isinstance(precision, str):
            raise TypeError(
                f"precision must be a string; got {type(precision).__name__}."
            )
        if tenant_id is not None and not isinstance(tenant_id, str):
            raise TypeError(
                f"tenant_id must be a string or None; got "
                f"{type(tenant_id).__name__}."
            )

        self._store_arg = store
        self._accelerator_request = accelerator
        self._precision_request = precision
        self._devices_request = devices
        self._tenant_id = tenant_id

        # DI slots. When an override is None, the Phase-3 default
        # construction path will populate the slot lazily. When an
        # override is supplied, the engine uses it as-is (§2.1 MUST 3).
        self._feature_store = feature_store
        self._registry = registry
        self._tracker = tracker
        self._trainer = trainer
        self._artifact_store = artifact_store
        self._connection_manager = connection_manager

        # Resolve the backend at construction time so that BackendInfo
        # is always available on the instance. For `accelerator="auto"`
        # this runs the priority resolver; for an explicit accelerator
        # this raises BackendUnavailable if the requested backend is
        # missing (§2.3 — translated to AcceleratorUnavailableError).
        self._backend_info: Optional[BackendInfo]
        self._backend_info = self._resolve_backend(accelerator)

        # Setup state: populated by .setup(); consumed by .fit() /
        # .compare() / .finalize(). None until the first setup() call.
        self._setup_result: Any = None

        # Store URL lazily resolved so the default directory is only
        # created when the user actually uses the default store. The
        # Phase-2 construction path does NOT touch the filesystem.
        self._resolved_store_url: Optional[str] = None

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_backend(requested: str) -> Optional[BackendInfo]:
        """Resolve the backend requested at construction time.

        Returns None only when backend detection is not possible (e.g.
        torch not installed AND an explicit non-cpu backend was
        requested — currently handled by `detect_backend` raising).
        """
        if requested == "auto":
            return detect_backend(None)
        # Translate the typed _device exception into the engine's
        # AcceleratorUnavailableError so that external callers only see
        # engine-shape exceptions from an engine-shape method.
        from kailash_ml._device import BackendUnavailable

        try:
            return detect_backend(requested)
        except BackendUnavailable as exc:
            raise AcceleratorUnavailableError(
                requested=requested,
                detected=exc.detected_backends,
            ) from exc
        except ValueError:
            # Unknown accelerator string — re-raise as-is; this is a
            # caller bug, not a hardware availability failure.
            raise

    # ------------------------------------------------------------------
    # Public read-only properties
    # ------------------------------------------------------------------

    @property
    def tenant_id(self) -> Optional[str]:
        return self._tenant_id

    @property
    def accelerator(self) -> str:
        """Resolved accelerator (concrete, never 'auto')."""
        if self._backend_info is None:
            # Defensive: detect_backend always returns a BackendInfo.
            return "cpu"
        return self._backend_info.accelerator

    @property
    def backend_info(self) -> Optional[BackendInfo]:
        """The resolved BackendInfo (None when detection is unavailable)."""
        return self._backend_info

    @property
    def store_url(self) -> str:
        """Resolved store URL (lazy — defaults to ~/.kailash_ml/ml.db)."""
        if self._resolved_store_url is not None:
            return self._resolved_store_url
        store = self._store_arg
        if store is None:
            self._resolved_store_url = _default_store_url()
        elif isinstance(store, str):
            self._resolved_store_url = store
        else:
            # ConnectionManager or similar object — expose its url attr
            # if available; otherwise record the type for logging.
            url_attr = getattr(store, "url", None)
            self._resolved_store_url = (
                url_attr
                if isinstance(url_attr, str)
                else f"<injected:{type(store).__name__}>"
            )
        return self._resolved_store_url

    # ------------------------------------------------------------------
    # The eight public methods (§2.1 MUST 5)
    # ------------------------------------------------------------------

    async def setup(
        self,
        data: Any,
        *,
        target: str,
        ignore: Optional[list[str]] = None,
        feature_store: Any = None,
        test_size: float = 0.2,
        split_strategy: str = "holdout",
        seed: int = 42,
    ) -> Any:
        """Profile data, infer schema, detect task type, split train/test.

        Per ``specs/ml-engines.md`` §2.1 MUST 6, ``setup()`` is
        idempotent: two calls with identical
        ``(df_fingerprint, target, ignore, feature_store_name)``
        produce the same ``schema_hash`` and the same ``split_seed``.
        The ``schema_hash`` doubles as the canonical cache/registry key
        for every downstream ``fit()`` / ``compare()`` / ``finalize()``
        reachable from this Engine instance.

        Split strategies: Phase 3 implements ``"holdout"``; other
        strategies (``"kfold"``, ``"stratified_kfold"``,
        ``"walk_forward"``) raise a typed
        :class:`NotImplementedError` naming the deferring phase so a
        future session can complete them without reading the body.
        See the phase 3.1 gap journal for the deferred roadmap.
        """
        # Validate target argument shape before touching data so bad
        # calls fail loud and fast (§2.3).
        if not isinstance(target, str) or not target:
            raise ValueError("setup(target=...) must be a non-empty string.")

        if split_strategy not in (
            "holdout",
            "kfold",
            "stratified_kfold",
            "walk_forward",
        ):
            raise ValueError(
                f"setup(split_strategy=...) must be 'holdout', 'kfold', "
                f"'stratified_kfold', or 'walk_forward'; got {split_strategy!r}."
            )
        if not isinstance(test_size, (int, float)) or not (0 < float(test_size) < 1):
            raise ValueError(
                f"setup(test_size=...) must be a float in (0, 1); got {test_size!r}."
            )

        # Phase 3 implements holdout end-to-end; the other three
        # strategies raise a typed deferral until Phase 3.1 lands. We
        # check this BEFORE touching the DataFrame so unsupported
        # strategies fail without side-effects.
        if split_strategy != "holdout":
            raise NotImplementedError(
                f"split_strategy={split_strategy!r} — Phase 3 implements "
                f"'holdout' end-to-end; stratified/kfold/walk_forward are "
                f"tracked for Phase 3.1."
            )

        # Normalize polars-LazyFrame → DataFrame at the boundary so the
        # rest of setup works against a materialized frame (§7.1 MUST 2
        # — pandas is accepted via interop conversion; polars is native).
        df = self._to_polars_dataframe(data)

        # Validate target presence / target-not-in-features (§2.3).
        columns = tuple(str(c) for c in df.columns)
        if target not in columns:
            raise TargetNotFoundError(column=target, columns=columns)

        ignore_list = sorted(set(ignore or []))
        feature_cols = tuple(c for c in columns if c != target and c not in ignore_list)
        if target in feature_cols:
            # Defensive — should be impossible given the filter above.
            raise TargetInFeaturesError(column=target)
        if not feature_cols:
            raise ValueError(
                f"setup(target={target!r}, ignore={ignore!r}) leaves zero "
                f"feature columns. At least one feature is required."
            )

        # Resolve the feature store name so the idempotency key is
        # deterministic across runs. When the caller supplies a
        # FeatureStore object, we use its table prefix; when they pass
        # a string, we use it directly; default is "engine_default".
        fs_name = self._resolve_feature_store_name(feature_store)

        # Compute the schema hash per §2.1 MUST 6. The inputs are
        # canonicalised (sorted columns, sorted dtypes, sorted ignore)
        # so permutations of the same DataFrame produce the same hash.
        schema_hash = self._compute_schema_hash(
            df=df,
            target=target,
            ignore=ignore_list,
            feature_store_name=fs_name,
        )

        # Infer task type from target dtype + cardinality.
        task_type = self._infer_task_type(df, target)
        primary_metric = {
            "classification": "accuracy",
            "regression": "rmse",
            "clustering": "silhouette",
        }.get(task_type, "accuracy")

        # Deterministic split per holdout strategy. We materialise sizes
        # at setup() time so the SetupResult records EXACTLY what the
        # downstream fit() will see.
        n_total = int(df.height)
        if n_total < 2:
            raise ValueError(
                f"setup() requires at least 2 rows to split; got {n_total}."
            )
        n_test = max(1, int(round(n_total * float(test_size))))
        if n_test >= n_total:
            n_test = n_total - 1
        n_train = n_total - n_test

        # Build the SetupResult (imported here to avoid circular imports
        # at module load — _results is a lightweight module but we keep
        # the import local for symmetry with the trainable.fit() path).
        from kailash_ml._results import SetupResult

        # Build the schema_info dict with concrete dtype + null-count
        # per column (Phase 3 extended profile per §2.2 SetupResult).
        schema_info = self._build_schema_info(df, feature_cols, target)

        result = SetupResult(
            schema_hash=schema_hash,
            task_type=task_type,
            target=target,
            feature_columns=feature_cols,
            ignored_columns=tuple(ignore_list),
            split_strategy=split_strategy,
            split_seed=seed,
            train_size=n_train,
            test_size=n_test,
            primary_metric=primary_metric,
            tenant_id=self._tenant_id,
            feature_store_name=fs_name,
            schema_info=schema_info,
        )

        # Idempotency (§2.1 MUST 6). Store the result on the engine so
        # subsequent fit()/compare()/finalize() see the same split. If
        # setup() was already called with the same schema_hash for this
        # Engine instance, we return the cached result unchanged — no
        # duplicate FeatureSchema registration, no new split seed.
        cached = self._setup_result
        if isinstance(cached, SetupResult) and cached.schema_hash == schema_hash:
            logger.info(
                "setup.idempotent_hit",
                extra={
                    "schema_hash": schema_hash,
                    "tenant_id": self._tenant_id,
                },
            )
            return cached

        # Register the feature schema in the FeatureStore when one is
        # available. When no feature_store was injected AND no default
        # store is wired yet, we keep the SetupResult on the engine but
        # do not raise — the Engine still works for the in-memory path
        # fit() currently supports.
        fs_impl = feature_store or self._feature_store
        if fs_impl is not None and hasattr(fs_impl, "register_features"):
            try:
                from kailash_ml.types import FeatureField, FeatureSchema

                schema = FeatureSchema(
                    name=fs_name,
                    features=[
                        FeatureField(
                            name=col,
                            dtype=schema_info["columns"][col]["dtype"],
                            nullable=bool(schema_info["columns"][col]["nullable"]),
                        )
                        for col in feature_cols
                    ],
                    entity_id_column=self._infer_entity_id_column(df),
                )
                await fs_impl.register_features(schema)
            except Exception as exc:
                # Re-register with the same hash is a no-op in the store;
                # re-register with a different hash surfaces as ValueError
                # — we let it propagate so drift is loud.
                if isinstance(exc, ValueError):
                    raise
                logger.warning(
                    "setup.feature_store_register_failed",
                    extra={
                        "schema_hash": schema_hash,
                        "tenant_id": self._tenant_id,
                        "error": str(exc),
                    },
                )

        self._setup_result = result
        logger.info(
            "setup.complete",
            extra={
                "schema_hash": schema_hash,
                "task_type": task_type,
                "train_size": n_train,
                "test_size": n_test,
                "tenant_id": self._tenant_id,
            },
        )
        return result

    async def compare(
        self,
        *,
        families: Optional[list] = None,
        n_trials: int = 0,
        hp_search: str = "none",
        metric: Optional[str] = None,
        early_stopping: Optional[Patience] = None,
        timeout_seconds: Optional[float] = None,
    ) -> Any:
        """Train & rank candidate families (AutoML sweep).

        Phase 2 enforces the setup-before-compare invariant (§2.3) and
        defers the concrete sweep to Phase 3.
        """
        if self._setup_result is None:
            raise EngineNotSetUpError(
                "MLEngine.compare() requires setup() to be called first. "
                "Invoke `await engine.setup(data, target='...')` before "
                "compare()."
            )
        raise NotImplementedError(f"MLEngine.compare — {_PHASE_3}")

    async def fit(
        self,
        data: Any = None,
        *,
        target: Optional[str] = None,
        family: Optional[str] = None,
        trainable: Any = None,
        hyperparameters: Optional[Mapping[str, Any]] = None,
        hp_search: str = "none",
        n_trials: int = 0,
        metric: Optional[str] = None,
    ) -> Any:
        """Train a single family through the Lightning-wrapped Trainable adapter.

        Per specs/ml-engines.md §5.1 the three-line hello world form is:

            engine = km.Engine()
            result = await engine.fit(df, target="churned", family="sklearn")

        When ``setup()`` has not been called, ``data`` and ``target`` MUST be
        supplied explicitly. Routing: dispatches to the family's Lightning
        adapter (`SklearnTrainable` / `XGBoostTrainable` / etc.) which
        internally constructs `pl.Trainer(accelerator=…, devices=…,
        precision=…)` with concrete values resolved from `detect_backend()`
        (§3 MUST 2 — custom training loops BLOCKED at the adapter
        boundary). `tenant_id` is propagated from Engine into TrainingResult
        per §4.2 MUST 3.
        """
        # Validate family/trainable mutually-exclusive per §2.3
        if family is not None and trainable is not None:
            raise ConflictingArgumentsError(
                "fit(family=..., trainable=...) cannot both be supplied. "
                "Pass a registered family name OR a Trainable instance, "
                "not both."
            )

        # Default family when neither given
        if family is None and trainable is None:
            family = "sklearn"

        # Resolve data + target
        if data is None and self._setup_result is None:
            raise EngineNotSetUpError(
                "MLEngine.fit() requires either data=... or a prior setup() "
                "call. Pass `data=df, target='...'` directly or invoke "
                "`await engine.setup(data, target='...')` first."
            )
        if data is None:
            # Pull from setup result
            raise EngineNotSetUpError(
                "MLEngine.fit() without explicit data requires setup() to "
                "have stored a train split. Pass data=df, target='...' "
                "directly to fit() for now; integrated setup()->fit() lands "
                "in a later phase."
            )
        if target is None:
            raise ValueError(
                "MLEngine.fit(data=..., target=...) requires a target column "
                "name when data is supplied directly."
            )

        # Build the trainable from family name if not supplied
        if trainable is None:
            trainable = _build_trainable_from_family(family, target=target)

        # Build TrainingContext from Engine's resolved backend so the
        # trainable does NOT re-resolve (§3.2 MUST 4).
        from kailash_ml.trainable import TrainingContext

        info = self._backend_info or detect_backend()
        ctx = TrainingContext(
            accelerator=info.accelerator,
            precision=info.precision,
            devices=info.devices,
            device_string=info.device_string,
            backend=info.backend,
            tenant_id=self._tenant_id,
        )

        # Delegate to the trainable's Lightning-wrapped fit path
        result = trainable.fit(data, hyperparameters=hyperparameters or {}, context=ctx)

        # §4.2 MUST 3: ensure tenant_id on result reflects Engine's tenant_id
        if result.tenant_id != self._tenant_id:
            from dataclasses import replace

            result = replace(result, tenant_id=self._tenant_id)

        return result

    async def predict(
        self,
        model: Any,
        features: Any,
        *,
        version: Optional[int] = None,
        channel: str = "direct",
        options: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        """Serve a prediction (single record or batch, direct or via endpoint).

        Phase 4 implements the inference path + channel dispatch.
        """
        if channel not in ("direct", "rest", "mcp"):
            raise ValueError(
                f"predict(channel=...) must be 'direct', 'rest', or 'mcp'; "
                f"got {channel!r}."
            )
        raise NotImplementedError(f"MLEngine.predict — {_PHASE_4}")

    async def finalize(
        self,
        candidate: Any,
        *,
        full_fit: bool = True,
    ) -> Any:
        """Retrain top candidate on full training + holdout data.

        Phase 3 implements the full-fit retraining path.
        """
        if candidate is None:
            raise ValueError("finalize(candidate) must not be None.")
        raise NotImplementedError(f"MLEngine.finalize — {_PHASE_3}")

    async def evaluate(
        self,
        model: Any,
        data: Any,
        *,
        metrics: Optional[list[str]] = None,
        mode: str = "holdout",
    ) -> Any:
        """Evaluate a registered model on new data.

        Phase 4 implements the evaluation path.
        """
        if mode not in ("holdout", "shadow", "live"):
            raise ValueError(
                f"evaluate(mode=...) must be 'holdout', 'shadow', or 'live'; "
                f"got {mode!r}."
            )
        raise NotImplementedError(f"MLEngine.evaluate — {_PHASE_4}")

    async def register(
        self,
        result: Any,
        *,
        name: Optional[str] = None,
        stage: str = "staging",
        format: str = "onnx",
        alias: Optional[str] = None,
    ) -> Any:
        """Register a trained model in the registry (ONNX-default, §6).

        Exports the underlying model via
        :mod:`kailash_ml.bridge.onnx_bridge` for formats ``"onnx"`` and
        ``"both"`` — all six framework branches (sklearn, xgboost,
        lightgbm, catboost, torch, lightning) are covered by the
        bridge's existing dispatch per §6.1 MUST 2. ``format="onnx"``
        (the default) MUST raise :class:`OnnxExportError` on export
        failure per §4.2 MUST 4; silent fallback to pickle is
        BLOCKED. ``format="both"`` tolerates partial ONNX failure
        (pickle-only RegisterResult) per §6.1 MUST 5.

        Tenant-aware: every version row persists ``tenant_id`` on
        ``_kml_engine_versions`` (§5.1 MUST 4); ``(tenant_id, name,
        version)`` is the primary key. Every ``register()`` call
        writes an audit row per §5.2 with ``operation="register"``,
        ``duration_ms``, ``outcome``.
        """
        # Validate argument shape up-front so bad calls fail loud (§2.3).
        if stage not in ("staging", "shadow", "production"):
            raise ValueError(
                f"register(stage=...) must be 'staging', 'shadow', or "
                f"'production'; got {stage!r}."
            )
        if format not in ("onnx", "pickle", "both"):
            raise ValueError(
                f"register(format=...) must be 'onnx', 'pickle', or 'both'; "
                f"got {format!r}."
            )

        # result MUST be a TrainingResult per the spec §2.2 signature.
        # We duck-type rather than strict isinstance so a lightweight
        # TrainingResult-shaped object (useful for tests) is accepted
        # provided it carries the fields register() actually reads.
        for required_attr in ("family", "artifact_uris", "tenant_id"):
            if not hasattr(result, required_attr):
                raise ValueError(
                    f"register(result=...) expected a TrainingResult-shaped "
                    f"object with '{required_attr}'; got "
                    f"{type(result).__name__}."
                )

        # tenant_id — Engine's tenant wins; a TrainingResult from a
        # different Engine instance that drifts from self._tenant_id is
        # caught here (multi-tenant safety: the Engine that registers
        # owns the audit row).
        tenant_id = self._tenant_id or result.tenant_id
        effective_tenant = (
            tenant_id if tenant_id is not None else (_sql.SENTINEL_GLOBAL_TENANT)
        )

        # Model-name synthesis: prefer explicit, then the training
        # result's family + short hash of model_uri (stable across
        # retries), then "model_<family>". Validated as an identifier
        # before being interpolated into SQL paths.
        model_name = name or self._synthesise_model_name(result)
        from kailash.db.dialect import _validate_identifier

        _validate_identifier(model_name)

        # Retrieve the actual model object. Trainables attached via
        # result._trainable are the canonical handle; some test paths
        # may pass the model directly via result.model. We look in
        # both slots and fall back to a helpful error if neither is
        # populated.
        model_obj = (
            getattr(result, "model", None)
            or getattr(result, "_model", None)
            or getattr(getattr(result, "_trainable", None), "model", None)
            or getattr(getattr(result, "trainable", None), "model", None)
        )
        if model_obj is None:
            raise ValueError(
                "register(result=...) could not locate the trained model. "
                "Attach the fitted model on result.model or pass a "
                "TrainingResult whose trainable exposes .model."
            )

        # Framework key for the ONNX bridge. Prefer the explicit
        # result.family when present; otherwise infer from the model
        # class module.
        framework = self._resolve_onnx_framework(result, model_obj)

        # Ensure the auxiliary engine tables exist. This is idempotent;
        # a real bootstrap path initialises them at construction, but
        # lazy creation here keeps the tests that construct an engine
        # without a prior setup() working.
        conn = await self._acquire_connection()
        await _sql.create_engine_tables(conn)

        # Monotonic version per (tenant_id, name). Read and insert
        # must share a transaction to close the TOCTOU window.
        t0 = time.monotonic()
        registered_at = time.time()
        audit_outcome = "failure"
        audit_model_uri: Optional[str] = None

        try:
            async with conn.transaction() as tx:
                version = await _sql.get_next_version(
                    tx, tenant_id=effective_tenant, name=model_name
                )
                model_uri = f"models://{model_name}/v{version}"
                audit_model_uri = model_uri

                # Artifact persistence. The ArtifactStore primitive is
                # shared with ModelRegistry so artifacts land in the
                # same filesystem layout, giving downstream readers a
                # uniform URI scheme.
                artifact_uris: dict[str, str] = {}
                store = self._resolve_artifact_store()

                # ONNX export — default path. Failure on format="onnx"
                # MUST raise OnnxExportError (§4.2 MUST 4); format="both"
                # tolerates partial failure (§6.1 MUST 5).
                if format in ("onnx", "both"):
                    onnx_uri = await self._export_and_save_onnx(
                        model=model_obj,
                        framework=framework,
                        name=model_name,
                        version=version,
                        artifact_store=store,
                        format=format,
                    )
                    if onnx_uri is not None:
                        artifact_uris["onnx"] = onnx_uri

                # Pickle export — always for format="pickle" and "both";
                # never for format="onnx" per §6.1 MUST 5.
                if format in ("pickle", "both"):
                    pickle_bytes = pickle.dumps(model_obj)
                    pickle_uri = await store.save(
                        model_name, version, pickle_bytes, "model.pkl"
                    )
                    artifact_uris["pickle"] = pickle_uri

                # Persist the version row (§5.1 MUST 4: tenant_id on the
                # model version table, indexed by the DDL helper).
                await _sql.insert_version_row(
                    tx,
                    tenant_id=effective_tenant,
                    name=model_name,
                    version=version,
                    model_uri=model_uri,
                    stage=stage,
                    alias=alias,
                    artifact_uris_json=json.dumps(artifact_uris),
                    registered_at=registered_at,
                )

            audit_outcome = "success"

        except OnnxExportError:
            # Let the typed ONNX error propagate; the audit row below
            # still fires with outcome="failure".
            raise
        except Exception as exc:  # noqa: BLE001 — see logger.exception
            logger.exception(
                "engine.register.error",
                extra={
                    "model_name": model_name,
                    "tenant_id": self._tenant_id,
                    "error": str(exc),
                },
            )
            raise
        finally:
            duration_ms = (time.monotonic() - t0) * 1000.0
            # Audit row always writes — §5.2 mandates the row regardless
            # of outcome so post-incident forensics can reconstruct
            # who tried to register what.
            try:
                await _sql.insert_audit_row(
                    conn,
                    audit_id=str(uuid.uuid4()),
                    tenant_id=effective_tenant,
                    actor_id=None,
                    model_uri=audit_model_uri,
                    operation="register",
                    occurred_at=registered_at,
                    duration_ms=duration_ms,
                    outcome=audit_outcome,
                )
            except Exception:  # noqa: BLE001 — audit write failure
                # Log at WARN; never mask the primary exception.
                logger.warning(
                    "engine.register.audit_write_failed",
                    extra={
                        "model_name": model_name,
                        "tenant_id": self._tenant_id,
                    },
                )

        from kailash_ml._results import RegisterResult

        result_envelope = RegisterResult(
            name=model_name,
            version=version,
            stage=stage,
            artifact_uris=artifact_uris,
            model_uri=model_uri,
            registered_at=registered_at,
            tenant_id=tenant_id,
            alias=alias,
        )
        logger.info(
            "engine.register.ok",
            extra={
                "model_name": model_name,
                "model_version": version,
                "stage": stage,
                "output_format": format,
                "tenant_id": self._tenant_id,
                "duration_ms": duration_ms,
            },
        )
        return result_envelope

    async def serve(
        self,
        model: Any,
        *,
        channels: list[str],
        version: Optional[int] = None,
        autoscale: bool = False,
        options: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        """Bind the model to inference channels and return URIs.

        Phase 5 implements the multi-channel serving (REST + MCP + gRPC
        from a single call per §2.1 MUST 10).
        """
        if not channels:
            raise ValueError(
                "serve(channels=...) must be a non-empty list; "
                "subset of ['rest', 'mcp', 'grpc']."
            )
        valid = {"rest", "mcp", "grpc"}
        bad = [c for c in channels if c not in valid]
        if bad:
            raise ValueError(
                f"serve(channels=...) contains unsupported channels {bad}; "
                f"valid: {sorted(valid)}."
            )
        raise NotImplementedError(f"MLEngine.serve — {_PHASE_5}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _columns_of(data: Any) -> Optional[tuple[str, ...]]:
        """Return column names of a polars / pandas / generic DataFrame.

        None when the value isn't a recognized frame-shape object.
        """
        cols = getattr(data, "columns", None)
        if cols is None:
            return None
        try:
            return tuple(str(c) for c in cols)
        except TypeError:
            return None

    # ------------------------------------------------------------------
    # setup() / register() internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_polars_dataframe(data: Any) -> Any:
        """Coerce supported input shapes to a polars DataFrame.

        Accepts ``pl.DataFrame``, ``pl.LazyFrame``, ``pandas.DataFrame``,
        and list-of-dict / dict-of-list records. Per §7.1 MUST 2 the
        Engine is polars-native; pandas is converted at the boundary.
        """
        import polars as pl

        if isinstance(data, pl.DataFrame):
            return data
        if isinstance(data, pl.LazyFrame):
            return data.collect()

        # pandas DataFrame detection without importing pandas
        # unconditionally (pandas is optional at the engine boundary).
        pd_mod = type(data).__module__
        if pd_mod.startswith("pandas."):
            try:
                return pl.from_pandas(data)
            except Exception as exc:
                raise ValueError(
                    f"setup(data=...) pandas-to-polars conversion failed: {exc}. "
                    f"Convert to polars.DataFrame before calling setup()."
                ) from exc

        if isinstance(data, (list, tuple)) and data and isinstance(data[0], dict):
            return pl.from_dicts(list(data))
        if isinstance(data, dict):
            return pl.DataFrame(data)

        raise ValueError(
            f"setup(data=...) expected polars.DataFrame, polars.LazyFrame, "
            f"pandas.DataFrame, or list[dict]; got {type(data).__name__}."
        )

    @staticmethod
    def _resolve_feature_store_name(feature_store: Any) -> str:
        """Resolve the feature-store name for the idempotency key.

        When a ``FeatureStore`` instance is passed, use its ``table_prefix``
        so two calls against the same store produce the same hash. When a
        string is passed, use it directly. Otherwise use the stable
        default ``"engine_default"``.
        """
        if feature_store is None:
            return "engine_default"
        if isinstance(feature_store, str):
            return feature_store
        prefix = getattr(feature_store, "_table_prefix", None)
        if isinstance(prefix, str) and prefix:
            return prefix.rstrip("_")
        name = getattr(feature_store, "name", None)
        if isinstance(name, str) and name:
            return name
        return f"fs_{type(feature_store).__name__.lower()}"

    @staticmethod
    def _compute_schema_hash(
        *,
        df: Any,
        target: str,
        ignore: list[str],
        feature_store_name: str,
    ) -> str:
        """Deterministic schema hash per §2.1 MUST 6.

        Inputs are canonicalised: columns are sorted, dtypes mapped to
        stable strings, row count quantised to the whole integer. The
        hash covers ``(sorted_columns + dtypes, row_count, target,
        sorted(ignore), feature_store_name)`` so permutations of the
        same DataFrame produce the same hash.
        """
        cols_sorted = sorted(str(c) for c in df.columns)
        dtypes_map = {str(c): str(df.schema[c]) for c in df.columns}
        dtypes_sorted = [(c, dtypes_map[c]) for c in cols_sorted]
        canonical = {
            "columns": dtypes_sorted,
            "row_count": int(df.height),
            "target": target,
            "ignore": sorted(list(ignore)),
            "feature_store": feature_store_name,
        }
        canonical_bytes = json.dumps(canonical, sort_keys=True).encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()[:16]

    @staticmethod
    def _infer_task_type(df: Any, target: str) -> str:
        """Infer classification/regression from the target column.

        - Boolean / categorical / Utf8 / low-cardinality integers (<=10
          distinct values) → classification.
        - Floating-point → regression.
        - Everything else → classification (integer labels commonly).
        """
        import polars as pl

        dtype = df.schema[target]
        if dtype in (pl.Boolean, pl.Utf8, pl.Categorical):
            return "classification"
        if dtype.is_float():
            return "regression"
        if dtype.is_integer():
            # Low-cardinality integer target → classification;
            # high-cardinality integer target → regression.
            distinct = int(df[target].n_unique())
            if distinct <= 10:
                return "classification"
            return "regression"
        # Unknown dtype — default to classification so at least the
        # sklearn path works without raising.
        return "classification"

    @staticmethod
    def _build_schema_info(
        df: Any,
        feature_cols: tuple[str, ...],
        target: str,
    ) -> Mapping[str, Any]:
        """Build the extended schema_info mapping (SetupResult).

        Contains one entry per feature column with canonical dtype +
        null count. The mapping is pickle-safe and JSON-safe so the
        result can be persisted by the tracker without further
        conversion.
        """
        import polars as pl

        def _polars_to_feature_dtype(dt: Any) -> str:
            # Map polars dtypes to the FeatureField dtype vocabulary
            # used by FeatureStore's sql.dtype_to_sql() mapping.
            if dt == pl.Boolean:
                return "bool"
            if dt == pl.Utf8:
                return "utf8"
            if dt == pl.Categorical:
                return "categorical"
            if dt.is_integer():
                return "int64"
            if dt.is_float():
                return "float64"
            if dt.is_temporal():
                return "datetime"
            return "utf8"

        columns_info: dict[str, Any] = {}
        for col in feature_cols:
            polars_dtype = df.schema[col]
            columns_info[col] = {
                "dtype": _polars_to_feature_dtype(polars_dtype),
                "polars_dtype": str(polars_dtype),
                "nullable": int(df[col].null_count()) > 0,
                "null_count": int(df[col].null_count()),
            }
        return {
            "columns": columns_info,
            "target": target,
            "target_dtype": str(df.schema[target]),
            "row_count": int(df.height),
        }

    @staticmethod
    def _infer_entity_id_column(df: Any) -> str:
        """Return a stable entity-id column name.

        Prefer a column literally named ``"id"`` when present; otherwise
        synthesise a pseudo-entity column name. The Phase 3 scope does
        not require true entity resolution — setup() only needs a
        consistent name for the FeatureStore schema row. Downstream
        fit() paths ignore the entity column entirely for in-memory
        training.
        """
        cols = [str(c) for c in df.columns]
        if "id" in cols:
            return "id"
        if "entity_id" in cols:
            return "entity_id"
        return "_engine_entity_id"

    # ------------------------------------------------------------------
    # register() internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _synthesise_model_name(result: Any) -> str:
        """Generate a stable model name from a TrainingResult.

        Prefers ``result.family`` when populated; falls back to a hash
        of ``model_uri`` so two register() calls against the same
        TrainingResult produce the same name. The returned name is
        sanitised to the identifier allowlist so it can be interpolated
        into SQL paths via ``_validate_identifier``.
        """
        family = getattr(result, "family", None)
        if isinstance(family, str) and family.isidentifier():
            base = family
        else:
            model_uri = getattr(result, "model_uri", None) or ""
            digest = hashlib.sha256(model_uri.encode("utf-8")).hexdigest()[:8]
            base = f"model_{digest}"
        # Collapse any non-allowlist chars defensively — identifier
        # allowlist is ^[a-zA-Z_][a-zA-Z0-9_]*$.
        sanitised = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in base)
        if not sanitised or not (sanitised[0].isalpha() or sanitised[0] == "_"):
            sanitised = f"_{sanitised or 'model'}"
        return sanitised

    @staticmethod
    def _resolve_onnx_framework(result: Any, model_obj: Any) -> str:
        """Resolve the ONNX bridge framework key from TrainingResult / model."""
        explicit = getattr(result, "family", None)
        if isinstance(explicit, str):
            # Normalise family aliases to the ONNX bridge keys.
            family_map = {
                "sklearn": "sklearn",
                "random_forest": "sklearn",
                "rf": "sklearn",
                "logreg": "sklearn",
                "logistic": "sklearn",
                "xgb": "xgboost",
                "xgboost": "xgboost",
                "lgbm": "lightgbm",
                "lightgbm": "lightgbm",
                "catboost": "catboost",
                "torch": "torch",
                "pytorch": "torch",
                "lightning": "lightning",
            }
            if explicit.lower() in family_map:
                return family_map[explicit.lower()]
        module = type(model_obj).__module__.lower()
        if module.startswith("sklearn"):
            return "sklearn"
        if module.startswith("xgboost"):
            return "xgboost"
        if module.startswith("lightgbm"):
            return "lightgbm"
        if module.startswith("catboost"):
            return "catboost"
        if module.startswith("lightning"):
            return "lightning"
        if module.startswith("torch"):
            return "torch"
        # Unknown framework — the bridge will return a "skipped" export
        # result; register() promotes that to OnnxExportError on
        # format="onnx".
        return "sklearn"

    async def _acquire_connection(self) -> Any:
        """Return an initialised ConnectionManager for the engine's store.

        When the engine was constructed with a ``ConnectionManager``
        instance, return it as-is (DI override); otherwise build the
        default SQLite connection on first use. The connection is
        cached on the engine so repeated ``register()`` calls reuse
        the pool.
        """
        from kailash.db.connection import ConnectionManager

        if isinstance(self._connection_manager, ConnectionManager):
            if getattr(self._connection_manager, "_pool", None) is None:
                await self._connection_manager.initialize()
            return self._connection_manager

        # Default path: construct + initialise a ConnectionManager
        # against the store URL. The store directory is created lazily
        # here (NOT in __init__) so zero-arg construction stays pure.
        if self._connection_manager is None:
            url = self.store_url
            # Ensure ~/.kailash_ml/ exists for the default SQLite case.
            if url.startswith("sqlite:///"):
                db_path = pathlib.Path(url[len("sqlite:///") :])
                db_path.parent.mkdir(parents=True, exist_ok=True)
            cm = ConnectionManager(url)
            await cm.initialize()
            self._connection_manager = cm
        return self._connection_manager

    def _resolve_artifact_store(self) -> Any:
        """Return the ArtifactStore (DI override or default local file store)."""
        if self._artifact_store is not None:
            return self._artifact_store
        from kailash_ml.engines.model_registry import LocalFileArtifactStore

        root = pathlib.Path(
            os.environ.get(
                "KAILASH_ML_ARTIFACT_ROOT",
                str(_DEFAULT_STORE_DIR / "artifacts"),
            )
        )
        self._artifact_store = LocalFileArtifactStore(root_dir=root)
        return self._artifact_store

    async def _export_and_save_onnx(
        self,
        *,
        model: Any,
        framework: str,
        name: str,
        version: int,
        artifact_store: Any,
        format: str,
    ) -> Optional[str]:
        """Export the model to ONNX and persist via the artifact store.

        Returns the artifact URI on success. On failure:
        - format="onnx" raises :class:`OnnxExportError` (§4.2 MUST 4).
        - format="both" returns ``None`` so pickle-only persistence
          proceeds (§6.1 MUST 5).
        """
        import tempfile

        from kailash_ml.bridge.onnx_bridge import OnnxBridge

        bridge = OnnxBridge()
        # torch / lightning exports require a sample input; tabular
        # frameworks (sklearn/xgboost/lightgbm/catboost) only need the
        # feature count. Phase 3 scope: we let the bridge's own
        # n_features inference (`model.n_features_in_`) handle the
        # tabular path; deep-learning sample_input plumbing is
        # tracked for a subsequent phase.
        with tempfile.TemporaryDirectory() as tmp:
            output_path = pathlib.Path(tmp) / "model.onnx"
            export_result = bridge.export(
                model,
                framework=framework,
                output_path=output_path,
            )
            if not export_result.success:
                cause = export_result.error_message or "unknown"
                if format == "onnx":
                    raise OnnxExportError(framework=framework, cause=cause)
                # format="both" tolerates ONNX failure per §6.1 MUST 5.
                logger.warning(
                    "engine.register.onnx_partial_failure",
                    extra={
                        "model_name": name,
                        "framework": framework,
                        "cause": cause,
                    },
                )
                return None
            onnx_bytes = output_path.read_bytes()
        uri = await artifact_store.save(name, version, onnx_bytes, "model.onnx")
        return uri
