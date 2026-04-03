# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for FabricMetrics (TODO-21)."""

from __future__ import annotations

from dataflow.fabric.metrics import FabricMetrics


class TestFabricMetrics:
    _metrics = None

    @classmethod
    def _get_metrics(cls) -> FabricMetrics:
        """Singleton to avoid Prometheus duplicate registration across tests."""
        if cls._metrics is None:
            cls._metrics = FabricMetrics()
        return cls._metrics

    def test_noop_when_no_prometheus(self):
        """Metrics should work even without prometheus_client."""
        metrics = self._get_metrics()
        # These should not raise regardless of whether prometheus_client is installed
        metrics.record_source_check("crm", 0.05, True)
        metrics.record_source_failure("crm", 3)
        metrics.record_pipeline_run("dashboard", 0.8, True)
        metrics.record_cache_hit("dashboard")
        metrics.record_cache_miss("dashboard")
        metrics.record_product_age("dashboard", 120.0)
        metrics.record_request("dashboard", 0.01, "fresh")

    def test_enabled_flag(self):
        metrics = self._get_metrics()
        # enabled depends on whether prometheus_client is importable
        assert isinstance(metrics.enabled, bool)
