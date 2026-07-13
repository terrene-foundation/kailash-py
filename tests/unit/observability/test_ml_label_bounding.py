# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 tests for non-tenant ML label bounding (issue #1708 W1e).

Before #1708 only ``tenant_id`` was bounded; ``model_name`` / ``version`` /
``engine_name`` / ``feature_name`` were emitted verbatim as metric labels — an
unbounded-cardinality axis (a flood of distinct values is a time-series bomb).
Each now routes through its own top-N admission bucketer: values stay verbatim
under the cap, an overflow collapses to ``"_other"``.
"""

from __future__ import annotations

import pytest

from kailash.observability import ml


@pytest.fixture(autouse=True)
def _reset_bucketers():
    ml._reset_bucketer_for_tests(top_n=100)
    yield
    ml._reset_bucketer_for_tests(top_n=100)


def test_label_bucketer_admits_top_n_then_other() -> None:
    ml._reset_bucketer_for_tests(top_n=2)
    assert ml._bucket_label(ml._model_bucketer, "m1") == "m1"
    assert ml._bucket_label(ml._model_bucketer, "m2") == "m2"
    # third distinct value overflows the cap
    assert ml._bucket_label(ml._model_bucketer, "m3") == "_other"


def test_dimensions_bound_independently() -> None:
    ml._reset_bucketer_for_tests(top_n=1)
    assert ml._bucket_label(ml._version_bucketer, "v1") == "v1"
    assert ml._bucket_label(ml._version_bucketer, "v2") == "_other"
    # a different dimension has its own independent cap
    assert ml._bucket_label(ml._feature_bucketer, "f1") == "f1"
    assert ml._bucket_label(ml._engine_bucketer, "e1") == "e1"


def test_empty_value_passes_through() -> None:
    ml._reset_bucketer_for_tests(top_n=1)
    assert ml._bucket_label(ml._model_bucketer, "") == ""


@pytest.mark.skipif(not ml.PROMETHEUS_AVAILABLE, reason="prometheus_client absent")
def test_record_inference_bounds_model_label_in_exposition() -> None:
    ml._reset_bucketer_for_tests(top_n=2)
    for name in ("bm1", "bm2", "bm3"):
        ml.record_inference_latency(
            model_name=name, version="v", tenant_id="tenant-x", latency_ms=1.0
        )

    from prometheus_client import generate_latest

    out = generate_latest().decode()
    # bm3 overflowed the cap → the label collapses to "_other" in the scrape,
    # proving the bounding is wired through the real recording path.
    assert 'model_name="_other"' in out
