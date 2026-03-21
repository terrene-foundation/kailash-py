# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Prometheus and OpenTelemetry metrics export.

Tests the metrics export functions that expose EATP trust health data
in Prometheus text format and via OpenTelemetry adapters.

TDD: These tests are written FIRST, before the implementation.
"""

from __future__ import annotations

import re

import pytest

from kailash.trust.metrics import TrustMetricsCollector, export_prometheus
from kailash.trust.posture.postures import TrustPosture


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def collector():
    """Create a fresh TrustMetricsCollector."""
    return TrustMetricsCollector()


@pytest.fixture
def populated_collector():
    """Create a TrustMetricsCollector pre-loaded with realistic data."""
    c = TrustMetricsCollector()

    # Record postures for multiple agents
    c.record_posture("agent-001", TrustPosture.DELEGATED)
    c.record_posture("agent-002", TrustPosture.SUPERVISED)
    c.record_posture("agent-003", TrustPosture.CONTINUOUS_INSIGHT)

    # Record transitions
    c.record_transition("upgrade")
    c.record_transition("upgrade")
    c.record_transition("downgrade")

    # Record circuit breaker events
    c.record_circuit_breaker_open()
    c.record_circuit_breaker_open()

    # Record constraint evaluations
    c.record_constraint_evaluation(passed=True, duration_ms=3.2)
    c.record_constraint_evaluation(passed=True, duration_ms=4.1)
    c.record_constraint_evaluation(
        passed=False,
        failed_dimensions=["rate_limit"],
        gaming_flags=["rapid_retry"],
        duration_ms=1.5,
    )

    return c


# ---------------------------------------------------------------------------
# Prometheus Export Tests
# ---------------------------------------------------------------------------


class TestExportPrometheus:
    """Tests for Prometheus text format metric export."""

    def test_returns_string(self, populated_collector):
        """export_prometheus must return a string."""
        result = export_prometheus(populated_collector)
        assert isinstance(result, str)

    def test_empty_collector_produces_valid_output(self, collector):
        """An empty collector must still produce valid Prometheus text format."""
        result = export_prometheus(collector)
        assert isinstance(result, str)
        # Should still have metric declarations even with zero values
        assert "eatp_" in result, "Output must contain eatp_ prefixed metrics"

    def test_contains_trust_score_metric(self, populated_collector):
        """Output must include eatp_trust_score gauge with agent_id labels."""
        result = export_prometheus(populated_collector)
        assert "eatp_trust_score" in result, "Must include eatp_trust_score metric"

    def test_trust_score_has_agent_id_label(self, populated_collector):
        """eatp_trust_score must include agent_id label."""
        result = export_prometheus(populated_collector)
        # Match pattern like: eatp_trust_score{agent_id="agent-001"} 5
        pattern = re.compile(r'eatp_trust_score\{agent_id="[^"]+"\}\s+\d+')
        assert pattern.search(result), f"eatp_trust_score must have agent_id label. Got:\n{result}"

    def test_trust_score_values_match_posture_levels(self, populated_collector):
        """eatp_trust_score values must correspond to posture autonomy levels."""
        result = export_prometheus(populated_collector)

        # agent-001 is DELEGATED (level 5)
        assert re.search(r'eatp_trust_score\{agent_id="agent-001"\}\s+5', result), (
            "agent-001 (DELEGATED) must have trust score 5"
        )

        # agent-002 is SUPERVISED (level 2)
        assert re.search(r'eatp_trust_score\{agent_id="agent-002"\}\s+2', result), (
            "agent-002 (SUPERVISED) must have trust score 2"
        )

        # agent-003 is CONTINUOUS_INSIGHT (level 4)
        assert re.search(r'eatp_trust_score\{agent_id="agent-003"\}\s+4', result), (
            "agent-003 (CONTINUOUS_INSIGHT) must have trust score 4"
        )

    def test_contains_verification_total_metric(self, populated_collector):
        """Output must include eatp_verification_total counter."""
        result = export_prometheus(populated_collector)
        assert "eatp_verification_total" in result, "Must include eatp_verification_total metric"

    def test_verification_total_equals_evaluations(self, populated_collector):
        """eatp_verification_total must equal total constraint evaluations."""
        result = export_prometheus(populated_collector)
        # 3 evaluations were recorded
        assert re.search(r"eatp_verification_total\s+3", result), "eatp_verification_total must be 3"

    def test_contains_posture_distribution_metric(self, populated_collector):
        """Output must include eatp_posture_distribution gauge with posture labels."""
        result = export_prometheus(populated_collector)
        assert "eatp_posture_distribution" in result, "Must include eatp_posture_distribution metric"

    def test_posture_distribution_has_posture_label(self, populated_collector):
        """eatp_posture_distribution must include posture label."""
        result = export_prometheus(populated_collector)
        pattern = re.compile(r'eatp_posture_distribution\{posture="[^"]+"\}\s+\d+')
        assert pattern.search(result), f"eatp_posture_distribution must have posture label. Got:\n{result}"

    def test_posture_distribution_values_match_agent_counts(self, populated_collector):
        """eatp_posture_distribution values must count agents at each posture level."""
        result = export_prometheus(populated_collector)

        # 1 agent at delegated, 1 at supervised, 1 at continuous_insight
        assert re.search(r'eatp_posture_distribution\{posture="delegated"\}\s+1', result), (
            "Should show 1 agent at delegated posture"
        )
        assert re.search(r'eatp_posture_distribution\{posture="supervised"\}\s+1', result), (
            "Should show 1 agent at supervised posture"
        )
        assert re.search(r'eatp_posture_distribution\{posture="continuous_insight"\}\s+1', result), (
            "Should show 1 agent at continuous_insight posture"
        )

    def test_contains_constraint_utilization_metric(self, populated_collector):
        """Output must include eatp_constraint_utilization gauge."""
        result = export_prometheus(populated_collector)
        assert "eatp_constraint_utilization" in result, "Must include eatp_constraint_utilization metric"

    def test_constraint_utilization_is_pass_rate(self, populated_collector):
        """eatp_constraint_utilization must represent the constraint pass rate (0.0-1.0)."""
        result = export_prometheus(populated_collector)
        # 2 passed out of 3 total = 0.666...
        match = re.search(r"eatp_constraint_utilization\s+([\d.]+)", result)
        assert match, "Must have eatp_constraint_utilization value"
        value = float(match.group(1))
        assert abs(value - 2.0 / 3.0) < 0.01, f"Utilization should be ~0.667, got {value}"

    def test_contains_circuit_breaker_opens_metric(self, populated_collector):
        """Output must include eatp_circuit_breaker_opens_total counter."""
        result = export_prometheus(populated_collector)
        assert "eatp_circuit_breaker_opens_total" in result, "Must include eatp_circuit_breaker_opens_total metric"

    def test_circuit_breaker_opens_count_matches(self, populated_collector):
        """eatp_circuit_breaker_opens_total must equal recorded circuit breaker events."""
        result = export_prometheus(populated_collector)
        # 2 circuit breaker opens were recorded
        assert re.search(r"eatp_circuit_breaker_opens_total\s+2", result), "eatp_circuit_breaker_opens_total must be 2"

    def test_all_metric_names_have_eatp_prefix(self, populated_collector):
        """Every metric line (non-comment, non-blank) must use the eatp_ prefix."""
        result = export_prometheus(populated_collector)
        for line in result.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            assert line.startswith("eatp_"), f"Metric line must start with 'eatp_' prefix: {line}"

    def test_prometheus_format_has_help_comments(self, populated_collector):
        """Output should include # HELP and # TYPE comment lines per Prometheus convention."""
        result = export_prometheus(populated_collector)
        assert "# HELP" in result, "Prometheus output must include # HELP comments"
        assert "# TYPE" in result, "Prometheus output must include # TYPE comments"

    def test_prometheus_format_type_declarations(self, populated_collector):
        """Prometheus TYPE declarations must use valid metric types."""
        result = export_prometheus(populated_collector)
        valid_types = {"gauge", "counter", "histogram", "summary", "untyped"}
        type_lines = [line for line in result.split("\n") if line.startswith("# TYPE")]
        assert len(type_lines) > 0, "Must have at least one TYPE declaration"
        for line in type_lines:
            parts = line.split()
            assert len(parts) >= 4, f"TYPE line malformed: {line}"
            metric_type = parts[3]
            assert metric_type in valid_types, f"Invalid Prometheus type '{metric_type}' in: {line}"

    def test_empty_collector_has_zero_values(self, collector):
        """An empty collector must produce metrics with zero/default values."""
        result = export_prometheus(collector)
        # Verification total should be 0
        assert re.search(r"eatp_verification_total\s+0", result), "Empty collector must have 0 verification total"
        # Circuit breaker opens should be 0
        assert re.search(r"eatp_circuit_breaker_opens_total\s+0", result), (
            "Empty collector must have 0 circuit breaker opens"
        )

    def test_output_is_valid_prometheus_text_format(self, populated_collector):
        """Output must conform to Prometheus text exposition format.

        Every non-blank, non-comment line must match: metric_name{labels} value
        or: metric_name value
        """
        result = export_prometheus(populated_collector)
        # Prometheus metric line pattern: name{labels} value [timestamp]
        metric_pattern = re.compile(
            r"^[a-zA-Z_:][a-zA-Z0-9_:]*"  # metric name
            r"(\{[^}]*\})?"  # optional labels
            r"\s+-?[\d.]+([eE][+-]?\d+)?"  # value (float or int)
            r"(\s+\d+)?$"  # optional timestamp
        )
        for line in result.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            assert metric_pattern.match(line), f"Line does not match Prometheus text format: '{line}'"


# ---------------------------------------------------------------------------
# OTelMetricsAdapter Tests
# ---------------------------------------------------------------------------


class TestOTelMetricsAdapter:
    """Tests for OpenTelemetry metrics adapter."""

    def test_import_raises_when_otel_not_available(self):
        """OTelMetricsAdapter must raise ImportError if opentelemetry-api is not installed."""
        # The adapter is importable, but instantiation should fail
        # if opentelemetry is not available
        from kailash.trust.metrics import OTelMetricsAdapter

        try:
            adapter = OTelMetricsAdapter()
            # If we get here, opentelemetry IS installed -- that's fine too
            assert adapter is not None
        except ImportError as e:
            assert "opentelemetry" in str(e).lower(), f"ImportError must mention opentelemetry, got: {e}"

    def test_adapter_class_exists(self):
        """OTelMetricsAdapter class must be importable from kailash.trust.metrics."""
        from kailash.trust.metrics import OTelMetricsAdapter

        assert OTelMetricsAdapter is not None

    def test_adapter_has_record_trust_score_method(self):
        """OTelMetricsAdapter must define record_trust_score method."""
        from kailash.trust.metrics import OTelMetricsAdapter

        assert hasattr(OTelMetricsAdapter, "record_trust_score")

    def test_adapter_has_record_verification_method(self):
        """OTelMetricsAdapter must define record_verification method."""
        from kailash.trust.metrics import OTelMetricsAdapter

        assert hasattr(OTelMetricsAdapter, "record_verification")

    def test_adapter_has_record_posture_method(self):
        """OTelMetricsAdapter must define record_posture method."""
        from kailash.trust.metrics import OTelMetricsAdapter

        assert hasattr(OTelMetricsAdapter, "record_posture")

    def test_adapter_default_meter_name(self):
        """OTelMetricsAdapter must accept a meter_name parameter defaulting to 'eatp'."""
        from kailash.trust.metrics import OTelMetricsAdapter

        # Check signature accepts meter_name
        import inspect

        sig = inspect.signature(OTelMetricsAdapter.__init__)
        params = sig.parameters
        assert "meter_name" in params, "Must accept meter_name parameter"
        assert params["meter_name"].default == "eatp", "meter_name must default to 'eatp'"
