# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``kailash_ml.from_brief()`` — prose-to-ML-plan realizer.

Closes issue #1125 AC 5 + AC 10: the ML surface of the ``from_brief()``
primitive family. Given a natural-language brief AND a polars DataFrame,
returns a ``(FeatureSchema, ModelSpec, EvalSpec)`` triple ready for
:class:`kailash_ml.TrainingPipeline` or ``km.train`` consumption.

Verb-choice rationale (per the 5-surface comparison documented in
README Quick Start): every other ``from_brief()`` surface returns an
INSTANCE of its containing class (``Workflow``, ``DataFlow``,
``Signature`` subclass), so they bind as classmethods. The ML surface
returns a TUPLE of three independent dataclasses — none of which is
``kailash_ml`` itself — so it lives as a module-level function. Pattern
mirrors :func:`kailash.bootstrap`: module-level when the result type
differs from the host module.

Pipeline (per ``workspaces/from-brief-1125/02-plans/01-architecture.md``
§3.5)::

    brief, df → extract df.dtypes + df.columns (pre-LLM structural plumbing)
             → scrub_brief()                          # credential scrub
             → MLPlanSignature (Kaizen Signature)     # LLM emits typed plan
             → coerce_plan + validate_plan            # structural plus confidence
             → validate feature_columns ⊆ df.columns  # data-grounding check
             → validate ModelSpec.task allowlist      # closed enum gate
             → return (FeatureSchema, ModelSpec, EvalSpec)

Per ``rules/agent-reasoning.md`` MUST Rule 1, the LLM does ALL reasoning
about which columns to use, which task type matches, which target column
maps to the prediction goal, and which evaluation metric fits. The
realizer is permitted deterministic logic (per § "Permitted Deterministic
Logic" exception 6 — tool result parsing / structural plumbing) — it
does NOT decide what the system should think, only how a validated plan
maps to the framework's typed dataclasses.

Per ``rules/env-models.md``, the LLM model is read from
``DEFAULT_LLM_MODEL`` in the environment; the helper raises
:class:`~kailash._from_brief.signatures.MissingDefaultLLMModelError`
when unset.

Per ``rules/orphan-detection.md`` MUST Rule 1, this module is the
production call site for the S1 ``_from_brief`` primitives: every
S1 gate (scrub, validate, allowlist, confidence) is invoked from
:func:`from_brief` on the hot path.

## FeatureSchema choice (architecture Q1 — APPROVED)

The realizer constructs the **frozen + content-addressed**
:class:`kailash_ml.features.schema.FeatureSchema` (registry-consumed
shape), NOT the mutable variant at ``kailash_ml.types``. Frozen-version
benefits:

- Content hash deduplicates byte-identical schemas across realize-calls.
- Registry-keyable by ``(name, version)`` so subsequent ``TrainingPipeline``
  + ``ModelRegistry`` calls compose cleanly.
- Refinement is explicit: callers wanting to add/remove fields use
  :meth:`FeatureSchema.with_features` to derive a new content-hashed
  schema (introduced in this same shard per the same-bug-class same-shard
  fix discipline in ``rules/autonomous-execution.md`` MUST-4).

The trade-off: the realizer cannot mutate the schema after construction.
Every refinement creates a new frozen instance. This matches the
upstream ``ModelRegistry`` contract — registry rows are content-keyed,
not mutable.

## Task allowlist

Per ``rules/zero-tolerance.md`` Rule 2 (no stubs / no fake dispatch),
``ModelSpec.task`` is gated against a closed allowlist that covers every
task the bundled adapters in :mod:`kailash_ml.trainable` can train. The
allowlist is enumerated explicitly so a hallucinated task ("anomaly",
"clustering", "embedding") fails LOUDLY at the validation gate rather
than silently producing a broken :class:`ModelSpec` whose
``model_class`` mapping is undefined.

Architecture context: ``workspaces/from-brief-1125/02-plans/01-architecture.md``
§3.5 names this surface as Sg-MLPlan. Sibling shards land Sg-Workflow
(S2, kailash core), Sg-Schema (S3, kailash-dataflow), Sg-Signature (S4,
kaizen), Sg-Bootstrap (S5, kailash.bootstrap).

Origin: issue #1125 AC 5 + AC 10 + AC 11 (README rewrite). User-anchored
value source (a): the issue body, AC 5 verbatim — "``kailash_ml.from_brief(brief,
df)`` returns a ``(FeatureSchema, ModelSpec, EvalSpec)`` triple whose
``FeatureSchema`` matches the dataframe's columns and ``ModelSpec.task``
matches the brief's stated prediction goal."
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, cast

import polars as pl
from kailash_ml.engines.training_pipeline import EvalSpec, ModelSpec
from kailash_ml.features.schema import FeatureField, FeatureSchema

from kailash._from_brief import (
    BriefInterpretationError,
    coerce_plan,
    scrub_brief,
    validate_plan,
)
from kailash._from_brief.confidence import DEFAULT_CONFIDENCE_THRESHOLD
from kailash._from_brief.validator import BriefPlan as _BasePlan

# kaizen-dependent imports (`BriefPlanSignature` / `get_default_llm_model` from
# kailash._from_brief, `OutputField` / `BaseAgent` from kaizen) are LAZY —
# deferred into function bodies + the lazy `_ml_plan_signature_cls()` factory
# below. kaizen is a SEPARATE downstream package (kailash-kaizen); kailash-ml
# MUST NOT import it at module scope (rules/dependencies.md "Declared =
# Imported"; rules/framework-first.md layering). Importing it eagerly here would
# make `import kailash_ml` (which re-exports `from_brief`) require kaizen,
# breaking every kailash-ml CI test at collection time when kaizen is absent.
# `get_default_llm_model` lives in `kailash._from_brief.signatures` which imports
# kaizen at module scope, so it is lazy too. Pattern mirrors
# `kailash/workflow/from_brief.py::_signature_cls`.
if TYPE_CHECKING:
    from kailash._from_brief import BriefPlanSignature  # noqa: F401

__all__ = [
    "ALLOWED_TASKS",
    "ALLOWED_EVAL_METRICS",
    "DEFAULT_MODEL_CLASS_BY_TASK",
    "MLPlanSignature",
    "MLPlan",
    "from_brief",
]

logger = logging.getLogger(__name__)


# =========================================================================
# Task + metric allowlists
# =========================================================================
#
# The closed sets below are the ONLY task / metric identifiers the LLM
# may emit. Extending these requires an explicit code change so a
# hallucinated task or metric fails loudly at the validation gate.
#
# Scope chosen to match the supervised-learning tasks exposed by
# `kailash_ml.trainable.SklearnTrainable`, `LightGBMTrainable`,
# `XGBoostTrainable`, and `LightningTrainable`. Tasks NOT in v1 of the
# `from_brief()` surface (clustering, anomaly detection, reinforcement
# learning) require their own realizer + signature in a future shard.

ALLOWED_TASKS: Set[str] = {
    "classification",
    "regression",
    "binary_classification",
    "multiclass_classification",
    "multilabel_classification",
}
"""Closed set of supervised-learning task identifiers the LLM may emit."""

ALLOWED_EVAL_METRICS: Set[str] = {
    # Classification metrics (per kailash_ml/engines/_shared.py
    # _CLASSIFICATION_METRICS).
    "accuracy",
    "f1",
    "precision",
    "recall",
    "auc",
    # Regression metrics (per kailash_ml/engines/_shared.py
    # _REGRESSION_METRICS).
    "mse",
    "rmse",
    "mae",
    "r2",
}
"""Closed set of evaluation-metric identifiers the LLM may emit."""

# Default model-class mapping per task type. Used when the LLM emits a
# task but does NOT emit a specific model_class (the common case for
# briefs that describe intent without naming the algorithm). All entries
# satisfy `engines/_shared.py::validate_model_class` allowlist.
DEFAULT_MODEL_CLASS_BY_TASK: Dict[str, str] = {
    "classification": "sklearn.ensemble.RandomForestClassifier",
    "binary_classification": "sklearn.ensemble.RandomForestClassifier",
    "multiclass_classification": "sklearn.ensemble.RandomForestClassifier",
    "multilabel_classification": "sklearn.ensemble.RandomForestClassifier",
    "regression": "sklearn.ensemble.RandomForestRegressor",
}
"""Default model_class string per task. Validated against the security allowlist."""

# Default metrics per task type. Used to populate `EvalSpec.metrics`
# when the LLM emits a task but no specific metrics. The choice mirrors
# what `EvalSpec`'s `default_factory` would assign for `accuracy` on
# classification and an MSE-equivalent for regression.
_DEFAULT_METRICS_BY_TASK: Dict[str, List[str]] = {
    "classification": ["accuracy", "f1"],
    "binary_classification": ["accuracy", "f1", "auc"],
    "multiclass_classification": ["accuracy", "f1"],
    "multilabel_classification": ["accuracy", "f1"],
    "regression": ["rmse", "r2"],
}


# =========================================================================
# Meta-Signature (Kaizen Signature that emits an ML plan) — LAZY
# =========================================================================
#
# `MLPlanSignature(BriefPlanSignature)` was a module-scope class; both its base
# (`BriefPlanSignature` from `kailash._from_brief`) and `OutputField` (from
# `kaizen.signatures`) carry the kaizen dependency. Defining it at module scope
# made `import kailash_ml` (which re-exports `from_brief`) require kaizen,
# breaking every kailash-ml CI test at collection time when kaizen is absent.
# The class is now built LAZILY via `_ml_plan_signature_cls()` and exposed at
# module scope through `__getattr__` (PEP 562) — mirroring
# `kailash/workflow/from_brief.py::_signature_cls`.

_ML_PLAN_SIGNATURE_CLS_CACHE: Optional[type] = None


def _ml_plan_signature_cls() -> type:
    """Return the :class:`MLPlanSignature` class, constructed lazily.

    Defers the ``kailash._from_brief.BriefPlanSignature`` +
    ``kaizen.signatures.OutputField`` imports to call time so importing this
    module — and thus ``import kailash_ml`` (which re-exports ``from_brief``) —
    does not require kaizen.

    Returns:
        The lazily-constructed :class:`MLPlanSignature` subclass, cached after
        first invocation.
    """
    global _ML_PLAN_SIGNATURE_CLS_CACHE
    if _ML_PLAN_SIGNATURE_CLS_CACHE is not None:
        return _ML_PLAN_SIGNATURE_CLS_CACHE

    from kailash._from_brief import BriefPlanSignature
    from kaizen.signatures import OutputField

    class MLPlanSignature(BriefPlanSignature):
        """Meta-Signature: parse a brief + dataframe schema into an ML plan.

        Per the architecture plan §3.5, this Signature is the LLM-mediation
        surface for :func:`kailash_ml.from_brief`. The realizer feeds the
        dataframe's structural metadata (column names + dtypes) into the
        Signature alongside the brief so the LLM can ground its column
        selections in real data.

        Per ``rules/agent-reasoning.md`` § "Permitted Deterministic Logic"
        exception 1 (input validation — presence/type), extracting
        ``df.dtypes`` + ``df.columns`` in Python BEFORE the LLM call is
        permitted structural plumbing — the LLM still does ALL reasoning
        about which columns to USE; the realizer only hands it the catalog.

        Plan-emitted fields:

        - ``feature_columns``: list of column-name strings the LLM selected
          as features. Validated against ``df.columns`` before realization;
          unknown columns raise
          :class:`BriefInterpretationError(unknown_value=<name>)`.
        - ``target_column``: column-name string the LLM identified as the
          supervised-learning target. Validated against ``df.columns``.
        - ``model_task``: task identifier from :data:`ALLOWED_TASKS`. The
          LLM is instructed to pick the task that matches the brief's
          stated prediction goal (AC 5).
        - ``eval_metric``: metric identifier from
          :data:`ALLOWED_EVAL_METRICS`. The LLM picks ONE primary metric;
          the realizer expands to a sensible default list per task.
        - ``schema_name``: identifier-safe name for the resulting
          :class:`FeatureSchema`. Per the FeatureSchema name regex
          (``^[a-zA-Z_][a-zA-Z0-9_]*$``), the realizer rejects malformed
          names.

        See :class:`BriefPlanSignature` for the inherited ``brief`` +
        ``interpretation_confidence`` floor contract.
        """

        # FIELD NAMING NOTE: the OutputField names below do not collide
        # with reserved property names on the Signature base class. The
        # pyright suppressions cite the same pattern as the S1 base — see
        # ``src/kailash/_from_brief/signatures.py:110-138`` for the full
        # rationale + #73 citation.
        dataframe_schema: dict = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "ECHO BACK the dataframe schema you were given. This "
                "is a structural verification field — copy the input "
                "dataframe_schema dict verbatim. The realizer uses "
                "this to detect LLM dropouts where the model ignored "
                "the data context."
            )
        )
        feature_columns: list = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "List of column-name strings to use as model features. "
                "Each entry MUST be a column name from the input dataframe "
                "(see dataframe_schema). Do NOT invent column names — only "
                "select from what the dataframe actually contains. Pick "
                "the columns the brief implies are predictive of the "
                "target; exclude identifier columns (e.g. 'id', 'uuid') "
                "and the target column itself."
            )
        )
        target_column: str = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "The single column name that represents the supervised-"
                "learning target the brief asks to predict. MUST be a "
                "column from the input dataframe. For a brief like "
                "'predict churn from customer behavior', the target column "
                "is typically named 'churn', 'churned', 'is_active', or "
                "similar — pick the one that exists in the dataframe."
            )
        )
        model_task: str = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "The supervised-learning task type. MUST be one of: "
                "'classification', 'binary_classification', "
                "'multiclass_classification', 'multilabel_classification', "
                "'regression'. Pick the task that matches the brief's "
                "stated prediction goal: 'predict X' where X is "
                "categorical → classification; 'predict X' where X is "
                "numeric → regression. If the target column has exactly "
                "two distinct values, prefer 'binary_classification'."
            )
        )
        eval_metric: str = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "Primary evaluation metric. MUST be one of: 'accuracy', "
                "'f1', 'precision', 'recall', 'auc' (classification) or "
                "'mse', 'rmse', 'mae', 'r2' (regression). Pick the metric "
                "that best reflects the brief's success criterion. Default "
                "to 'accuracy' for classification, 'rmse' for regression "
                "when the brief is silent."
            )
        )
        schema_name: str = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "A snake_case identifier for the resulting FeatureSchema "
                "(e.g. 'customer_churn', 'house_prices'). MUST match the "
                "regex ^[a-zA-Z_][a-zA-Z0-9_]*$ — letters, digits, "
                "underscores, starting with a letter or underscore. Pick a "
                "name that reflects the brief's domain; the name appears "
                "in registry rows and error messages."
            )
        )

    _ML_PLAN_SIGNATURE_CLS_CACHE = MLPlanSignature
    return MLPlanSignature


def __getattr__(name: str) -> Any:
    """PEP 562 module-level ``__getattr__`` for lazy class resolution.

    Per ``rules/orphan-detection.md`` § 6b, lazy-loaded symbols MUST stay
    discoverable through the module's public surface. This hook resolves
    ``from kailash_ml.from_brief import MLPlanSignature`` at call-time (the
    symbol is in ``__all__``, has a lazy resolver, and has a ``TYPE_CHECKING``
    stub below).
    """
    if name == "MLPlanSignature":
        return _ml_plan_signature_cls()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    # Surface the lazy class to static analyzers (CodeQL py/undefined-export,
    # pyright, mypy) per `rules/orphan-detection.md` § 6b. Runtime body lives
    # inside `_ml_plan_signature_cls`.
    class MLPlanSignature:  # type: ignore[no-redef]
        """Static-analyzer stub; runtime body in :func:`_ml_plan_signature_cls`."""

        dataframe_schema: dict
        feature_columns: list
        target_column: str
        model_task: str
        eval_metric: str
        schema_name: str


# =========================================================================
# Pydantic plan (for typed validation between Signature and realizer)
# =========================================================================


class MLPlan(_BasePlan):
    """Typed plan model for ``kailash_ml.from_brief()`` outputs.

    Pydantic v2 model that mirrors :class:`MLPlanSignature`'s
    OutputFields. The S1 :func:`coerce_plan` helper converts the LLM's
    raw dict output into an instance of this model, raising
    :class:`BriefInterpretationError(malformed=True)` on schema
    violations.

    The ``field_types`` property is intentionally empty — this plan
    does NOT carry a field-type allowlist gate (the dataframe schema
    is the structural constraint, validated separately against
    ``df.columns``). Allowlist validation for tasks/metrics runs via
    explicit checks in the realizer.
    """

    dataframe_schema: Dict[str, Any]
    feature_columns: List[str]
    target_column: str
    model_task: str
    eval_metric: str
    schema_name: str


# =========================================================================
# Validation helpers (deterministic structural plumbing per
# rules/agent-reasoning.md § Permitted Deterministic Logic — items 1, 6)
# =========================================================================


def _polars_dtype_to_feature_dtype(pl_dtype: pl.DataType) -> str:
    """Normalize a polars dtype into a FeatureField-compatible string.

    FeatureField.dtype uses a small allowlist (see
    :data:`kailash_ml.features.schema.ALLOWED_DTYPES`). Polars dtypes
    map cleanly to that allowlist; the unmapped fallback is ``"utf8"``
    so an exotic dtype (e.g. Struct, List) still produces a valid
    FeatureField rather than raising. Realizer callers needing strict
    dtype preservation use :meth:`FeatureSchema.with_features` to
    refine after construction.
    """
    # polars dtype objects have stable string reprs — use them as the
    # mapping key. The mapping below is exhaustive over polars's
    # numeric + text + temporal dtype set.
    name = str(pl_dtype).lower()
    if name.startswith("float"):
        # float32 / float64
        return "float64" if "64" in name else "float32"
    if name.startswith(("int", "uint")):
        # int8/16/32/64, uint8/16/32/64
        for width in ("64", "32", "16", "8"):
            if width in name:
                return ("int" if name.startswith("int") else "uint") + width
        return "int64"
    if name in ("utf8", "string", "str"):
        return "utf8"
    if name == "boolean" or name == "bool":
        return "bool"
    if name == "date":
        return "date"
    if name.startswith("datetime"):
        return "datetime"
    if name == "time":
        return "time"
    if name == "duration":
        return "duration"
    if name == "binary":
        return "binary"
    if name == "categorical":
        return "categorical"
    # Unknown polars dtype — fall back to utf8 (safest at the
    # FeatureField allowlist boundary). The realizer surfaces this in
    # the FeatureField description so callers can spot the fallback.
    return "utf8"


def _validate_columns_subset(
    selected: List[str],
    df_columns: List[str],
    *,
    field_name: str,
) -> None:
    """Raise BriefInterpretationError if any selected column is not in df.

    Per AC 5 invariant 4: every LLM-emitted feature column AND target
    column MUST be a member of ``df.columns``. The check is mechanical
    — set membership — and the failure is loud with the offending name
    in ``unknown_value`` so callers can branch on the discriminator
    without parsing the message.
    """
    df_set = set(df_columns)
    for name in selected:
        if not isinstance(name, str):
            raise BriefInterpretationError(
                f"{field_name}[?]={name!r} is not a string; the LLM "
                f"emitted a malformed plan entry",
                malformed=True,
            )
        if name not in df_set:
            raise BriefInterpretationError(
                f"{field_name} entry {name!r} is not a column in the "
                f"provided dataframe (have: {sorted(df_set)!r}); the LLM "
                f"hallucinated a column name not present in the data",
                unknown_value=name,
            )


def _validate_task(task: str) -> None:
    """Raise BriefInterpretationError if task is not in :data:`ALLOWED_TASKS`."""
    if not isinstance(task, str) or task not in ALLOWED_TASKS:
        raise BriefInterpretationError(
            f"model_task={task!r} is not in the closed allowlist "
            f"(allowed: {sorted(ALLOWED_TASKS)!r}); the LLM emitted a "
            f"task identifier the realizer cannot map to a model class",
            unknown_value=task if isinstance(task, str) else None,
        )


def _validate_eval_metric(metric: str) -> None:
    """Raise BriefInterpretationError if metric is not in :data:`ALLOWED_EVAL_METRICS`."""
    if not isinstance(metric, str) or metric not in ALLOWED_EVAL_METRICS:
        raise BriefInterpretationError(
            f"eval_metric={metric!r} is not in the closed allowlist "
            f"(allowed: {sorted(ALLOWED_EVAL_METRICS)!r}); the LLM "
            f"emitted a metric identifier the EvalSpec cannot compute",
            unknown_value=metric if isinstance(metric, str) else None,
        )


# =========================================================================
# Realizer (deterministic dataclass construction)
# =========================================================================


def _realize_triple(
    plan: MLPlan, df: pl.DataFrame
) -> Tuple[FeatureSchema, ModelSpec, EvalSpec]:
    """Materialize the validated plan into (FeatureSchema, ModelSpec, EvalSpec).

    Per the architecture plan §3.5 + AC 5, the three dataclasses MUST
    be byte-identically constructible from the same plan + dataframe
    pair (deterministic for a given LLM output). The FeatureSchema is
    the frozen + content-addressed variant from
    ``kailash_ml.features.schema``.

    Args:
        plan: A validated :class:`MLPlan` whose feature_columns /
            target_column have already passed
            :func:`_validate_columns_subset`, task has passed
            :func:`_validate_task`, and metric has passed
            :func:`_validate_eval_metric`.
        df: The polars DataFrame; consulted ONLY to extract dtypes for
            each FeatureField. The data values are never read — the
            realizer is a structural plumbing step, not a statistical
            inference.

    Returns:
        ``(FeatureSchema, ModelSpec, EvalSpec)`` triple.
    """
    # Build FeatureField list in plan order. Each field carries the
    # polars-native dtype derived from the dataframe column.
    df_dtypes = dict(zip(df.columns, df.dtypes, strict=False))
    fields: List[FeatureField] = []
    for col_name in plan.feature_columns:
        pl_dtype = df_dtypes[col_name]
        dtype_str = _polars_dtype_to_feature_dtype(pl_dtype)
        fields.append(
            FeatureField(
                name=col_name,
                dtype=dtype_str,
                nullable=True,
                description=f"Feature column derived from dataframe (polars dtype: {pl_dtype!s})",
            )
        )

    # Construct the frozen + content-addressed FeatureSchema. The
    # entity_id_column defaults to "entity_id"; if the dataframe has
    # no such column, that is fine — entity_id is a registry-side
    # concept and the realized schema is consumed by TrainingPipeline,
    # not by a feature-store materialization here.
    schema = FeatureSchema(
        name=plan.schema_name,
        version=1,
        fields=tuple(fields),
    )

    # Construct the ModelSpec using the per-task default model_class.
    # The allowlist gate in `engines/_shared.py::validate_model_class`
    # runs at instantiation time, not construction; but DEFAULT_MODEL_CLASS_BY_TASK
    # is hand-authored to satisfy the allowlist so construction is safe.
    model_class = DEFAULT_MODEL_CLASS_BY_TASK[plan.model_task]
    framework = "sklearn" if model_class.startswith("sklearn.") else "lightgbm"
    model_spec = ModelSpec(
        model_class=model_class,
        hyperparameters={},
        framework=framework,
    )

    # Construct the EvalSpec. The LLM's eval_metric is the primary
    # metric; we expand to a sensible per-task default list with the
    # LLM-chosen metric pinned first so a caller iterating metrics in
    # order sees the brief-derived choice first.
    default_metrics = list(_DEFAULT_METRICS_BY_TASK[plan.model_task])
    if plan.eval_metric in default_metrics:
        default_metrics.remove(plan.eval_metric)
    metrics = [plan.eval_metric, *default_metrics]
    eval_spec = EvalSpec(metrics=metrics)

    return schema, model_spec, eval_spec


# =========================================================================
# Public entry point — module-level function (NOT a classmethod)
# =========================================================================


def from_brief(
    brief: str,
    df: pl.DataFrame,
    *,
    model: Optional[str] = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> Tuple[FeatureSchema, ModelSpec, EvalSpec]:
    """Realize a ``(FeatureSchema, ModelSpec, EvalSpec)`` triple from a brief.

    Closes issue #1125 acceptance criterion 5. The result is a tuple of
    three independent dataclasses ready for
    :class:`kailash_ml.TrainingPipeline` or ``km.train`` consumption.

    Pipeline (composes :mod:`kailash._from_brief`):

    1. Extract ``df.dtypes`` + ``df.columns`` (permitted deterministic
       structural plumbing per ``rules/agent-reasoning.md`` §
       "Permitted Deterministic Logic" item 1).
    2. :func:`scrub_brief` masks credentials BEFORE logging or LLM call.
    3. :class:`MLPlanSignature` emits a typed plan (feature columns,
       target column, task type, eval metric, schema name, confidence).
    4. :func:`coerce_plan` + :func:`validate_plan` enforce the
       structural + confidence gates.
    5. :func:`_validate_columns_subset` enforces feature_columns ∪
       {target_column} ⊆ df.columns (AC 5 invariant).
    6. :func:`_validate_task` + :func:`_validate_eval_metric` enforce
       the closed allowlist gates.
    7. :func:`_realize_triple` constructs the three dataclasses.

    Args:
        brief: The user's natural-language description of the ML task.
            Credentials are scrubbed at intake; the raw brief is never
            logged.
        df: The polars DataFrame whose schema grounds the LLM's column
            selections. Values are NOT consumed; only ``df.columns``
            and ``df.dtypes`` are read. Pass an empty DataFrame if you
            want pure-schema realization (the LLM still needs the
            column catalog).
        model: Optional LLM model identifier. Defaults to the value of
            ``DEFAULT_LLM_MODEL`` in the environment (per
            ``rules/env-models.md``); raises
            :class:`MissingDefaultLLMModelError` when neither is set.
        confidence_threshold: Minimum interpretation confidence
            required to realize the plan (default 0.6).

    Returns:
        A ``(FeatureSchema, ModelSpec, EvalSpec)`` triple. The
        FeatureSchema is the FROZEN + content-addressed variant from
        ``kailash_ml.features.schema``; refinement uses
        :meth:`FeatureSchema.with_features` to derive a new
        content-hashed schema.

    Raises:
        BriefInterpretationError: When the LLM's plan fails the
            confidence gate, the column-subset gate, the task allowlist
            gate, or the metric allowlist gate.
        MissingDefaultLLMModelError: When ``model`` is None AND
            ``DEFAULT_LLM_MODEL`` is unset.
        TypeError: When ``df`` is not a polars DataFrame.

    Example:
        >>> import polars as pl
        >>> import kailash_ml
        >>> df = pl.DataFrame({
        ...     "age": [25, 47, 33],
        ...     "tenure_months": [12, 60, 24],
        ...     "churned": [0, 1, 0],
        ... })
        >>> schema, model_spec, eval_spec = kailash_ml.from_brief(
        ...     "Predict customer churn from age and tenure.", df
        ... )
        >>> schema.field_names  # doctest: +SKIP
        ['age', 'tenure_months']
        >>> model_spec.framework  # doctest: +SKIP
        'sklearn'
    """
    # Input validation FIRST (permitted per agent-reasoning.md item 1 —
    # presence/type checks, NOT content classification). These deterministic
    # guards use ONLY polars (imported at module scope, line 95) + the
    # kaizen-free `kailash._from_brief` exceptions, so a bad-input rejection
    # MUST fire BEFORE the lazy kaizen imports below. In a kaizen-absent env
    # (the Base CI matrix runs the kailash-ml unit suite without kaizen),
    # the Tier-1 rejection tests pass deliberately-bad input and assert the
    # validation error (TypeError / ValueError) — hoisting these guards above
    # the kaizen import ensures they raise the expected error, NOT a
    # ModuleNotFoundError. Per `rules/zero-tolerance.md` Rule 3, the rejection
    # is a loud, explicit error that fires without requiring kaizen.
    if not isinstance(df, pl.DataFrame):
        raise TypeError(
            f"df must be a polars.DataFrame, got {type(df).__name__}; "
            f"convert from pandas via `pl.from_pandas(df)` if needed"
        )
    if not df.columns:
        raise ValueError(
            "df has no columns; the LLM cannot select feature columns "
            "from an empty schema. Pass a DataFrame whose columns "
            "match the brief's described data"
        )

    # Lazy kaizen imports — deferred to call time (AND below the deterministic
    # input guards above) so importing this module (and thus `import
    # kailash_ml`, which re-exports `from_brief`) does not require kaizen, AND
    # so a bad-input caller gets the typed rejection rather than a kaizen
    # ModuleNotFoundError. A caller passing VALID input IS in an execution
    # path where kaizen is present. `get_default_llm_model` lives in
    # `kailash._from_brief.signatures` which imports kaizen at module scope,
    # so it is lazy too.
    from kailash._from_brief import get_default_llm_model
    from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

    # Step 1 — extract dataframe schema BEFORE the LLM call. This is
    # the structural plumbing the LLM uses to ground its column
    # selections. The dict is small (column → dtype string) so passing
    # it through the Signature is cheap.
    dataframe_schema: Dict[str, str] = {
        col: str(dtype) for col, dtype in zip(df.columns, df.dtypes, strict=False)
    }
    df_columns = list(df.columns)

    # Step 2 — credential scrub. The brief may embed credentials in
    # docstring-style examples ("connect to postgres://admin:hunter2@...");
    # the scrubber masks them before any logging or LLM call surface
    # sees the raw bytes.
    scrubbed = scrub_brief(brief)

    # Step 3 — LLM model resolution. Resolve ONCE before agent
    # construction so the error path surfaces a typed missing-env
    # failure rather than a deep RuntimeError inside BaseAgent.
    resolved_model = model if model is not None else get_default_llm_model()

    logger.debug(
        "kailash_ml.from_brief: invoking LLM (model=%s, brief_len=%d, df_cols=%d)",
        resolved_model,
        len(scrubbed),
        len(df_columns),
    )

    # Step 4 — invoke the meta-Signature via BaseAgent. The Signature
    # is the LLM-mediation surface; the agent dispatches a single
    # one-shot inference (no tool-use loop required for schema
    # synthesis from prose).
    agent_config = BaseAgentConfig(
        model=resolved_model,
        strategy_type="single_shot",
    )
    agent = BaseAgent(
        config=agent_config,
        signature=_ml_plan_signature_cls()(),
        mcp_servers=[],
    )
    # The Signature consumes `brief` (inherited InputField) AND
    # `dataframe_schema` (which we surface as a virtual input via the
    # signature's prompt context). Kaizen's BaseAgent.run() accepts
    # arbitrary kwargs corresponding to the Signature's input fields;
    # we pass dataframe_schema as a serializable dict so the LLM sees
    # the catalog inline.
    raw_output = agent.run(brief=scrubbed, dataframe_schema=dataframe_schema)

    # Step 5 — typed plan coercion. Translates Pydantic ValidationError
    # into BriefInterpretationError(malformed=True).
    raw_plan: Dict[str, Any] = {
        "interpretation_confidence": raw_output.get("interpretation_confidence"),
        "dataframe_schema": raw_output.get("dataframe_schema", {}),
        "feature_columns": raw_output.get("feature_columns", []),
        "target_column": raw_output.get("target_column", ""),
        "model_task": raw_output.get("model_task", ""),
        "eval_metric": raw_output.get("eval_metric", ""),
        "schema_name": raw_output.get("schema_name", ""),
    }
    plan = cast(MLPlan, coerce_plan(raw_plan, MLPlan))

    # Step 6 — confidence gate + structural validation. validate_plan
    # raises BriefInterpretationError(low_confidence=True) when the
    # LLM's interpretation_confidence is below threshold.
    validate_plan(plan, confidence_threshold=confidence_threshold)

    # Step 7 — column-subset gate (AC 5 invariant: feature_columns ∪
    # {target_column} ⊆ df.columns).
    _validate_columns_subset(
        plan.feature_columns, df_columns, field_name="feature_columns"
    )
    _validate_columns_subset(
        [plan.target_column], df_columns, field_name="target_column"
    )
    # Defensive: target_column MUST NOT also appear in feature_columns
    # (data leakage; the model would trivially achieve perfect score).
    if plan.target_column in plan.feature_columns:
        raise BriefInterpretationError(
            f"target_column={plan.target_column!r} also appears in "
            f"feature_columns; this would cause data leakage at training "
            f"time. The LLM emitted a self-referential plan",
            malformed=True,
        )

    # Step 8 — task + metric allowlist gates.
    _validate_task(plan.model_task)
    _validate_eval_metric(plan.eval_metric)

    # Step 9 — realize the typed dataclasses.
    return _realize_triple(plan, df)
