# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Drift alerting surface — ``AlertConfig`` + dispatcher + channels.

This module closes W26.d of the drift monitoring shard (see
``specs/ml-drift.md §6``).  The dispatcher lives in-memory per
``DriftMonitor`` instance; cross-process coordination is explicitly
out of scope for this shard.

Design points:

* ``AlertConfig`` / ``AlertRule`` / ``DriftAlert`` are frozen, slotted
  dataclasses carrying no classified values (column NAMES only, never
  raw feature values — per ``rules/event-payload-classification.md``).
* ``AlertChannel`` is a ``typing.Protocol`` (duck-typed, subclass-free).
* Two first-class channels ship:
    - :class:`WebhookAlertChannel` — HTTPS POST via ``httpx``.
    - :class:`TrackerEventAlertChannel` — in-band emission to the
      same duck-typed tracker ``DriftMonitor`` already holds.
* :class:`DriftAlertDispatcher` enforces per-``(tenant, model, axis)``
  cooldown + per-``(tenant, model)`` rolling-hour rate limit and
  dispatches to every configured channel.  Per-channel exceptions are
  caught and logged; sibling channels still fire.

Alert payloads encode ``top_columns`` as
``[{"name": str, "score": float, "statistic": str}]`` — no raw
feature values are serialized.  Callers who need richer payloads
(e.g. ``ModelExplainer``) wire them outside the alert surface.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol, runtime_checkable

from kailash_ml.drift._types import DriftReport, FeatureDriftResult

logger = logging.getLogger(__name__)

__all__ = [
    "AlertChannel",
    "AlertConfig",
    "AlertRule",
    "DriftAlert",
    "DriftAlertDispatcher",
    "TrackerEventAlertChannel",
    "WebhookAlertChannel",
]


# ---------------------------------------------------------------------------
# Dataclasses (spec §6.1 + §6.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AlertRule:
    """Single-axis alert trigger.

    Per ``specs/ml-drift.md §6.1``, the trigger semantics are:

    * ``"any_column"`` — fire when the maximum per-column drift score
      observed on the axis is ``>= threshold``.
    * ``"fraction_columns"`` — fire when the fraction of columns marked
      drifted is ``>= threshold``.
    * ``"model_score"`` — fire when the axis-level aggregate drift score
      (max across columns, per ``§3.5``) is ``>= threshold``.
    """

    trigger: Literal["any_column", "fraction_columns", "model_score"]
    threshold: float
    severity: Literal["info", "warning", "critical"] = "warning"


@dataclass(frozen=True, slots=True)
class AlertConfig:
    """Dispatcher configuration.

    ``channels`` is a ``tuple`` (not ``list``) because ``frozen=True``
    dataclasses only hash cleanly with immutable fields.  The tuple
    ordering is preserved during dispatch.
    """

    channels: tuple["AlertChannel", ...] = ()
    per_axis_rules: dict[str, AlertRule] = field(default_factory=dict)
    cooldown_seconds: int = 900
    max_alerts_per_hour: int = 12


@dataclass(frozen=True, slots=True)
class DriftAlert:
    """Alert payload delivered to channels.

    ``top_columns`` is a list of dicts with fixed keys
    ``{"name", "score", "statistic"}``.  Values are never included
    per ``rules/event-payload-classification.md``.
    """

    alert_id: str
    tenant_id: str
    model_name: str
    model_version: int
    axis: Literal["feature", "prediction", "performance"]
    trigger_rule: str
    severity: Literal["info", "warning", "critical"]
    detected_at: datetime
    drift_score: float
    top_columns: list[dict]  # [{"name": str, "score": float, "statistic": str}]
    report_id: str
    dashboard_url: str | None = None


# ---------------------------------------------------------------------------
# Channel Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AlertChannel(Protocol):
    """Duck-typed alert-channel contract.

    Implementations must be async-callable via ``send(alert)``.  They
    MAY raise; the dispatcher catches per-channel exceptions and
    continues with sibling channels.
    """

    async def send(self, alert: DriftAlert) -> None: ...


# ---------------------------------------------------------------------------
# First-class channels
# ---------------------------------------------------------------------------


def _alert_to_jsonable(alert: DriftAlert) -> dict[str, Any]:
    """Serialize a ``DriftAlert`` into a JSON-safe dict.

    ``detected_at`` is emitted in ISO 8601 UTC form.  Every other
    field already round-trips through ``dataclasses.asdict``.
    """
    payload = asdict(alert)
    payload["detected_at"] = alert.detected_at.isoformat()
    return payload


class WebhookAlertChannel:
    """HTTPS webhook channel.

    POSTs the JSON-serialized alert to the configured URL.  Emits
    ``drift.alert.webhook.error`` on non-2xx responses and raises so
    the dispatcher's channel-error handler can log + isolate.
    """

    def __init__(
        self,
        url: str,
        *,
        timeout_seconds: float = 10.0,
        allow_insecure: bool = False,
        headers: dict[str, str] | None = None,
    ) -> None:
        if not url:
            raise ValueError("WebhookAlertChannel.url must be non-empty")
        if not allow_insecure and not url.lower().startswith("https://"):
            raise ValueError(
                "WebhookAlertChannel requires HTTPS; pass allow_insecure=True "
                "to opt into plaintext (tests, localhost)."
            )
        self._url = url
        self._timeout_seconds = float(timeout_seconds)
        self._headers = dict(headers) if headers else {}
        self._headers.setdefault("Content-Type", "application/json")

    def _serialize_payload(self, alert: DriftAlert) -> str:
        """Exposed for unit tests — mirrors what ``send`` POSTs."""
        return json.dumps(_alert_to_jsonable(alert), sort_keys=True)

    async def send(self, alert: DriftAlert) -> None:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - httpx is a base dep
            raise ImportError(
                "WebhookAlertChannel requires httpx>=0.27 (already a base "
                "dependency of kailash-ml); install with `pip install httpx`."
            ) from exc

        body = self._serialize_payload(alert)
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(self._url, content=body, headers=self._headers)

        if response.status_code >= 400:
            logger.error(
                "drift.alert.webhook.error",
                extra={
                    "alert_id": alert.alert_id,
                    "webhook_status": response.status_code,
                    "webhook_url_host": _host_only(self._url),
                },
            )
            raise RuntimeError(
                f"WebhookAlertChannel POST returned {response.status_code} "
                f"(alert_id={alert.alert_id})"
            )


def _host_only(url: str) -> str:
    """Extract host from URL for logging (avoid leaking full path)."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return parsed.hostname or "<unparseable>"
    except Exception:
        return "<unparseable>"


class TrackerEventAlertChannel:
    """In-band tracker emission channel.

    Accepts the same duck-typed tracker the ``DriftMonitor`` holds.
    Emits ``log_metric(f"drift.alert.{axis}", drift_score)`` for every
    alert and ``log_event("drift.alert.sent", payload)`` when the
    tracker exposes that method.
    """

    def __init__(self, tracker: Any) -> None:
        if tracker is None:
            raise ValueError("TrackerEventAlertChannel.tracker must not be None")
        self._tracker = tracker

    async def send(self, alert: DriftAlert) -> None:
        metric_key = f"drift.alert.{alert.axis}"
        try:
            self._tracker.log_metric(metric_key, float(alert.drift_score), step=None)
        except TypeError:
            # Tracker does not accept step= kwarg — fall back to positional.
            self._tracker.log_metric(metric_key, float(alert.drift_score))

        log_event = getattr(self._tracker, "log_event", None)
        if callable(log_event):
            log_event("drift.alert.sent", payload=_alert_to_jsonable(alert))


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class DriftAlertDispatcher:
    """Evaluate alert rules and dispatch to configured channels.

    State (cooldown timestamps + rolling hourly counts) lives in memory
    per ``DriftMonitor`` instance.  Cross-process coordination is an
    explicit non-goal for W26.d (see spec §6.2 + shard boundaries).
    """

    def __init__(self, config: AlertConfig) -> None:
        self._cfg = config
        # (tenant_id, model_name, axis) -> last detected_at
        self._last_alert_at: dict[tuple[str, str, str], datetime] = {}
        # (tenant_id, model_name) -> bounded rolling window of detected_at
        # stamps inside the last hour.  Bounded at 2*max_alerts_per_hour
        # so a burst-hour cannot unbound the deque.
        self._hourly_window: dict[tuple[str, str], deque[datetime]] = {}

    async def evaluate_and_dispatch(
        self,
        *,
        report: "DriftReport",
        tenant_id: str,
        model_name: str,
        model_version: int,
        report_id: str,
    ) -> list[DriftAlert]:
        """Evaluate every configured rule and fire matching alerts.

        Returns the list of alerts that were actually dispatched
        (post-suppression).  Per-channel exceptions are caught — sibling
        channels still fire.
        """
        if not self._cfg.per_axis_rules:
            return []

        sent: list[DriftAlert] = []
        now = datetime.now(timezone.utc)

        # Precompute axis inputs once (feature axis is the only one
        # DriftReport currently carries; prediction/performance follow
        # the same shape when the serving/reconciliation paths land).
        axis_inputs = self._axis_inputs_from_report(report)

        for axis, rule in self._cfg.per_axis_rules.items():
            inputs = axis_inputs.get(axis)
            if inputs is None:
                # Axis not represented in this report — skip silently.
                continue

            triggered, axis_score = self._evaluate_rule(rule, inputs)
            logger.debug(
                "drift.alert.evaluated",
                extra={
                    "tenant_id": tenant_id,
                    "model_name": model_name,
                    "axis": axis,
                    "trigger": rule.trigger,
                    "threshold": rule.threshold,
                    "score": axis_score,
                    "triggered": triggered,
                },
            )
            if not triggered:
                continue

            # Cooldown suppression.
            cooldown_key = (tenant_id, model_name, axis)
            last_at = self._last_alert_at.get(cooldown_key)
            if last_at is not None:
                elapsed = (now - last_at).total_seconds()
                if elapsed < self._cfg.cooldown_seconds:
                    logger.debug(
                        "drift.alert.suppressed",
                        extra={
                            "tenant_id": tenant_id,
                            "model_name": model_name,
                            "axis": axis,
                            "cooldown_remaining_s": (
                                self._cfg.cooldown_seconds - elapsed
                            ),
                        },
                    )
                    continue

            # Rate limiting.
            rate_key = (tenant_id, model_name)
            window = self._hourly_window.setdefault(
                rate_key,
                deque(maxlen=max(2 * self._cfg.max_alerts_per_hour, 1)),
            )
            self._trim_window(window, now)
            if len(window) >= self._cfg.max_alerts_per_hour:
                logger.warning(
                    "drift.alert.rate_limited",
                    extra={
                        "tenant_id": tenant_id,
                        "model_name": model_name,
                        "current_count": len(window),
                        "limit": self._cfg.max_alerts_per_hour,
                    },
                )
                continue

            top_columns = self._top_columns(report)
            alert = DriftAlert(
                alert_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                model_name=model_name,
                model_version=model_version,
                axis=axis,  # type: ignore[arg-type]
                trigger_rule=rule.trigger,
                severity=rule.severity,
                detected_at=now,
                drift_score=float(axis_score),
                top_columns=top_columns,
                report_id=report_id,
                dashboard_url=None,
            )

            # Update state BEFORE dispatch so a crashing channel cannot
            # bypass cooldown on retry.
            self._last_alert_at[cooldown_key] = now
            window.append(now)

            await self._dispatch_to_channels(alert)
            sent.append(alert)

            logger.info(
                "drift.alert.sent",
                extra={
                    "alert_id": alert.alert_id,
                    "severity": alert.severity,
                    "channel_count": len(self._cfg.channels),
                },
            )

        return sent

    # ------------------------------------------------------------------
    # Rule evaluation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _axis_inputs_from_report(
        report: "DriftReport",
    ) -> dict[str, dict[str, Any]]:
        """Project the report into per-axis evaluation inputs.

        Returns a mapping with one entry per axis the report carries.
        For W26.d this is ``{"feature": {...}}``; prediction/performance
        will slot in here when their drift paths land.
        """
        feature_results: list["FeatureDriftResult"] = list(report.feature_results)
        if not feature_results:
            return {}
        scores = [_column_score(r) for r in feature_results]
        drifted = [r for r in feature_results if r.drift_detected]
        return {
            "feature": {
                "scores": scores,
                "total_columns": len(feature_results),
                "drifted_columns": len(drifted),
            }
        }

    @staticmethod
    def _evaluate_rule(
        rule: AlertRule,
        inputs: dict[str, Any],
    ) -> tuple[bool, float]:
        """Return ``(triggered, score)`` for a single rule / axis pair."""
        scores: list[float] = inputs.get("scores", [])
        total = int(inputs.get("total_columns", 0))
        drifted = int(inputs.get("drifted_columns", 0))
        if rule.trigger == "any_column":
            top = max(scores) if scores else 0.0
            return top >= rule.threshold, top
        if rule.trigger == "fraction_columns":
            frac = (drifted / total) if total > 0 else 0.0
            return frac >= rule.threshold, frac
        if rule.trigger == "model_score":
            top = max(scores) if scores else 0.0
            return top >= rule.threshold, top
        raise ValueError(f"Unknown AlertRule.trigger: {rule.trigger!r}")

    @staticmethod
    def _top_columns(report: "DriftReport") -> list[dict]:
        """Top-5 drifted column descriptors, sorted by score desc.

        Each entry is ``{"name": str, "score": float, "statistic": str}``
        — no raw values per ``rules/event-payload-classification.md``.
        """
        enriched: list[tuple[float, str, str]] = []
        for r in report.feature_results:
            score = _column_score(r)
            stat = _primary_statistic(r)
            enriched.append((score, r.feature_name, stat))
        enriched.sort(key=lambda tup: tup[0], reverse=True)
        top = enriched[:5]
        return [
            {"name": name, "score": float(score), "statistic": stat}
            for (score, name, stat) in top
        ]

    # ------------------------------------------------------------------
    # Dispatch + windowing
    # ------------------------------------------------------------------

    async def _dispatch_to_channels(self, alert: DriftAlert) -> None:
        for channel in self._cfg.channels:
            try:
                await channel.send(alert)
            except Exception:
                logger.exception(
                    "drift.alert.channel_error",
                    extra={
                        "channel_type": type(channel).__name__,
                        "alert_id": alert.alert_id,
                    },
                )

    @staticmethod
    def _trim_window(window: deque[datetime], now: datetime) -> None:
        cutoff = now - timedelta(hours=1)
        while window and window[0] < cutoff:
            window.popleft()


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _column_score(result: "FeatureDriftResult") -> float:
    """Collapse a ``FeatureDriftResult`` into a single scalar for comparison.

    Takes the max of the finite statistic values the result carries.
    Falls back to 0.0 when all statistics are ``None`` / non-finite.
    """
    import math

    candidates: list[float] = []
    if math.isfinite(result.psi):
        candidates.append(float(result.psi))
    # ks_statistic is 0..1 where 1 is maximally-drifted.
    if math.isfinite(result.ks_statistic):
        candidates.append(float(result.ks_statistic))
    if result.jsd is not None and math.isfinite(result.jsd):
        candidates.append(float(result.jsd))
    if result.new_category_fraction is not None and math.isfinite(
        result.new_category_fraction
    ):
        candidates.append(float(result.new_category_fraction))
    if result.chi2_statistic is not None and math.isfinite(result.chi2_statistic):
        # chi² can be unbounded; don't let it dominate — normalise by
        # saturating at 1.0 so the per-column score remains comparable
        # across statistics with bounded ranges.
        candidates.append(min(float(result.chi2_statistic), 1.0))
    return max(candidates) if candidates else 0.0


def _primary_statistic(result: "FeatureDriftResult") -> str:
    """Pick the statistic that contributed the max score.

    Used purely for the ``top_columns`` payload — the operator sees
    which statistic flagged the column.
    """
    import math

    pairs: list[tuple[float, str]] = []
    if math.isfinite(result.psi):
        pairs.append((float(result.psi), "psi"))
    if math.isfinite(result.ks_statistic):
        pairs.append((float(result.ks_statistic), "ks"))
    if result.jsd is not None and math.isfinite(result.jsd):
        pairs.append((float(result.jsd), "jsd"))
    if result.new_category_fraction is not None and math.isfinite(
        result.new_category_fraction
    ):
        pairs.append((float(result.new_category_fraction), "new_category_fraction"))
    if result.chi2_statistic is not None and math.isfinite(result.chi2_statistic):
        pairs.append((min(float(result.chi2_statistic), 1.0), "chi2"))
    if not pairs:
        return "unknown"
    pairs.sort(key=lambda p: p[0], reverse=True)
    return pairs[0][1]
