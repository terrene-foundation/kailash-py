# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 direct coverage for OnlineDPOAdapter (incl. sampling_temperature default 0.9)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_online_dpo_class_attrs():
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter

    assert OnlineDPOAdapter.name == "online-dpo"
    assert OnlineDPOAdapter.paradigm == "rlhf"
    assert OnlineDPOAdapter.buffer_kind == "preference"


def test_online_dpo_satisfies_protocol():
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter
    from kailash_ml.rl.protocols import RLLifecycleProtocol

    instance = OnlineDPOAdapter.__make_for_test__()
    assert isinstance(instance, RLLifecycleProtocol)


def test_online_dpo_ref_temperature_default_one():
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter

    adapter = OnlineDPOAdapter()
    assert adapter.ref_temperature == 1.0


def test_online_dpo_sampling_temperature_default_nine_tenths():
    """sampling_temperature default 0.9 — Online-DPO canonical (spec §3.4b)."""
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter

    adapter = OnlineDPOAdapter()
    assert adapter.sampling_temperature == 0.9


def test_online_dpo_temperatures_are_distinct():
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter

    adapter = OnlineDPOAdapter(ref_temperature=1.0, sampling_temperature=0.9)
    assert adapter.ref_temperature != adapter.sampling_temperature


def test_online_dpo_rejects_bad_ref_temperature():
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter

    with pytest.raises(ValueError, match="ref_temperature"):
        OnlineDPOAdapter(ref_temperature=-0.5)


def test_online_dpo_rejects_bad_sampling_temperature():
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter

    with pytest.raises(ValueError, match="sampling_temperature"):
        OnlineDPOAdapter(sampling_temperature=-1.0)


def test_online_dpo_reward_model_optional():
    """Online-DPO may run without a reward_model (judge-based preferences)."""
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter

    adapter = OnlineDPOAdapter(reward_model=None)
    assert adapter._reward_model is None
