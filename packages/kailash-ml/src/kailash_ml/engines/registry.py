# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Engine discovery registry (`km.list_engines` + `km.engine_info`).

Per ``specs/ml-engines-v2-addendum.md §E11``, this module hosts the
discovery surface for every engine in `kailash-ml`. The registry is
populated at import-time via the :func:`_register` helper below;
each engine is recorded as a frozen :class:`EngineInfo` so the
values are hashable and safe to cache in Kaizen agent tool
descriptors.

The public entry points are :func:`list_engines` and :func:`engine_info`;
they are re-exported from ``kailash_ml/__init__.py`` under
``__all__`` Group 6 (`ml-engines-v2.md §15.9`).

Implementation posture (W33)
----------------------------

The §E1.1 matrix enumerates 18 engines. Every entry below carries:

- ``name`` — class name (e.g. ``"MLEngine"`` / ``"ModelRegistry"``).
- ``version`` — pulled from :data:`kailash_ml.__version__` per
  ``§E11.3 MUST 3`` (split-version states are
  ``rules/zero-tolerance.md`` Rule 5 violations).
- ``module_path`` — dotted import path for the owning module.
- ``accepts_tenant_id``, ``emits_to_tracker`` — all 18 engines
  auto-wire + accept ``tenant_id`` per §E1.1, so these are ``True``
  across the board.
- ``clearance_level`` — per §E9.2's D/T/R axis + L/M/H level matrix.
  ``None`` entries are engines that do not require clearance at their
  primary mutation boundary (e.g. :class:`DataExplorer` does
  read-only profiling). When the §E9.2 matrix assigns a clearance,
  it is captured as a tuple of
  :class:`ClearanceRequirement` entries.
- ``signatures`` — tuple of :class:`MethodSignature` dataclasses, one
  per public method the engine exposes. The per-engine count varies
  (MLEngine=8, support engines 1-4 per §E1.1 "Primary mutation methods
  audited" column).
- ``extras_required`` — tuple of extras the engine needs beyond the
  base install (e.g. ``("rl",)`` for any RL surface).

The registry is a module-level ``OrderedDict`` keyed by engine name;
:func:`list_engines` returns its values as an immutable tuple (stable
insertion order per Python >= 3.7), and :func:`engine_info` does an
O(1) lookup, raising :class:`EngineNotFoundError` with the valid-names
list in the error message per §E11.2.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import ClassVar, Literal, Optional

from kailash_ml._version import __version__ as _KML_VERSION
from kailash_ml.errors import MLError


# --------------------------------------------------------------------------
# Frozen dataclasses — per §E11.1
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamSpec:
    """Single parameter of a public method signature.

    Per ``ml-engines-v2-addendum.md §E11.1``:

    - ``annotation`` is the stringified type annotation so the
      dataclass stays hashable and safe to cache in agent tool
      descriptors (types themselves may be unhashable).
    - ``default`` is ``None`` when the parameter has no default or
      the sentinel ``"<NO_DEFAULT>"`` when the arg is
      positional-required.
    - ``kind`` follows :class:`inspect.Parameter` kinds collapsed to
      four semantically-distinct buckets.
    """

    name: str
    annotation: str
    default: Optional[str]
    kind: Literal[
        "positional_or_keyword",
        "keyword_only",
        "var_positional",
        "var_keyword",
    ]


@dataclass(frozen=True)
class MethodSignature:
    """Complete public-method signature entry."""

    method_name: str
    params: tuple[ParamSpec, ...]
    return_annotation: str
    is_async: bool
    is_deprecated: bool = False
    deprecated_since: Optional[str] = None
    deprecated_removal: Optional[str] = None


ClearanceLevel = Literal["L", "M", "H"]
ClearanceAxis = Literal["D", "T", "R"]


@dataclass(frozen=True)
class ClearanceRequirement:
    """One (axis, min_level) pair per ``§E9.2``."""

    axis: ClearanceAxis
    min_level: ClearanceLevel


@dataclass(frozen=True)
class EngineInfo:
    """Agent-discoverable engine metadata.

    Returned by :func:`engine_info` and enumerated by
    :func:`list_engines`. Hashable (every field is hashable per
    ``frozen=True`` + tuple-not-list choices).
    """

    name: str
    version: str
    module_path: str
    accepts_tenant_id: bool
    emits_to_tracker: bool
    clearance_level: Optional[tuple[ClearanceRequirement, ...]]
    signatures: tuple[MethodSignature, ...]
    extras_required: tuple[str, ...] = ()


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class EngineNotFoundError(MLError):
    """Raised by :func:`engine_info` when ``name`` is not registered.

    The error message MUST list the available engine names per
    ``ml-engines-v2-addendum.md §E11.2``.
    """


# --------------------------------------------------------------------------
# Registry storage — module-level ordered dict
# --------------------------------------------------------------------------

# Insertion-order preserved per Python >= 3.7. The 18 engines from
# `§E1.1` are registered below; ``list_engines()`` returns the values
# in this order.
_REGISTRY: "OrderedDict[str, EngineInfo]" = OrderedDict()


def _register(info: EngineInfo) -> None:
    """Register an engine. Idempotent on re-import."""
    _REGISTRY[info.name] = info


# --------------------------------------------------------------------------
# Public API — §E11.2
# --------------------------------------------------------------------------


def list_engines() -> tuple[EngineInfo, ...]:
    """Return all registered engines.

    Returns an immutable tuple in insertion order (stable across
    Python >= 3.7). Per ``ml-engines-v2-addendum.md §E11.3 MUST 2``,
    an engine missing from the registry is not discoverable and
    therefore not available to Kaizen agents — adding an engine
    without an :func:`_register` call is a spec violation.
    """
    return tuple(_REGISTRY.values())


def engine_info(name: str) -> EngineInfo:
    """Look up a single engine by class name.

    :param name: Engine class name (e.g. ``"MLEngine"``, ``"ModelRegistry"``).
    :raises EngineNotFoundError: When ``name`` is not registered.
        The error message lists the available engine names so the
        caller can correct the typo.

    Typical usage::

        info = km.engine_info("TrainingPipeline")
        for sig in info.signatures:
            print(sig.method_name, sig.is_async, sig.return_annotation)
    """
    if name not in _REGISTRY:
        raise EngineNotFoundError(
            reason=(
                f"engine_info({name!r}) — no such engine. Available: "
                f"{tuple(_REGISTRY.keys())}"
            ),
            resource_id=name,
        )
    return _REGISTRY[name]


# --------------------------------------------------------------------------
# Registration — one entry per §E1.1 row
#
# Method signatures are captured as :class:`MethodSignature` tuples
# rather than generated via :mod:`inspect` so the module stays
# importable before every engine module is loaded (engines are
# lazy-imported from ``kailash_ml`` per the legacy ``__getattr__``
# layer). Kaizen agents calling ``engine_info("AutoMLEngine")`` do not
# need AutoML's ``scikit-learn`` / ``lightgbm`` sub-imports to land.
# --------------------------------------------------------------------------


# Shared builders --------------------------------------------------------

_DATA_MED = (ClearanceRequirement(axis="D", min_level="M"),)
_DATA_HIGH = (ClearanceRequirement(axis="D", min_level="H"),)
_TRAIN_MED = (
    ClearanceRequirement(axis="D", min_level="M"),
    ClearanceRequirement(axis="T", min_level="L"),
)
_REGISTER_MED = (
    ClearanceRequirement(axis="D", min_level="M"),
    ClearanceRequirement(axis="R", min_level="M"),
)


def _p(
    name: str,
    annotation: str,
    default: Optional[str] = "<NO_DEFAULT>",
    kind: str = "keyword_only",
) -> ParamSpec:
    """Compact ParamSpec builder."""
    return ParamSpec(name=name, annotation=annotation, default=default, kind=kind)  # type: ignore[arg-type]


def _sig(
    method_name: str,
    params: tuple[ParamSpec, ...],
    return_annotation: str,
    is_async: bool = True,
) -> MethodSignature:
    return MethodSignature(
        method_name=method_name,
        params=params,
        return_annotation=return_annotation,
        is_async=is_async,
    )


# MLEngine — 8 methods per §2.1 MUST 5 ---------------------------------

_register(
    EngineInfo(
        name="MLEngine",
        version=_KML_VERSION,
        module_path="kailash_ml.engine",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=_TRAIN_MED,
        signatures=(
            _sig(
                "setup",
                (
                    _p("data", "Any", kind="positional_or_keyword"),
                    _p("target", "Optional[str]", default="None"),
                    _p("ignore", "Optional[list[str]]", default="None"),
                ),
                "SetupResult",
            ),
            _sig(
                "compare",
                (
                    _p("families", "Optional[list[str]]", default="None"),
                    _p("metric", "Optional[str]", default="None"),
                ),
                "ComparisonResult",
            ),
            _sig(
                "fit",
                (
                    _p("data", "Any", default="None", kind="positional_or_keyword"),
                    _p("target", "Optional[str]", default="None"),
                    _p("family", "Optional[str]", default="None"),
                    _p("trainable", "Any", default="None"),
                ),
                "TrainingResult",
            ),
            _sig(
                "predict",
                (_p("X", "Any", kind="positional_or_keyword"),),
                "PredictionResult",
            ),
            _sig(
                "finalize",
                (_p("result", "TrainingResult", kind="positional_or_keyword"),),
                "FinalizeResult",
            ),
            _sig(
                "evaluate",
                (
                    _p("result", "TrainingResult", kind="positional_or_keyword"),
                    _p("data", "Any", kind="positional_or_keyword"),
                ),
                "EvaluationResult",
            ),
            _sig(
                "register",
                (
                    _p("result", "TrainingResult", kind="positional_or_keyword"),
                    _p("name", "Optional[str]", default="None"),
                    _p("stage", "str", default='"staging"'),
                    _p("format", "str", default='"onnx"'),
                ),
                "RegisterResult",
            ),
            _sig(
                "serve",
                (
                    _p("model", "Any", kind="positional_or_keyword"),
                    _p("channels", "list[str]"),
                ),
                "ServeResult",
            ),
        ),
        extras_required=(),
    )
)


# Support engines — one registration per §E1.1 row ---------------------

_register(
    EngineInfo(
        name="TrainingPipeline",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.training_pipeline",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=_TRAIN_MED,
        signatures=(
            _sig(
                "train",
                (
                    _p("schema", "FeatureSchema", kind="positional_or_keyword"),
                    _p("model_spec", "ModelSpec", kind="positional_or_keyword"),
                    _p("eval_spec", "EvalSpec", kind="positional_or_keyword"),
                ),
                "TrainingResult",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="ExperimentTracker",
        version=_KML_VERSION,
        module_path="kailash_ml.tracking.tracker",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=None,
        signatures=(
            _sig("create_experiment", (_p("name", "str"),), "str"),
            _sig(
                "create_run",
                (
                    _p("experiment_name", "str"),
                    _p("run_name", "Optional[str]", default="None"),
                ),
                "ExperimentRun",
            ),
            _sig(
                "log_metric",
                (
                    _p("run_id", "str"),
                    _p("name", "str"),
                    _p("value", "float"),
                ),
                "None",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="ModelRegistry",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.model_registry",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=_REGISTER_MED,
        signatures=(
            _sig(
                "register_model",
                (
                    _p(
                        "training_result",
                        "TrainingResult",
                        kind="positional_or_keyword",
                    ),
                    _p("name", "str"),
                ),
                "RegisterResult",
            ),
            _sig("promote_model", (_p("name", "str"), _p("version", "int")), "None"),
            _sig("demote_model", (_p("name", "str"), _p("version", "int")), "None"),
            _sig(
                "delete_model",
                (_p("name", "str"), _p("version", "int")),
                "None",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="FeatureStore",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.feature_store",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=_DATA_MED,
        signatures=(
            _sig(
                "register_group",
                (_p("schema", "FeatureSchema", kind="positional_or_keyword"),),
                "None",
            ),
            _sig(
                "materialize",
                (
                    _p("group", "str"),
                    _p("as_of", "Optional[str]", default="None"),
                ),
                "pl.DataFrame",
            ),
            _sig(
                "ingest",
                (
                    _p("group", "str"),
                    _p("schema", "FeatureSchema"),
                    _p("data", "pl.DataFrame"),
                ),
                "None",
            ),
            _sig(
                "erase_tenant",
                (_p("tenant_id", "str"),),
                "None",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="InferenceServer",
        version=_KML_VERSION,
        # W6-004 (F-E1-28): legacy `engines.inference_server` deleted;
        # canonical surface lives at `serving.server`. Signatures track
        # the W25 lifecycle (`from_registry`/`start`/`predict`/`stop`).
        module_path="kailash_ml.serving.server",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=_DATA_MED,
        signatures=(
            _sig(
                "predict",
                (_p("features", "Mapping[str, Any]", kind="positional_or_keyword"),),
                "Mapping[str, Any]",
            ),
            _sig(
                "start",
                (),
                "ServeHandle",
            ),
            _sig(
                "stop",
                (),
                "None",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="DriftMonitor",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.drift_monitor",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=_DATA_MED,
        signatures=(
            _sig(
                "set_reference_data",
                (
                    _p("model_uri", "str"),
                    _p("data", "pl.DataFrame"),
                ),
                "None",
            ),
            _sig(
                "check_drift",
                (
                    _p("model_uri", "str"),
                    _p("current_data", "pl.DataFrame"),
                ),
                "DriftReport",
            ),
            _sig(
                "schedule_monitoring",
                (_p("model_uri", "str"), _p("interval_s", "int")),
                "None",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="AutoMLEngine",
        version=_KML_VERSION,
        module_path="kailash_ml.automl.engine",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=_TRAIN_MED,
        signatures=(
            _sig(
                "run",
                (
                    _p("schema", "FeatureSchema", kind="positional_or_keyword"),
                    _p("data", "pl.DataFrame", kind="positional_or_keyword"),
                ),
                "AutoMLResult",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="HyperparameterSearch",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.hyperparameter_search",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=_TRAIN_MED,
        signatures=(
            _sig(
                "search",
                (
                    _p("trainable", "Trainable", kind="positional_or_keyword"),
                    _p("space", "dict", kind="positional_or_keyword"),
                    _p("n_trials", "int", default="50"),
                ),
                "SearchResult",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="Ensemble",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.ensemble",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=_TRAIN_MED,
        signatures=(
            _sig(
                "from_leaderboard",
                (_p("leaderboard", "ComparisonResult", kind="positional_or_keyword"),),
                "Ensemble",
                is_async=False,
            ),
            _sig(
                "fit",
                (
                    _p("data", "pl.DataFrame", kind="positional_or_keyword"),
                    _p("target", "str"),
                ),
                "TrainingResult",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="Preprocessing",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.preprocessing",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=None,
        signatures=(
            _sig(
                "setup",
                (
                    _p("data", "pl.DataFrame", kind="positional_or_keyword"),
                    _p("target", "Optional[str]", default="None"),
                ),
                "PreprocessingResult",
                is_async=False,
            ),
            _sig(
                "transform",
                (_p("data", "pl.DataFrame", kind="positional_or_keyword"),),
                "pl.DataFrame",
                is_async=False,
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="FeatureEngineer",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.feature_engineer",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=None,
        signatures=(
            _sig(
                "generate",
                (_p("data", "pl.DataFrame", kind="positional_or_keyword"),),
                "pl.DataFrame",
                is_async=False,
            ),
            _sig(
                "select",
                (
                    _p("data", "pl.DataFrame", kind="positional_or_keyword"),
                    _p("target", "str"),
                ),
                "pl.DataFrame",
                is_async=False,
            ),
            _sig(
                "rank",
                (
                    _p("data", "pl.DataFrame", kind="positional_or_keyword"),
                    _p("target", "str"),
                ),
                "pl.DataFrame",
                is_async=False,
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="ModelExplainer",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.model_explainer",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=None,
        signatures=(
            _sig(
                "explain_global",
                (_p("max_display", "int", default="10"),),
                "dict",
                is_async=False,
            ),
            _sig(
                "explain_local",
                (
                    _p("X", "pl.DataFrame", kind="positional_or_keyword"),
                    _p("index", "int", default="0"),
                ),
                "dict",
                is_async=False,
            ),
        ),
        extras_required=("explain",),
    )
)

_register(
    EngineInfo(
        name="DataExplorer",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.data_explorer",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=None,
        signatures=(
            _sig(
                "profile",
                (_p("data", "pl.DataFrame", kind="positional_or_keyword"),),
                "DataProfile",
            ),
            _sig(
                "to_html",
                (_p("data", "pl.DataFrame", kind="positional_or_keyword"),),
                "str",
            ),
            _sig(
                "compare",
                (
                    _p("a", "pl.DataFrame", kind="positional_or_keyword"),
                    _p("b", "pl.DataFrame", kind="positional_or_keyword"),
                ),
                "DataComparison",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="ModelVisualizer",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.model_visualizer",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=None,
        signatures=(
            _sig(
                "confusion_matrix",
                (
                    _p("y_true", "Any", kind="positional_or_keyword"),
                    _p("y_pred", "Any", kind="positional_or_keyword"),
                ),
                "Figure",
                is_async=False,
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="Clustering",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.clustering",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=_TRAIN_MED,
        signatures=(
            _sig(
                "fit",
                (_p("data", "pl.DataFrame", kind="positional_or_keyword"),),
                "ClusteringResult",
            ),
            _sig(
                "predict",
                (_p("data", "pl.DataFrame", kind="positional_or_keyword"),),
                "pl.Series",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="AnomalyDetection",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.anomaly_detection",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=_DATA_MED,
        signatures=(
            _sig(
                "fit",
                (_p("data", "pl.DataFrame", kind="positional_or_keyword"),),
                "None",
            ),
            _sig(
                "score",
                (_p("data", "pl.DataFrame", kind="positional_or_keyword"),),
                "pl.Series",
            ),
            _sig(
                "flag",
                (_p("data", "pl.DataFrame", kind="positional_or_keyword"),),
                "pl.Series",
            ),
        ),
    )
)

_register(
    EngineInfo(
        name="DimReduction",
        version=_KML_VERSION,
        module_path="kailash_ml.engines.dim_reduction",
        accepts_tenant_id=True,
        emits_to_tracker=True,
        clearance_level=None,
        signatures=(
            _sig(
                "fit",
                (_p("data", "pl.DataFrame", kind="positional_or_keyword"),),
                "None",
            ),
            _sig(
                "transform",
                (_p("data", "pl.DataFrame", kind="positional_or_keyword"),),
                "pl.DataFrame",
            ),
        ),
    )
)


__all__ = [
    "ParamSpec",
    "MethodSignature",
    "ClearanceRequirement",
    "EngineInfo",
    "EngineNotFoundError",
    "engine_info",
    "list_engines",
]
