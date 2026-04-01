# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Reinforcement learning module -- SB3-backed trainer, env/policy registries.

Requires ``pip install kailash-ml[rl]`` (stable-baselines3, gymnasium).
"""
from __future__ import annotations

__all__ = ["RLTrainer", "EnvironmentRegistry", "PolicyRegistry"]


def __getattr__(name: str):  # noqa: N807
    _map = {
        "RLTrainer": "kailash_ml.rl.trainer",
        "EnvironmentRegistry": "kailash_ml.rl.env_registry",
        "PolicyRegistry": "kailash_ml.rl.policy_registry",
    }
    if name in _map:
        import importlib

        module = importlib.import_module(_map[name])
        return getattr(module, name)
    raise AttributeError(f"module 'kailash_ml.rl' has no attribute {name!r}")
