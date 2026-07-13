"""Regression test: the acquire-wait histogram singleton must tolerate this
module being imported under two distinct qualified names in the same
process (#1708 W1c).

This repo's test suite mixes ``from kailash.x import ...`` and
``from src.kailash.x import ...`` across different files (both resolve, but
as TWO SEPARATE module objects in ``sys.modules``, each with its own
module-level globals). A naive "create once, guarded by a module-level
None-check" singleton breaks the moment BOTH import paths call
``track_acquisition()`` in the same process: the second path's ``None``
check passes (its own global was never set) and it attempts to register a
second ``prometheus_client.Histogram`` with the same name against the same
process-wide default ``REGISTRY``, raising
``ValueError: Duplicated timeseries in CollectorRegistry``.

The fix: on ``ValueError`` from registration, adopt the already-registered
collector via ``REGISTRY._names_to_collectors`` instead of propagating the
error.

@pytest.mark.regression per rules/testing.md § "Regression Testing".
"""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.mark.regression
def test_histogram_singleton_survives_dual_qualified_module_import():
    # Ensure both qualified names are absent from sys.modules so this test
    # exercises a genuine first-import race rather than reusing whatever
    # another test file already imported.
    for mod_name in (
        "kailash.core.monitoring.connection_metrics",
        "src.kailash.core.monitoring.connection_metrics",
    ):
        sys.modules.pop(mod_name, None)

    kailash_mod = importlib.import_module("kailash.core.monitoring.connection_metrics")
    src_mod = importlib.import_module("src.kailash.core.monitoring.connection_metrics")
    assert kailash_mod is not src_mod, (
        "test setup invalid: both qualified names resolved to the SAME "
        "module object, so this test would not exercise the dual-import "
        "race the fix targets"
    )

    collector_a = kailash_mod.ConnectionMetricsCollector("dual_import_pool_a")
    collector_b = src_mod.ConnectionMetricsCollector("dual_import_pool_b")

    # Neither call may raise "Duplicated timeseries in CollectorRegistry".
    with collector_a.track_acquisition():
        pass
    with collector_b.track_acquisition():
        pass

    # Both label series actually landed on the ONE shared registry.
    import prometheus_client

    body = prometheus_client.generate_latest().decode("utf-8")
    assert 'kailash_pool_acquire_wait_seconds_count{pool="dual_import_pool_a"}' in body
    assert 'kailash_pool_acquire_wait_seconds_count{pool="dual_import_pool_b"}' in body
