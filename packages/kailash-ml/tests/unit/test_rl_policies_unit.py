# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests — PolicyRegistry reward registry (W29 invariant #5)."""
from __future__ import annotations

import pytest

from kailash_ml.errors import RLError
from kailash_ml.rl.policies import PolicyRegistry


def _reward_fn(obs, action, next_obs, env_info):  # pragma: no cover - stub
    return 1.0


def _other_reward_fn(obs, action, next_obs, env_info):  # pragma: no cover - stub
    return 2.0


class TestRewardRegistry:
    """register_reward / get_reward (W29 invariant #5)."""

    def test_register_and_get(self) -> None:
        reg = PolicyRegistry()
        reg.register_reward("dense-reward", _reward_fn)
        assert reg.get_reward("dense-reward") is _reward_fn

    def test_get_unknown_raises(self) -> None:
        reg = PolicyRegistry()
        with pytest.raises(RLError) as exc:
            reg.get_reward("not-registered")
        assert exc.value.reason == "reward_not_found"

    def test_idempotent_reregistration_same_fn(self) -> None:
        reg = PolicyRegistry()
        reg.register_reward("r", _reward_fn)
        # Same function is idempotent — no exception.
        reg.register_reward("r", _reward_fn)
        assert reg.get_reward("r") is _reward_fn

    def test_name_collision_raises(self) -> None:
        reg = PolicyRegistry()
        reg.register_reward("r", _reward_fn)
        with pytest.raises(RLError, match="reward_name_occupied"):
            reg.register_reward("r", _other_reward_fn)

    def test_non_callable_rejected(self) -> None:
        reg = PolicyRegistry()
        with pytest.raises(RLError, match="reward_not_callable"):
            reg.register_reward("bad", "not-a-function")  # type: ignore[arg-type]

    def test_list_rewards_is_sorted(self) -> None:
        reg = PolicyRegistry()
        reg.register_reward("zebra", _reward_fn)
        reg.register_reward("alpha", _reward_fn)
        assert reg.list_rewards() == ["alpha", "zebra"]


class TestTenantIdPropagation:
    """Tenant id stored on the instance for later persistence shards."""

    def test_tenant_id_stored(self) -> None:
        reg = PolicyRegistry(tenant_id="tenant-42")
        assert reg._tenant_id == "tenant-42"
