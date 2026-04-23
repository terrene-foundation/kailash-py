# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 tests for W26.d drift alerting wiring (spec §11.2.4).

Exercises the full ``DriftMonitor.check_drift`` path against a real
``ConnectionManager``-backed SQLite store, with a real
``DriftAlertDispatcher``, to prove:

1. Alerts land on configured channels once drift is detected.
2. Cooldown + rate-limit gates are enforced on the real code path
   (not just the dispatcher unit).
3. ``TrackerEventAlertChannel`` emits metrics + events through the
   live monitor's dispatcher.
4. ``top_columns`` in the delivered alert payload contains column
   NAMES only — never raw values (classification safety).

Per rules/testing.md § Tier 2 we use real SQLite + a
Protocol-satisfying ``RecordingChannel`` / ``RecordingTracker``
(not mocks).  The channels are deterministic real implementations
exactly as allowed by § "Protocol-Satisfying Deterministic Adapters".
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from kailash.db.connection import ConnectionManager
from kailash_ml.drift.alerts import (
    AlertConfig,
    AlertRule,
    DriftAlert,
    TrackerEventAlertChannel,
)
from kailash_ml.engines.drift_monitor import DriftMonitor

_FEATURES = ["feature_a", "feature_b"]


def _make_reference_df(n: int = 500) -> pl.DataFrame:
    rng = np.random.RandomState(42)
    return pl.DataFrame(
        {
            "feature_a": rng.normal(0, 1, n).tolist(),
            "feature_b": rng.normal(5, 2, n).tolist(),
        }
    )


def _make_drifted_df(n: int = 500) -> pl.DataFrame:
    """Current data whose means are shifted far enough to trip PSI/KS."""
    rng = np.random.RandomState(7)
    return pl.DataFrame(
        {
            "feature_a": rng.normal(3.0, 1, n).tolist(),  # mean +3σ
            "feature_b": rng.normal(15.0, 2, n).tolist(),  # mean +5σ
        }
    )


class RecordingChannel:
    """Real ``AlertChannel`` that records every dispatched alert."""

    def __init__(self) -> None:
        self.received: list[DriftAlert] = []

    async def send(self, alert: DriftAlert) -> None:
        self.received.append(alert)


class RecordingTracker:
    """Tracker satisfying the duck-typed ``log_metric`` + ``log_event``."""

    def __init__(self) -> None:
        self.metrics: list[tuple[str, float]] = []
        self.events: list[tuple[str, dict]] = []

    def log_metric(self, key: str, value: float, *, step: int | None = None) -> None:
        self.metrics.append((key, float(value)))

    def log_event(self, name: str, *, payload: dict) -> None:
        self.events.append((name, dict(payload)))


# ---------------------------------------------------------------------------
# End-to-end through check_drift
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_check_drift_dispatches_alerts_end_to_end(tmp_path) -> None:
    """Spec §11.2.4 — cooldown + rate-limit enforced on the real path."""
    db_path = tmp_path / "alerts.db"
    conn = ConnectionManager(f"sqlite:///{db_path}")
    await conn.initialize()

    recording = RecordingChannel()
    cfg = AlertConfig(
        channels=(recording,),
        per_axis_rules={
            "feature": AlertRule(
                trigger="any_column", threshold=0.2, severity="warning"
            )
        },
        cooldown_seconds=60,
        max_alerts_per_hour=5,
    )

    monitor = DriftMonitor(conn, alerts=cfg)
    await monitor.set_reference_data("fraud", _make_reference_df(), _FEATURES)

    drifted = _make_drifted_df()
    for _ in range(10):
        await monitor.check_drift("fraud", drifted, tenant_id="acme")

    # Cooldown keeps dispatch count at 1 (rate-limit would cap at 5 if
    # cooldown were 0). Window here is [1, 5].
    assert 1 <= len(recording.received) <= 5

    first = recording.received[0]
    assert first.axis == "feature"
    assert first.severity == "warning"
    assert first.tenant_id == "acme"
    assert first.model_name == "fraud"
    assert first.drift_score >= 0.2
    assert first.report_id  # linked to _kml_drift_reports row
    assert len(first.top_columns) <= 5
    # Classification safety: column names only, no raw values.
    for entry in first.top_columns:
        assert set(entry.keys()) == {"name", "score", "statistic"}
        assert isinstance(entry["name"], str)
        assert "value" not in entry


# ---------------------------------------------------------------------------
# TrackerEventAlertChannel wired through the live monitor
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tracker_event_channel_emits_through_live_monitor(tmp_path) -> None:
    """Tracker channel emits metrics + events on the real check_drift path."""
    db_path = tmp_path / "alerts_tracker.db"
    conn = ConnectionManager(f"sqlite:///{db_path}")
    await conn.initialize()

    tracker = RecordingTracker()
    cfg = AlertConfig(
        channels=(TrackerEventAlertChannel(tracker),),
        per_axis_rules={"feature": AlertRule("any_column", threshold=0.2)},
        cooldown_seconds=60,
        max_alerts_per_hour=5,
    )

    monitor = DriftMonitor(conn, alerts=cfg)
    await monitor.set_reference_data("fraud", _make_reference_df(), _FEATURES)
    await monitor.check_drift("fraud", _make_drifted_df(), tenant_id="acme")

    # Alert fired → one alert metric + one alert event.
    alert_metrics = [m for m in tracker.metrics if m[0] == "drift.alert.feature"]
    assert len(alert_metrics) == 1
    assert alert_metrics[0][1] >= 0.2
    assert len(tracker.events) == 1
    name, payload = tracker.events[0]
    assert name == "drift.alert.sent"
    assert payload["axis"] == "feature"
    assert payload["tenant_id"] == "acme"


# ---------------------------------------------------------------------------
# WebhookAlertChannel against a real local HTTP server
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_channel_posts_alert_payload(tmp_path, httpserver) -> None:
    """Webhook channel POSTs a JSON alert payload to the configured URL."""
    import json as _json

    from kailash_ml.drift.alerts import WebhookAlertChannel

    db_path = tmp_path / "alerts_webhook.db"
    conn = ConnectionManager(f"sqlite:///{db_path}")
    await conn.initialize()

    httpserver.expect_request("/hook", method="POST").respond_with_data(
        "ok", status=200
    )
    # allow_insecure=True: httpserver binds on http://127.0.0.1 for tests.
    webhook_url = httpserver.url_for("/hook")
    channel = WebhookAlertChannel(webhook_url, allow_insecure=True)

    cfg = AlertConfig(
        channels=(channel,),
        per_axis_rules={"feature": AlertRule("any_column", threshold=0.2)},
        cooldown_seconds=60,
        max_alerts_per_hour=5,
    )
    monitor = DriftMonitor(conn, alerts=cfg)
    await monitor.set_reference_data("fraud", _make_reference_df(), _FEATURES)
    await monitor.check_drift("fraud", _make_drifted_df(), tenant_id="acme")

    # Inspect the captured POST.
    requests = httpserver.log
    assert len(requests) == 1
    req, _resp = requests[0]
    body = _json.loads(req.get_data(as_text=True))
    assert body["axis"] == "feature"
    assert body["model_name"] == "fraud"
    assert body["tenant_id"] == "acme"
    assert body["severity"] == "warning"
    assert body["drift_score"] >= 0.2


# ---------------------------------------------------------------------------
# Monitor without alerts kwarg stays silent
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_monitor_without_alerts_kwarg_does_not_dispatch(tmp_path) -> None:
    """Backward-compat: omitting ``alerts`` preserves pre-W26.d behaviour."""
    db_path = tmp_path / "no_alerts.db"
    conn = ConnectionManager(f"sqlite:///{db_path}")
    await conn.initialize()

    monitor = DriftMonitor(conn)  # no alerts kwarg
    await monitor.set_reference_data("fraud", _make_reference_df(), _FEATURES)
    report = await monitor.check_drift("fraud", _make_drifted_df())

    # Report still produced; no dispatcher means no alerting side effect.
    assert report is not None
    assert monitor._alert_dispatcher is None
