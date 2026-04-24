# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""statsmodels autolog integration (W23.g).

Implements ``specs/ml-autolog.md §3.1`` row 6:

- Wraps :meth:`statsmodels.regression.linear_model.RegressionResults.summary`
  at the class level, scoped to the ``km.autolog()`` block via the
  ABC's :meth:`detach` contract (§3.2). Global / persistent
  monkey-patching is BLOCKED per §1.3; the class-level wrap restores
  in the CM's ``finally:`` even on exception.
- When the wrapped ``summary()`` is called, captures:
    * Metrics: ``rsquared``, ``aic``, ``bic``, ``llf``, ``f_pvalue``
      (per spec row 6; only fields the results object exposes — not
      every subclass defines all five, missing attrs silently skip).
    * Params: serialized ``params`` array under ``statsmodels.params``.
    * Artifact: ``summary().as_html()`` encoded as ``text/html``
      under ``statsmodels.summary.html``.

Per ``rules/orphan-detection.md`` §1, this module's registration site
is ``kailash_ml/autolog/__init__.py`` which eagerly imports this
module. The production call site is the CM's auto-detect + explicit-
name resolver.

Framework imports (``statsmodels``) are deferred to :meth:`attach` so
importing this module does NOT pull statsmodels into ``sys.modules``.
The auto-detect path is preserved for users who never
``import statsmodels``.
"""
from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any, Awaitable, Callable, List, Optional

from kailash_ml.autolog._distribution import is_main_process
from kailash_ml.autolog._registry import (
    FrameworkIntegration,
    register_integration,
)

if TYPE_CHECKING:
    from kailash_ml.autolog.config import AutologConfig
    from kailash_ml.tracking import ExperimentRun


__all__ = ["StatsmodelsIntegration"]


logger = logging.getLogger(__name__)


_METRIC_ATTRS = ("rsquared", "aic", "bic", "llf", "f_pvalue")


@register_integration
class StatsmodelsIntegration(FrameworkIntegration):
    """Autolog for statsmodels ``RegressionResults.summary`` calls.

    See module docstring for the full design. Attach replaces
    :meth:`RegressionResults.summary` with a wrapper that captures
    metrics + params + HTML artifact on call; detach restores the
    original.
    """

    name = "statsmodels"

    def __init__(self) -> None:
        super().__init__()
        self._results_cls: Optional[type] = None
        self._original_summary: Optional[Callable[..., Any]] = None
        self._events: List[Callable[["ExperimentRun"], Awaitable[None]]] = []
        self._run: Optional["ExperimentRun"] = None
        self._config: Optional["AutologConfig"] = None

    @classmethod
    def is_available(cls) -> bool:
        return "statsmodels" in sys.modules

    def attach(self, run: "ExperimentRun", config: "AutologConfig") -> None:
        self._guard_double_attach()
        self._run = run
        self._config = config

        from statsmodels.regression.linear_model import (  # noqa: PLC0415
            RegressionResults,
        )

        self._results_cls = RegressionResults
        self._original_summary = RegressionResults.__dict__.get("summary")
        if self._original_summary is None:
            logger.debug("autolog.statsmodels.summary_not_defined")
            return

        integ = self
        original_summary = self._original_summary

        def wrapped_summary(self_results: Any, *args: Any, **kwargs: Any) -> Any:
            summary_obj = original_summary(self_results, *args, **kwargs)
            if not is_main_process():
                return summary_obj
            integ._events.append(
                integ._make_post_summary_event(self_results, summary_obj)
            )
            return summary_obj

        try:
            RegressionResults.summary = wrapped_summary  # type: ignore[method-assign]
        except (AttributeError, TypeError):
            logger.debug("autolog.statsmodels.patch_skipped")
            self._original_summary = None

        logger.info(
            "autolog.statsmodels.attach",
            extra={"run_id": run.run_id},
        )

    def detach(self) -> None:
        if self._results_cls is not None and self._original_summary is not None:
            try:
                self._results_cls.summary = self._original_summary  # type: ignore[method-assign]
            except (AttributeError, TypeError):
                logger.exception("autolog.statsmodels.unpatch_failed")
        self._events.clear()
        self._results_cls = None
        self._original_summary = None
        self._run = None
        self._config = None
        self._mark_detached()

    async def flush(self, run: "ExperimentRun") -> None:
        flush_errors: List[BaseException] = []
        for event in self._events:
            try:
                await event(run)
            except Exception as exc:  # noqa: BLE001
                flush_errors.append(exc)
                logger.exception("autolog.statsmodels.event_failed")
        self._events.clear()
        if flush_errors:
            raise flush_errors[0]

    def _make_post_summary_event(
        self,
        results: Any,
        summary_obj: Any,
    ) -> Callable[["ExperimentRun"], Awaitable[None]]:
        log_figures = self._config.log_figures if self._config else True

        # Capture values AT wrap-time (before we return to the user)
        # so a later mutation of results doesn't race the drain.
        metrics: dict[str, float] = {}
        for attr in _METRIC_ATTRS:
            if not hasattr(results, attr):
                continue
            try:
                v = getattr(results, attr)
                if v is None:
                    continue
                import math  # noqa: PLC0415

                fv = float(v)
                if math.isfinite(fv):
                    metrics[attr] = fv
            except Exception:
                continue

        # Serialised params array — per spec "params array serialized".
        params_repr: Optional[str] = None
        try:
            params_obj = getattr(results, "params", None)
            if params_obj is not None:
                # `.to_dict()` for pandas Series; `.tolist()` for numpy.
                if hasattr(params_obj, "to_dict"):
                    params_repr = repr(dict(params_obj.to_dict()))
                elif hasattr(params_obj, "tolist"):
                    params_repr = repr(list(params_obj.tolist()))
                else:
                    params_repr = repr(params_obj)
        except Exception:
            params_repr = None

        # HTML artifact — capture NOW, not at drain time (summary_obj
        # may be garbage-collected by the time flush runs).
        html_bytes: Optional[bytes] = None
        if log_figures:
            try:
                html_bytes = summary_obj.as_html().encode("utf-8")
            except Exception:
                logger.debug("autolog.statsmodels.summary_html_unavailable")

        async def event(run: "ExperimentRun") -> None:
            if metrics:
                try:
                    await run.log_metrics(metrics)
                except Exception:
                    logger.exception("autolog.statsmodels.metrics_emit_failed")
            if params_repr is not None:
                try:
                    await run.log_params({"statsmodels.params": params_repr})
                except Exception:
                    logger.exception("autolog.statsmodels.params_emit_failed")
            if html_bytes is not None:
                try:
                    await run.log_artifact(
                        html_bytes,
                        "statsmodels.summary.html",
                        content_type="text/html",
                    )
                except Exception:
                    logger.exception("autolog.statsmodels.html_emit_failed")

        return event
