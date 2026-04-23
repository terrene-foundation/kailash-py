# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash_align.rl_bridge — TRL-backed adapters satisfying ``RLLifecycleProtocol``.

Per ``specs/ml-rl-align-unification.md`` v1.0.0 §2–§3 + §7, this package
is the cross-SDK bridge between ``kailash-align`` and
``kailash-ml``'s dispatch layer:

* Importing this package REGISTERS every v1-scope bridge adapter
  (``dpo``, ``ppo-rlhf``, ``rloo``, ``online-dpo``) into
  :data:`kailash_ml.rl.align_adapter.BRIDGE_ADAPTERS` by calling
  :func:`register_bridge_adapters` at the bottom of this module.
* ``kailash-ml``'s ``km.rl_train(algo=<name>)`` calls
  :func:`kailash_ml.rl.align_adapter.resolve_bridge_adapter` which
  lazy-imports THIS module to populate the registry.
* Requires the ``[rl-bridge]`` extra (pulls ``kailash-ml[rl]>=1.1,<2.0``).

Loud-fail on missing extra
--------------------------

Per ``rules/dependencies.md`` § "Optional Extras with Loud Failure",
if ``kailash-ml`` is not installed (the ``[rl-bridge]`` extra was
skipped), importing this module raises ``ImportError`` with a message
naming the extra. Silent degradation to ``None`` is BLOCKED.

DPO reference-temperature contract (spec §3.4b)
----------------------------------------------

All four adapters honour the spec §3.4b separation of log-probability
extraction temperature (``ref_temperature=1.0`` default, TRL-canonical)
from sampling temperature (``sampling_temperature=0.0`` default, or a
method-specific default like ``0.7`` for RLOO and ``0.9`` for OnlineDPO).
DPOAdapter emits ``rl.train.update.ref_temperature`` as a categorical
tag on every update per §3.3.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = [
    "register_bridge_adapters",
    "DPOAdapter",
    "PPORLHFAdapter",
    "RLOOAdapter",
    "OnlineDPOAdapter",
]


# --- Loud-fail guard for the [rl-bridge] extra --------------------------
#
# ``kailash-align`` itself depends on ``kailash-ml>=0.11`` as a runtime
# dependency (see packages/kailash-align/pyproject.toml). The
# ``[rl-bridge]`` extra tightens that floor to ``kailash-ml[rl]>=1.1,<2.0``
# so the RL Protocol + dispatch registry introduced in W30 Shard 1 is
# present. Importing ``rl_bridge`` without the extra surfaces as an
# ImportError naming the extra — NOT a silent ``None`` that corrupts
# downstream dispatch.
try:
    from kailash_ml.rl.align_adapter import (
        BRIDGE_ADAPTERS,
        FeatureNotAvailableError,
        register_bridge_adapter,
    )
except ImportError as exc:  # pragma: no cover — optional-extra guard
    raise ImportError(
        "kailash_align.rl_bridge requires the [rl-bridge] extra "
        "(kailash-ml[rl]>=1.1,<2.0). Install via "
        "'pip install kailash-align[rl-bridge]'."
    ) from exc


def register_bridge_adapters() -> None:
    """Register the v1-scope bridge adapters into ``BRIDGE_ADAPTERS``.

    Called at module-import time (bottom of this file) so merely
    ``import kailash_align.rl_bridge`` activates the bridge. Idempotent:
    :func:`register_bridge_adapter` raises :class:`ValueError` only when
    a DIFFERENT class is registered under the same name (cross-SDK drift
    guard), not on re-registration of the same class.

    Per spec §9 (v1 scope) the four adapters registered here are:

    * ``dpo`` — offline preference-pair via ``DPOTrainer``
    * ``ppo-rlhf`` — online policy-gradient via ``PPOTrainer`` with reward model
    * ``rloo`` — REINFORCE Leave-One-Out via ``RLOOTrainer``
    * ``online-dpo`` — online preference-pair via ``OnlineDPOTrainer``

    Adapter imports are deferred inside this function so the scaffold
    module can land ahead of the concrete adapter files without a
    cyclic-import failure at collection time. Once all four adapters
    exist on disk (commits 2-4 of W30 Shard 2) this function is a
    pure registry-population call.
    """
    from kailash_align.rl_bridge._dpo import DPOAdapter
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter
    from kailash_align.rl_bridge._ppo_rlhf import PPORLHFAdapter
    from kailash_align.rl_bridge._rloo import RLOOAdapter

    register_bridge_adapter("dpo", DPOAdapter)
    register_bridge_adapter("ppo-rlhf", PPORLHFAdapter)
    register_bridge_adapter("rloo", RLOOAdapter)
    register_bridge_adapter("online-dpo", OnlineDPOAdapter)

    # Top-level re-exports for ``from kailash_align.rl_bridge import DPOAdapter``.
    globals().update(
        {
            "DPOAdapter": DPOAdapter,
            "PPORLHFAdapter": PPORLHFAdapter,
            "RLOOAdapter": RLOOAdapter,
            "OnlineDPOAdapter": OnlineDPOAdapter,
        }
    )

    logger.info(
        "align.rl_bridge.init",
        extra={
            "rl_bridge_adapters": ["dpo", "ppo-rlhf", "rloo", "online-dpo"],
            "rl_bridge_registry_size": len(BRIDGE_ADAPTERS),
            "mode": "real",
        },
    )


# --- Import-time side effect: register the adapters --------------------
#
# Per spec §3: ``km.rl_train`` lazy-imports ``kailash_align.rl_bridge``,
# and that import's side effect is to populate the registry. Without
# this call, the registry stays empty and ``km.rl_train(algo="dpo")``
# raises ``FeatureNotAvailableError`` even when the extra is installed.
#
# In Commit 1 of W30 Shard 2 the concrete adapter files do not yet
# exist — registration is deferred until Commit 4 lands all four.
# Guarded by a ModuleNotFoundError check so the scaffold-only state
# is importable (tests against the registration hook itself live in
# Commit 6, after every adapter file is committed).
try:
    register_bridge_adapters()
except ModuleNotFoundError as exc:  # pragma: no cover — scaffold-only state
    logger.warning(
        "align.rl_bridge.init.pending",
        extra={
            "reason": "adapter_module_not_yet_committed",
            "missing_module": exc.name,
            "mode": "real",
        },
    )


# Re-export the registry-API symbols so consumers can write
# ``from kailash_align.rl_bridge import BRIDGE_ADAPTERS`` without a
# round-trip through kailash_ml. Keeps the import graph simpler for
# tests + downstream tooling.
__all__.extend(
    ["BRIDGE_ADAPTERS", "FeatureNotAvailableError", "register_bridge_adapter"]
)
