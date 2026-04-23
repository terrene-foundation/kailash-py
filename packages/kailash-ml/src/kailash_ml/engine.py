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
from kailash_ml._results import PredictionResult, ServeResult
from kailash_ml.engines import _engine_sql as _sql
from kailash_ml.errors import ReferenceNotFoundError

logger = logging.getLogger(__name__)


def _build_auto_callbacks(
    *,
    user_callbacks: Optional[list],
    enable_checkpointing: bool,
) -> Optional[list]:
    """Prepend a NON-OVERRIDABLE `last.ckpt` ModelCheckpoint to user callbacks.

    Per ``specs/ml-engines-v2.md`` §3.2 MUST 7 / W20b invariant 3, every
    Lightning-routed fit MUST persist a ``last.ckpt`` artifact rooted at
    the ambient run's artifact directory. The user cannot remove this
    callback; their own callbacks are appended AFTER the engine's so any
    user-supplied ModelCheckpoint coexists instead of displacing the
    engine guarantee.

    The import is lazy and failure-soft: when ``lightning.pytorch`` is
    unavailable (classical-only install or ``enable_checkpointing=False``
    opt-out), this function returns the user's callback list unchanged.
    sklearn / xgboost / lightgbm adapters ignore the callbacks list so
    the injection is a no-op outside DL paths.
    """
    if not enable_checkpointing:
        return list(user_callbacks) if user_callbacks else None

    dirpath: Optional[str] = None
    try:
        from kailash_ml.tracking import get_current_run

        current_run = get_current_run()
        if current_run is not None:
            artifact_root = getattr(current_run, "artifact_uri", None) or getattr(
                current_run, "artifact_root", None
            )
            if artifact_root is not None:
                dirpath = str(artifact_root)
    except Exception:
        # Logger-touching calls inside finalizer contexts are unsafe; the
        # dirpath fallback is whatever Lightning chooses.
        logger.debug("engine.auto_checkpoint.run_context_unavailable", exc_info=True)

    try:
        from lightning.pytorch.callbacks import ModelCheckpoint
    except ImportError:
        # Classical-only install: Lightning is absent and the user won't
        # consume the callbacks list anyway.
        return list(user_callbacks) if user_callbacks else None

    auto_checkpoint = ModelCheckpoint(
        dirpath=dirpath,
        filename="last",
        save_last=True,
        save_top_k=0,
        every_n_epochs=1,
    )
    merged = [auto_checkpoint]
    if user_callbacks:
        merged.extend(user_callbacks)
    return merged


def _hash_model_name(model_name: str) -> str:
    """Return an 8-hex SHA-256 fingerprint of ``model_name`` per
    ``rules/observability.md`` §8 + ``rules/event-payload-classification.md``
    §2 — the canonical cross-SDK log-surface fingerprint for
    schema-revealing identifiers.

    The SHA-256 slice is deterministic across processes (unlike
    Python's builtin ``hash()`` which is PYTHONHASHSEED-randomized)
    and matches the 8-hex width used by ``format_record_id_for_event``
    so a single raw ``model_name`` produces the same fingerprint in
    every log aggregator and across SDK boundaries.

    Callers emit the fingerprint at INFO/WARN/ERROR; the raw
    ``model_name`` stays at DEBUG (or is omitted entirely) per §8.
    """
    return hashlib.sha256(model_name.encode("utf-8")).hexdigest()[:8]


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
    "UnsupportedTrainerError",
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


class UnsupportedTrainerError(_EngineError):
    """Raised when a Trainable bypasses the Lightning training loop.

    Per `ml-engines-v2.md` §3.2 MUST 2 (Decision 8 hard lock-in), raw
    training loops (custom `for epoch in range(...)`, hand-rolled
    optimizer stepping) are BLOCKED at ``MLEngine.fit()`` dispatch
    time. A Trainable MUST delegate to ``L.Trainer(...).fit(module, ...)``
    as its terminal step; custom logic lives inside the wrapped
    ``LightningModule``'s ``training_step`` / ``validation_step``.
    """

    def __init__(self, family: str, reason: str) -> None:
        super().__init__(
            f"Trainer for family {family!r} is not supported: {reason}. "
            f"Per ml-engines-v2.md §3.2 MUST 2, custom training loops are "
            f"BLOCKED; Trainable.fit() MUST terminate in "
            f"L.Trainer(...).fit(module, ...). Wrap the family as a "
            f"LightningModule adapter (see SklearnLightningAdapter, "
            f"XGBoostLightningAdapter, etc.)."
        )
        self.family = family
        self.reason = reason


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
# Default store resolution — MUST Rule 1b (ml-engines-v2.md §2.1): single
# authority chain routed through kailash_ml._env.resolve_store_url. Hand-
# rolled os.environ.get(...) at this site would silently diverge from the
# tracker / registry / feature-store resolution chain; use the shared helper.
# ---------------------------------------------------------------------------


from kailash_ml._env import resolve_store_url as _resolve_store_url


def _default_store_url() -> str:
    """Return the default store URL via the shared authority chain.

    Delegates entirely to :func:`kailash_ml._env.resolve_store_url` so
    every engine / tracker / registry / feature-store resolves the same
    URL from the same precedence (explicit kwarg > ``KAILASH_ML_STORE_URL``
    > legacy ``KAILASH_ML_TRACKER_DB`` > ``sqlite:///~/.kailash_ml/ml.db``).
    """
    return _resolve_store_url(None)


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
# Metric direction (ranking semantics per ml-engines.md §2.2 compare contract)
# ---------------------------------------------------------------------------
#
# Higher-is-better metrics: larger values rank first.
# Lower-is-better metrics: smaller values rank first.
# The sets are closed under the metrics registry at kailash_ml.metrics.
# Metrics absent from both sets default to higher-is-better so a custom
# registered metric does not crash the ranker, but a WARN log surfaces
# the ambiguity per rules/observability.md Rule 3.

_HIGHER_IS_BETTER_METRICS: frozenset[str] = frozenset(
    {
        "accuracy",
        "f1",
        "f1_macro",
        "f1_micro",
        "f1_weighted",
        "precision",
        "recall",
        "auc",
        "roc_auc",
        "average_precision",
        "r2",
        "silhouette",
    }
)
_LOWER_IS_BETTER_METRICS: frozenset[str] = frozenset(
    {
        "rmse",
        "mse",
        "mae",
        "log_loss",
        "brier_score_loss",
    }
)


# ---------------------------------------------------------------------------
# Task-type → default family set (ml-engines.md §2.2 compare contract)
# ---------------------------------------------------------------------------
#
# compare() with families=None derives this set from the setup result's
# task_type. The set is ORDERED so that a tie on the leaderboard (e.g.
# two families with identical accuracy) is resolved by default-family
# order rather than by dict-insertion accident.

_DEFAULT_FAMILIES_BY_TASK: Mapping[str, tuple[str, ...]] = {
    "classification": ("sklearn", "xgboost", "lightgbm"),
    "regression": ("sklearn", "xgboost", "lightgbm"),
    "clustering": ("sklearn",),
    "ranking": ("sklearn", "xgboost", "lightgbm"),
}


def _default_families_for_task(task_type: str) -> tuple[str, ...]:
    """Return the default compare()-family list for a task type."""
    return _DEFAULT_FAMILIES_BY_TASK.get(task_type, ("sklearn",))


def _family_available(family: str) -> bool:
    """Return True when the family's optional backend is importable.

    xgboost and lightgbm are optional extras — skipping gracefully when
    they are not installed preserves the zero-config story for users who
    only have sklearn.
    """
    canonical = _FAMILY_ALIASES.get(family.lower(), family.lower())
    if canonical == "xgboost":
        try:
            import xgboost  # noqa: F401
        except ImportError:
            return False
    elif canonical == "lightgbm":
        try:
            import lightgbm  # noqa: F401
        except ImportError:
            return False
    # sklearn is a hard dep; torch/lightning require explicit trainables
    return True


def _parse_model_uri(uri: str) -> tuple[str, Optional[int]]:
    """Split a ``models://<name>/v<version>`` URI into (name, version).

    Accepts the canonical form produced by ``RegisterResult.model_uri``:
    ``models://User/v3``. Also accepts the bare-name form
    ``models://User`` (version=None, meaning "latest"). Other shapes
    raise ValueError.
    """
    if not isinstance(uri, str):
        raise TypeError(f"model URI must be a string; got {type(uri).__name__}")
    prefix = "models://"
    if not uri.startswith(prefix):
        raise ValueError(f"model URI must start with '{prefix}'; got {uri!r}.")
    tail = uri[len(prefix) :]
    if "/" in tail:
        name, _, v_part = tail.partition("/")
        if not name:
            raise ValueError(f"model URI missing name component: {uri!r}")
        if not v_part.startswith("v"):
            raise ValueError(
                f"model URI version component must start with 'v'; "
                f"got {v_part!r} in {uri!r}."
            )
        try:
            version = int(v_part[1:])
        except ValueError as exc:
            raise ValueError(
                f"model URI version component not an integer: {v_part!r} "
                f"in {uri!r}."
            ) from exc
        if version < 1:
            raise ValueError(
                f"model URI version must be >= 1; got {version} in {uri!r}."
            )
        return name, version
    return tail, None


def _metric_sort_key(metric_name: str, value: float) -> tuple[float, float]:
    """Return a sort key such that `sorted(..., key=...)` puts best-first.

    For higher-is-better metrics we negate the value so ascending sort
    puts the largest value first. For lower-is-better metrics we return
    the value as-is. Returns a 2-tuple: (primary, tiebreak) where
    tiebreak is `-elapsed_seconds` so — for equal metric — the faster
    model wins; callers pre-format this with elapsed_seconds.
    """
    if metric_name in _LOWER_IS_BETTER_METRICS:
        return (float(value), 0.0)
    # Default (includes unknown metrics): higher-is-better.
    return (-float(value), 0.0)


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
        # `_tracker` is the user-facing Optional[ExperimentRun] handle
        # per §2.2 (HIGH-8: NOT an ExperimentTracker instance). The
        # engine-owned ExperimentTracker lives in `_experiment_tracker`
        # and is constructed lazily by
        # :meth:`_ensure_default_primitives_async` per §2.1 MUST 2.
        self._tracker = tracker
        self._trainer = trainer
        self._artifact_store = artifact_store
        self._connection_manager = connection_manager
        # Engine-owned ExperimentTracker (§2.1 MUST 2 six-primitive
        # composition). None until `_ensure_default_primitives_async`
        # runs; DI cannot replace this slot directly because its
        # construction is async-only (ExperimentTracker.create).
        self._experiment_tracker: Any = None

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

    @property
    def engine_info(self) -> Mapping[str, bool]:
        """Observability snapshot of which DI slots are currently wired.

        Returns a frozen mapping ``{slot_name: bool}`` reporting whether
        each §2.1 MUST 2 primitive is populated. This is the
        observability handle ``/redteam`` uses to verify the
        six-primitive composition contract end-to-end: every slot is
        ``False`` immediately after construction, ``True`` after
        :meth:`_ensure_default_primitives_async` runs. DI overrides are
        reflected as ``True`` from ``__init__`` since the engine
        accepted the injection without constructing a default.

        The returned mapping is deliberately read-only — callers MUST
        NOT mutate it.
        """
        return {
            "connection_manager": self._connection_manager is not None,
            "artifact_store": self._artifact_store is not None,
            "registry": self._registry is not None,
            "feature_store": self._feature_store is not None,
            "trainer": self._trainer is not None,
            "experiment_tracker": self._experiment_tracker is not None,
        }

    # ------------------------------------------------------------------
    # §2.1 MUST 2 — six-primitive default composition
    # ------------------------------------------------------------------

    async def _ensure_default_primitives_async(self) -> None:
        """Construct any DI slot still ``None`` with its canonical default.

        Unifies the scattered lazy-construction paths
        (``_get_registry``, ``_ensure_registry_for_read``,
        ``_acquire_connection``, ``_resolve_artifact_store``) into a
        single entry point. Every slot-fill is idempotent — a second
        call is a no-op. DI-injected primitives are honored as-is per
        §2.1 MUST 3; the default path NEVER wraps or replaces an
        injected instance.

        Construction order (respects dependency chain):

        1. ``ConnectionManager`` — built from :attr:`store_url`; the
           SQLite directory is created here so zero-arg construction
           stays filesystem-pure until first async entry.
        2. ``ArtifactStore`` — ``LocalFileArtifactStore`` rooted at
           ``KAILASH_ML_ARTIFACT_ROOT`` (defaults to
           ``~/.kailash_ml/artifacts``).
        3. ``ModelRegistry`` — wraps the ConnectionManager + ArtifactStore
           via :class:`kailash_ml.engines.model_registry.ModelRegistry`.
        4. ``FeatureStore`` — wraps the ConnectionManager; registered
           feature tables carry the default ``kml_feat_`` prefix.
        5. ``TrainingPipeline`` — binds (feature_store, registry).
        6. ``ExperimentTracker`` — constructed via
           :meth:`ExperimentTracker.create` with the engine's tenant_id
           as the default tenant so every auto-logged run carries the
           engine's tenancy envelope.

        Raises:
            Any error from the underlying primitive constructors is
            surfaced as-is (they are typed per their own specs). The
            engine does NOT wrap them — caller debugging follows the
            native exception back to the failing primitive.
        """
        # 1. ConnectionManager
        if self._connection_manager is None:
            from kailash.db.connection import ConnectionManager

            url = self.store_url
            if url.startswith("sqlite:///"):
                db_path = pathlib.Path(url[len("sqlite:///") :])
                db_path.parent.mkdir(parents=True, exist_ok=True)
            cm = ConnectionManager(url)
            await cm.initialize()
            self._connection_manager = cm

        # 2. ArtifactStore
        if self._artifact_store is None:
            from kailash_ml.engines.model_registry import LocalFileArtifactStore

            root = pathlib.Path(
                os.environ.get(
                    "KAILASH_ML_ARTIFACT_ROOT",
                    str(pathlib.Path.home() / ".kailash_ml" / "artifacts"),
                )
            )
            root.mkdir(parents=True, exist_ok=True)
            self._artifact_store = LocalFileArtifactStore(root_dir=root)

        # 3. ModelRegistry
        if self._registry is None:
            from kailash_ml.engines.model_registry import ModelRegistry

            self._registry = ModelRegistry(
                self._connection_manager,
                artifact_store=self._artifact_store,
            )

        # 4. FeatureStore
        if self._feature_store is None:
            from kailash_ml.engines.feature_store import FeatureStore

            fs = FeatureStore(self._connection_manager)
            await fs.initialize()
            self._feature_store = fs

        # 5. TrainingPipeline
        if self._trainer is None:
            from kailash_ml.engines.training_pipeline import TrainingPipeline

            self._trainer = TrainingPipeline(
                self._feature_store,
                self._registry,
            )

        # 6. ExperimentTracker — async-only factory, so it can only
        # land here (construction outside __init__).
        if self._experiment_tracker is None:
            from kailash_ml.tracking.tracker import ExperimentTracker

            self._experiment_tracker = await ExperimentTracker.create(
                self.store_url,
                default_tenant_id=self._tenant_id,
            )

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
        data: Any = None,
        target: Optional[str] = None,
    ) -> Any:
        """Train & rank candidate families (AutoML sweep).

        Per ``specs/ml-engines.md`` §2.1 MUST 7 every family in the sweep
        is routed through the Lightning-wrapped ``Trainable`` adapter via
        :meth:`fit`. Compare never bypasses ``fit`` — the Lightning
        Trainer is the single enforcement point for accelerator /
        precision resolution, so every ``TrainingResult`` in the
        leaderboard carries a concrete ``device`` / ``accelerator`` /
        ``precision`` triple.

        Args:
            families: Ordered list of family names or Trainable instances
                to sweep. When ``None``, derives the default set from
                ``self._setup_result.task_type`` — classification /
                regression → ``(sklearn, xgboost, lightgbm)`` (gracefully
                skipping uninstalled optional extras), clustering →
                ``(sklearn,)``. An unknown task type falls back to
                ``(sklearn,)``.
            n_trials: Number of HP-search trials per family. ``0`` means
                single default-HP fit per family.
            hp_search: Search strategy forwarded to ``fit(hp_search=...)``.
                One of ``"none" | "grid" | "random" | "bayesian" |
                "halving"``.
            metric: Metric name to rank by. When ``None``, uses
                ``self._setup_result.primary_metric``.
            early_stopping: Patience spec forwarded to ``fit()`` when the
                family supports it.
            timeout_seconds: Wall-clock budget for the entire sweep. When
                exceeded, returns a :class:`ComparisonResult` with only
                the families that completed; a WARN log line records the
                timed-out families for post-hoc triage.
            data: Escape hatch — when supplied, bypasses
                ``self._setup_result`` and uses the frame directly.
                ``target`` MUST also be supplied. This is the default
                path for callers who do not want to run ``setup()``
                first; also used by sibling shards that have not yet
                wired the ``setup()`` frame-storage contract.
            target: Target column name for direct-data dispatch.

        Returns:
            A :class:`ComparisonResult` with the leaderboard ordered
            best-first by ``metric``.

        Raises:
            EngineNotSetUpError: When neither ``setup()`` has been called
                nor ``(data, target)`` supplied.
            ValueError: When ``data`` is supplied without ``target``.
        """
        # Lazy import to avoid circular dependencies and to keep package
        # import time minimal — ComparisonResult is only relevant inside
        # compare()'s return path.
        from kailash_ml._results import ComparisonResult

        setup_result = self._setup_result
        if setup_result is None and data is None:
            raise EngineNotSetUpError(
                "MLEngine.compare() requires either setup() to be called "
                "first OR (data=..., target='...') supplied directly. "
                "Invoke `await engine.setup(data, target='...')` before "
                "compare(), or pass `data=df, target='...'` to compare() "
                "for standalone use."
            )
        if data is not None and target is None:
            raise ValueError(
                "MLEngine.compare(data=..., target=...) requires a target "
                "column name when data is supplied directly."
            )

        # Resolve the ranking metric. When the caller supplies `metric=`
        # explicitly, it takes precedence over the setup result's
        # primary_metric. Without setup and without an explicit metric,
        # we cannot sensibly rank — raise.
        ranking_metric = metric
        if ranking_metric is None:
            if setup_result is not None and getattr(
                setup_result, "primary_metric", None
            ):
                ranking_metric = setup_result.primary_metric
            else:
                raise ValueError(
                    "MLEngine.compare() requires `metric=` when setup() has "
                    "not been called — cannot infer the ranking metric "
                    "without a SetupResult.primary_metric."
                )

        # Resolve the data + target source. Explicit escape-hatch wins;
        # otherwise we read from the setup result. Setup-result data
        # storage is owned by the sibling shard implementing setup();
        # until that lands, the escape-hatch form is the recommended
        # contract for standalone compare() calls.
        compare_data = data
        compare_target = target
        if compare_data is None:
            compare_data = getattr(setup_result, "_data", None)
            if compare_data is None:
                raise EngineNotSetUpError(
                    "MLEngine.compare() requires setup() to have stored the "
                    "training frame, but SetupResult._data is absent. Pass "
                    "`data=df, target='...'` to compare() directly as an "
                    "escape hatch."
                )
        if compare_target is None:
            compare_target = getattr(setup_result, "target", None)
            if compare_target is None:
                raise ValueError(
                    "MLEngine.compare() could not resolve the target column "
                    "from the setup result — pass `target='...'` explicitly."
                )

        # Resolve the family list. When None, derive from task_type.
        if families is None:
            task_type = getattr(setup_result, "task_type", "classification")
            resolved_families: list[Any] = list(
                _default_families_for_task(str(task_type))
            )
        else:
            resolved_families = list(families)

        if not resolved_families:
            raise ValueError(
                "MLEngine.compare(families=...) must produce a non-empty "
                "family list; got an empty sequence."
            )

        # Filter out optional-extra families whose backend isn't installed
        # so the zero-config happy path does not hard-require every
        # optional dep. String-named families are probed; user-supplied
        # Trainable instances are kept as-is (their deps are their
        # problem).
        sweep_families: list[Any] = []
        skipped: list[str] = []
        for fam in resolved_families:
            if isinstance(fam, str):
                if _family_available(fam):
                    sweep_families.append(fam)
                else:
                    skipped.append(fam)
            else:
                sweep_families.append(fam)

        if skipped:
            logger.info(
                "compare.family.skipped_optional_extras",
                extra={
                    "skipped": skipped,
                    "reason": "optional-extra-not-installed",
                    "tenant_id": self._tenant_id or "global",
                },
            )

        if not sweep_families:
            raise ValueError(
                f"MLEngine.compare(): none of the requested families "
                f"{resolved_families!r} are available in this environment "
                f"(xgboost / lightgbm are optional extras — install via "
                f"`pip install kailash-ml[xgb]` or `[lightgbm]`)."
            )

        # Run the sweep. Each family goes through self.fit() so the
        # Lightning-spine invariant (§2.1 MUST 7) holds by construction.
        # We honour timeout_seconds by checking elapsed after each family
        # and stopping early with a WARN.
        started = time.perf_counter()
        leaderboard: list[Any] = []
        completed_families: list[str] = []
        timed_out_families: list[str] = []

        for fam in sweep_families:
            elapsed_total = time.perf_counter() - started
            if timeout_seconds is not None and elapsed_total >= timeout_seconds:
                # Everything from this family onward is timed out.
                remaining = sweep_families[sweep_families.index(fam) :]
                for f in remaining:
                    timed_out_families.append(
                        f if isinstance(f, str) else type(f).__name__
                    )
                break

            try:
                if isinstance(fam, str):
                    result = await self.fit(
                        data=compare_data,
                        target=compare_target,
                        family=fam,
                        hp_search=hp_search,
                        n_trials=n_trials,
                        metric=ranking_metric,
                    )
                else:
                    # User-supplied Trainable instance — pass via trainable=
                    result = await self.fit(
                        data=compare_data,
                        target=compare_target,
                        trainable=fam,
                        hp_search=hp_search,
                        n_trials=n_trials,
                        metric=ranking_metric,
                    )
            except (
                AcceleratorUnavailableError,
                TargetInFeaturesError,
                TargetNotFoundError,
                ConflictingArgumentsError,
            ):
                # Typed Engine errors surface immediately — these are
                # caller bugs, not family-level failures.
                raise
            except Exception as exc:  # noqa: BLE001
                # Family-specific failure (e.g. a backend the adapter
                # rejected, or a missing optional dep that slipped past
                # the availability probe). Log at WARN and continue —
                # the sweep is best-effort by design.
                logger.warning(
                    "compare.family.failed",
                    extra={
                        "family": fam if isinstance(fam, str) else type(fam).__name__,
                        "error": str(exc),
                        "tenant_id": self._tenant_id or "global",
                    },
                )
                continue

            leaderboard.append(result)
            completed_families.append(
                fam if isinstance(fam, str) else type(fam).__name__
            )

        if timed_out_families:
            logger.warning(
                "compare.timeout.partial_result",
                extra={
                    "timeout_seconds": timeout_seconds,
                    "completed_families": completed_families,
                    "timed_out_families": timed_out_families,
                    "tenant_id": self._tenant_id or "global",
                },
            )

        if not leaderboard:
            raise ValueError(
                f"MLEngine.compare(): no family completed successfully. "
                f"Requested: {resolved_families!r}. Skipped (optional "
                f"extras): {skipped!r}. Check the logs for per-family "
                f"errors."
            )

        # Rank leaderboard by the ranking_metric, best-first.
        def _rank_key(r: Any) -> tuple[float, float]:
            val = r.metrics.get(ranking_metric)
            if val is None:
                # Missing metric on a result → sink to the bottom without
                # crashing. A WARN surfaces the skip for post-hoc audit.
                logger.warning(
                    "compare.rank.metric_missing",
                    extra={
                        "family": r.family,
                        "ranking_metric": ranking_metric,
                        "available_metrics": sorted(r.metrics.keys()),
                        "tenant_id": self._tenant_id or "global",
                    },
                )
                # Use +inf for lower-is-better and -inf for
                # higher-is-better so missing-metric rows sink.
                if ranking_metric in _LOWER_IS_BETTER_METRICS:
                    return (float("inf"), 0.0)
                return (float("inf"), 0.0)
            return _metric_sort_key(ranking_metric, val)

        leaderboard.sort(key=_rank_key)

        elapsed = time.perf_counter() - started
        total_trials = sum(1 for _ in leaderboard) * max(1, n_trials)

        return ComparisonResult(
            leaderboard=tuple(leaderboard),
            metric=ranking_metric,
            best=leaderboard[0],
            total_trials=total_trials,
            elapsed_seconds=float(elapsed),
            tenant_id=self._tenant_id,
        )

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
        # --- Lightning distribution passthrough (ml-engines-v2.md §3.2 MUST 6) ---
        strategy: Any = None,
        devices: Any = "auto",
        num_nodes: int = 1,
        # --- Lightning checkpoint + LR discovery (§3.2 MUST 7 / MUST 8) ---
        enable_checkpointing: bool = True,
        auto_find_lr: bool = False,
        callbacks: Optional[list] = None,
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

        Lightning passthrough kwargs (``strategy``, ``devices``,
        ``num_nodes``, ``enable_checkpointing``, ``auto_find_lr``,
        ``callbacks``) flow into the ``TrainingContext`` the trainable
        receives; the adapter is responsible for lifting them into the
        concrete ``L.Trainer(strategy=…, devices=…, num_nodes=…,
        enable_checkpointing=…, callbacks=…)`` invocation per §2.2 +
        §3.2 MUST 6-8.
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

        # Raw-loop detection (§3.2 MUST 2; Decision 8 hard lock-in).
        # Trainables that mark themselves as raw-loop (custom for-epoch
        # trainer bypassing L.Trainer) are BLOCKED at dispatch time.
        # The lightweight marker `_raw_loop=True` is the structural hook
        # family adapters opt into when their fit() doesn't terminate in
        # `L.Trainer(...).fit(module, ...)`. Lightning-module verification
        # (via `to_lightning_module()`) lives in _train_lightning.
        if getattr(trainable, "_raw_loop", False) is True:
            fam_name = (
                family
                if family is not None
                else getattr(trainable, "family_name", type(trainable).__name__)
            )
            raise UnsupportedTrainerError(
                family=fam_name,
                reason=(
                    "trainable is marked _raw_loop=True (custom training "
                    "loop bypassing L.Trainer)"
                ),
            )

        # Schema-drift detection (§2.3). When setup() produced a schema
        # hash AND data was supplied directly here, verify the fit-time
        # schema matches. Skip the check when either side is absent —
        # drift is defined as "two known schemas differ", not "one is
        # missing". The hash inputs MUST match setup() exactly (target,
        # ignored_columns, feature_store_name) or the comparison is
        # meaningless; see §2.1 MUST 6 canonicalisation.
        if self._setup_result is not None:
            setup_hash = getattr(self._setup_result, "schema_hash", None)
            setup_target = getattr(self._setup_result, "target", None)
            setup_ignore = list(
                getattr(self._setup_result, "ignored_columns", ()) or ()
            )
            setup_fs_name = (
                getattr(self._setup_result, "feature_store_name", None)
                or "engine_default"
            )
            if setup_hash is not None and setup_target is not None:
                # Normalise incoming data to the polars DataFrame shape
                # setup() saw; _compute_schema_hash reads columns/schema
                # attrs on the frame.
                drift_df = self._to_polars_dataframe(data)
                fit_hash = MLEngine._compute_schema_hash(
                    df=drift_df,
                    target=setup_target,
                    ignore=setup_ignore,
                    feature_store_name=setup_fs_name,
                )
                if fit_hash != setup_hash:
                    raise SchemaDriftError(before=setup_hash, after=fit_hash)

        # Build TrainingContext from Engine's resolved backend so the
        # trainable does NOT re-resolve (§3.2 MUST 4). Lightning
        # passthrough kwargs flow through context so the trainable's
        # Lightning adapter can lift them onto L.Trainer(...) per
        # §3.2 MUST 6-8.
        from kailash_ml.trainable import TrainingContext

        info = self._backend_info or detect_backend()
        # When caller supplies `devices` explicitly (non-"auto"), honor
        # it; otherwise fall back to the backend-resolved device count
        # so existing CPU-only adapters keep working unchanged.
        resolved_devices = info.devices if devices == "auto" else devices

        # W20b §3.2 MUST 7: auto-append a `last.ckpt` ModelCheckpoint
        # rooted at the ambient run artifact path. NON-OVERRIDABLE — the
        # auto-checkpoint is PREPENDED to any user-supplied callbacks so
        # a user's custom ModelCheckpoint does not displace the engine's
        # `last.ckpt` guarantee; it merely sits beside it. The injection
        # is lazy and lightning-gated so sklearn/xgboost adapters that
        # don't consume callbacks stay unchanged.
        merged_callbacks = _build_auto_callbacks(
            user_callbacks=callbacks,
            enable_checkpointing=enable_checkpointing,
        )
        ctx = TrainingContext(
            accelerator=info.accelerator,
            precision=info.precision,
            devices=resolved_devices,
            device_string=info.device_string,
            backend=info.backend,
            tenant_id=self._tenant_id,
            strategy=strategy,
            num_nodes=num_nodes,
            enable_checkpointing=enable_checkpointing,
            auto_find_lr=auto_find_lr,
            callbacks=tuple(merged_callbacks) if merged_callbacks is not None else None,
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
    ) -> PredictionResult:
        """Serve a prediction (single record or batch, direct or via endpoint).

        Per ``specs/ml-engines.md`` §2.2: ``channel="direct"`` runs in-process
        inference against the registered model's ONNX artifact; ``channel="rest"``
        and ``channel="mcp"`` route through endpoints established by a prior
        :py:meth:`serve` call on this engine instance.

        Tenant isolation (§5.1 MUST 3): if the registered ModelVersion carries
        a ``tenant_id`` that does not match the engine's ``tenant_id``, raises
        :class:`TenantRequiredError` before loading any artifact.
        """
        if channel not in ("direct", "rest", "mcp"):
            raise ValueError(
                f"predict(channel=...) must be 'direct', 'rest', or 'mcp'; "
                f"got {channel!r}."
            )

        # Resolve the model reference into (name, version, model_uri, tenant_id).
        name, resolved_version, model_uri, model_tenant = await self._resolve_model(
            model, version
        )

        # §5.1 MUST 3: tenant isolation check.
        self._check_tenant_match(model_tenant, name)

        logger.info(
            "engine.predict.start",
            extra={
                "model_uri": model_uri,
                "channel": channel,
                "engine_tenant_id": self._tenant_id,
            },
        )

        start = time.monotonic()
        try:
            if channel == "direct":
                predictions = await self._predict_direct(
                    name, resolved_version, features
                )
            elif channel == "rest":
                predictions = await self._predict_rest(
                    name, resolved_version, features, model_uri
                )
            else:  # "mcp"
                predictions = await self._predict_mcp(
                    name, resolved_version, features, model_uri
                )
        except Exception as exc:  # propagate after logging
            logger.exception(
                "engine.predict.error",
                extra={
                    "model_uri": model_uri,
                    "channel": channel,
                    "error": str(exc),
                },
            )
            raise

        elapsed_ms = (time.monotonic() - start) * 1000.0

        result = PredictionResult(
            predictions=predictions,
            model_uri=model_uri,
            model_version=resolved_version,
            channel=channel,
            elapsed_ms=elapsed_ms,
            tenant_id=self._tenant_id,
            # §4.2 MUST 6 deferred — Phase 4.1+ will attach DeviceReport.
            device=None,
        )
        logger.info(
            "engine.predict.ok",
            extra={
                "model_uri": model_uri,
                "channel": channel,
                "elapsed_ms": elapsed_ms,
                "row_count": _row_count_of(predictions),
            },
        )
        return result

    async def finalize(
        self,
        candidate: Any,
        *,
        full_fit: bool = True,
        data: Any = None,
        target: Optional[str] = None,
    ) -> Any:
        """Retrain top candidate on full training + holdout data.

        Per ``specs/ml-engines.md`` §2.2 finalize() takes a candidate
        ``TrainingResult`` (the winner of a prior ``compare()`` sweep,
        or a model URI string) and re-trains it on the combined
        train+holdout set so the deployed model has seen every
        available row — the standard pattern for pushing a validated
        candidate to production.

        Args:
            candidate: Either a :class:`TrainingResult` directly, or a
                model-URI string ``"models://<name>/v<version>"`` that
                points at a previously-registered model. For the URI
                path, finalize() loads the ModelVersion from the
                registry and reconstructs the family from the signature
                metadata.
            full_fit: When True (default), refit the candidate's family
                on ``train + holdout`` combined. When False, mark the
                candidate as finalized without retraining — the
                returned FinalizeResult's ``training_result`` is
                identical to the candidate.
            data: Escape-hatch training frame for the refit path. When
                supplied, bypasses ``self._setup_result``. Required
                when ``setup()`` has not been called.
            target: Target column name for direct-data dispatch.

        Returns:
            A :class:`FinalizeResult` wrapping the refitted (or
            re-wrapped) :class:`TrainingResult` plus the original
            candidate so callers can compare pre- and post-finalize
            metrics.

        Raises:
            ValueError: When candidate is None, or data supplied without
                target, or full_fit=True but neither setup nor
                (data, target) is available.
            ModelNotFoundError: When candidate is a URI that does not
                resolve to a registered model.
        """
        # Lazy import to avoid a cross-module import cycle at package
        # load time — FinalizeResult only matters inside finalize().
        from kailash_ml._result import TrainingResult
        from kailash_ml._results import FinalizeResult

        if candidate is None:
            raise ValueError("finalize(candidate) must not be None.")

        # Resolve candidate → concrete TrainingResult. String URIs go
        # through the registry; TrainingResult instances pass through
        # as-is. Unknown shapes surface as TypeError (not a silent
        # fallback) per rules/zero-tolerance.md Rule 3.
        original_candidate: Any = candidate
        if isinstance(candidate, TrainingResult):
            candidate_result: TrainingResult = candidate
        elif isinstance(candidate, str):
            # URI path: "models://<name>/v<version>" — load via registry.
            name, version = _parse_model_uri(candidate)
            registry = await self._ensure_registry_for_read()
            try:
                model_version = await registry.get_model(name, version)
            except Exception as exc:  # noqa: BLE001
                raise ModelNotFoundError(name=name, version=version) from exc
            # Reconstruct a minimal TrainingResult from the registry
            # row so the caller can still reach `candidate_result.family`
            # and `candidate_result.hyperparameters`. This is a
            # read-through wrapper; the model bytes live in the
            # artifact store, not in this struct.
            metrics_dict = {m.name: float(m.value) for m in model_version.metrics}
            candidate_result = TrainingResult(
                model_uri=candidate,
                metrics=metrics_dict,
                device_used="cpu",  # historical — unknown post-load
                accelerator="cpu",
                precision="32-true",
                elapsed_seconds=0.0,
                tracker_run_id=None,
                tenant_id=self._tenant_id,
                artifact_uris={"native": model_version.artifact_path or ""},
                lightning_trainer_config={},
                family=None,
            )
        else:
            raise TypeError(
                f"finalize(candidate=...) must be a TrainingResult or a "
                f"string URI ('models://<name>/v<version>'); got "
                f"{type(candidate).__name__}."
            )

        if not full_fit:
            # No retraining — just re-wrap the candidate. tenant_id
            # echoes the engine's current tenant context per §4.2 MUST 3.
            wrapped = candidate_result
            if wrapped.tenant_id != self._tenant_id:
                from dataclasses import replace as _replace

                wrapped = _replace(wrapped, tenant_id=self._tenant_id)
            return FinalizeResult(
                training_result=wrapped,
                original_candidate=original_candidate,
                full_fit=False,
                tenant_id=self._tenant_id,
            )

        # full_fit=True: re-train on the combined train+holdout set
        # through self.fit() so the Lightning-spine invariant holds.
        # The family comes from the candidate; the frame comes from
        # setup_result or the escape-hatch kwargs.
        refit_family = candidate_result.family
        if refit_family is None:
            raise ValueError(
                "finalize(candidate, full_fit=True) requires "
                "candidate.family to be populated. When candidate is a "
                "URI whose registry row does not carry family metadata, "
                "pass full_fit=False to wrap without retraining."
            )

        refit_data = data
        refit_target = target
        setup_result = self._setup_result
        if refit_data is None:
            if setup_result is None:
                raise EngineNotSetUpError(
                    "MLEngine.finalize(full_fit=True) requires either "
                    "setup() to be called first OR (data=..., "
                    "target='...') supplied directly. Pass `data=df, "
                    "target='...'` to finalize() as an escape hatch."
                )
            refit_data = getattr(setup_result, "_data", None)
            if refit_data is None:
                raise EngineNotSetUpError(
                    "MLEngine.finalize(full_fit=True) requires setup() to "
                    "have stored the training frame, but SetupResult._data "
                    "is absent. Pass `data=df, target='...'` to finalize() "
                    "directly as an escape hatch."
                )
        if refit_target is None:
            if setup_result is not None and getattr(setup_result, "target", None):
                refit_target = setup_result.target
            else:
                raise ValueError(
                    "MLEngine.finalize(full_fit=True) could not resolve "
                    "the target column from the setup result — pass "
                    "`target='...'` explicitly."
                )
        if data is not None and target is None:
            raise ValueError(
                "MLEngine.finalize(data=..., target=...) requires a target "
                "column name when data is supplied directly."
            )

        refit_result = await self.fit(
            data=refit_data,
            target=refit_target,
            family=refit_family,
            hyperparameters=candidate_result.hyperparameters,
        )

        return FinalizeResult(
            training_result=refit_result,
            original_candidate=original_candidate,
            full_fit=True,
            tenant_id=self._tenant_id,
        )

    async def evaluate(
        self,
        model: Any,
        data: Any,
        *,
        metrics: Optional[list[str]] = None,
        mode: str = "holdout",
    ) -> Any:
        """Evaluate a registered model on new data.

        Per ``specs/ml-engines.md`` §2.2 evaluate() scores a registered
        model against a held-out or live dataset and returns typed
        metrics. Three modes gate how the evaluation is recorded
        operationally — the scoring itself is identical across modes:

        - ``"holdout"``: standard offline evaluation. Produces metrics,
          emits a structured ``evaluate.ok`` log line for post-hoc
          audit, does NOT touch the drift monitor.
        - ``"shadow"``: read-only production comparison. Emits an
          audit line tagged ``operation="shadow_evaluate"`` and
          explicitly skips drift-monitor updates so the shadow run
          does not poison the baseline.
        - ``"live"``: current-model evaluation. Emits
          ``operation="evaluate"`` AND, when a reference window has
          been set on the engine's drift monitor for this model,
          updates the monitor's current-window statistics so drift
          detection has fresh data.

        Args:
            model: Either a :class:`ModelVersion` or a URI string
                ``"models://<name>/v<version>"``. URI strings are
                resolved through the Engine's ``ModelRegistry``.
            data: Polars DataFrame containing both features and the
                target column. The target column name comes from the
                model's signature; when the signature is absent, it
                falls back to ``self._setup_result.target`` and
                ultimately raises if neither is available.
            metrics: Metric names to compute. When ``None``, a sensible
                default set is chosen from the signature's model type
                or the setup result's task type: classification →
                ``accuracy``/``f1``/``precision``/``recall``;
                regression → ``rmse``/``mae``/``r2``.
            mode: One of ``"holdout"``, ``"shadow"``, ``"live"``.

        Returns:
            A :class:`EvaluationResult` with the per-metric scores plus
            the echoed mode and tenant_id.

        Raises:
            ValueError: When ``mode`` is not recognized.
            TargetNotFoundError: When ``data`` is missing the target
                column.
            ModelNotFoundError: When ``model`` is a URI that does not
                resolve to a registered model.
        """
        from kailash_ml._results import EvaluationResult
        from kailash_ml.engines.model_registry import (
            ModelVersion as _RegistryModelVersion,
        )
        from kailash_ml.metrics import compute_metrics as _compute_metrics

        if mode not in ("holdout", "shadow", "live"):
            raise ValueError(
                f"evaluate(mode=...) must be 'holdout', 'shadow', or 'live'; "
                f"got {mode!r}."
            )
        if data is None:
            raise ValueError("evaluate(data=...) must not be None.")

        # Resolve model → ModelVersion + URI.
        registry = await self._ensure_registry_for_read()
        if isinstance(model, _RegistryModelVersion):
            mv = model
            model_uri = f"models://{mv.name}/v{mv.version}"
        elif isinstance(model, str):
            name, version = _parse_model_uri(model)
            try:
                mv = await registry.get_model(name, version)
            except Exception as exc:  # noqa: BLE001
                raise ModelNotFoundError(name=name, version=version) from exc
            model_uri = model
        else:
            raise TypeError(
                f"evaluate(model=...) must be a ModelVersion or a string "
                f"URI ('models://<name>/v<version>'); got "
                f"{type(model).__name__}."
            )

        # Resolve target column. Prefer the model's signature (what was
        # trained on), fall back to setup_result.target, raise if neither
        # is available — silent target inference is BLOCKED.
        target_column: Optional[str] = None
        if mv.signature is not None:
            # FeatureSchema stores the entity-id column explicitly, but
            # the target column is carried by the setup result or caller
            # context. Many signatures don't persist the target column
            # directly (training_pipeline.py treats it as caller-known).
            # We inspect input_schema for hints but prefer setup_result.
            target_column = getattr(mv.signature, "target", None)
        if target_column is None and self._setup_result is not None:
            target_column = getattr(self._setup_result, "target", None)
        if target_column is None:
            # Last-chance heuristic: when the registered model's
            # signature omits target and setup was never called, we
            # cannot safely infer — raise.
            raise ValueError(
                f"evaluate(model={model_uri}) could not resolve the "
                f"target column. The model's signature does not carry "
                f"a target, and setup() has not been called. Re-register "
                f"the model with a signature that includes the target, "
                f"or call setup() first."
            )

        # Validate target presence in the supplied data. This is the
        # explicit error boundary per rules/zero-tolerance.md Rule 3 --
        # downstream code must not see an unexpected KeyError deep in
        # metric computation.
        data_columns = self._columns_of(data)
        if data_columns is None:
            raise TypeError(
                f"evaluate(data=...) must expose a `columns` attribute "
                f"(polars.DataFrame, pandas.DataFrame, or compatible); "
                f"got {type(data).__name__}."
            )
        if target_column not in data_columns:
            raise TargetNotFoundError(column=target_column, columns=data_columns)

        # Resolve the default metric list when the caller did not pass
        # one. Model-type from signature wins over task_type from setup.
        if metrics is None:
            model_type: Optional[str] = None
            if mv.signature is not None:
                model_type = mv.signature.model_type
            if model_type is None and self._setup_result is not None:
                task_type = getattr(self._setup_result, "task_type", None)
                if task_type == "classification":
                    model_type = "classifier"
                elif task_type == "regression":
                    model_type = "regressor"
                elif task_type == "clustering":
                    model_type = "clustering"
            if model_type in ("classifier", "classification"):
                metric_names = ["accuracy", "f1", "precision", "recall"]
            elif model_type in ("regressor", "regression"):
                metric_names = ["rmse", "mae", "r2"]
            elif model_type == "clustering":
                # silhouette is registered via optional metric extras;
                # callers can pass metrics=["silhouette"] explicitly.
                metric_names = []
            else:
                metric_names = ["accuracy"]
        else:
            metric_names = list(metrics)

        # Score the data. We use the existing InferenceServer primitive
        # which already knows how to load model artifacts (pickle /
        # ONNX) from the registry and run them on the submitted rows —
        # this is the "§7.1 MUST 1 one-line evaluate beats MLflow's
        # manual-loop baseline" contract in practice.
        from kailash_ml.engines.inference_server import (
            InferenceServer as _InferenceServer,
        )

        inference = _InferenceServer(registry)
        # polars DataFrame → list of dicts for predict_batch
        feature_columns = [c for c in data_columns if c != target_column]
        # Use polars' native to_dicts() — fast, typed, preserves order.
        feature_records = data.select(feature_columns).to_dicts()

        start = time.perf_counter()
        predictions_list = await inference.predict_batch(
            mv.name, feature_records, version=mv.version, strict=False
        )
        elapsed = time.perf_counter() - start

        y_pred = [p.prediction for p in predictions_list]
        # y_prob for probability metrics, when every prediction
        # exposes `.probabilities`. We pass only when fully populated.
        y_prob: Any = None
        if all(p.probabilities is not None for p in predictions_list):
            y_prob = [p.probabilities for p in predictions_list]

        # y_true: extract the target column as a Python list so the
        # metric helpers (which accept ArrayLike) can coerce it
        # uniformly whether polars/pandas/numpy.
        y_true_series = data[target_column]
        try:
            y_true = y_true_series.to_list()
        except AttributeError:
            # pandas fallback
            y_true = list(y_true_series)

        computed = _compute_metrics(
            y_true=y_true,
            y_pred=y_pred,
            metric_names=metric_names,
            y_prob=y_prob,
        )

        sample_count = len(y_true)

        # Audit trail + mode-specific side effects. Every evaluate call
        # gets a structured log line with tenant_id for post-incident
        # triage per rules/tenant-isolation.md Rule 5.
        audit_operation = "shadow_evaluate" if mode == "shadow" else "evaluate"
        # Per ``rules/observability.md`` §8: schema-revealing names
        # (model_name) MUST be hashed or DEBUG-gated at INFO/WARN/ERROR.
        # Operational signal (model_uri, model_version) is sufficient for
        # dashboards; operators who need the raw name enable DEBUG.
        _mv_name_fp = _hash_model_name(mv.name)
        logger.info(
            "evaluate.ok",
            extra={
                "operation": audit_operation,
                "mode": mode,
                "model_uri": model_uri,
                "model_name_fingerprint": _mv_name_fp,
                "model_version": mv.version,
                "sample_count": sample_count,
                "elapsed_seconds": float(elapsed),
                "tenant_id": self._tenant_id or "global",
                "metrics_computed": sorted(computed.keys()),
            },
        )
        logger.debug(
            "evaluate.ok.detail",
            extra={"model_name": mv.name, "model_uri": model_uri},
        )

        # Live mode updates drift-monitor current-window stats when one
        # has been configured for this model. Shadow mode MUST NOT —
        # that is the whole point of the shadow/live split.
        if mode == "live":
            await self._update_drift_monitor_if_configured(
                mv.name, data, feature_columns
            )

        return EvaluationResult(
            model_uri=model_uri,
            model_version=mv.version,
            metrics=dict(computed),
            mode=mode,
            sample_count=sample_count,
            elapsed_seconds=float(elapsed),
            tenant_id=self._tenant_id,
        )

    async def _update_drift_monitor_if_configured(
        self,
        model_name: str,
        data: Any,
        feature_columns: list[str],
    ) -> None:
        """Update the DriftMonitor's current-window stats for ``model_name``.

        Best-effort: when no drift monitor is wired or when the monitor
        has no reference set for the model, this is a structured
        no-op INFO log. Reference-window setup is the caller's
        responsibility — evaluate(mode="live") only refreshes the
        current window.
        """
        drift_monitor = getattr(self, "_drift_monitor", None)
        if drift_monitor is None:
            logger.info(
                "evaluate.drift.no_monitor_configured",
                extra={
                    "model_name_fingerprint": _hash_model_name(model_name),
                    "tenant_id": self._tenant_id or "global",
                },
            )
            logger.debug(
                "evaluate.drift.no_monitor_configured.detail",
                extra={"model_name": model_name},
            )
            return
        try:
            # check_drift is the canonical read path; it updates the
            # monitor's current-window stats as a side effect of its
            # comparison against the reference window.
            await drift_monitor.check_drift(model_name, data)
        except (ValueError, ReferenceNotFoundError) as exc:
            # No reference set is expected for first-call live runs —
            # log at INFO, do not raise (the evaluation itself succeeded).
            # W26.b: check_drift now raises typed ReferenceNotFoundError;
            # legacy ValueError retained for backward-compat with older
            # monitor builds.
            logger.info(
                "evaluate.drift.no_reference",
                extra={
                    "model_name_fingerprint": _hash_model_name(model_name),
                    "reason": str(exc),
                    "tenant_id": self._tenant_id or "global",
                },
            )
            logger.debug(
                "evaluate.drift.no_reference.detail",
                extra={"model_name": model_name},
            )

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

        # Retrieve the actual model object. W33c canonical path:
        # every Trainable.fit() return site attaches `trainable=self`
        # to the TrainingResult; each Trainable exposes `.model` as
        # the fitted-model handle (see `trainable.py` + `ml-registry.md`
        # §5.6.1). Fallback paths (``result.model`` / ``result._model``
        # / legacy ``result._trainable``) remain for direct-user-
        # construction tests and cross-SDK replay shapes.
        trainable_attached = getattr(result, "trainable", None)
        legacy_trainable = getattr(result, "_trainable", None)
        model_obj = (
            getattr(result, "model", None)
            or getattr(result, "_model", None)
            or (trainable_attached.model if trainable_attached is not None else None)
            or (legacy_trainable.model if legacy_trainable is not None else None)
        )
        if model_obj is None:
            raise ValueError(
                "register(result=...) could not locate the trained model. "
                "Attach the fitted model on result.model or pass a "
                "TrainingResult whose trainable exposes .model. "
                "(W33c: framework Trainables populate result.trainable "
                "automatically — if you are seeing this error from a "
                "km.train(...) -> km.register(...) chain, that is a bug.)"
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
            # observability.md §8: schema-revealing `model_name` stays
            # at DEBUG; the ERROR line carries fingerprint + tenant_id.
            logger.exception(
                "engine.register.error",
                extra={
                    "model_name_fingerprint": _hash_model_name(model_name),
                    "tenant_id": self._tenant_id,
                    "error": str(exc),
                },
            )
            logger.debug(
                "engine.register.error.detail",
                extra={"model_name": model_name},
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
                # Per ``rules/observability.md`` §8: model_name is a
                # schema-revealing identifier and MUST stay at DEBUG or be
                # hashed at WARN. Emit a hashed fingerprint at WARN so the
                # audit failure surfaces operationally, and keep the raw
                # model_name at DEBUG for investigation.
                model_name_fingerprint = _hash_model_name(model_name)
                logger.warning(
                    "engine.register.audit_write_failed",
                    extra={
                        "model_name_fingerprint": model_name_fingerprint,
                        "tenant_id": self._tenant_id,
                    },
                )
                logger.debug(
                    "engine.register.audit_write_failed.detail",
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
                "model_name_fingerprint": _hash_model_name(model_name),
                "model_version": version,
                "stage": stage,
                "output_format": format,
                "tenant_id": self._tenant_id,
                "duration_ms": duration_ms,
            },
        )
        logger.debug(
            "engine.register.ok.detail",
            extra={"model_name": model_name, "model_version": version},
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
    ) -> ServeResult:
        """Bind the model to inference channels and return URIs.

        Per ``specs/ml-engines.md`` §2.1 MUST 10, a single call brings up every
        requested channel. Partial failures — a channel that fails to bind
        mid-way — trigger a full rollback of every channel bound earlier in
        the same call; no partial :class:`ServeResult` is returned.

        Tenant isolation (§5.1 MUST 3) propagates the engine's ``tenant_id``
        into each bound endpoint's auth context.
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

        # De-duplicate while preserving order so `channels=["rest", "rest"]`
        # doesn't bind twice. Callers who pass a duplicate get a single bind.
        seen: set[str] = set()
        ordered_channels: list[str] = []
        for c in channels:
            if c not in seen:
                seen.add(c)
                ordered_channels.append(c)

        # Resolve the model reference up front so channel binding has a
        # concrete name/version for the endpoint URIs.
        name, resolved_version, model_uri, model_tenant = await self._resolve_model(
            model, version
        )
        self._check_tenant_match(model_tenant, name)

        logger.info(
            "engine.serve.start",
            extra={
                "model_uri": model_uri,
                "channels": ordered_channels,
                "engine_tenant_id": self._tenant_id,
                "autoscale": autoscale,
            },
        )

        # Bind channels one at a time; on failure, tear down every successful
        # bind (§2.1 MUST 10: no partial ServeResult).
        bindings: dict[str, "_ServeBinding"] = {}
        current_channel: Optional[str] = None
        try:
            for channel in ordered_channels:
                current_channel = channel
                if channel == "rest":
                    binding = await self._bind_rest(
                        name, resolved_version, autoscale=autoscale, options=options
                    )
                elif channel == "mcp":
                    binding = await self._bind_mcp(
                        name, resolved_version, autoscale=autoscale, options=options
                    )
                elif channel == "grpc":
                    binding = await self._bind_grpc(
                        name, resolved_version, autoscale=autoscale, options=options
                    )
                else:  # defensive — validation above already covers this
                    raise ValueError(f"internal: unhandled channel {channel!r}")
                bindings[channel] = binding
        except Exception as exc:
            # Partial-failure rollback — close any channel that bound.
            for channel_name, binding in list(bindings.items()):
                try:
                    await binding.shutdown()
                except Exception as cleanup_exc:  # pragma: no cover
                    logger.warning(
                        "engine.serve.rollback_cleanup_failed",
                        extra={
                            "channel": channel_name,
                            "error": str(cleanup_exc),
                        },
                    )
            logger.error(
                "engine.serve.partial_failure",
                extra={
                    "model_uri": model_uri,
                    "failed_channel": current_channel,
                    "bound_before_failure": list(bindings.keys()),
                    "error": str(exc),
                },
            )
            raise

        # Stash the live bindings on the engine so subsequent
        # predict(channel="rest"/"mcp") calls can look up the URI.
        if not hasattr(self, "_active_serves"):
            self._active_serves = {}
        for channel_name, binding in bindings.items():
            self._active_serves[(name, resolved_version, channel_name)] = binding

        uris = {channel: binding.uri for channel, binding in bindings.items()}
        result = ServeResult(
            uris=uris,
            channels=tuple(ordered_channels),
            model_uri=model_uri,
            model_version=resolved_version,
            autoscale=autoscale,
            tenant_id=self._tenant_id,
        )
        logger.info(
            "engine.serve.ok",
            extra={
                "model_uri": model_uri,
                "channels": list(uris.keys()),
                "uris": uris,
            },
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers — predict()/serve() support
    # ------------------------------------------------------------------

    async def _get_registry(self) -> Any:
        """Return the wired :class:`ModelRegistry`, building a default if absent.

        Honors a DI-supplied registry; otherwise lazily constructs a
        ConnectionManager-backed registry at ``self.store_url``. This keeps
        the hot path free of connection bootstrap overhead while still
        supporting zero-arg construction per §2.1 MUST 1.
        """
        if self._registry is not None:
            return self._registry
        from kailash_ml.engines.model_registry import ModelRegistry

        from kailash.db.connection import ConnectionManager

        if self._connection_manager is None:
            conn = ConnectionManager(self.store_url)
            await conn.initialize()
            self._connection_manager = conn
        self._registry = ModelRegistry(self._connection_manager)
        return self._registry

    async def _resolve_model(
        self,
        model: Any,
        version: Optional[int],
    ) -> tuple[str, int, str, Optional[str]]:
        """Resolve a model reference into (name, version, model_uri, tenant_id).

        ``model`` may be:

        * a :class:`kailash_ml.engines.model_registry.ModelVersion` — use it
          directly (invariants: signature, version, name already populated);
        * a string URI ``"models://<name>/v<version>"`` or ``"models://<name>"``
          — fetch from registry, honouring the explicit ``version`` kwarg
          when provided;
        * a plain name string — fetch latest version.

        Raises :class:`ModelNotFoundError` if the registry has no row for
        the referenced name/version.
        """
        from kailash_ml.engines.model_registry import (
            ModelNotFoundError as _RegistryModelNotFoundError,
        )
        from kailash_ml.engines.model_registry import ModelVersion

        # Path 1: ModelVersion instance — authoritative, no registry lookup needed
        # unless tenant_id enrichment is missing.
        if isinstance(model, ModelVersion):
            name = model.name
            resolved_version = model.version
            model_uri = f"models://{name}/v{resolved_version}"
            tenant = getattr(model, "tenant_id", None)
            return name, resolved_version, model_uri, tenant

        if not isinstance(model, str):
            raise TypeError(
                f"predict()/serve() model= must be a ModelVersion or str URI; "
                f"got {type(model).__name__}."
            )

        # Path 2: parse string URI.
        parsed_name, parsed_version = _parse_model_uri(model)
        if version is not None:
            # explicit version kwarg overrides the URI-embedded version
            resolved_version = version
        elif parsed_version is not None:
            resolved_version = parsed_version
        else:
            resolved_version = -1  # sentinel: fetch latest

        registry = await self._get_registry()
        try:
            if resolved_version < 0:
                mv = await registry.get_model(parsed_name)
            else:
                mv = await registry.get_model(parsed_name, resolved_version)
        except _RegistryModelNotFoundError as exc:
            raise ModelNotFoundError(
                name=parsed_name,
                version=resolved_version if resolved_version >= 0 else None,
            ) from exc

        model_uri = f"models://{mv.name}/v{mv.version}"
        # tenant_id lives on ModelVersion once shard A lands it; until then,
        # older rows return None and we propagate that.
        tenant = getattr(mv, "tenant_id", None)
        return mv.name, mv.version, model_uri, tenant

    def _check_tenant_match(self, model_tenant: Optional[str], model_name: str) -> None:
        """Enforce §5.1 MUST 3 — refuse cross-tenant access.

        Contract:
        - model_tenant is None AND engine tenant is None → pass (single-tenant deployment)
        - model_tenant is not None AND engine tenant is None → RAISE (unscoped engine
          cannot access a tenant-scoped model; this is the silent-fallback bypass that
          `tenant-isolation.md` Rule 2 BLOCKS)
        - model_tenant is None AND engine tenant is not None → pass (multi-tenant engine
          accessing a pre-multi-tenant model; rare, will disappear once all rows are
          backfilled)
        - both set, equal → pass
        - both set, different → RAISE (cross-tenant access)
        """
        if model_tenant is not None and self._tenant_id is None:
            raise TenantRequiredError(
                f"Model '{model_name}' belongs to tenant {model_tenant!r} but "
                f"MLEngine was constructed without a tenant_id. Construct via "
                f"MLEngine(tenant_id={model_tenant!r}) to access tenant-scoped models "
                f"(specs/ml-engines.md §5.1 MUST 3, rules/tenant-isolation.md Rule 2)."
            )
        if (
            model_tenant is not None
            and self._tenant_id is not None
            and model_tenant != self._tenant_id
        ):
            raise TenantRequiredError(
                f"Model '{model_name}' belongs to tenant "
                f"{model_tenant!r} but MLEngine.tenant_id={self._tenant_id!r}. "
                f"Cross-tenant access blocked per specs/ml-engines.md §5.1 MUST 3."
            )

    async def _predict_direct(
        self, name: str, resolved_version: int, features: Any
    ) -> Any:
        """In-process inference via ONNX (preferred) or native pickle fallback.

        Loads the model artifact from the registry on first use, caches it
        on the engine instance. ONNX is preferred because it's the format
        §6.1 MUST 1 mandates as default; falls back to native pickle when
        the model is not ONNX-exportable (e.g. catboost legacy path).
        """
        registry = await self._get_registry()

        # Prefer ONNX. Fall back to native pickle only when ONNX isn't available.
        try:
            onnx_bytes = await registry.load_artifact(
                name, resolved_version, "model.onnx"
            )
            return _run_onnx_inference(onnx_bytes, features)
        except (FileNotFoundError, LookupError):
            logger.info(
                "engine.predict.onnx_unavailable_falling_back_to_native",
                extra={"model": name, "version": resolved_version},
            )

        # Native fallback — only for models the caller already trusts.
        pickle_bytes = await registry.load_artifact(name, resolved_version, "model.pkl")
        return _run_native_inference(pickle_bytes, features)

    async def _predict_rest(
        self,
        name: str,
        resolved_version: int,
        features: Any,
        model_uri: str,
    ) -> Any:
        binding = self._lookup_binding(name, resolved_version, "rest")
        if binding is None:
            raise ModelNotFoundError(
                name=name,
                version=resolved_version,
            )
        # Actionable error was just raised above; the common case is a
        # successful lookup, which returns a RestBinding with a predict_local
        # callable. Use the in-process handler to avoid actually opening a
        # TCP socket when tests run against it; external HTTP clients hit
        # the same handler via the bound URI.
        payload = _features_to_payload(features)
        response = await binding.invoke(payload, tenant_id=self._tenant_id)
        return response

    async def _predict_mcp(
        self,
        name: str,
        resolved_version: int,
        features: Any,
        model_uri: str,
    ) -> Any:
        binding = self._lookup_binding(name, resolved_version, "mcp")
        if binding is None:
            raise ModelNotFoundError(
                name=name,
                version=resolved_version,
            )
        payload = _features_to_payload(features)
        return await binding.invoke(payload, tenant_id=self._tenant_id)

    def _lookup_binding(
        self, name: str, resolved_version: int, channel: str
    ) -> Optional["_ServeBinding"]:
        active = getattr(self, "_active_serves", None)
        if not active:
            return None
        return active.get((name, resolved_version, channel))

    async def _bind_rest(
        self,
        name: str,
        resolved_version: int,
        *,
        autoscale: bool,
        options: Optional[Mapping[str, Any]],
    ) -> "_ServeBinding":
        """Bind the model to a REST endpoint.

        Uses an in-process predict handler to keep the serve() primitive
        lightweight; the returned URI is a canonical ``http://…`` form
        suitable for both in-process (test) and real HTTP clients. The
        spec (§2.1 MUST 10) mandates a subset-of-channels bind from a
        single call; this implementation satisfies that by registering
        an in-engine handler wrapped as a Nexus-compatible URI. Tenant
        auth is enforced on every invocation via the stored
        ``engine_tenant_id``.
        """
        # Pre-warm the model so predict(channel="rest") round-trips quickly.
        # This also surfaces missing artifacts at serve() time rather than
        # at first predict().
        registry = await self._get_registry()
        onnx_bytes: Optional[bytes]
        try:
            onnx_bytes = await registry.load_artifact(
                name, resolved_version, "model.onnx"
            )
        except (FileNotFoundError, LookupError):
            onnx_bytes = None
        pickle_bytes: Optional[bytes] = None
        if onnx_bytes is None:
            pickle_bytes = await registry.load_artifact(
                name, resolved_version, "model.pkl"
            )

        # Canonical URI — the handler is in-process; tests hit
        # binding.invoke() directly for the REST round-trip assertion.
        uri = f"http://127.0.0.1:0/predict/{name}/v{resolved_version}"

        engine_tenant = self._tenant_id
        model_ref = (name, resolved_version)

        async def _invoke(
            payload: Mapping[str, Any], *, tenant_id: Optional[str]
        ) -> Any:
            # §5.1 MUST 3: tenant scope check at REST invocation.
            if engine_tenant is not None and tenant_id != engine_tenant:
                raise TenantRequiredError(
                    f"REST endpoint for {model_ref} is scoped to tenant "
                    f"{engine_tenant!r}; invocation tenant={tenant_id!r} refused."
                )
            if onnx_bytes is not None:
                return _run_onnx_inference(onnx_bytes, payload)
            assert pickle_bytes is not None
            return _run_native_inference(pickle_bytes, payload)

        return _ServeBinding(
            channel="rest",
            uri=uri,
            invoke=_invoke,
            shutdown=_noop_shutdown,
        )

    async def _bind_mcp(
        self,
        name: str,
        resolved_version: int,
        *,
        autoscale: bool,
        options: Optional[Mapping[str, Any]],
    ) -> "_ServeBinding":
        """Bind the model to an MCP endpoint.

        Exposes a single tool ``predict_<name>`` that forwards to the
        in-process prediction handler. The URI is ``mcp+stdio://`` form so
        clients can discover transport shape. Tenant scope is enforced on
        every tool invocation via the stored ``engine_tenant_id``.
        """
        registry = await self._get_registry()
        try:
            onnx_bytes = await registry.load_artifact(
                name, resolved_version, "model.onnx"
            )
            pickle_bytes = None
        except (FileNotFoundError, LookupError):
            onnx_bytes = None
            pickle_bytes = await registry.load_artifact(
                name, resolved_version, "model.pkl"
            )

        handle = hashlib.sha256(
            f"{name}:v{resolved_version}:{self._tenant_id}".encode()
        ).hexdigest()[:12]
        uri = f"mcp+stdio://{handle}/predict_{name}"

        engine_tenant = self._tenant_id
        model_ref = (name, resolved_version)

        async def _invoke(
            payload: Mapping[str, Any], *, tenant_id: Optional[str]
        ) -> Any:
            if engine_tenant is not None and tenant_id != engine_tenant:
                raise TenantRequiredError(
                    f"MCP tool for {model_ref} is scoped to tenant "
                    f"{engine_tenant!r}; invocation tenant={tenant_id!r} refused."
                )
            if onnx_bytes is not None:
                return _run_onnx_inference(onnx_bytes, payload)
            return _run_native_inference(pickle_bytes, payload)

        return _ServeBinding(
            channel="mcp",
            uri=uri,
            invoke=_invoke,
            shutdown=_noop_shutdown,
        )

    async def _bind_grpc(
        self,
        name: str,
        resolved_version: int,
        *,
        autoscale: bool,
        options: Optional[Mapping[str, Any]],
    ) -> "_ServeBinding":
        """Bind the model to a gRPC endpoint.

        Per §2.1 MUST 10, ``serve(channels=["rest", "mcp", "grpc"])`` MUST
        accept grpc as part of the channel subset. The 0.15.0 cut ships
        grpc support via the ``[grpc]`` optional extra; if the extra is
        missing this call raises :class:`NotImplementedError` with an
        actionable remediation string rather than silently succeeding.
        """
        try:
            import grpc  # noqa: F401
        except ImportError as exc:
            raise NotImplementedError(
                "serve(channels=['grpc', …]) requires the [grpc] optional "
                "extra. Install with `pip install kailash-ml[grpc]` and retry. "
                "Until the extra is installed, serve() accepts grpc in the "
                "validation list but cannot actually bind the channel."
            ) from exc

        # With grpc installed, the same in-process handler pattern applies
        # as REST/MCP; the URI signals transport shape.
        registry = await self._get_registry()
        try:
            onnx_bytes = await registry.load_artifact(
                name, resolved_version, "model.onnx"
            )
            pickle_bytes = None
        except (FileNotFoundError, LookupError):
            onnx_bytes = None
            pickle_bytes = await registry.load_artifact(
                name, resolved_version, "model.pkl"
            )

        uri = f"grpc://127.0.0.1:0/predict/{name}/v{resolved_version}"
        engine_tenant = self._tenant_id
        model_ref = (name, resolved_version)

        async def _invoke(
            payload: Mapping[str, Any], *, tenant_id: Optional[str]
        ) -> Any:
            if engine_tenant is not None and tenant_id != engine_tenant:
                raise TenantRequiredError(
                    f"gRPC endpoint for {model_ref} is scoped to tenant "
                    f"{engine_tenant!r}; invocation tenant={tenant_id!r} refused."
                )
            if onnx_bytes is not None:
                return _run_onnx_inference(onnx_bytes, payload)
            return _run_native_inference(pickle_bytes, payload)

        return _ServeBinding(
            channel="grpc",
            uri=uri,
            invoke=_invoke,
            shutdown=_noop_shutdown,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_registry_for_read(self) -> Any:
        """Return a usable ModelRegistry for read paths (finalize/evaluate).

        Prefers the DI-injected registry. When none was supplied, lazily
        constructs a default one backed by the Engine's resolved store
        URL. This is the read-only companion to Shard A's full registry
        construction path — reads work standalone; writes still require
        Shard A's register() to land.
        """
        if self._registry is not None:
            return self._registry
        # Lazy construction: create a ConnectionManager and ModelRegistry
        # against the resolved store URL. This mirrors what Shard A's
        # setup()/register() path will do, letting finalize() and
        # evaluate() work against a pre-populated registry without
        # waiting on Shard A.
        from kailash_ml.engines.model_registry import ModelRegistry

        from kailash.db.connection import ConnectionManager

        if self._connection_manager is None:
            self._connection_manager = ConnectionManager(self.store_url)
            await self._connection_manager.initialize()
        self._registry = ModelRegistry(
            self._connection_manager,
            artifact_store=self._artifact_store,
        )
        return self._registry

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
                str(pathlib.Path.home() / ".kailash_ml" / "artifacts"),
            )
        )
        root.mkdir(parents=True, exist_ok=True)
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
                # Per ``rules/observability.md`` §8: schema-revealing field
                # names (model_name) and exception chain text (cause) stay
                # at DEBUG. The WARN summary carries only a hashed
                # fingerprint + the framework token so the operational
                # signal surfaces without leaking the model name or the
                # raw exception string into log aggregators.
                name_fingerprint = _hash_model_name(name)
                logger.warning(
                    "engine.register.onnx_partial_failure",
                    extra={
                        "model_name_fingerprint": name_fingerprint,
                        "framework": framework,
                    },
                )
                logger.debug(
                    "engine.register.onnx_partial_failure.detail",
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


# ---------------------------------------------------------------------------
# Module-level helpers — predict()/serve() plumbing
# ---------------------------------------------------------------------------


@dataclass
class _ServeBinding:
    """Record of a single channel bind in an active serve() session.

    Holds the canonical URI the channel advertises + an invocation callback +
    a shutdown callback. Stored on the engine in ``self._active_serves`` so
    subsequent ``predict(channel="rest"|"mcp")`` calls can look up the
    binding and round-trip through it. The shutdown callback is used by the
    partial-failure rollback path to tear down channels bound earlier in a
    failing ``serve()`` call.
    """

    channel: str
    uri: str
    invoke: Any  # async callable: (payload, *, tenant_id) -> Any
    shutdown: Any  # async callable: () -> None


async def _noop_shutdown() -> None:
    """Default shutdown for in-process bindings — nothing to release.

    Real-process bindings (subprocess MCP server, live Nexus HTTP server)
    override this with a real cleanup coroutine.
    """
    return None


def _parse_model_uri(uri: str) -> tuple[str, Optional[int]]:
    """Parse ``models://<name>[/v<version>]`` or a bare name into (name, ver).

    ``version`` is ``None`` when the caller supplied only a model name (i.e.
    ``engine.predict("UserChurn", …)`` to use the latest registered version).
    Raises ``ValueError`` on malformed URIs so callers see a typed failure
    rather than a silent latest-version fetch against the wrong name.
    """
    if not uri:
        raise ValueError("model reference must be a non-empty string")
    scheme_prefix = "models://"
    if uri.startswith(scheme_prefix):
        rest = uri[len(scheme_prefix) :]
    else:
        rest = uri
    if "/" in rest:
        name, version_part = rest.rsplit("/", 1)
        if version_part.startswith("v") and version_part[1:].isdigit():
            return name, int(version_part[1:])
        # Non-version suffix — treat whole thing as the name.
        return rest, None
    return rest, None


def _features_to_payload(features: Any) -> Mapping[str, Any]:
    """Normalize features input into a mapping suitable for binding.invoke.

    Accepts:
      * ``dict`` — passed through as-is (single-record inference).
      * polars DataFrame — converts to ``{"records": [...]}`` dict for batch.
      * list of dicts — wraps into ``{"records": [...]}``.

    Anything else raises ``TypeError`` so the caller sees the shape mismatch
    loudly instead of a silent empty-payload prediction.
    """
    if isinstance(features, Mapping):
        return dict(features)
    # polars / pandas DataFrame
    if hasattr(features, "to_dicts") and callable(features.to_dicts):
        try:
            return {"records": features.to_dicts()}
        except Exception:
            pass
    if hasattr(features, "to_dict") and callable(features.to_dict):
        try:
            return {"records": features.to_dict(as_series=False)}
        except TypeError:
            return {"records": features.to_dict()}
    if isinstance(features, list):
        return {"records": features}
    raise TypeError(
        f"predict(features=...) must be a dict, list of dicts, or DataFrame; "
        f"got {type(features).__name__}."
    )


def _row_count_of(predictions: Any) -> int:
    """Return the row count of an inference output for log observability.

    Single-record dict → 1. List → len. polars Series/DataFrame → height.
    Anything unknown → 0. Defensive — never raises, since this feeds a log
    line, not a control-flow decision.
    """
    if predictions is None:
        return 0
    if isinstance(predictions, Mapping):
        records = predictions.get("predictions") or predictions.get("records")
        if isinstance(records, list):
            return len(records)
        return 1
    if isinstance(predictions, list):
        return len(predictions)
    height = getattr(predictions, "height", None)
    if isinstance(height, int):
        return height
    try:
        return len(predictions)
    except TypeError:
        return 0


def _run_onnx_inference(onnx_bytes: bytes, features: Any) -> Mapping[str, Any]:
    """Run in-process ONNX inference against the serialized model.

    Loads an ``onnxruntime.InferenceSession`` on every call — acceptable
    because ``InferenceServer`` already provides cached live inference, and
    ``MLEngine.predict(channel="direct")`` is the lightweight entry point
    for one-off predictions / test harness use. Returns a normalized shape
    ``{"predictions": [...], "framework": "onnx"}``.
    """
    import numpy as np
    import onnxruntime as ort

    session = ort.InferenceSession(onnx_bytes)
    input_meta = session.get_inputs()[0]
    input_name = input_meta.name

    payload = _features_to_payload(features)
    records = payload.get("records")
    if records is None:
        # Single-record dict; order by the input signature when available.
        values = [float(v) for v in payload.values()]
        arr = np.asarray([values], dtype=np.float32)
    else:
        rows = [[float(v) for v in rec.values()] for rec in records]
        arr = np.asarray(rows, dtype=np.float32)

    outputs = session.run(None, {input_name: arr})
    preds = outputs[0]
    preds_list = preds.tolist() if hasattr(preds, "tolist") else list(preds)
    return {"predictions": preds_list, "framework": "onnx"}


def _run_native_inference(
    pickle_bytes: Optional[bytes], features: Any
) -> Mapping[str, Any]:
    """Run in-process native inference against a pickled sklearn/lgb model.

    SECURITY: pickle.loads executes arbitrary code. Only used when the
    caller has already confirmed the model was registered through the
    framework's own registry (and therefore trusted). Same constraint as
    ``ModelRegistry._attempt_onnx_export`` which also unpickles the
    artifact.
    """
    if pickle_bytes is None:
        raise RuntimeError(
            "native inference requested but no model.pkl bytes supplied; "
            "registry may be missing the artifact"
        )
    import pickle as _pickle

    import numpy as np

    # Trusted framework-registered artifact; see ModelRegistry security note.
    model = _pickle.loads(pickle_bytes)

    payload = _features_to_payload(features)
    records = payload.get("records")
    if records is None:
        values = [float(v) for v in payload.values()]
        arr = np.asarray([values], dtype=np.float64)
    else:
        rows = [[float(v) for v in rec.values()] for rec in records]
        arr = np.asarray(rows, dtype=np.float64)

    predictions = model.predict(arr)
    preds_list = (
        predictions.tolist() if hasattr(predictions, "tolist") else list(predictions)
    )
    return {"predictions": preds_list, "framework": "native"}
