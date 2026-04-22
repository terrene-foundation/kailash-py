# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""scikit-learn autolog integration (W23.b).

Implements ``specs/ml-autolog.md §3.1`` row 2:

- Wraps :meth:`sklearn.base.BaseEstimator.fit` on every concrete
  subclass at class level — scoped to the ``km.autolog()`` block via
  the ABC's :meth:`detach` contract (§3.2). Global / persistent
  monkey-patching is BLOCKED per §1.3; the class-level patch restores
  in the CM's ``finally:`` even on exception.
- Captures ``estimator.get_params(deep=True)`` before fit (in case fit
  mutates them).
- On fit-exit (under async ``flush``), logs:
    * ``{cls}.score`` metric if the estimator supports ``.score`` on
      the fit-time ``X``/``y``.
    * Classifier figures (``{cls}.confusion_matrix`` +
      ``{cls}.classification_report``) for classifier subclasses.
    * Model artifact via ONNX (``skl2onnx`` — base dep of kailash-ml).
      Pickle fallback with ``onnx_status=legacy_pickle_only`` per
      Phase-B SAFE-DEFAULT A-02 when ONNX export raises.

Per ``rules/orphan-detection.md`` §1, this module's registration site
is ``kailash_ml/autolog/__init__.py`` which eagerly imports this
module — the :func:`register_integration` decorator fires at import
time. The production call site for the instantiated class is the
:func:`kailash_ml.autolog.autolog` context manager, which reads
:data:`_REGISTERED_INTEGRATIONS` during auto-detect (§4.1) and
explicit-name resolution (§4.2).

Framework imports (``sklearn.base``, ``skl2onnx``, ``matplotlib``) are
deferred to :meth:`attach` / :meth:`flush` so importing this module
does NOT pull sklearn into ``sys.modules``. The auto-detect path is
preserved for users who never ``import sklearn``.
"""
from __future__ import annotations

import functools
import logging
import pickle
import sys
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

from kailash_ml.autolog._registry import (
    FrameworkIntegration,
    register_integration,
)

if TYPE_CHECKING:
    from kailash_ml.autolog.config import AutologConfig
    from kailash_ml.tracking import ExperimentRun


__all__ = ["SklearnIntegration"]


logger = logging.getLogger(__name__)


def _iter_concrete_subclasses(cls: type) -> List[type]:
    """Recursive flat list of every subclass of ``cls`` currently
    imported.

    Ordered by BFS so the patch-discovery order is deterministic across
    runs — makes test reproducibility robust.
    """
    seen: Dict[type, None] = {}
    stack: List[type] = list(cls.__subclasses__())
    while stack:
        sub = stack.pop(0)
        if sub in seen:
            continue
        seen[sub] = None
        stack.extend(sub.__subclasses__())
    return list(seen.keys())


def _truncate_repr(value: Any, limit: int = 500) -> str:
    """Param values get stringified-then-truncated so the tracker's
    param table doesn't blow up on nested estimators (e.g. Pipelines
    with nested transformers).
    """
    rendered = repr(value)
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit] + "...[truncated]"


@register_integration
class SklearnIntegration(FrameworkIntegration):
    """Autolog for scikit-learn estimators.

    See module docstring for the full design. Attach walks
    :class:`sklearn.base.BaseEstimator` subclasses and patches each
    concrete ``fit`` method; detach restores them. Buffers post-fit
    closures in ``self._events`` during the block; drains in
    :meth:`flush` where ``await`` is valid.
    """

    name = "sklearn"

    def __init__(self) -> None:
        super().__init__()
        self._patched: Dict[type, Callable[..., Any]] = {}
        self._events: List[Callable[["ExperimentRun"], Awaitable[None]]] = []
        self._run: Optional["ExperimentRun"] = None
        self._config: Optional["AutologConfig"] = None

    @classmethod
    def is_available(cls) -> bool:
        # §4.1 — sys.modules check only; surprise-importing sklearn is
        # BLOCKED per the "zero overhead when unused" contract.
        return "sklearn" in sys.modules or "sklearn.base" in sys.modules

    def attach(self, run: "ExperimentRun", config: "AutologConfig") -> None:
        self._guard_double_attach()
        self._run = run
        self._config = config

        # Local import — only fires when the user has explicitly
        # chosen "sklearn" (§4.2) or is_available returned True.
        import sklearn.base  # noqa: PLC0415

        targets = _iter_concrete_subclasses(sklearn.base.BaseEstimator)
        for est_cls in targets:
            # Patch only classes that define their OWN `fit`; skip
            # classes that inherit fit from a parent we've already
            # patched (double-wrap would emit duplicate events).
            if "fit" not in est_cls.__dict__:
                continue
            original_fit = est_cls.__dict__["fit"]
            wrapped = self._make_fit_wrapper(original_fit)
            try:
                est_cls.fit = wrapped
            except (AttributeError, TypeError):
                # Read-only attribute (e.g. Cython class) — skip.
                # Missing coverage on that estimator is preferable to
                # an attach-level failure that prevents the CM entirely.
                logger.debug(
                    "autolog.sklearn.patch_skipped",
                    extra={"estimator_cls": est_cls.__name__},
                )
                continue
            self._patched[est_cls] = original_fit

        logger.info(
            "autolog.sklearn.attach",
            extra={
                "run_id": run.run_id,
                "patched_classes": len(self._patched),
            },
        )

    def detach(self) -> None:
        for est_cls, original_fit in self._patched.items():
            try:
                est_cls.fit = original_fit
            except (AttributeError, TypeError):
                # Mirror attach's tolerance — some classes can't have
                # attrs reassigned. Detach-failure is BLOCKED from
                # raising per §3.2 idempotency + rules/zero-tolerance
                # §3 "log-and-continue on cleanup where failure is
                # expected" carve-out.
                logger.exception(
                    "autolog.sklearn.unpatch_failed",
                    extra={"estimator_cls": est_cls.__name__},
                )
        self._patched.clear()
        self._events.clear()
        self._run = None
        self._config = None
        self._mark_detached()

    async def flush(self, run: "ExperimentRun") -> None:
        """Drain buffered post-fit events to the tracker.

        Per ``rules/zero-tolerance.md`` Rule 3, the first event failure
        is re-raised so the CM's finally block surfaces it via
        :class:`AutologDetachError`. Subsequent event failures are
        logged but don't shadow the first.
        """
        flush_errors: List[BaseException] = []
        for event in self._events:
            try:
                await event(run)
            except Exception as exc:  # noqa: BLE001
                flush_errors.append(exc)
                logger.exception("autolog.sklearn.event_failed")
        self._events.clear()
        if flush_errors:
            raise flush_errors[0]

    def _make_fit_wrapper(
        self,
        original_fit: Callable[..., Any],
    ) -> Callable[..., Any]:
        integ = self

        @functools.wraps(original_fit)
        def wrapped_fit(
            self_est: Any,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            # Capture params BEFORE fit in case fit mutates them
            # (GridSearchCV mutates best_estimator_, etc.).
            try:
                params = (
                    self_est.get_params(deep=True)
                    if hasattr(self_est, "get_params")
                    else {}
                )
            except Exception:
                params = {}
            result = original_fit(self_est, *args, **kwargs)

            # Extract X / y by the canonical sklearn positional order.
            x_in = args[0] if args else kwargs.get("X")
            y_in = args[1] if len(args) > 1 else kwargs.get("y")

            integ._events.append(
                integ._make_post_fit_event(self_est, params, x_in, y_in)
            )
            return result

        return wrapped_fit

    def _make_post_fit_event(
        self,
        estimator: Any,
        params: Dict[str, Any],
        X: Any,
        y: Any,
    ) -> Callable[["ExperimentRun"], Awaitable[None]]:
        cls_name = type(estimator).__name__
        log_models = self._config.log_models if self._config else True
        log_figures = self._config.log_figures if self._config else True

        async def event(run: "ExperimentRun") -> None:
            # Params — prefix with class name so multiple estimators
            # in the same run don't collide.
            if params:
                safe_params = {
                    f"{cls_name}.{k}": _truncate_repr(v) for k, v in params.items()
                }
                await run.log_params(safe_params)

            # Score metric.
            if X is not None and y is not None and hasattr(estimator, "score"):
                try:
                    score = float(estimator.score(X, y))
                    await run.log_metric(f"{cls_name}.score", score)
                except Exception:
                    logger.debug(
                        "autolog.sklearn.score_failed",
                        extra={"estimator_cls": cls_name},
                    )

            # best_score_ for GridSearchCV / RandomizedSearchCV per
            # §3.1 row 2.
            if hasattr(estimator, "best_score_"):
                try:
                    await run.log_metric(
                        f"{cls_name}.best_score_",
                        float(estimator.best_score_),
                    )
                except Exception:
                    logger.debug(
                        "autolog.sklearn.best_score_failed",
                        extra={"estimator_cls": cls_name},
                    )

            # Classifier figures.
            if log_figures and X is not None and y is not None:
                try:
                    from sklearn.base import is_classifier  # noqa: PLC0415

                    if is_classifier(estimator):
                        await _log_classifier_figures(run, estimator, X, y, cls_name)
                except Exception:
                    logger.exception(
                        "autolog.sklearn.classifier_figures_failed",
                        extra={"estimator_cls": cls_name},
                    )

            # Model artifact — ONNX first, pickle fallback (§3.1 row 2
            # + Phase-B A-02).
            if log_models:
                try:
                    await _log_estimator_artifact(run, estimator, X, cls_name)
                except Exception:
                    logger.exception(
                        "autolog.sklearn.log_artifact_failed",
                        extra={"estimator_cls": cls_name},
                    )

        return event


async def _log_classifier_figures(
    run: "ExperimentRun",
    estimator: Any,
    X: Any,
    y: Any,
    cls_name: str,
) -> None:
    """Emit confusion-matrix + classification-report figures.

    Uses plotly (base kailash-ml dep) via the tracker's §4.4
    ``log_figure`` plotly path. Matplotlib is NOT a kailash-ml
    dep, so using plotly avoids a new extras requirement.
    """
    import plotly.figure_factory as ff  # noqa: PLC0415
    import plotly.graph_objects as go  # noqa: PLC0415
    from sklearn.metrics import (  # noqa: PLC0415
        classification_report,
        confusion_matrix,
    )

    try:
        y_pred = estimator.predict(X)
    except Exception:
        logger.debug(
            "autolog.sklearn.predict_failed",
            extra={"estimator_cls": cls_name},
        )
        return

    # Confusion matrix — plotly annotated heatmap.
    try:
        cm = confusion_matrix(y, y_pred)
        cm_fig = ff.create_annotated_heatmap(
            z=cm.tolist(),
            colorscale="Blues",
            showscale=True,
        )
        cm_fig.update_layout(
            title_text=f"{cls_name} Confusion Matrix",
            xaxis_title="Predicted",
            yaxis_title="Actual",
        )
        await run.log_figure(cm_fig, f"{cls_name}.confusion_matrix")
    except Exception:
        logger.debug(
            "autolog.sklearn.confusion_matrix_failed",
            extra={"estimator_cls": cls_name},
        )

    # Classification report — plotly Table.
    try:
        report = classification_report(y, y_pred, output_dict=True, zero_division=0)
    except Exception:
        logger.debug(
            "autolog.sklearn.classification_report_failed",
            extra={"estimator_cls": cls_name},
        )
        return

    headers = ["label", "precision", "recall", "f1-score", "support"]
    rows: List[List[str]] = []
    for label, metrics in report.items():
        if isinstance(metrics, dict):
            rows.append(
                [
                    str(label),
                    f"{float(metrics.get('precision', 0.0)):.3f}",
                    f"{float(metrics.get('recall', 0.0)):.3f}",
                    f"{float(metrics.get('f1-score', 0.0)):.3f}",
                    f"{int(metrics.get('support', 0))}",
                ]
            )
        else:
            # Scalar rows (e.g. ``accuracy``) — report under f1-score.
            rows.append(
                [
                    str(label),
                    "",
                    "",
                    (
                        f"{float(metrics):.3f}"
                        if isinstance(metrics, (int, float))
                        else str(metrics)
                    ),
                    "",
                ]
            )
    columns = list(zip(*rows)) if rows else [[] for _ in headers]
    try:
        report_fig = go.Figure(
            data=[
                go.Table(
                    header={"values": headers, "fill_color": "paleturquoise"},
                    cells={"values": [list(c) for c in columns]},
                )
            ]
        )
        report_fig.update_layout(title_text=f"{cls_name} Classification Report")
        await run.log_figure(report_fig, f"{cls_name}.classification_report")
    except Exception:
        logger.debug(
            "autolog.sklearn.classification_report_figure_failed",
            extra={"estimator_cls": cls_name},
        )


async def _log_estimator_artifact(
    run: "ExperimentRun",
    estimator: Any,
    X: Any,
    cls_name: str,
) -> None:
    """Emit model artifact as ONNX; fall back to pickle on export failure.

    Per Phase-B SAFE-DEFAULT A-02 the fallback artifact name carries
    the ``legacy_pickle_only`` sentinel so a later audit can grep for
    runs whose models were not ONNX-exportable.
    """
    onnx_bytes = _try_onnx_export(estimator, X, cls_name)
    if onnx_bytes is not None:
        await run.log_artifact(
            onnx_bytes,
            f"{cls_name}.model.onnx",
            content_type="application/octet-stream",
        )
        return

    # Fallback — pickle with onnx_status sentinel.
    logger.warning(
        "autolog.sklearn.onnx_failed",
        extra={
            "estimator_cls": cls_name,
            "onnx_status": "legacy_pickle_only",
        },
    )
    try:
        blob = pickle.dumps(estimator)
    except Exception:
        logger.exception(
            "autolog.sklearn.pickle_failed",
            extra={"estimator_cls": cls_name},
        )
        return
    await run.log_artifact(
        blob,
        f"{cls_name}.model.pickle.legacy_pickle_only",
        content_type="application/x-pickle",
    )


def _try_onnx_export(
    estimator: Any,
    X: Any,
    cls_name: str,
) -> Optional[bytes]:
    """Attempt ONNX export via ``skl2onnx`` (base dep of kailash-ml).

    Returns serialized bytes on success, ``None`` on any export
    failure — the caller then falls back to pickle.
    """
    try:
        from skl2onnx import convert_sklearn  # noqa: PLC0415
        from skl2onnx.common.data_types import FloatTensorType  # noqa: PLC0415
    except ImportError:
        # Should not happen on kailash-ml (skl2onnx is a base dep) but
        # defend against installs that pruned the extra.
        return None

    try:
        import numpy as np  # noqa: PLC0415

        arr = np.asarray(X)
        n_features = int(arr.shape[1]) if arr.ndim >= 2 else 1
        initial_type = [("input", FloatTensorType([None, n_features]))]
        model_onnx = convert_sklearn(
            estimator, initial_types=initial_type, target_opset=15
        )
        return model_onnx.SerializeToString()
    except Exception:
        # ONNX export is best-effort — many sklearn features have
        # incomplete skl2onnx coverage (e.g. stacking meta-estimators,
        # custom transformers). Fall back to pickle silently at this
        # layer; the caller emits the WARN log with the onnx_status
        # sentinel per §3.1 row 2 + Phase-B A-02.
        logger.debug(
            "autolog.sklearn.onnx_export_raised",
            extra={"estimator_cls": cls_name},
        )
        return None
