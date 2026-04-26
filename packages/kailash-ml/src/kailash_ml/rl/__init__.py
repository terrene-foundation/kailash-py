# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Reinforcement learning module — SB3-backed trainer + registries + rl_train.

Public surface (W29):

* :class:`RLTrainer` — SB3 lifecycle wrapper (manager-shape).
* :class:`EnvironmentRegistry` — Gymnasium env registrations.
* :class:`PolicyRegistry` — policy specs, trained versions, reward fns.
* :func:`rl_train` — module-level entry backing ``km.rl_train``
  (top-level re-export lives in W33 per the split-ownership rule).

The module deliberately avoids a module-scope ``import stable_baselines3``
or ``import gymnasium`` — those dependencies live behind the ``[rl]``
extra. Importing this package without the extra is safe; every method
that requires SB3/gymnasium imports them lazily and raises a typed
``ImportError`` when missing (``rules/dependencies.md`` § "Optional
Extras with Loud Failure").

Requires ``pip install kailash-ml[rl]``.
"""
from __future__ import annotations

# Eager re-exports. Per ``rules/orphan-detection.md`` §6, module-scope
# public symbols MUST appear in ``__all__``; lazy ``__getattr__`` is
# reserved for symbols whose backend imports are expensive. These four
# are cheap (no SB3 touch at import time).
from kailash_ml.rl._lineage import RLLineage
from kailash_ml.rl._records import EpisodeRecord, EvalRecord
from kailash_ml.rl._rl_train import rl_train
from kailash_ml.rl._trajectory import TrajectorySchema
from kailash_ml.rl.align_adapter import (
    FeatureNotAvailableError,
    register_bridge_adapter,
    resolve_bridge_adapter,
)
from kailash_ml.rl.envs import EnvironmentRegistry, EnvironmentSpec
from kailash_ml.rl.policies import PolicyRegistry, PolicySpec, PolicyVersion
from kailash_ml.rl.protocols import PolicyArtifactRef, RLLifecycleProtocol
from kailash_ml.rl.trainer import RLTrainer, RLTrainingConfig, RLTrainingResult

__all__ = [
    "EnvironmentRegistry",
    "EnvironmentSpec",
    "EpisodeRecord",
    "EvalRecord",
    "FeatureNotAvailableError",
    "PolicyArtifactRef",
    "PolicyRegistry",
    "PolicySpec",
    "PolicyVersion",
    "RLLifecycleProtocol",
    "RLLineage",
    "RLTrainer",
    "RLTrainingConfig",
    "RLTrainingResult",
    "TrajectorySchema",
    "register_bridge_adapter",
    "resolve_bridge_adapter",
    "rl_train",
]
