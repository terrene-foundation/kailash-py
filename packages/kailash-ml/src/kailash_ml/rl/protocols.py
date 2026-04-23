# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared cross-SDK RL Protocol for ``kailash-ml`` <-> ``kailash-align``.

Per ``specs/ml-rl-align-unification.md`` §2, this module defines the
runtime-checkable :class:`RLLifecycleProtocol` contract that BOTH
first-party classical-RL adapters (SB3-backed) AND kailash-align's
TRL-backed bridge adapters (DPO, PPO-RLHF, RLOO, OnlineDPO, etc.)
implement. Dispatch through ``km.rl_train(algo=<name>)`` routes by
name into either registry; the Protocol is the conformance gate.

Zero align-side imports
-----------------------

This module MUST NOT import ``kailash_align`` at module scope (spec §7
dependency topology). The Protocol lives in ``kailash-ml`` so
``kailash-align`` can satisfy it without forcing ``kailash-ml`` to
take a hard dependency on align — align remains an optional extra.
The bridge resolver in :mod:`kailash_ml.rl.align_adapter` does the
lazy ``importlib.import_module("kailash_align.rl_bridge")`` dance.

Conformance gate
----------------

.. code-block:: python

    from kailash_ml.rl.protocols import RLLifecycleProtocol
    from kailash_align.rl_bridge import AlignDPOAdapter

    adapter = AlignDPOAdapter(...)
    assert isinstance(adapter, RLLifecycleProtocol)  # must hold at runtime
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, ClassVar, Literal, Protocol, runtime_checkable

__all__ = ["RLLifecycleProtocol", "PolicyArtifactRef"]


@dataclass(frozen=True)
class PolicyArtifactRef:
    """Reference to a persisted RL policy artifact.

    Produced by :meth:`RLLifecycleProtocol.save` and consumed by
    :meth:`RLLifecycleProtocol.load`. Frozen so downstream code can use
    refs as cache keys / lineage fingerprints without defensive copies.

    Parameters
    ----------
    path:
        Filesystem path to the serialized policy artifact (SB3 ``.zip``,
        TRL PEFT adapter directory, d3rlpy pickle, etc.).
    sha:
        Content-addressed hash of the artifact payload. The exact
        hashing convention is up to the producing adapter; consumers
        MUST treat ``sha`` as an opaque fingerprint string.
    algorithm:
        Canonical algorithm name (``"ppo"``, ``"dpo"``, ``"rloo"``, ...) —
        matches the ``name`` class attribute of the adapter that
        produced the artifact.
    policy_class:
        Fully-qualified name of the underlying policy class
        (``"stable_baselines3.common.policies.ActorCriticPolicy"``,
        ``"transformers.AutoModelForCausalLM"``, etc.). Used at load
        time to reconstruct the policy shape.
    created_at:
        UTC timestamp at which the artifact was persisted.
    tenant_id:
        Optional tenant scope. ``None`` when the run was single-tenant
        or the caller explicitly passed ``tenant_id=None``.
    """

    path: Path
    sha: str
    algorithm: str
    policy_class: str
    created_at: datetime
    tenant_id: str | None = None


@runtime_checkable
class RLLifecycleProtocol(Protocol):
    """The shared cross-SDK contract for every RL training run.

    Classical (SB3 / d3rlpy) AND RLHF (TRL via kailash-align) adapters
    both satisfy this Protocol. Any adapter for which
    ``isinstance(adapter, RLLifecycleProtocol)`` holds at runtime can be
    dispatched via ``km.rl_train(..., algo=<registered-name>)`` and emits
    metrics to the same tracker backend as every other kailash-ml engine.

    The Protocol is intentionally a ``typing.Protocol`` (not an abstract
    base class) so ``kailash-align`` does not need to inherit from
    ``kailash-ml`` to implement it — duck typing plus
    ``@runtime_checkable`` is sufficient, and it mirrors the
    ``kailash.diagnostics.protocols.Diagnostic`` / ``JudgeCallable``
    pattern already shared across the wave.

    Class-level attributes
    ----------------------
    name:
        Canonical algorithm identifier (``"ppo"``, ``"dpo"``, ...).
    paradigm:
        One of ``"on-policy"`` / ``"off-policy"`` / ``"offline"`` /
        ``"rlhf"``. Drives tracker-panel layout and the policy-shape
        compatibility gate in ``km.rl_train``.
    buffer_kind:
        One of ``"rollout"`` / ``"replay"`` / ``"dataset"`` /
        ``"preference"``. Drives buffer-stats metric family selection.

    Instance attributes
    -------------------
    run_id:
        Correlation id for this training run. Logged on every metric.
    tenant_id:
        Tenant scope (``None`` for single-tenant runs).
    device:
        :class:`kailash_ml.DeviceReport` for the run — concrete evidence
        of backend / precision / fallback, never ``"auto"``.

    Lifecycle contract
    ------------------
    ``build()`` constructs the backend trainer. ``learn(...)`` runs the
    training loop and returns a :class:`~kailash_ml.rl.trainer.RLTrainingResult`
    populated with the spec §3.2 parity fields. ``save`` / ``load`` are
    round-trip complements via :class:`PolicyArtifactRef`. ``checkpoint``
    / ``resume`` persist full training state for warm restarts.

    Telemetry
    ---------
    ``emit_metric(key, value, *, step)`` is the canonical metric emit
    point; implementations MUST forward to both the ambient tracker
    (so ``MLDashboard`` sees the metric) AND the adapter's own
    ``RLDiagnostics`` / ``AlignmentDiagnostics`` instance.
    """

    # -- Class-level declarations --------------------------------------
    name: ClassVar[str]
    paradigm: ClassVar[Literal["on-policy", "off-policy", "offline", "rlhf"]]
    buffer_kind: ClassVar[Literal["rollout", "replay", "dataset", "preference"]]

    # -- Instance state ------------------------------------------------
    run_id: str
    tenant_id: str | None
    device: Any  # DeviceReport; typed as Any to keep this module import-light.

    # -- Lifecycle methods ---------------------------------------------
    def build(self) -> None:
        """Construct the backend trainer (SB3 model / TRL trainer / d3rlpy)."""
        ...

    def learn(
        self,
        total_timesteps: int,
        *,
        callbacks: list[Any],
        eval_env_fn: Callable[[], Any] | None,
        eval_freq: int,
        n_eval_episodes: int,
    ) -> Any:
        """Run training; emit ``rl.*`` metrics via the ambient tracker.

        Returns an :class:`~kailash_ml.rl.trainer.RLTrainingResult`
        populated per the cross-algorithm parity contract.
        """
        ...

    def save(self, path: Path) -> "PolicyArtifactRef":
        """Persist the policy (+ optimizer + buffer + RNG) to disk."""
        ...

    @classmethod
    def load(cls, ref: "PolicyArtifactRef") -> "RLLifecycleProtocol":
        """Round-trip complement of :meth:`save`."""
        ...

    def checkpoint(self, path: Path) -> None:
        """Persist full training state for ``resume_from=``."""
        ...

    def resume(self, path: Path) -> None:
        """Restore full training state from a checkpoint directory."""
        ...

    # -- Telemetry contract --------------------------------------------
    def emit_metric(self, key: str, value: float, *, step: int) -> None:
        """Canonical metric emit point.

        Forwards to the ambient tracker (so ``MLDashboard`` renders the
        metric) AND to the adapter's own diagnostics instance.
        """
        ...
