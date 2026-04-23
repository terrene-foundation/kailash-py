# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash_align.ml — integration facade between kailash-align and kailash-ml.

Per ``workspaces/kailash-ml-audit/todos/active/W32-kaizen-align-pact-integrations.md``
§32b (amended 2026-04-23) this package is the spec-mandated integration
facade that ``kailash-ml`` and downstream consumers import to wire
alignment training into the unified kailash-ml lifecycle.

Surface
-------

* **W30 RL bridge adapters** — re-exported from
  :mod:`kailash_align.rl_bridge`. These were shipped by W30.2/W30.3 and
  live under ``kailash_align.rl_bridge.*``; this namespace re-exports
  them under the names the spec §2 table uses (``DPOTrainer``,
  ``PPOTrainer``, ``RLOOTrainer``, ``OnlineDPOTrainer``) so integration
  call sites can import the canonical name without caring about the
  storage module.
* **LoRA Lightning callback** — :class:`LoRALightningCallback` is a
  ``pytorch_lightning.Callback`` subclass that auto-emits training
  metrics via an ambient ``ExperimentRun`` when attached to an
  ``MLEngine.fit`` for a LoRA-trainable model. Exposed via
  :func:`lora_callback_for` so ``MLEngine.fit`` looks it up without
  importing this module at module-scope (keeps the ml→align import
  boundary one-way).
* **Trajectory unification entry** — :func:`trajectory_from_alignment_run`
  converts an :class:`~kailash_align.AlignmentResult` into the W30
  unified cross-SDK schema (:class:`kailash_ml.rl.RLLineage`). Per
  ``specs/ml-rl-align-unification.md`` v1.0.0 §5 / §7 the unified schema
  lives on the kailash-ml side; align never defines its own.

Dependency direction (spec §7)
------------------------------

Strict one-way: ``kailash_align.ml`` MAY import from ``kailash_ml.rl``;
``kailash_ml`` MUST NOT import from ``kailash_align`` (enforced in W30
scaffolding). The re-exports below work because ``kailash-align``
already depends on ``kailash-ml>=0.11`` at runtime; the ``[rl-bridge]``
extra tightens the floor to ``kailash-ml[rl]>=1.1,<2.0`` when the bridge
adapters are actually used.

Spec-deviation note (specs-authority.md MUST Rule 6)
----------------------------------------------------

The 32b amendment refers to the unified cross-SDK schema as
"``Trajectory``" in prose, but the W30 implementation authored in
:mod:`kailash_ml.rl._lineage` named it ``RLLineage`` (matches
``specs/ml-rl-align-unification.md`` v1.0.0 §5 field names exactly).
This module uses ``RLLineage`` as the unified schema; no parallel
"Trajectory" class is introduced because W30 spec §7 mandates a single
source. The ``trajectory_from_alignment_run`` callable name preserves
the 32b vocabulary while the return type is the actual W30 dataclass.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

# Eager re-exports from the W30 rl_bridge — orphan-detection.md §6
# mandates every __all__ entry resolve at module scope. The rl_bridge
# package itself guards the ``[rl-bridge]`` extra via a loud ImportError
# when ``kailash-ml[rl]>=1.1`` is missing (see
# ``kailash_align.rl_bridge.__init__``), so the import chain either
# succeeds cleanly or fails early with an actionable extra name.
from kailash_align.rl_bridge import (
    DPOAdapter as DPOTrainer,
    OnlineDPOAdapter as OnlineDPOTrainer,
    PPORLHFAdapter as PPOTrainer,
    RLOOAdapter as RLOOTrainer,
)
from kailash_align.ml._lora_callback import (
    LoRALightningCallback,
    lora_callback_for,
)
from kailash_align.ml._trajectory import trajectory_from_alignment_run

if TYPE_CHECKING:  # pragma: no cover — typing-only imports
    from kailash_ml.rl import RLLineage  # re-exported via trajectory_from_alignment_run

logger = logging.getLogger(__name__)

__all__ = [
    # W30 bridge adapters — canonical spec §2 table names. Storage
    # module aliases preserved for call sites that want the align-
    # specific names (DPOAdapter, PPORLHFAdapter, RLOOAdapter,
    # OnlineDPOAdapter) via the full rl_bridge path.
    "DPOTrainer",
    "PPOTrainer",
    "RLOOTrainer",
    "OnlineDPOTrainer",
    # LoRA Lightning callback entry points
    "LoRALightningCallback",
    "lora_callback_for",
    # Trajectory unification (returns kailash_ml.rl.RLLineage)
    "trajectory_from_alignment_run",
]
