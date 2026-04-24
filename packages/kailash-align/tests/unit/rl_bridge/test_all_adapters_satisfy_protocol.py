# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Spec §4 sweep: every BRIDGE_ADAPTERS entry satisfies RLLifecycleProtocol.

This is the cross-SDK Protocol-conformance gate. If a future adapter
lands that drifts from the Protocol contract (missing run_id attr,
wrong paradigm type, etc.) this test fails loudly without needing
every caller to add a targeted check.

Referenced in spec ``specs/ml-rl-align-unification.md`` v1.0.0 §4 as
``test_align_bridge_adapters_all_satisfy_protocol``.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_every_registered_adapter_satisfies_protocol():
    """For each name in BRIDGE_ADAPTERS, __make_for_test__() → Protocol-conformant."""
    # Import side effect populates the registry.
    import kailash_align.rl_bridge  # noqa: F401

    from kailash_ml.rl.align_adapter import BRIDGE_ADAPTERS
    from kailash_ml.rl.protocols import RLLifecycleProtocol

    assert len(BRIDGE_ADAPTERS) >= 4, (
        f"Expected at least 4 v1-scope bridge adapters, found {len(BRIDGE_ADAPTERS)}: "
        f"{sorted(BRIDGE_ADAPTERS)!r}"
    )

    failures: list[tuple[str, str]] = []
    for name, adapter_cls in BRIDGE_ADAPTERS.items():
        # Every adapter class must expose the __make_for_test__ factory
        # — spec §4 requires it for this conformance sweep.
        factory = getattr(adapter_cls, "__make_for_test__", None)
        if factory is None:
            failures.append(
                (name, f"{adapter_cls.__name__} missing __make_for_test__ classmethod")
            )
            continue

        instance = factory()
        if not isinstance(instance, RLLifecycleProtocol):
            failures.append(
                (
                    name,
                    f"{adapter_cls.__name__} instance does NOT satisfy "
                    f"RLLifecycleProtocol. Check class-level attrs "
                    f"(name/paradigm/buffer_kind), instance attrs "
                    f"(run_id/tenant_id/device), and method slots "
                    f"(build/learn/save/load/checkpoint/resume/emit_metric).",
                )
            )

    assert not failures, (
        "Spec §4 Protocol-conformance sweep FAILED for the following adapters:\n"
        + "\n".join(f"  - {name}: {reason}" for name, reason in failures)
        + "\n\nEvery adapter registered in BRIDGE_ADAPTERS MUST satisfy "
        "RLLifecycleProtocol at runtime. See spec §2 (Protocol contract) "
        "and specs/ml-rl-align-unification.md v1.0.0 §4."
    )


def test_class_level_attrs_match_registration_name():
    """adapter_cls.name == the key it is registered under in BRIDGE_ADAPTERS."""
    import kailash_align.rl_bridge  # noqa: F401

    from kailash_ml.rl.align_adapter import BRIDGE_ADAPTERS

    mismatches = [
        (name, adapter_cls.name)
        for name, adapter_cls in BRIDGE_ADAPTERS.items()
        if adapter_cls.name != name
    ]
    assert not mismatches, (
        f"BRIDGE_ADAPTERS registration-key drift from adapter.name: {mismatches!r}. "
        f"Every key must match adapter_cls.name so km.rl_train(algo=X) and "
        f"adapter_instance.name both resolve identically."
    )


def test_every_adapter_declares_rlhf_paradigm():
    """All v1-scope bridge adapters are paradigm='rlhf'."""
    import kailash_align.rl_bridge  # noqa: F401

    from kailash_ml.rl.align_adapter import BRIDGE_ADAPTERS

    wrong = [
        (name, adapter_cls.paradigm)
        for name, adapter_cls in BRIDGE_ADAPTERS.items()
        if adapter_cls.paradigm != "rlhf"
    ]
    assert not wrong, (
        f"Spec §9 v1 scope mandates paradigm='rlhf' for every bridge adapter; "
        f"drift detected: {wrong!r}"
    )


def test_buffer_kind_is_rollout_or_preference():
    """v1-scope bridge adapters use rollout or preference buffers (spec §9)."""
    import kailash_align.rl_bridge  # noqa: F401

    from kailash_ml.rl.align_adapter import BRIDGE_ADAPTERS

    allowed = {"rollout", "preference"}
    wrong = [
        (name, adapter_cls.buffer_kind)
        for name, adapter_cls in BRIDGE_ADAPTERS.items()
        if adapter_cls.buffer_kind not in allowed
    ]
    assert not wrong, (
        f"v1-scope bridge adapters restricted to rollout|preference buffers; "
        f"drift: {wrong!r}"
    )
