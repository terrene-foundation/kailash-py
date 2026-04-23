# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 direct coverage for PPORLHFAdapter."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_ppo_rlhf_class_attrs():
    from kailash_align.rl_bridge._ppo_rlhf import PPORLHFAdapter

    assert PPORLHFAdapter.name == "ppo-rlhf"
    assert PPORLHFAdapter.paradigm == "rlhf"
    assert PPORLHFAdapter.buffer_kind == "rollout"


def test_ppo_rlhf_satisfies_protocol():
    from kailash_align.rl_bridge._ppo_rlhf import PPORLHFAdapter
    from kailash_ml.rl.protocols import RLLifecycleProtocol

    instance = PPORLHFAdapter.__make_for_test__()
    assert isinstance(instance, RLLifecycleProtocol)


def test_ppo_rlhf_instance_attrs_present():
    from kailash_align.rl_bridge._ppo_rlhf import PPORLHFAdapter

    adapter = PPORLHFAdapter(tenant_id="t-1", run_id="r-1")
    assert adapter.run_id == "r-1"
    assert adapter.tenant_id == "t-1"
    assert hasattr(adapter, "device")


def test_ppo_rlhf_accepts_rlhf_triplet():
    """policy + reward_model + reference_model are the full RLHF triplet."""
    from kailash_align.rl_bridge._ppo_rlhf import PPORLHFAdapter

    adapter = PPORLHFAdapter(
        policy="policy_stub",
        reward_model="reward_stub",
        reference_model="ref_stub",
        hyperparameters={"learning_rate": 1e-5},
    )
    assert adapter._policy == "policy_stub"
    assert adapter._reward_model == "reward_stub"
    assert adapter._reference_model == "ref_stub"
    assert adapter._hyperparameters == {"learning_rate": 1e-5}
