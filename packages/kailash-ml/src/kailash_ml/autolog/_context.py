# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Autolog async-context-manager + decorator entry points.

Implements ``specs/ml-autolog.md §2.1`` (async CM), §2.2 (decorator),
§4 (dispatch), §5 (opt-out), §6 (ambient-tracker requirement), §7
(typed errors), §8.5 (detach-on-exception).

No framework-specific code lives here — the CM routes every
attach/detach through the :class:`~kailash_ml.autolog._registry.FrameworkIntegration`
ABC so W23.b-d framework integrations plug in without touching this
module.

Module-scope dependencies are only ``contextlib`` / ``fnmatch`` /
``functools`` / standard logging — every framework import is deferred
to the concrete integrations (``autolog-*`` extras).
"""
from __future__ import annotations

import fnmatch
import functools
import logging
import os
from contextlib import asynccontextmanager
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Optional,
    Sequence,
    TypeVar,
)

from kailash_ml.autolog._registry import (
    FrameworkIntegration,
    _REGISTERED_INTEGRATIONS,
    registered_integration_names,
)
from kailash_ml.autolog.config import AutologConfig, AutologHandle


__all__ = ["autolog", "autolog_fn"]


logger = logging.getLogger(__name__)


_ENV_DISABLED = "KAILASH_ML_AUTOLOG_DISABLED"
"""Environment variable short-circuiting every ``autolog()`` block to a
no-op that still validates the ambient-run requirement per §5.3."""


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def _build_config(
    frameworks: Sequence[str],
    *,
    disable: Optional[Sequence[str]],
    log_models: bool,
    log_datasets: bool,
    log_figures: bool,
    log_system_metrics: bool,
    system_metrics_interval_s: int,
    sample_rate_steps: int,
    disable_metrics: Optional[Sequence[str]],
    tokens_per_second_window: int,
) -> AutologConfig:
    """Translate kwargs into a frozen :class:`AutologConfig`.

    Empty ``frameworks`` tuple collapses to the sentinel ``("auto",)``
    per §4.1 so integrations can distinguish "auto-detect" from
    "explicit empty selection".
    """
    fw_tuple: tuple[str, ...] = tuple(frameworks) if frameworks else ("auto",)
    return AutologConfig(
        frameworks=fw_tuple,
        log_models=log_models,
        log_datasets=log_datasets,
        log_figures=log_figures,
        log_system_metrics=log_system_metrics,
        system_metrics_interval_s=system_metrics_interval_s,
        sample_rate_steps=sample_rate_steps,
        disable=tuple(disable or ()),
        disable_metrics=tuple(disable_metrics or ()),
        tokens_per_second_window=tokens_per_second_window,
    )


def _resolve_integrations(
    config: AutologConfig,
) -> list[FrameworkIntegration]:
    """Resolve the config's framework selection to instantiated
    integrations per §4.1–§4.3.

    - ``("auto",)`` → every registered integration whose
      ``is_available()`` returns True.
    - Explicit names → every name MUST resolve; unknown names raise
      :class:`AutologUnknownFrameworkError`.
    - ``disable`` filter applies after resolution; unknown ``disable``
      names also raise per §4.3.
    """
    from kailash.ml.errors import AutologUnknownFrameworkError

    available_names = registered_integration_names()

    # Validate disable names first — typo in disable is BLOCKED even
    # in auto-detect mode (§4.3). Unknown disable names have to be
    # loud because silent acceptance of a typo means the framework the
    # user meant to disable is STILL attached.
    for name in config.disable:
        if name not in available_names:
            raise AutologUnknownFrameworkError(
                reason=(
                    f"autolog(disable=...) received unknown framework "
                    f"{name!r}; registered integrations: "
                    f"{list(available_names)}"
                )
            )

    # Build the target-names set.
    if config.frameworks == ("auto",):
        # Auto-detect — only attach integrations whose framework is
        # already imported in sys.modules per §4.1 MUST.
        target_names = [
            cls.name for cls in _REGISTERED_INTEGRATIONS if cls.is_available()
        ]
    else:
        # Explicit selection — every name MUST resolve.
        for name in config.frameworks:
            if name not in available_names:
                raise AutologUnknownFrameworkError(
                    reason=(
                        f"autolog({name!r}) received unknown framework; "
                        f"registered integrations: {list(available_names)}"
                    )
                )
        target_names = list(config.frameworks)

    # Apply disable filter.
    disabled = set(config.disable)
    filtered = [n for n in target_names if n not in disabled]

    # Instantiate each resolved class. Instantiation MUST be per-block
    # so each `async with autolog()` gets a fresh state bag.
    integrations: list[FrameworkIntegration] = []
    for cls in _REGISTERED_INTEGRATIONS:
        if cls.name in filtered:
            integrations.append(cls())
    return integrations


def _env_disabled() -> bool:
    """Return True if ``KAILASH_ML_AUTOLOG_DISABLED`` is set to any
    non-empty non-zero value.

    Accepts ``1``, ``true``, ``yes``, ``on`` (case-insensitive) per §5.3.
    Anything else (``0``, empty, unset) → not disabled.
    """
    raw = os.environ.get(_ENV_DISABLED, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


@asynccontextmanager
async def autolog(
    *frameworks: str,
    disable: Optional[Sequence[str]] = None,
    log_models: bool = True,
    log_datasets: bool = True,
    log_figures: bool = True,
    log_system_metrics: bool = False,
    system_metrics_interval_s: int = 5,
    sample_rate_steps: int = 1,
    disable_metrics: Optional[Sequence[str]] = None,
    tokens_per_second_window: int = 128,
) -> AsyncIterator[AutologHandle]:
    """Async context manager that auto-logs metrics, params, artifacts,
    and models from popular ML / DL frameworks into the ambient
    ``km.track()`` run.

    Per ``specs/ml-autolog.md §2.1`` + §6.1:

    - MUST raise :class:`~kailash.ml.errors.AutologNoAmbientRunError`
      when called outside ``km.track()``. Silent no-op is BLOCKED.
    - Positional ``frameworks`` arguments select explicit integrations;
      empty tuple auto-detects every registered framework whose module
      is already imported in ``sys.modules`` per §4.1.
    - ``KAILASH_ML_AUTOLOG_DISABLED=1`` short-circuits to a no-op CM
      that STILL validates the ambient-run requirement per §5.3.

    Yields an :class:`AutologHandle` with the live block's
    ``run_id``, ``config`` snapshot, and
    ``attached_integrations`` tuple.

    Usage::

        async with km.track("my-exp") as run:
            async with km.autolog() as handle:
                # handle.attached_integrations == ("lightning", "sklearn")
                trainer = pl.Trainer(max_epochs=3)
                trainer.fit(model, datamodule)

    :raises AutologNoAmbientRunError: no ambient ``km.track()`` run.
    :raises AutologUnknownFrameworkError: explicit or disable name does
        not resolve to a registered integration.
    :raises AutologAttachError: a framework integration's ``attach``
        call raised; wraps the inner exception as ``__cause__``.
    """
    from kailash.ml.errors import (
        AutologAttachError,
        AutologDetachError,
        AutologNoAmbientRunError,
    )
    from kailash_ml.tracking import get_current_run

    # Ambient-run gate per §6.1 — evaluated BEFORE the env-disable
    # short-circuit so the disabled-autolog path still surfaces the
    # "forgot km.track()" error loudly.
    run = get_current_run()
    if run is None:
        raise AutologNoAmbientRunError(
            reason=(
                "autolog() called outside km.track() — metrics would have "
                "nowhere to go. Wrap the call in `async with km.track(name) "
                "as run: async with km.autolog(): ...`"
            )
        )

    config = _build_config(
        frameworks=frameworks,
        disable=disable,
        log_models=log_models,
        log_datasets=log_datasets,
        log_figures=log_figures,
        log_system_metrics=log_system_metrics,
        system_metrics_interval_s=system_metrics_interval_s,
        sample_rate_steps=sample_rate_steps,
        disable_metrics=disable_metrics,
        tokens_per_second_window=tokens_per_second_window,
    )

    # §5.3 env-var short-circuit. Ambient-run check already fired;
    # yield a handle with zero integrations and exit cleanly.
    if _env_disabled():
        logger.info(
            "autolog.env_disabled",
            extra={
                "run_id": run.run_id,
                "env_var": _ENV_DISABLED,
            },
        )
        yield AutologHandle(
            run_id=run.run_id,
            config=config,
            attached_integrations=(),
            _active=[],
        )
        return

    # Validate the explicit framework names + disable filter BEFORE any
    # attach fires so a typo never leaves the block in a half-attached
    # state. Raises AutologUnknownFrameworkError per §4.2 / §4.3.
    resolved = _resolve_integrations(config)

    active: list[FrameworkIntegration] = []
    logger.info(
        "autolog.start",
        extra={
            "run_id": run.run_id,
            "frameworks": [i.name for i in resolved],
        },
    )

    # Attach each integration; on the first failure we unwind the
    # already-attached ones so the block never yields in a partial
    # state.
    try:
        for integ in resolved:
            try:
                integ.attach(run, config)
            except Exception as exc:  # noqa: BLE001
                # Unwind LIFO before surfacing the failure.
                for already in reversed(active):
                    try:
                        already.detach()
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "autolog.unwind_detach_failed",
                            extra={"integration": already.name},
                        )
                raise AutologAttachError(
                    reason=(
                        f"FrameworkIntegration {integ.name!r} attach() failed: "
                        f"{type(exc).__name__}: {exc}"
                    )
                ) from exc
            active.append(integ)

        handle = AutologHandle(
            run_id=run.run_id,
            config=config,
            attached_integrations=tuple(i.name for i in active),
            _active=active,
        )

        try:
            yield handle
        finally:
            # §8.5 — detach MUST run even when the wrapped block
            # raised. Preserve the user's exception via __context__ if
            # any detach fails (§7.1 MUST — losing the user's stack is
            # BLOCKED per zero-tolerance.md Rule 3).
            detach_errors: list[BaseException] = []
            while active:
                integ = active.pop()
                try:
                    integ.detach()
                except Exception as exc:  # noqa: BLE001
                    detach_errors.append(exc)
                    logger.exception(
                        "autolog.detach_failed",
                        extra={"integration": integ.name},
                    )
            if detach_errors:
                first = detach_errors[0]
                wrapped = AutologDetachError(
                    reason=(
                        f"{len(detach_errors)} detach() failure(s) during "
                        f"autolog exit; first: {type(first).__name__}: {first}"
                    )
                )
                wrapped.__cause__ = first
                raise wrapped
    finally:
        logger.info(
            "autolog.end",
            extra={"run_id": run.run_id},
        )


def autolog_fn(
    *frameworks: str,
    **kwargs: Any,
) -> Callable[[F], F]:
    """Decorator wrapping an ``async def`` function in an
    ``autolog(...)`` block.

    Per ``specs/ml-autolog.md §2.2``:

    - The wrapped callable MUST run inside a :func:`km.track` context
      — the decorator does NOT auto-create a run.
    - Args passed to :func:`autolog_fn` are forwarded to
      :func:`autolog` on every call.

    Usage::

        @km.autolog_fn("lightning")
        async def train(model, data):
            trainer = pl.Trainer(...)
            trainer.fit(model, data)

        async with km.track("my-exp"):
            await train(model, data)  # autolog active for train()'s scope
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **call_kwargs: Any) -> Any:
            async with autolog(*frameworks, **kwargs):
                return await func(*args, **call_kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


_DISABLE_METRIC_CACHE: dict[tuple[str, ...], Callable[[str], bool]] = {}


def _is_metric_disabled(key: str, disable_metrics: tuple[str, ...]) -> bool:
    """Return True if ``key`` matches any glob in ``disable_metrics``.

    Helper for concrete framework integrations in W23.b-d to consult
    before emitting a metric per §5.2. Cached per-tuple for the common
    case where the same config's disable list is checked thousands of
    times per run.
    """
    if not disable_metrics:
        return False
    matcher = _DISABLE_METRIC_CACHE.get(disable_metrics)
    if matcher is None:

        def _match(k: str, patterns: tuple[str, ...] = disable_metrics) -> bool:
            return any(fnmatch.fnmatchcase(k, p) for p in patterns)

        matcher = _match
        _DISABLE_METRIC_CACHE[disable_metrics] = matcher
    return matcher(key)
