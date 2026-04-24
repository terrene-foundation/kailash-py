# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""LightGBM autolog integration (W23.c).

Implements ``specs/ml-autolog.md §3.1`` row 5:

- Wraps :func:`lightgbm.train` at the module level, scoped to the
  ``km.autolog()`` block via the ABC's :meth:`detach` contract (§3.2).
  Global / persistent monkey-patching is BLOCKED per §1.3; the
  module-level wrap restores in the CM's ``finally:`` even on exception.
- Prepends :func:`lightgbm.callback.record_evaluation` to the user's
  ``callbacks`` kwarg so per-iteration metrics accumulate in a dict
  the wrapper owns; the raw user callbacks continue to fire unchanged.
- Captures ``params`` (the first positional arg of ``lgb.train``)
  before training — drained as ``lgb_params.*`` during :meth:`flush`.
- On train-exit (under async ``flush``), logs:
    * ``{dataset_name}_{metric_name}`` per iteration — the dataset
      names are whatever the user passed in ``valid_names``
      (``training``, ``valid``, etc.), so the spec's
      ``training_<metric>`` / ``valid_<metric>`` shape falls out of
      the user's own config.
    * ``lgb_params.*`` for every key in the params dict.
    * Model artifact via :meth:`Booster.model_to_string` —
      lightgbm's native text format, round-trippable via
      :func:`lightgbm.Booster(model_str=...)`.
    * Feature-importance plotly bar chart per §3.1 row 5.

Per ``rules/orphan-detection.md`` §1, this module's registration site
is ``kailash_ml/autolog/__init__.py`` which eagerly imports this
module — the :func:`register_integration` decorator fires at import
time. The production call site for the instantiated class is the
:func:`kailash_ml.autolog.autolog` context manager, which reads
:data:`_REGISTERED_INTEGRATIONS` during auto-detect (§4.1) and
explicit-name resolution (§4.2).

Framework imports (``lightgbm``) are deferred to :meth:`attach` /
:meth:`flush` so importing this module does NOT pull lightgbm into
``sys.modules``. The auto-detect path is preserved for users who
never ``import lightgbm``.
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


__all__ = ["LightgbmIntegration"]


logger = logging.getLogger(__name__)


def _truncate_repr(value: Any, limit: int = 500) -> str:
    """Param values get stringified-then-truncated so the tracker's
    param table doesn't blow up on large nested param dicts (e.g. a
    dict passed via ``params=`` carrying a custom objective callable).
    """
    rendered = repr(value)
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit] + "...[truncated]"


@register_integration
class LightgbmIntegration(FrameworkIntegration):
    """Autolog for LightGBM ``lgb.train``.

    See module docstring for the full design. Attach replaces
    :func:`lightgbm.train` with a wrapper that captures params +
    prepends ``record_evaluation``; detach restores the original.
    Buffers post-train closures in ``self._events`` during the block;
    drains in :meth:`flush` where ``await`` is valid.
    """

    name = "lightgbm"

    def __init__(self) -> None:
        super().__init__()
        self._lgb_module: Optional[Any] = None
        self._original_train: Optional[Callable[..., Any]] = None
        self._events: List[Callable[["ExperimentRun"], Awaitable[None]]] = []
        self._run: Optional["ExperimentRun"] = None
        self._config: Optional["AutologConfig"] = None

    @classmethod
    def is_available(cls) -> bool:
        # §4.1 — sys.modules check only; surprise-importing lightgbm is
        # BLOCKED per the "zero overhead when unused" contract.
        import sys  # noqa: PLC0415 — deferred per module-level contract

        return "lightgbm" in sys.modules

    def attach(self, run: "ExperimentRun", config: "AutologConfig") -> None:
        self._guard_double_attach()
        self._run = run
        self._config = config

        # Local import — only fires when the user has explicitly
        # chosen "lightgbm" (§4.2) or is_available returned True.
        import lightgbm as lgb  # noqa: PLC0415

        self._lgb_module = lgb
        self._original_train = lgb.train

        integ = self
        original_train = self._original_train

        def wrapped_train(*args: Any, **kwargs: Any) -> Any:
            # Capture params BEFORE training. `lgb.train(params, train_set, ...)`
            # — params is the first positional. Copy so user-side mutation
            # post-train doesn't race the post-train event drain.
            params = args[0] if args else kwargs.get("params", {})
            captured_params: Dict[str, Any] = dict(params) if params else {}

            # Prepend record_evaluation so per-iteration metrics land in
            # our dict. User callbacks continue to fire unchanged —
            # record_evaluation is read-only on the booster state.
            eval_result: Dict[str, Dict[str, List[float]]] = {}
            user_callbacks = list(kwargs.get("callbacks") or [])
            user_callbacks.insert(0, lgb.callback.record_evaluation(eval_result))
            kwargs["callbacks"] = user_callbacks

            booster = original_train(*args, **kwargs)

            integ._events.append(
                integ._make_post_train_event(booster, captured_params, eval_result)
            )
            return booster

        try:
            lgb.train = wrapped_train
        except (AttributeError, TypeError):
            # Module-level attr on lightgbm should always be writable,
            # but guard for parity with _sklearn.attach's tolerance
            # (cf. Cython read-only attrs). Failure here is recoverable —
            # we emit a DEBUG and let the user continue without autolog.
            logger.debug("autolog.lightgbm.patch_skipped")
            self._original_train = None

        logger.info(
            "autolog.lightgbm.attach",
            extra={"run_id": run.run_id},
        )

    def detach(self) -> None:
        if self._lgb_module is not None and self._original_train is not None:
            try:
                self._lgb_module.train = self._original_train
            except (AttributeError, TypeError):
                # Mirror attach's tolerance — detach-failure is BLOCKED
                # from raising per §3.2 idempotency + rules/zero-tolerance
                # §3 "log-and-continue on cleanup where failure is
                # expected" carve-out.
                logger.exception("autolog.lightgbm.unpatch_failed")
        self._events.clear()
        self._lgb_module = None
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
                logger.exception("autolog.lightgbm.event_failed")
        self._events.clear()
        if flush_errors:
            raise flush_errors[0]

    def _make_post_train_event(
        self,
        booster: Any,
        params: Dict[str, Any],
        eval_result: Dict[str, Dict[str, List[float]]],
    ) -> Callable[["ExperimentRun"], Awaitable[None]]:
        log_models = self._config.log_models if self._config else True
        log_figures = self._config.log_figures if self._config else True

        async def event(run: "ExperimentRun") -> None:
            # Params — prefix with `lgb_params.` per spec §3.1 row 5.
            if params:
                safe_params = {
                    f"lgb_params.{k}": _truncate_repr(v) for k, v in params.items()
                }
                await run.log_params(safe_params)

            # Metrics — eval_result shape is
            # ``{dataset_name: {metric_name: [values_per_iter]}}``.
            # The spec's ``training_<metric>`` / ``valid_<metric>``
            # naming falls out of the user's `valid_names` kwarg on
            # `lgb.train`; we don't fabricate names.
            for dataset_name, metrics_dict in eval_result.items():
                for metric_name, values in metrics_dict.items():
                    metric_key = f"{dataset_name}_{metric_name}"
                    for step, value in enumerate(values):
                        try:
                            await run.log_metric(metric_key, float(value), step=step)
                        except Exception:
                            # Skip the rest of this metric rather than
                            # flooding the error log on every iteration —
                            # a single log_metric failure is rarely
                            # per-row; it's a backend-wide problem.
                            logger.debug(
                                "autolog.lightgbm.metric_failed",
                                extra={"metric_key": metric_key, "step": step},
                            )
                            break

            # Model artifact — native lightgbm text format, round-trippable
            # via `lightgbm.Booster(model_str=...)`.
            if log_models:
                try:
                    model_str = booster.model_to_string()
                    await run.log_artifact(
                        model_str.encode("utf-8"),
                        "lightgbm.model.txt",
                        content_type="text/plain",
                    )
                except Exception:
                    logger.exception("autolog.lightgbm.log_model_failed")

            # Feature-importance figure (plotly — base kailash-ml dep,
            # avoids matplotlib requirement).
            if log_figures:
                try:
                    await _log_feature_importance(run, booster)
                except Exception:
                    logger.exception("autolog.lightgbm.feature_importance_failed")

        return event


async def _log_feature_importance(run: "ExperimentRun", booster: Any) -> None:
    """Emit a plotly bar chart of LightGBM feature importances.

    Uses ``importance_type="gain"`` — gain is the canonical tree-based
    importance signal (contribution to loss reduction) and is less
    biased than ``"split"`` (raw split count), which favours features
    with many unique values regardless of predictive power.
    """
    import plotly.graph_objects as go  # noqa: PLC0415

    try:
        importances = booster.feature_importance(importance_type="gain")
        feature_names = booster.feature_name()
    except Exception:
        logger.debug("autolog.lightgbm.feature_importance_unavailable")
        return

    # `importances` is a numpy array; `feature_names` is a list[str].
    importances_list = [float(v) for v in importances]
    fig = go.Figure(
        data=[
            go.Bar(
                x=list(feature_names),
                y=importances_list,
                marker={"color": "steelblue"},
            )
        ]
    )
    fig.update_layout(
        title_text="LightGBM Feature Importance (gain)",
        xaxis_title="Feature",
        yaxis_title="Importance (gain)",
    )
    await run.log_figure(fig, "lightgbm.feature_importance")
