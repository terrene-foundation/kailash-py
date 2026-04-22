# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""XGBoost autolog integration (W23.d).

Implements ``specs/ml-autolog.md §3.1`` row 4:

- Wraps :func:`xgboost.train` at the module level, scoped to the
  ``km.autolog()`` block via the ABC's :meth:`detach` contract (§3.2).
  Global / persistent monkey-patching is BLOCKED per §1.3; the
  module-level wrap restores in the CM's ``finally:`` even on exception.
- Injects an ``evals_result={}`` kwarg if the user didn't pass one, and
  keeps a reference so we can drain the per-iteration metrics in
  :meth:`flush`. If the user passed their own ``evals_result`` dict we
  share the reference — their dict remains populated for their use.
- Captures ``params`` (the first positional arg of ``xgb.train``)
  before training — drained as ``xgb_params.*`` during :meth:`flush`.
- On train-exit (under async ``flush``), logs:
    * ``{dataset_name}_{metric_name}`` per boosting round — the
      dataset names come from the user's ``evals=[(dmat, "name"), ...]``
      list, so the spec's ``train-<metric>`` / ``eval-<metric>`` shape
      falls out of the user's own config.
    * ``xgb_params.*`` for every key in the params dict.
    * Model artifact via :meth:`Booster.save_raw` — xgboost's native
      binary format, round-trippable via
      :func:`xgboost.Booster(model_file=...)` or ``load_model``.
    * Feature-importance plotly bar chart per §3.1 row 4.

Per ``rules/orphan-detection.md`` §1, this module's registration site
is ``kailash_ml/autolog/__init__.py`` which eagerly imports this
module — the :func:`register_integration` decorator fires at import
time. The production call site for the instantiated class is the
:func:`kailash_ml.autolog.autolog` context manager, which reads
:data:`_REGISTERED_INTEGRATIONS` during auto-detect (§4.1) and
explicit-name resolution (§4.2).

Framework imports (``xgboost``) are deferred to :meth:`attach` /
:meth:`flush` so importing this module does NOT pull xgboost into
``sys.modules``. The auto-detect path is preserved for users who
never ``import xgboost``.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

from kailash_ml.autolog._registry import (
    FrameworkIntegration,
    register_integration,
)

if TYPE_CHECKING:
    from kailash_ml.autolog.config import AutologConfig
    from kailash_ml.tracking import ExperimentRun


__all__ = ["XgboostIntegration"]


logger = logging.getLogger(__name__)


def _truncate_repr(value: Any, limit: int = 500) -> str:
    """Param values get stringified-then-truncated so the tracker's
    param table doesn't blow up on nested param dicts.
    """
    rendered = repr(value)
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit] + "...[truncated]"


@register_integration
class XgboostIntegration(FrameworkIntegration):
    """Autolog for XGBoost ``xgb.train``.

    See module docstring for the full design. Attach replaces
    :func:`xgboost.train` with a wrapper that captures params +
    injects/shares ``evals_result``; detach restores the original.
    Buffers post-train closures in ``self._events`` during the block;
    drains in :meth:`flush` where ``await`` is valid.
    """

    name = "xgboost"

    def __init__(self) -> None:
        super().__init__()
        self._xgb_module: Optional[Any] = None
        self._original_train: Optional[Callable[..., Any]] = None
        self._events: List[Callable[["ExperimentRun"], Awaitable[None]]] = []
        self._run: Optional["ExperimentRun"] = None
        self._config: Optional["AutologConfig"] = None

    @classmethod
    def is_available(cls) -> bool:
        # §4.1 — sys.modules check only; surprise-importing xgboost is
        # BLOCKED per the "zero overhead when unused" contract.
        import sys  # noqa: PLC0415 — deferred per module-level contract

        return "xgboost" in sys.modules

    def attach(self, run: "ExperimentRun", config: "AutologConfig") -> None:
        self._guard_double_attach()
        self._run = run
        self._config = config

        # Local import — only fires when the user has explicitly
        # chosen "xgboost" (§4.2) or is_available returned True.
        import xgboost as xgb  # noqa: PLC0415

        self._xgb_module = xgb
        self._original_train = xgb.train

        integ = self
        original_train = self._original_train

        def wrapped_train(*args: Any, **kwargs: Any) -> Any:
            # Capture params BEFORE training. `xgb.train(params, dtrain, ...)`
            # — params is the first positional. Copy so user-side mutation
            # post-train doesn't race the post-train event drain.
            params = args[0] if args else kwargs.get("params", {})
            captured_params: Dict[str, Any] = dict(params) if params else {}

            # Inject / share evals_result so per-iteration metrics land
            # in a dict the wrapper can drain. If the user passed their
            # own dict we share the reference (both their code and
            # autolog see the same data).
            evals_result = kwargs.get("evals_result")
            if evals_result is None:
                evals_result = {}
                kwargs["evals_result"] = evals_result

            booster = original_train(*args, **kwargs)

            integ._events.append(
                integ._make_post_train_event(booster, captured_params, evals_result)
            )
            return booster

        try:
            xgb.train = wrapped_train
        except (AttributeError, TypeError):
            # Module-level attr on xgboost should always be writable,
            # but guard for parity with _sklearn.attach's tolerance.
            # Failure here is recoverable — emit DEBUG and continue.
            logger.debug("autolog.xgboost.patch_skipped")
            self._original_train = None

        logger.info(
            "autolog.xgboost.attach",
            extra={"run_id": run.run_id},
        )

    def detach(self) -> None:
        if self._xgb_module is not None and self._original_train is not None:
            try:
                self._xgb_module.train = self._original_train
            except (AttributeError, TypeError):
                # Mirror attach's tolerance — detach-failure is BLOCKED
                # from raising per §3.2 idempotency + rules/zero-tolerance
                # §3 "log-and-continue on cleanup where failure is
                # expected" carve-out.
                logger.exception("autolog.xgboost.unpatch_failed")
        self._events.clear()
        self._xgb_module = None
        self._original_train = None
        self._run = None
        self._config = None
        self._mark_detached()

    async def flush(self, run: "ExperimentRun") -> None:
        """Drain buffered post-train events to the tracker.

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
                logger.exception("autolog.xgboost.event_failed")
        self._events.clear()
        if flush_errors:
            raise flush_errors[0]

    def _make_post_train_event(
        self,
        booster: Any,
        params: Dict[str, Any],
        evals_result: Dict[str, Dict[str, List[float]]],
    ) -> Callable[["ExperimentRun"], Awaitable[None]]:
        log_models = self._config.log_models if self._config else True
        log_figures = self._config.log_figures if self._config else True

        async def event(run: "ExperimentRun") -> None:
            # Params — prefix with `xgb_params.` per spec §3.1 row 4.
            if params:
                safe_params = {
                    f"xgb_params.{k}": _truncate_repr(v) for k, v in params.items()
                }
                await run.log_params(safe_params)

            # Metrics — evals_result shape is
            # ``{dataset_name: {metric_name: [values_per_round]}}``.
            # The spec's ``train-<metric>`` / ``eval-<metric>`` naming
            # falls out of the user's `evals=[(dmat, "name"), ...]`
            # kwarg on `xgb.train`; we don't fabricate names.
            for dataset_name, metrics_dict in evals_result.items():
                for metric_name, values in metrics_dict.items():
                    metric_key = f"{dataset_name}_{metric_name}"
                    for step, value in enumerate(values):
                        try:
                            # xgboost emits (mean, std) tuples when
                            # cross-validating — take the mean. Plain
                            # training emits floats.
                            scalar = (
                                float(value[0])
                                if isinstance(value, (tuple, list))
                                else float(value)
                            )
                            await run.log_metric(metric_key, scalar, step=step)
                        except Exception:
                            # Skip the rest of this metric rather than
                            # flooding the error log on every round —
                            # a single log_metric failure is rarely
                            # per-row; it's a backend-wide problem.
                            logger.debug(
                                "autolog.xgboost.metric_failed",
                                extra={"metric_key": metric_key, "step": step},
                            )
                            break

            # Model artifact — native xgboost UBJSON/binary format,
            # round-trippable via xgb.Booster().load_model(bytearray).
            if log_models:
                try:
                    raw = booster.save_raw()
                    await run.log_artifact(
                        bytes(raw),
                        "xgboost.model.ubj",
                        content_type="application/octet-stream",
                    )
                except Exception:
                    logger.exception("autolog.xgboost.log_model_failed")

            # Feature-importance figure (plotly — base kailash-ml dep,
            # avoids matplotlib requirement).
            if log_figures:
                try:
                    await _log_feature_importance(run, booster)
                except Exception:
                    logger.exception("autolog.xgboost.feature_importance_failed")

        return event


async def _log_feature_importance(run: "ExperimentRun", booster: Any) -> None:
    """Emit a plotly bar chart of XGBoost feature importances.

    Uses ``importance_type="gain"`` — gain is the canonical tree-based
    importance signal (contribution to loss reduction) and is less
    biased than ``"weight"`` (raw split count), which favours features
    with many unique values regardless of predictive power.
    """
    import plotly.graph_objects as go  # noqa: PLC0415

    try:
        # `get_score` returns {feature_name: importance}. Features that
        # never participated in a split are omitted from the dict.
        scores = booster.get_score(importance_type="gain")
    except Exception:
        logger.debug("autolog.xgboost.feature_importance_unavailable")
        return

    if not scores:
        # An under-trained model (e.g. 0 rounds) may return an empty
        # dict. Emit nothing rather than a blank figure.
        logger.debug("autolog.xgboost.feature_importance_empty")
        return

    # Sort by importance descending so the plot is read-left-to-right
    # most→least important.
    sorted_items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    feature_names = [k for k, _ in sorted_items]
    importances = [float(v) for _, v in sorted_items]

    fig = go.Figure(
        data=[
            go.Bar(
                x=feature_names,
                y=importances,
                marker={"color": "darkorange"},
            )
        ]
    )
    fig.update_layout(
        title_text="XGBoost Feature Importance (gain)",
        xaxis_title="Feature",
        yaxis_title="Importance (gain)",
    )
    await run.log_figure(fig, "xgboost.feature_importance")
