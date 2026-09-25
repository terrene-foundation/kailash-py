# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``kailash_ml.rl.protocols``.

Covers spec §2 invariants:

* The Protocol is ``@runtime_checkable``.
* A class that declares the required attrs + methods — WITHOUT
  inheriting from the Protocol — satisfies ``isinstance`` at runtime.
* ``PolicyArtifactRef`` is frozen (dataclass invariance).

These tests do NOT require ``stable-baselines3``, ``gymnasium``, or
``kailash-align``; they exercise the Protocol contract itself.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pytest

from kailash_ml.rl.protocols import PolicyArtifactRef, RLLifecycleProtocol


class _ConformingAdapter:
    """Adapter that satisfies ``RLLifecycleProtocol`` by declaration only.

    Deliberately does NOT inherit from ``RLLifecycleProtocol`` — the
    whole point of a runtime-checkable Protocol is that duck typing
    works without inheritance. This mirrors the align-side pattern
    where ``kailash_align.rl_bridge.AlignDPOAdapter`` satisfies the
    Protocol without depending on kailash-ml at class-definition time.
    """

    # Class-level declarations
    name = "conforming"
    paradigm = "rlhf"
    buffer_kind = "preference"

    def __init__(self) -> None:
        self.run_id = "test-run-001"
        self.tenant_id = None
        self.device = None  # DeviceReport-shaped; any value satisfies Protocol

    def build(self) -> None:
        return None

    def learn(
        self,
        total_timesteps: int,
        *,
        callbacks: list[Any],
        eval_env_fn: Callable[[], Any] | None,
        eval_freq: int,
        n_eval_episodes: int,
    ) -> Any:
        return None

    def save(self, path: Path) -> PolicyArtifactRef:
        return PolicyArtifactRef(
            path=path,
            sha="deadbeef",
            algorithm=self.name,
            policy_class="conforming.Adapter",
            created_at=datetime.now(timezone.utc),
        )

    @classmethod
    def load(cls, ref: PolicyArtifactRef) -> "RLLifecycleProtocol":
        return cls()

    def checkpoint(self, path: Path) -> None:
        return None

    def resume(self, path: Path) -> None:
        return None

    def emit_metric(self, key: str, value: float, *, step: int) -> None:
        return None


def test_rl_lifecycle_protocol_is_runtime_checkable() -> None:
    """Spec §2.1: Protocol MUST be ``@runtime_checkable``."""
    # ``_is_runtime_protocol`` is set by the @runtime_checkable decorator.
    assert getattr(RLLifecycleProtocol, "_is_runtime_protocol", False) is True


def test_conforming_adapter_passes_isinstance() -> None:
    """Spec §2.3: duck-typed adapter satisfies ``isinstance`` at runtime."""
    adapter = _ConformingAdapter()
    assert isinstance(adapter, RLLifecycleProtocol)


def test_non_conforming_adapter_fails_isinstance() -> None:
    """A class missing required methods MUST fail the Protocol check."""

    class _NotConforming:
        name = "bad"
        # Missing paradigm, buffer_kind, lifecycle methods.

    assert not isinstance(_NotConforming(), RLLifecycleProtocol)


def test_policy_artifact_ref_frozen() -> None:
    """``PolicyArtifactRef`` is a frozen dataclass — attr assignment blocked."""
    ref = PolicyArtifactRef(
        path=Path("/tmp/artifact"),
        sha="cafebabe",
        algorithm="dpo",
        policy_class="transformers.AutoModelForCausalLM",
        created_at=datetime.now(timezone.utc),
    )
    with pytest.raises(FrozenInstanceError):
        ref.sha = "mutated"  # type: ignore[misc]


def test_policy_artifact_ref_carries_tenant_id() -> None:
    """``tenant_id`` is optional but defaults to None (not empty string)."""
    ref = PolicyArtifactRef(
        path=Path("/tmp/x"),
        sha="abc",
        algorithm="ppo",
        policy_class="stable_baselines3.PPO",
        created_at=datetime.now(timezone.utc),
    )
    assert ref.tenant_id is None

    ref_t = PolicyArtifactRef(
        path=Path("/tmp/x"),
        sha="abc",
        algorithm="ppo",
        policy_class="stable_baselines3.PPO",
        created_at=datetime.now(timezone.utc),
        tenant_id="tenant-42",
    )
    assert ref_t.tenant_id == "tenant-42"
