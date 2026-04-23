# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 direct coverage for RLOOAdapter (incl. sampling_temperature default 0.7)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_rloo_class_attrs():
    from kailash_align.rl_bridge._rloo import RLOOAdapter

    assert RLOOAdapter.name == "rloo"
    assert RLOOAdapter.paradigm == "rlhf"
    assert RLOOAdapter.buffer_kind == "rollout"


def test_rloo_satisfies_protocol():
    from kailash_align.rl_bridge._rloo import RLOOAdapter
    from kailash_ml.rl.protocols import RLLifecycleProtocol

    instance = RLOOAdapter.__make_for_test__()
    assert isinstance(instance, RLLifecycleProtocol)


def test_rloo_ref_temperature_default_one():
    """ref_temperature stays TRL-canonical 1.0 (spec §3.4b)."""
    from kailash_align.rl_bridge._rloo import RLOOAdapter

    adapter = RLOOAdapter()
    assert adapter.ref_temperature == 1.0


def test_rloo_sampling_temperature_default_seven_tenths():
    """sampling_temperature default 0.7 — RLOO-canonical for diverse rollouts (spec §3.4b)."""
    from kailash_align.rl_bridge._rloo import RLOOAdapter

    adapter = RLOOAdapter()
    assert adapter.sampling_temperature == 0.7


def test_rloo_temperatures_are_distinct_kwargs():
    from kailash_align.rl_bridge._rloo import RLOOAdapter

    adapter = RLOOAdapter(ref_temperature=1.0, sampling_temperature=0.7)
    assert adapter.ref_temperature != adapter.sampling_temperature


def test_rloo_rejects_zero_ref_temperature():
    from kailash_align.rl_bridge._rloo import RLOOAdapter

    with pytest.raises(ValueError, match="ref_temperature"):
        RLOOAdapter(ref_temperature=0.0)


def test_rloo_rejects_negative_sampling_temperature():
    from kailash_align.rl_bridge._rloo import RLOOAdapter

    with pytest.raises(ValueError, match="sampling_temperature"):
        RLOOAdapter(sampling_temperature=-0.01)
