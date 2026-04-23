# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for the W26.d drift alerting surface.

Covers:
  * ``AlertRule`` / ``AlertConfig`` / ``DriftAlert`` dataclass contracts
    (frozen, slotted, default values).
  * Rule evaluation for all three triggers
    (``any_column``, ``fraction_columns``, ``model_score``).
  * Cooldown suppression.
  * Rate-limit suppression.
  * ``top_columns`` shape and classification-safety.
  * ``WebhookAlertChannel._serialize_payload`` shape + HTTPS gate.
  * ``TrackerEventAlertChannel`` metric + event emission paths.

All tests use a ``RecordingChannel`` real class (``AlertChannel``
Protocol satisfied) rather than a mock — see rules/testing.md
§ "Protocol-Satisfying Deterministic Adapters Are Not Mocks".
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from datetime import datetime, timedelta, timezone

import pytest
from kailash_ml.drift.alerts import (
    AlertChannel,
    AlertConfig,
    AlertRule,
    DriftAlert,
    DriftAlertDispatcher,
    TrackerEventAlertChannel,
    WebhookAlertChannel,
)
from kailash_ml.engines.drift_monitor import DriftReport, FeatureDriftResult


# ---------------------------------------------------------------------------
# Test doubles — real classes satisfying the Protocol
# ---------------------------------------------------------------------------


class RecordingChannel:
    """Real ``AlertChannel`` impl that records every delivered alert."""

    def __init__(self) -> None:
        self.received: list[DriftAlert] = []

    async def send(self, alert: DriftAlert) -> None:
        self.received.append(alert)


class RaisingChannel:
    """Channel that always raises — used to exercise isolation."""

    async def send(self, alert: DriftAlert) -> None:
        raise RuntimeError("boom")


class RecordingTracker:
    """Duck-typed tracker satisfying ``log_metric`` + ``log_event``."""

    def __init__(self) -> None:
        self.metrics: list[tuple[str, float]] = []
        self.events: list[tuple[str, dict]] = []

    def log_metric(self, key: str, value: float, *, step: int | None = None) -> None:
        self.metrics.append((key, float(value)))

    def log_event(self, name: str, *, payload: dict) -> None:
        self.events.append((name, dict(payload)))


class MinimalTracker:
    """Tracker without ``log_event`` — exercises the fallback path."""

    def __init__(self) -> None:
        self.metrics: list[tuple[str, float]] = []

    def log_metric(self, key: str, value: float, *, step: int | None = None) -> None:
        self.metrics.append((key, float(value)))


# ---------------------------------------------------------------------------
# Helpers — construct synthetic DriftReports without touching stats code
# ---------------------------------------------------------------------------


def _result(
    name: str,
    *,
    psi: float = 0.0,
    ks_statistic: float = 0.0,
    ks_pvalue: float = 1.0,
    drift_detected: bool = False,
    jsd: float | None = None,
    chi2_statistic: float | None = None,
) -> FeatureDriftResult:
    return FeatureDriftResult(
        feature_name=name,
        psi=psi,
        ks_statistic=ks_statistic,
        ks_pvalue=ks_pvalue,
        drift_detected=drift_detected,
        drift_type="severe" if drift_detected else "none",
        jsd=jsd,
        chi2_statistic=chi2_statistic,
    )


def _report(results: list[FeatureDriftResult]) -> DriftReport:
    now = datetime.now(timezone.utc)
    return DriftReport(
        model_name="fraud",
        feature_results=results,
        overall_drift_detected=any(r.drift_detected for r in results),
        overall_severity="severe" if any(r.drift_detected for r in results) else "none",
        checked_at=now,
        reference_set_at=now - timedelta(minutes=5),
        sample_size_reference=500,
        sample_size_current=500,
    )


# ---------------------------------------------------------------------------
# Dataclass contracts
# ---------------------------------------------------------------------------


class TestAlertDataclasses:
    def test_alert_rule_frozen_slots(self) -> None:
        rule = AlertRule(trigger="any_column", threshold=0.2)
        assert rule.severity == "warning"  # default
        assert rule.trigger == "any_column"
        assert rule.threshold == pytest.approx(0.2)
        # frozen=True
        with pytest.raises(dataclasses.FrozenInstanceError):
            rule.threshold = 0.5  # type: ignore[misc]

    def test_alert_config_defaults(self) -> None:
        cfg = AlertConfig()
        assert cfg.channels == ()
        assert cfg.per_axis_rules == {}
        assert cfg.cooldown_seconds == 900
        assert cfg.max_alerts_per_hour == 12

    def test_alert_config_channels_is_tuple(self) -> None:
        """`frozen=True` requires hashable/immutable channel collection."""
        ch = RecordingChannel()
        cfg = AlertConfig(channels=(ch,))
        assert isinstance(cfg.channels, tuple)
        assert cfg.channels[0] is ch

    def test_drift_alert_frozen(self) -> None:
        alert = DriftAlert(
            alert_id="abc",
            tenant_id="",
            model_name="fraud",
            model_version=0,
            axis="feature",
            trigger_rule="any_column",
            severity="warning",
            detected_at=datetime.now(timezone.utc),
            drift_score=0.42,
            top_columns=[],
            report_id="r-1",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            alert.drift_score = 0.99  # type: ignore[misc]
        assert alert.dashboard_url is None


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_recording_channel_satisfies_protocol(self) -> None:
        assert isinstance(RecordingChannel(), AlertChannel)

    def test_tracker_channel_satisfies_protocol(self) -> None:
        tracker = RecordingTracker()
        ch = TrackerEventAlertChannel(tracker)
        assert isinstance(ch, AlertChannel)

    def test_webhook_channel_satisfies_protocol(self) -> None:
        ch = WebhookAlertChannel("https://example.com/hook")
        assert isinstance(ch, AlertChannel)


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRuleEvaluation:
    async def test_any_column_fires_when_max_score_meets_threshold(self) -> None:
        channel = RecordingChannel()
        cfg = AlertConfig(
            channels=(channel,),
            per_axis_rules={"feature": AlertRule("any_column", threshold=0.2)},
        )
        dispatcher = DriftAlertDispatcher(cfg)
        report = _report(
            [
                _result("a", psi=0.05),
                _result("b", psi=0.3, drift_detected=True),
            ]
        )
        sent = await dispatcher.evaluate_and_dispatch(
            report=report,
            tenant_id="",
            model_name="fraud",
            model_version=0,
            report_id="r-1",
        )
        assert len(sent) == 1
        assert len(channel.received) == 1
        assert channel.received[0].drift_score >= 0.2

    async def test_any_column_suppresses_below_threshold(self) -> None:
        channel = RecordingChannel()
        cfg = AlertConfig(
            channels=(channel,),
            per_axis_rules={"feature": AlertRule("any_column", threshold=0.5)},
        )
        dispatcher = DriftAlertDispatcher(cfg)
        report = _report([_result("a", psi=0.1), _result("b", psi=0.2)])
        sent = await dispatcher.evaluate_and_dispatch(
            report=report,
            tenant_id="",
            model_name="fraud",
            model_version=0,
            report_id="r-1",
        )
        assert sent == []
        assert channel.received == []

    async def test_fraction_columns_fires_when_majority_drifted(self) -> None:
        channel = RecordingChannel()
        cfg = AlertConfig(
            channels=(channel,),
            per_axis_rules={"feature": AlertRule("fraction_columns", threshold=0.5)},
        )
        dispatcher = DriftAlertDispatcher(cfg)
        report = _report(
            [
                _result("a", drift_detected=True),
                _result("b", drift_detected=True),
                _result("c", drift_detected=False),
            ]
        )
        sent = await dispatcher.evaluate_and_dispatch(
            report=report,
            tenant_id="",
            model_name="fraud",
            model_version=0,
            report_id="r-1",
        )
        assert len(sent) == 1
        # 2/3 drifted = ~0.67 >= 0.5
        assert sent[0].drift_score >= 0.5

    async def test_model_score_uses_max_column_score(self) -> None:
        channel = RecordingChannel()
        cfg = AlertConfig(
            channels=(channel,),
            per_axis_rules={"feature": AlertRule("model_score", threshold=0.3)},
        )
        dispatcher = DriftAlertDispatcher(cfg)
        report = _report([_result("a", psi=0.35, drift_detected=True)])
        sent = await dispatcher.evaluate_and_dispatch(
            report=report,
            tenant_id="",
            model_name="fraud",
            model_version=0,
            report_id="r-1",
        )
        assert len(sent) == 1

    async def test_no_axis_match_no_dispatch(self) -> None:
        channel = RecordingChannel()
        cfg = AlertConfig(
            channels=(channel,),
            # Only prediction rule — but report carries feature axis.
            per_axis_rules={"prediction": AlertRule("any_column", threshold=0.1)},
        )
        dispatcher = DriftAlertDispatcher(cfg)
        report = _report([_result("a", psi=0.5, drift_detected=True)])
        sent = await dispatcher.evaluate_and_dispatch(
            report=report,
            tenant_id="",
            model_name="fraud",
            model_version=0,
            report_id="r-1",
        )
        assert sent == []


# ---------------------------------------------------------------------------
# Cooldown + rate limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCooldownAndRateLimit:
    async def test_cooldown_suppresses_duplicate_within_window(self) -> None:
        channel = RecordingChannel()
        cfg = AlertConfig(
            channels=(channel,),
            per_axis_rules={"feature": AlertRule("model_score", threshold=0.1)},
            cooldown_seconds=60,
            max_alerts_per_hour=100,
        )
        dispatcher = DriftAlertDispatcher(cfg)
        report = _report([_result("a", psi=0.5, drift_detected=True)])

        first = await dispatcher.evaluate_and_dispatch(
            report=report,
            tenant_id="acme",
            model_name="fraud",
            model_version=0,
            report_id="r-1",
        )
        second = await dispatcher.evaluate_and_dispatch(
            report=report,
            tenant_id="acme",
            model_name="fraud",
            model_version=0,
            report_id="r-2",
        )
        assert len(first) == 1
        assert second == []
        assert len(channel.received) == 1

    async def test_cooldown_allows_after_window_expires(self) -> None:
        channel = RecordingChannel()
        cfg = AlertConfig(
            channels=(channel,),
            per_axis_rules={"feature": AlertRule("model_score", threshold=0.1)},
            cooldown_seconds=60,
            max_alerts_per_hour=100,
        )
        dispatcher = DriftAlertDispatcher(cfg)
        report = _report([_result("a", psi=0.5, drift_detected=True)])

        first = await dispatcher.evaluate_and_dispatch(
            report=report,
            tenant_id="acme",
            model_name="fraud",
            model_version=0,
            report_id="r-1",
        )
        assert len(first) == 1

        # Artificially age the last-alert stamp past the cooldown window.
        past = datetime.now(timezone.utc) - timedelta(seconds=120)
        dispatcher._last_alert_at[("acme", "fraud", "feature")] = past

        second = await dispatcher.evaluate_and_dispatch(
            report=report,
            tenant_id="acme",
            model_name="fraud",
            model_version=0,
            report_id="r-2",
        )
        assert len(second) == 1
        assert len(channel.received) == 2

    async def test_rate_limit_caps_alerts_per_hour(self) -> None:
        channel = RecordingChannel()
        cfg = AlertConfig(
            channels=(channel,),
            per_axis_rules={"feature": AlertRule("model_score", threshold=0.1)},
            # Cooldown disabled so only rate-limit gates dispatch.
            cooldown_seconds=0,
            max_alerts_per_hour=3,
        )
        dispatcher = DriftAlertDispatcher(cfg)
        report = _report([_result("a", psi=0.5, drift_detected=True)])
        for i in range(5):
            await dispatcher.evaluate_and_dispatch(
                report=report,
                tenant_id="acme",
                model_name="fraud",
                model_version=0,
                report_id=f"r-{i}",
            )
        assert len(channel.received) == 3  # capped at max_alerts_per_hour


# ---------------------------------------------------------------------------
# top_columns hygiene
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTopColumns:
    async def test_top_columns_max_five_sorted_desc(self) -> None:
        channel = RecordingChannel()
        cfg = AlertConfig(
            channels=(channel,),
            per_axis_rules={"feature": AlertRule("any_column", threshold=0.1)},
        )
        dispatcher = DriftAlertDispatcher(cfg)
        results = [
            _result(f"f{i}", psi=0.1 * (i + 1), drift_detected=True) for i in range(8)
        ]
        report = _report(results)
        await dispatcher.evaluate_and_dispatch(
            report=report,
            tenant_id="",
            model_name="fraud",
            model_version=0,
            report_id="r-1",
        )
        alert = channel.received[0]
        assert len(alert.top_columns) == 5
        scores = [c["score"] for c in alert.top_columns]
        assert scores == sorted(scores, reverse=True)
        # Strict name-only — no `value` / raw feature fields.
        for entry in alert.top_columns:
            assert set(entry.keys()) == {"name", "score", "statistic"}
            assert "value" not in entry
            assert isinstance(entry["name"], str)


# ---------------------------------------------------------------------------
# Channel isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestChannelIsolation:
    async def test_raising_channel_does_not_suppress_sibling(self) -> None:
        recording = RecordingChannel()
        cfg = AlertConfig(
            channels=(RaisingChannel(), recording),
            per_axis_rules={"feature": AlertRule("any_column", threshold=0.1)},
        )
        dispatcher = DriftAlertDispatcher(cfg)
        report = _report([_result("a", psi=0.5, drift_detected=True)])
        sent = await dispatcher.evaluate_and_dispatch(
            report=report,
            tenant_id="",
            model_name="fraud",
            model_version=0,
            report_id="r-1",
        )
        assert len(sent) == 1
        assert len(recording.received) == 1


# ---------------------------------------------------------------------------
# Webhook channel
# ---------------------------------------------------------------------------


class TestWebhookAlertChannel:
    def test_rejects_http_by_default(self) -> None:
        with pytest.raises(ValueError, match="HTTPS"):
            WebhookAlertChannel("http://example.com/hook")

    def test_accepts_http_with_allow_insecure(self) -> None:
        ch = WebhookAlertChannel("http://127.0.0.1:9999/hook", allow_insecure=True)
        assert ch is not None

    def test_rejects_empty_url(self) -> None:
        with pytest.raises(ValueError):
            WebhookAlertChannel("")

    def test_serialize_payload_is_json_sorted(self) -> None:
        ch = WebhookAlertChannel("https://example.com/hook")
        alert = DriftAlert(
            alert_id="abc",
            tenant_id="acme",
            model_name="fraud",
            model_version=3,
            axis="feature",
            trigger_rule="any_column",
            severity="warning",
            detected_at=datetime(2026, 4, 23, 12, 0, 0, tzinfo=timezone.utc),
            drift_score=0.42,
            top_columns=[{"name": "x", "score": 0.42, "statistic": "psi"}],
            report_id="r-1",
        )
        body = ch._serialize_payload(alert)
        decoded = json.loads(body)
        assert decoded["alert_id"] == "abc"
        assert decoded["tenant_id"] == "acme"
        assert decoded["drift_score"] == pytest.approx(0.42)
        assert decoded["detected_at"].startswith("2026-04-23T12:00:00")
        # sorted keys
        keys = list(decoded.keys())
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Tracker channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTrackerEventAlertChannel:
    async def test_rejects_none_tracker(self) -> None:
        with pytest.raises(ValueError):
            TrackerEventAlertChannel(None)  # type: ignore[arg-type]

    async def test_emits_metric_and_event(self) -> None:
        tracker = RecordingTracker()
        ch = TrackerEventAlertChannel(tracker)
        alert = DriftAlert(
            alert_id="abc",
            tenant_id="",
            model_name="fraud",
            model_version=0,
            axis="feature",
            trigger_rule="any_column",
            severity="warning",
            detected_at=datetime.now(timezone.utc),
            drift_score=0.42,
            top_columns=[],
            report_id="r-1",
        )
        await ch.send(alert)
        assert tracker.metrics == [("drift.alert.feature", 0.42)]
        assert len(tracker.events) == 1
        name, payload = tracker.events[0]
        assert name == "drift.alert.sent"
        assert payload["alert_id"] == "abc"

    async def test_tracker_without_log_event_only_emits_metric(self) -> None:
        tracker = MinimalTracker()
        ch = TrackerEventAlertChannel(tracker)
        alert = DriftAlert(
            alert_id="abc",
            tenant_id="",
            model_name="fraud",
            model_version=0,
            axis="feature",
            trigger_rule="any_column",
            severity="warning",
            detected_at=datetime.now(timezone.utc),
            drift_score=0.5,
            top_columns=[],
            report_id="r-1",
        )
        await ch.send(alert)
        assert tracker.metrics == [("drift.alert.feature", 0.5)]
