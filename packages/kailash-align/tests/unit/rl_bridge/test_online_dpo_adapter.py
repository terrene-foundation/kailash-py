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


def test_online_dpo_build_raises_informative_unavailable_error():
    """build() raises an informative TrainingError naming the trl>=1.0 removal and
    the DPO/GRPO alternatives — NOT the opaque AlignmentError 'Unknown training
    method online_dpo' the un-registered method registry produced (issue #1429).

    Mirrors OnlineDPOConfig.to_trl_config() in config.py.
    """
    from kailash_align.exceptions import TrainingError
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter

    adapter = OnlineDPOAdapter()
    with pytest.raises(TrainingError, match="Online DPO is unavailable"):
        adapter.build()


def test_online_dpo_learn_raises_informative_unavailable_error():
    """learn() builds the trainer first, so it surfaces the SAME informative
    TrainingError as build() rather than a confusing registry miss (issue #1429)."""
    from kailash_align.exceptions import TrainingError
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter

    adapter = OnlineDPOAdapter()
    with pytest.raises(TrainingError, match="Online DPO is unavailable"):
        adapter.learn(total_timesteps=1)


def test_online_dpo_build_error_matches_config_to_trl_config():
    """The adapter's build() error MUST stay byte-identical to
    OnlineDPOConfig.to_trl_config()'s — the fix's basis is that the bridge mirrors
    the config layer's informative raise (issue #1429). Pin that config<->adapter
    parity so editing one message without the other fails loudly."""
    from kailash_align.config import OnlineDPOConfig
    from kailash_align.exceptions import TrainingError
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter

    with pytest.raises(TrainingError) as build_exc:
        OnlineDPOAdapter().build()
    with pytest.raises(TrainingError) as config_exc:
        OnlineDPOConfig().to_trl_config(output_dir="unused")

    assert str(build_exc.value) == str(config_exc.value)
