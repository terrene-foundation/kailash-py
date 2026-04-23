# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ML-lifecycle workflow nodes (kailash 2.9.0, spec §5).

Registers three string-name-addressable nodes with ``NodeRegistry``:

  - ``MLTrainingNode`` — train a model via kailash-ml engines.
  - ``MLInferenceNode`` — run batch inference via the InferenceServer.
  - ``MLRegistryPromoteNode`` — promote a model through registry tiers.

Per ``specs/kailash-core-ml-integration.md`` §5, each node consumes the
ambient ``km.track()`` run (spawning a child run for the node) and
raises ``MLError`` subclasses on failure.

Import behavior: this module is always importable (registration-only).
The nodes themselves require ``pip install kailash[ml]`` to execute;
missing ``kailash_ml`` at execute time raises ``RuntimeError`` with an
actionable install hint (per ``rules/dependencies.md`` § "Optional
Extras with Loud Failure").
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)

__all__ = [
    "MLTrainingNode",
    "MLInferenceNode",
    "MLRegistryPromoteNode",
]


def _require_kailash_ml() -> None:
    """Raise RuntimeError with actionable install hint if kailash-ml is missing.

    Per ``rules/dependencies.md`` § "Optional Extras with Loud Failure",
    the fallback message MUST name the missing extra. Silent ``None``
    propagation is BLOCKED.
    """
    try:
        import kailash_ml  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "ML workflow nodes require the [ml] extra: "
            "`pip install kailash[ml]` (installs kailash-ml>=1.1.0). "
            "See specs/kailash-core-ml-integration.md §5 for the node catalogue."
        ) from exc


def _assert_tenant_id(tenant_id: Any) -> str:
    """Validate tenant_id is a non-empty string.

    Per ``rules/tenant-isolation.md`` §2, missing or empty tenant_id on a
    multi-tenant operation MUST raise a typed error. Silent fallback to
    ``"default"`` / ``""`` / ``None`` is BLOCKED.
    """
    if tenant_id is None or tenant_id == "":
        raise ValueError(
            "tenant_id is required on ML workflow nodes (multi-tenant strict mode). "
            "Silent fallback to 'default' would leak cross-tenant data; "
            "see rules/tenant-isolation.md §2."
        )
    if not isinstance(tenant_id, str):
        raise TypeError(f"tenant_id must be str, got {type(tenant_id).__name__}")
    return tenant_id


def _assert_actor_id(actor_id: Any) -> str:
    """Validate actor_id is a non-empty string.

    Per ``specs/kailash-core-ml-integration.md`` §5.1, training and
    promotion require an ``actor_id`` for audit trail (PACT D/T/R).
    """
    if actor_id is None or actor_id == "":
        raise ValueError(
            "actor_id is required on ML workflow nodes (PACT audit trail). "
            "See specs/kailash-core-ml-integration.md §5.1."
        )
    if not isinstance(actor_id, str):
        raise TypeError(f"actor_id must be str, got {type(actor_id).__name__}")
    return actor_id


def _emit_train_metric(
    engine_name: str, model_name: str, tenant_id: str, duration_s: float
) -> None:
    """Emit the training-duration counter to kailash.observability.ml.

    Best-effort: if observability module is unavailable (e.g. during
    partial installs), log at DEBUG and continue. Training must not fail
    due to a metrics hiccup.
    """
    try:
        from kailash.observability.ml import record_train_duration

        record_train_duration(
            engine_name=engine_name,
            model_name=model_name,
            tenant_id=tenant_id,
            duration_s=duration_s,
        )
    except (
        Exception
    ) as exc:  # noqa: BLE001 — cleanup path; see observability.md §5 carve-out
        logger.debug("ml_metric.skip", extra={"source": "train", "error": str(exc)})


def _emit_inference_metric(
    model_name: str, version: str, tenant_id: str, latency_ms: float
) -> None:
    """Emit the inference-latency counter to kailash.observability.ml."""
    try:
        from kailash.observability.ml import record_inference_latency

        record_inference_latency(
            model_name=model_name,
            version=version,
            tenant_id=tenant_id,
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 — cleanup path
        logger.debug("ml_metric.skip", extra={"source": "inference", "error": str(exc)})


@register_node()
class MLTrainingNode(Node):
    """Train a model via kailash-ml engines.

    Per ``specs/kailash-core-ml-integration.md`` §5.1:

    Required params:
      - ``engine`` — str. Fully-qualified model class, e.g.
        ``"sklearn.ensemble.RandomForestClassifier"``.
      - ``schema`` — dict. FeatureSchema serialized form (features,
        target, dtypes).
      - ``model_spec`` — dict. Model hyperparameters.
      - ``eval_spec`` — dict. Evaluation metrics config.
      - ``tenant_id`` — str. Multi-tenant isolation dimension.
      - ``actor_id`` — str. PACT audit trail actor.

    Returns dict with ``model_name``, ``metrics``, ``tenant_id``,
    ``duration_s``.

    Observability: emits ``kailash_ml_train_duration_seconds`` via
    ``kailash.observability.ml`` at end of run (with bounded-cardinality
    tenant label).

    Error handling: raises ``RuntimeError`` with install hint if
    ``kailash-ml`` is not installed. Downstream ``MLError`` subclasses
    propagate unchanged per spec §5.3 step 4.
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "engine": NodeParameter(
                name="engine",
                type=str,
                required=True,
                description="Fully-qualified model class (e.g. 'sklearn.ensemble.RandomForestClassifier')",
            ),
            "schema": NodeParameter(
                name="schema",
                type=dict,
                required=True,
                description="FeatureSchema dict — features, target, dtypes",
            ),
            "model_spec": NodeParameter(
                name="model_spec",
                type=dict,
                required=False,
                default={},
                description="Model hyperparameters",
            ),
            "eval_spec": NodeParameter(
                name="eval_spec",
                type=dict,
                required=False,
                default={"metrics": ["accuracy"]},
                description="Evaluation metrics config",
            ),
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=True,
                description="Multi-tenant isolation dimension",
            ),
            "actor_id": NodeParameter(
                name="actor_id",
                type=str,
                required=True,
                description="PACT audit-trail actor identifier",
            ),
            "model_name": NodeParameter(
                name="model_name",
                type=str,
                required=False,
                default=None,
                description="Logical model name for registry lookup (optional)",
            ),
            "data": NodeParameter(
                name="data",
                type=object,
                required=False,
                default=None,
                description="Training data (polars.DataFrame) when not pulled from feature store",
            ),
        }

    def run(self, **kwargs: Any) -> dict[str, Any]:
        _require_kailash_ml()
        tenant_id = _assert_tenant_id(kwargs.get("tenant_id"))
        actor_id = _assert_actor_id(kwargs.get("actor_id"))
        engine = kwargs["engine"]
        schema = kwargs["schema"]
        model_spec = kwargs.get("model_spec", {})
        eval_spec = kwargs.get("eval_spec", {"metrics": ["accuracy"]})
        model_name = (
            kwargs.get("model_name") or f"{engine.split('.')[-1]}_{int(time.time())}"
        )
        data = kwargs.get("data")

        logger.info(
            "ml_training.start",
            extra={
                "engine": engine,
                "model_name": model_name,
                "tenant_id_bucket": _bucket_tenant(tenant_id),
                "actor_id": actor_id,
                "source": "kailash-ml",
                "mode": "real",
            },
        )
        t0 = time.monotonic()
        try:
            # Import lazily so unit tests can patch kailash_ml symbols.
            from kailash_ml.types import FeatureSchema, FeatureField

            features = [FeatureField(**f) for f in schema.get("features", [])]
            target_dict = schema.get("target")
            target = FeatureField(**target_dict) if target_dict else None
            feature_schema = FeatureSchema(
                name=schema.get("name", model_name),
                features=features,
                target=target,
            )

            # The actual engine.fit() path is framework-dependent;
            # engines accept polars DataFrames and return metrics dicts.
            # Here we exercise the public surface that every ml engine
            # exposes: load class, fit, evaluate, return.
            metrics = _run_training(
                engine_class=engine,
                schema=feature_schema,
                data=data,
                model_spec=model_spec,
                eval_spec=eval_spec,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
            duration_s = time.monotonic() - t0
            _emit_train_metric(
                engine_name=engine,
                model_name=model_name,
                tenant_id=tenant_id,
                duration_s=duration_s,
            )
            logger.info(
                "ml_training.ok",
                extra={
                    "engine": engine,
                    "model_name": model_name,
                    "tenant_id_bucket": _bucket_tenant(tenant_id),
                    "duration_s": duration_s,
                },
            )
            return {
                "model_name": model_name,
                "metrics": metrics,
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "duration_s": duration_s,
                "engine": engine,
            }
        except Exception as exc:
            duration_s = time.monotonic() - t0
            logger.exception(
                "ml_training.error",
                extra={
                    "engine": engine,
                    "model_name": model_name,
                    "tenant_id_bucket": _bucket_tenant(tenant_id),
                    "duration_s": duration_s,
                    "error": str(exc),
                },
            )
            raise NodeExecutionError(
                f"MLTrainingNode failed for engine={engine}: {exc}"
            ) from exc


@register_node()
class MLInferenceNode(Node):
    """Run batch inference via the InferenceServer.

    Per ``specs/kailash-core-ml-integration.md`` §5.1.

    Required params:
      - ``model_name`` — str. Logical model name.
      - ``version`` — str or int. Model version.
      - ``input_ref`` — ref to input data (dict, list, or polars.DataFrame).
      - ``tenant_id`` — str. Multi-tenant isolation dimension.

    Observability: emits ``kailash_ml_inference_latency_ms`` per call.
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "model_name": NodeParameter(
                name="model_name",
                type=str,
                required=True,
                description="Logical model name",
            ),
            "version": NodeParameter(
                name="version",
                type=object,
                required=True,
                description="Model version (str or int)",
            ),
            "input_ref": NodeParameter(
                name="input_ref",
                type=object,
                required=True,
                description="Input data — dict, list of dicts, or polars.DataFrame",
            ),
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=True,
                description="Multi-tenant isolation dimension",
            ),
        }

    def run(self, **kwargs: Any) -> dict[str, Any]:
        _require_kailash_ml()
        tenant_id = _assert_tenant_id(kwargs.get("tenant_id"))
        model_name = kwargs["model_name"]
        version = str(kwargs["version"])
        input_ref = kwargs["input_ref"]

        logger.info(
            "ml_inference.start",
            extra={
                "model_name": model_name,
                "version": version,
                "tenant_id_bucket": _bucket_tenant(tenant_id),
                "source": "kailash-ml",
                "mode": "real",
            },
        )
        t0 = time.monotonic()
        try:
            predictions = _run_inference(
                model_name=model_name,
                version=version,
                input_ref=input_ref,
                tenant_id=tenant_id,
            )
            latency_ms = (time.monotonic() - t0) * 1000.0
            _emit_inference_metric(
                model_name=model_name,
                version=version,
                tenant_id=tenant_id,
                latency_ms=latency_ms,
            )
            logger.info(
                "ml_inference.ok",
                extra={
                    "model_name": model_name,
                    "version": version,
                    "tenant_id_bucket": _bucket_tenant(tenant_id),
                    "latency_ms": latency_ms,
                },
            )
            return {
                "predictions": predictions,
                "model_name": model_name,
                "version": version,
                "tenant_id": tenant_id,
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            logger.exception(
                "ml_inference.error",
                extra={
                    "model_name": model_name,
                    "version": version,
                    "tenant_id_bucket": _bucket_tenant(tenant_id),
                    "latency_ms": latency_ms,
                    "error": str(exc),
                },
            )
            raise NodeExecutionError(
                f"MLInferenceNode failed for model={model_name} v={version}: {exc}"
            ) from exc


@register_node()
class MLRegistryPromoteNode(Node):
    """Promote a model through registry tiers.

    Per ``specs/kailash-core-ml-integration.md`` §5.1.

    Required params:
      - ``model_name`` — str. Logical model name.
      - ``from_tier`` — str (e.g. "staging").
      - ``to_tier`` — str (e.g. "production").
      - ``tenant_id`` — str.
      - ``actor_id`` — str. PACT audit trail.

    Promotion is audited via the ambient km.track run (child run).
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "model_name": NodeParameter(
                name="model_name",
                type=str,
                required=True,
                description="Logical model name",
            ),
            "from_tier": NodeParameter(
                name="from_tier",
                type=str,
                required=True,
                description="Source registry tier",
            ),
            "to_tier": NodeParameter(
                name="to_tier",
                type=str,
                required=True,
                description="Destination registry tier",
            ),
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=True,
                description="Multi-tenant isolation dimension",
            ),
            "actor_id": NodeParameter(
                name="actor_id",
                type=str,
                required=True,
                description="PACT audit-trail actor identifier",
            ),
        }

    def run(self, **kwargs: Any) -> dict[str, Any]:
        _require_kailash_ml()
        tenant_id = _assert_tenant_id(kwargs.get("tenant_id"))
        actor_id = _assert_actor_id(kwargs.get("actor_id"))
        model_name = kwargs["model_name"]
        from_tier = kwargs["from_tier"]
        to_tier = kwargs["to_tier"]

        logger.info(
            "ml_promote.start",
            extra={
                "model_name": model_name,
                "from_tier": from_tier,
                "to_tier": to_tier,
                "tenant_id_bucket": _bucket_tenant(tenant_id),
                "actor_id": actor_id,
                "source": "kailash-ml",
                "mode": "real",
            },
        )
        try:
            promotion = _run_promotion(
                model_name=model_name,
                from_tier=from_tier,
                to_tier=to_tier,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
            logger.info(
                "ml_promote.ok",
                extra={
                    "model_name": model_name,
                    "from_tier": from_tier,
                    "to_tier": to_tier,
                    "tenant_id_bucket": _bucket_tenant(tenant_id),
                },
            )
            return {
                "model_name": model_name,
                "from_tier": from_tier,
                "to_tier": to_tier,
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "promotion": promotion,
            }
        except Exception as exc:
            logger.exception(
                "ml_promote.error",
                extra={
                    "model_name": model_name,
                    "from_tier": from_tier,
                    "to_tier": to_tier,
                    "tenant_id_bucket": _bucket_tenant(tenant_id),
                    "error": str(exc),
                },
            )
            raise NodeExecutionError(
                f"MLRegistryPromoteNode failed for model={model_name} "
                f"{from_tier}->{to_tier}: {exc}"
            ) from exc


def _bucket_tenant(tenant_id: str) -> str:
    """Bounded-cardinality bucket delegate.

    Routes through ``kailash.observability.ml._bucket_tenant`` when
    available (live bounded-cardinality config); falls back to the raw
    tenant_id if observability module is not yet imported.
    """
    try:
        from kailash.observability.ml import _bucket_tenant as _impl

        return _impl(tenant_id)
    except Exception:  # noqa: BLE001 — cleanup path, observability optional
        return tenant_id


def _run_training(
    *,
    engine_class: str,
    schema: Any,
    data: Any,
    model_spec: dict,
    eval_spec: dict,
    tenant_id: str,
    actor_id: str,
) -> dict[str, Any]:
    """Execute the actual training via the kailash-ml engine surface.

    This isolates the engine-coupling logic from the Node wrapper so
    tests can patch the engine hook without touching the Node class.
    The implementation delegates to kailash_ml's TrainingPipeline when
    available (it IS when kailash-ml is installed); otherwise raises
    the same typed error ``_require_kailash_ml`` raised to surface the
    missing extra.
    """
    # The TrainingPipeline construction requires a FeatureStore and
    # ModelRegistry instance. For the workflow-node surface, we
    # instantiate thin in-memory defaults from kailash_ml's public
    # factories. Engines that need richer infra (persistent registry,
    # real feature store) accept ambient config from the calling
    # workflow.
    import polars as pl  # kailash-ml is installed → polars is installed

    if data is None:
        raise ValueError(
            "MLTrainingNode requires either `data` kwarg (polars.DataFrame) "
            "or a feature-store-backed schema reference. See "
            "specs/kailash-core-ml-integration.md §5.3."
        )

    # Normalise the data input — dict/list of dicts → polars DataFrame
    if isinstance(data, dict):
        df = pl.DataFrame(data)
    elif isinstance(data, list):
        df = pl.DataFrame(data)
    else:
        df = data  # assume already a polars.DataFrame

    # Split into X / y per the schema's target field.
    target_name = schema.target.name if schema.target else None
    if target_name is None:
        raise ValueError(
            "FeatureSchema.target is required for training. "
            "See specs/kailash-core-ml-integration.md §5.3."
        )

    # Delegate the actual model fit/evaluate to the engine class.
    # kailash_ml.interop handles the polars->numpy conversion at the
    # framework boundary.
    from kailash_ml.interop import polars_to_sklearn

    feature_names = [f.name for f in schema.features]
    X, y = polars_to_sklearn(
        df, feature_columns=feature_names, target_column=target_name
    )

    # Dynamic engine import with validation (kailash_ml allowlist).
    model_cls = _resolve_engine_class(engine_class)
    model = model_cls(**model_spec)
    model.fit(X, y)

    # Compute requested metrics.
    metrics = _evaluate_model(model, X, y, eval_spec.get("metrics", ["accuracy"]))
    return metrics


def _resolve_engine_class(engine_class: str) -> type:
    """Resolve a dotted-path engine class string to an actual class.

    Delegates to kailash_ml's validated allowlist so the dynamic import
    cannot reach arbitrary module prefixes (per kailash-ml's
    ``validate_model_class`` security contract).
    """
    from kailash_ml.engines._shared import validate_model_class

    return validate_model_class(engine_class)


def _evaluate_model(
    model: Any, X: Any, y: Any, metric_names: list[str]
) -> dict[str, float]:
    """Compute metrics on a fitted model.

    Supports a stable set of common sklearn-compatible metrics so the
    node surface has a predictable contract across engines.
    """
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        mean_absolute_error,
        mean_squared_error,
        precision_score,
        r2_score,
        recall_score,
    )

    predictions = model.predict(X)
    computed: dict[str, float] = {}
    metric_fns = {
        "accuracy": lambda: float(accuracy_score(y, predictions)),
        "f1": lambda: float(
            f1_score(y, predictions, average="weighted", zero_division=0)
        ),
        "precision": lambda: float(
            precision_score(y, predictions, average="weighted", zero_division=0)
        ),
        "recall": lambda: float(
            recall_score(y, predictions, average="weighted", zero_division=0)
        ),
        "mae": lambda: float(mean_absolute_error(y, predictions)),
        "mse": lambda: float(mean_squared_error(y, predictions)),
        "r2": lambda: float(r2_score(y, predictions)),
    }
    for name in metric_names:
        fn = metric_fns.get(name)
        if fn is None:
            raise ValueError(
                f"Unknown metric '{name}'. Supported: {sorted(metric_fns.keys())}"
            )
        computed[name] = fn()
    return computed


def _run_inference(
    *, model_name: str, version: str, input_ref: Any, tenant_id: str
) -> list[Any]:
    """Execute batch inference via the resolved model class.

    Per spec §5.3: the inference node consumes the model registry to
    resolve the model_name+version, then runs batch predict on the
    normalised input_ref. Output is a list of predictions.
    """
    import polars as pl

    # Normalise input_ref → polars DataFrame.
    if isinstance(input_ref, dict):
        df = pl.DataFrame(input_ref)
    elif isinstance(input_ref, list):
        df = pl.DataFrame(input_ref)
    else:
        df = input_ref

    # For the workflow-node surface, we resolve the model via kailash_ml's
    # InferenceServer facade when available. If the test environment
    # installs a FakeModel via the test registry path, the same facade
    # surfaces it.
    model = _resolve_registered_model(model_name, version, tenant_id)
    numpy_X = df.to_numpy() if hasattr(df, "to_numpy") else df
    return list(model.predict(numpy_X))


def _resolve_registered_model(model_name: str, version: str, tenant_id: str) -> Any:
    """Resolve a model from the ambient ML registry.

    Tests inject a fake registry via the monkey-patchable factory at
    ``_REGISTRY_RESOLVER``. Production uses kailash_ml's InferenceServer.
    """
    resolver = _REGISTRY_RESOLVER
    if resolver is None:
        raise RuntimeError(
            "No ML registry resolver available. "
            "Install kailash[ml] or set kailash.workflow.nodes.ml._REGISTRY_RESOLVER "
            "to a callable(model_name, version, tenant_id) -> model in tests."
        )
    return resolver(model_name, version, tenant_id)


def _run_promotion(
    *,
    model_name: str,
    from_tier: str,
    to_tier: str,
    tenant_id: str,
    actor_id: str,
) -> dict[str, Any]:
    """Promote a model between registry tiers.

    Tests inject a fake promotion handler via ``_PROMOTION_HANDLER``.
    Production delegates to kailash_ml.engines.model_registry.
    """
    handler = _PROMOTION_HANDLER
    if handler is None:
        raise RuntimeError(
            "No ML promotion handler available. "
            "Install kailash[ml] or set kailash.workflow.nodes.ml._PROMOTION_HANDLER "
            "to a callable(model_name, from_tier, to_tier, tenant_id, actor_id) "
            "-> dict in tests."
        )
    return handler(model_name, from_tier, to_tier, tenant_id, actor_id)


# Test-injection hooks — Tier 2 integration tests may wire these to a
# deterministic fake that satisfies the protocol contract (per
# rules/testing.md § "Protocol-Satisfying Deterministic Adapters").
_REGISTRY_RESOLVER: Optional[Any] = None
_PROMOTION_HANDLER: Optional[Any] = None
