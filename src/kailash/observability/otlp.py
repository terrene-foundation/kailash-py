# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""OTLP + Prometheus observability bootstrap (issue #1708).

The SDK already creates OpenTelemetry metric instruments (``MetricsBridge`` in
:mod:`kailash.runtime.metrics`, trust metrics, ML metrics) and tracer spans
(:mod:`kailash.runtime.tracing`), but nothing configures the global OTel
providers — so every instrument records into the default no-op provider and
exports nowhere.

:func:`configure_observability` installs the global ``MeterProvider`` /
``TracerProvider`` / ``LoggerProvider`` with:

* a ``Resource`` carrying ``service.name`` + ``service.version`` on every signal,
* a Prometheus exposition reader (bridges OTel metrics into the ``prometheus_client``
  default registry, so a single ``generate_latest()`` on ``/metrics`` exports both
  OTel-emitted and ``prometheus_client``-native metrics), and
* an OTLP exporter for metrics **and** traces (and optionally logs), gated on
  ``OTEL_EXPORTER_OTLP_ENDPOINT``.

Once configured, the instruments the SDK already creates begin exporting with no
call-site changes. Everything degrades to a documented no-op when the optional
``kailash[telemetry]`` dependencies are absent — the function never raises.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "ObservabilityHandle",
    "configure_observability",
    "get_observability_handle",
    "shutdown_observability",
]

DEFAULT_SERVICE_NAME = "kailash"

_LOCK = threading.RLock()
_STATE: "Optional[ObservabilityHandle]" = None

# Class-name fragments identifying a provider that has NOT been meaningfully
# configured yet (the API-layer proxy or a no-op default). Only these are safe
# to override — a real, host-installed provider is respected unless force=True.
_UNSET_PROVIDER_MARKERS = ("Proxy", "NoOp", "Default", "_DefaultMeterProvider")


@dataclass
class ObservabilityHandle:
    """Result of :func:`configure_observability`.

    ``configured`` is True when at least one signal was wired to an exporter.
    When the telemetry extra is missing (or nothing was enabled) ``configured``
    is False and ``reason`` explains why — the SDK keeps running, just without
    export.
    """

    configured: bool
    service_name: str
    service_version: str
    metrics_enabled: bool = False
    traces_enabled: bool = False
    logs_enabled: bool = False
    prometheus_enabled: bool = False
    otlp_endpoint: Optional[str] = None
    reason: Optional[str] = None
    _meter_provider: Any = field(default=None, repr=False)
    _tracer_provider: Any = field(default=None, repr=False)
    _logger_provider: Any = field(default=None, repr=False)

    def shutdown(self) -> None:
        """Flush + shut down every provider this handle installed. Idempotent."""
        for prov in (
            self._meter_provider,
            self._tracer_provider,
            self._logger_provider,
        ):
            if prov is not None and hasattr(prov, "shutdown"):
                try:
                    prov.shutdown()
                except Exception as exc:  # pragma: no cover - best-effort flush
                    logger.warning("observability provider shutdown failed: %s", exc)


def _resolve_version() -> str:
    try:
        from kailash import __version__

        return __version__
    except Exception:  # pragma: no cover - version import should not fail
        return "unknown"


def _provider_is_unset(provider: Any) -> bool:
    """True when ``provider`` is the API proxy / no-op default (safe to override)."""
    name = type(provider).__name__
    return any(marker in name for marker in _UNSET_PROVIDER_MARKERS)


def get_observability_handle() -> "Optional[ObservabilityHandle]":
    """Return the handle from the last :func:`configure_observability`, or None."""
    return _STATE


def shutdown_observability() -> None:
    """Shut down and clear the process-global observability handle."""
    global _STATE
    with _LOCK:
        if _STATE is not None:
            _STATE.shutdown()
            _STATE = None


def configure_observability(
    *,
    service_name: Optional[str] = None,
    service_version: Optional[str] = None,
    otlp_endpoint: Optional[str] = None,
    prometheus: bool = True,
    enable_metrics: bool = True,
    enable_traces: bool = True,
    enable_logs: bool = False,
    force: bool = False,
) -> ObservabilityHandle:
    """Configure the global OpenTelemetry providers so SDK instruments export.

    Args:
        service_name: Resource ``service.name``. Defaults to ``$OTEL_SERVICE_NAME``
            then ``"kailash"``.
        service_version: Resource ``service.version``. Defaults to
            :data:`kailash.__version__`.
        otlp_endpoint: OTLP collector endpoint for the metrics + traces (+ logs)
            signal. Defaults to ``$OTEL_EXPORTER_OTLP_ENDPOINT``. When unset, OTLP
            export is skipped (Prometheus scrape still works).
        prometheus: Install a Prometheus exposition reader so ``/metrics`` exports
            the OTel metrics alongside ``prometheus_client``-native ones.
        enable_metrics / enable_traces / enable_logs: Per-signal toggles.
        force: Override an already-installed (host-configured) provider.

    Returns:
        An :class:`ObservabilityHandle`. Never raises — a missing telemetry extra
        yields ``configured=False`` with an explanatory ``reason``.
    """
    global _STATE
    with _LOCK:
        if _STATE is not None and _STATE.configured and not force:
            return _STATE

        service_name = (
            service_name or os.environ.get("OTEL_SERVICE_NAME") or DEFAULT_SERVICE_NAME
        )
        service_version = service_version or _resolve_version()
        if otlp_endpoint is None:
            otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

        try:
            from opentelemetry.sdk.resources import Resource
        except ImportError:
            handle = ObservabilityHandle(
                configured=False,
                service_name=service_name,
                service_version=service_version,
                otlp_endpoint=otlp_endpoint,
                reason=(
                    "opentelemetry-sdk not installed; run "
                    "`pip install kailash[telemetry]` to enable OTLP/Prometheus export"
                ),
            )
            logger.warning("observability: %s", handle.reason)
            _STATE = handle
            return handle

        resource = Resource.create(
            {"service.name": service_name, "service.version": service_version}
        )

        metrics_enabled = (
            _configure_metrics(resource, otlp_endpoint, prometheus, force)
            if enable_metrics
            else (False, False, None)
        )
        traces_enabled = (
            _configure_traces(resource, otlp_endpoint, force)
            if enable_traces
            else (False, None)
        )
        logs_enabled = (
            _configure_logs(resource, otlp_endpoint) if enable_logs else (False, None)
        )

        metrics_ok, prom_ok, meter_provider = metrics_enabled
        traces_ok, tracer_provider = traces_enabled
        logs_ok, logger_provider = logs_enabled

        configured = metrics_ok or traces_ok or logs_ok
        reason = None
        if not configured:
            reason = (
                "no signal exported: OTEL_EXPORTER_OTLP_ENDPOINT unset and Prometheus "
                "reader unavailable"
            )
            logger.warning("observability: %s", reason)

        handle = ObservabilityHandle(
            configured=configured,
            service_name=service_name,
            service_version=service_version,
            metrics_enabled=metrics_ok,
            traces_enabled=traces_ok,
            logs_enabled=logs_ok,
            prometheus_enabled=prom_ok,
            otlp_endpoint=otlp_endpoint,
            reason=reason,
            _meter_provider=meter_provider,
            _tracer_provider=tracer_provider,
            _logger_provider=logger_provider,
        )
        _STATE = handle
        logger.info(
            "observability configured: service=%s v=%s metrics=%s prometheus=%s "
            "traces=%s logs=%s otlp=%s",
            service_name,
            service_version,
            metrics_ok,
            prom_ok,
            traces_ok,
            logs_ok,
            otlp_endpoint or "(none)",
        )
        return handle


def _configure_metrics(resource, otlp_endpoint, prometheus, force):
    """Returns (metrics_exported, prometheus_reader_installed, meter_provider)."""
    from opentelemetry import metrics as _metrics
    from opentelemetry.sdk.metrics import MeterProvider

    readers: list[Any] = []
    prom_ok = False
    if prometheus:
        try:
            from opentelemetry.exporter.prometheus import PrometheusMetricReader

            readers.append(PrometheusMetricReader())
            prom_ok = True
        except ImportError:
            logger.warning(
                "observability: Prometheus reader unavailable; "
                "`pip install kailash[telemetry]` pulls opentelemetry-exporter-prometheus"
            )

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.metrics.export import (
                PeriodicExportingMetricReader,
            )

            readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=otlp_endpoint)
                )
            )
        except ImportError:
            logger.warning(
                "observability: OTLP metric exporter unavailable; "
                "install kailash[telemetry]"
            )

    if not readers:
        return (False, prom_ok, None)

    current = _metrics.get_meter_provider()
    if not _provider_is_unset(current) and not force:
        logger.info(
            "observability: MeterProvider already configured (%s); not overriding "
            "(pass force=True to override)",
            type(current).__name__,
        )
        return (True, prom_ok, None)

    provider = MeterProvider(resource=resource, metric_readers=readers)
    _metrics.set_meter_provider(provider)
    return (True, prom_ok, provider)


def _configure_traces(resource, otlp_endpoint, force):
    """Returns (traces_exported, tracer_provider)."""
    if not otlp_endpoint:
        return (False, None)
    from opentelemetry import trace as _trace

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "observability: OTLP span exporter unavailable; install kailash[telemetry]"
        )
        return (False, None)

    current = _trace.get_tracer_provider()
    if not _provider_is_unset(current) and not force:
        logger.info(
            "observability: TracerProvider already configured (%s); not overriding",
            type(current).__name__,
        )
        return (True, None)

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
    )
    _trace.set_tracer_provider(provider)
    return (True, provider)


def _configure_logs(resource, otlp_endpoint):
    """Returns (logs_exported, logger_provider)."""
    if not otlp_endpoint:
        return (False, None)
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
            OTLPLogExporter,
        )
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    except ImportError:
        logger.warning(
            "observability: OTLP log exporter unavailable; install kailash[telemetry]"
        )
        return (False, None)

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=otlp_endpoint))
    )
    set_logger_provider(provider)
    return (True, provider)
