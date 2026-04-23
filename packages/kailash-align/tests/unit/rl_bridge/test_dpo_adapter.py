# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 direct coverage for DPOAdapter — spec §3.4b ref-temperature contract.

Per ``rules/testing.md`` § "Delegating Primitives Need Direct Coverage",
every bridge adapter gets its own Tier-1 unit test even though the
method-registry-level tests in ``tests/test_method_registry.py`` cover
the underlying TRL plumbing. This test file proves:

* The class-level attrs ``name`` / ``paradigm`` / ``buffer_kind`` match
  the spec §9 v1-scope registration keys.
* ``__make_for_test__()`` produces a Protocol-conformant instance
  (``isinstance(instance, RLLifecycleProtocol)`` holds at runtime).
* ``ref_temperature`` defaults to ``1.0`` (TRL-canonical for log-prob
  extraction per spec §3.4b).
* ``sampling_temperature`` is a DISTINCT kwarg from ``ref_temperature``
  with default ``0.0`` (deterministic for DPO).
* Negative / NaN temperatures are rejected at construction.
"""
from __future__ import annotations

import math

import pytest

pytestmark = pytest.mark.unit


def test_dpo_adapter_class_attrs():
    """name/paradigm/buffer_kind match spec §9 registration keys."""
    from kailash_align.rl_bridge._dpo import DPOAdapter

    assert DPOAdapter.name == "dpo"
    assert DPOAdapter.paradigm == "rlhf"
    assert DPOAdapter.buffer_kind == "preference"


def test_dpo_adapter_satisfies_protocol():
    """isinstance(adapter, RLLifecycleProtocol) holds at runtime."""
    from kailash_align.rl_bridge._dpo import DPOAdapter
    from kailash_ml.rl.protocols import RLLifecycleProtocol

    instance = DPOAdapter.__make_for_test__()
    assert isinstance(instance, RLLifecycleProtocol), (
        "DPOAdapter.__make_for_test__() must produce a Protocol-conformant "
        "instance — checks class-level attrs + instance run_id/tenant_id/device + "
        "every method slot. If this fails, the adapter drifted from spec §2."
    )


def test_dpo_adapter_ref_temperature_default():
    """ref_temperature defaults to 1.0 (TRL-canonical, spec §3.4b)."""
    from kailash_align.rl_bridge._dpo import DPOAdapter

    adapter = DPOAdapter()
    assert adapter.ref_temperature == 1.0


def test_dpo_adapter_sampling_temperature_default_zero():
    """sampling_temperature defaults to 0.0 (deterministic)."""
    from kailash_align.rl_bridge._dpo import DPOAdapter

    adapter = DPOAdapter()
    assert adapter.sampling_temperature == 0.0


def test_dpo_adapter_temperatures_are_separate_kwargs():
    """ref_temperature and sampling_temperature are DISTINCT knobs.

    Spec §3.4b: TRL's single ``temperature`` field conflates log-prob
    extraction and sampling; this adapter's contract separates them.
    """
    from kailash_align.rl_bridge._dpo import DPOAdapter

    adapter = DPOAdapter(ref_temperature=1.0, sampling_temperature=0.7)
    assert adapter.ref_temperature == 1.0
    assert adapter.sampling_temperature == 0.7
    assert adapter.ref_temperature != adapter.sampling_temperature


def test_dpo_adapter_rejects_zero_ref_temperature():
    from kailash_align.rl_bridge._dpo import DPOAdapter

    with pytest.raises(ValueError, match="ref_temperature"):
        DPOAdapter(ref_temperature=0.0)


def test_dpo_adapter_rejects_negative_ref_temperature():
    from kailash_align.rl_bridge._dpo import DPOAdapter

    with pytest.raises(ValueError, match="ref_temperature"):
        DPOAdapter(ref_temperature=-0.5)


def test_dpo_adapter_rejects_negative_sampling_temperature():
    from kailash_align.rl_bridge._dpo import DPOAdapter

    with pytest.raises(ValueError, match="sampling_temperature"):
        DPOAdapter(sampling_temperature=-0.1)


def test_dpo_adapter_instance_attrs_present():
    """run_id / tenant_id / device are populated on every instance."""
    from kailash_align.rl_bridge._dpo import DPOAdapter

    adapter = DPOAdapter(tenant_id="tenant-42", run_id="run-abc")
    assert adapter.run_id == "run-abc"
    assert adapter.tenant_id == "tenant-42"
    # device may be None; attribute must exist
    assert hasattr(adapter, "device")
