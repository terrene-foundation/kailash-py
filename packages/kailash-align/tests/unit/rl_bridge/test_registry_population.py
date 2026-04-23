# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Registry-population test: import kailash_align.rl_bridge activates BRIDGE_ADAPTERS.

Per spec §3, ``km.rl_train(algo=<name>)`` lazy-imports
``kailash_align.rl_bridge`` and the import side effect populates
:data:`kailash_ml.rl.align_adapter.BRIDGE_ADAPTERS` with the four
v1-scope adapter classes. This test validates that contract.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_import_registers_all_four_adapters():
    """Importing the bridge populates BRIDGE_ADAPTERS with the v1 names."""
    # Fresh import of the bridge package — side effect registers adapters.
    import kailash_align.rl_bridge  # noqa: F401 — imported for side effect

    from kailash_ml.rl.align_adapter import BRIDGE_ADAPTERS

    expected = {"dpo", "ppo-rlhf", "rloo", "online-dpo"}
    actual = set(BRIDGE_ADAPTERS.keys())
    missing = expected - actual
    assert not missing, (
        f"BRIDGE_ADAPTERS missing {missing!r} after import kailash_align.rl_bridge. "
        f"Current registry: {sorted(actual)!r}. "
        f"Check register_bridge_adapters() in "
        f"packages/kailash-align/src/kailash_align/rl_bridge/__init__.py."
    )


def test_registered_classes_match_adapter_types():
    """Each registered entry is the expected adapter class."""
    import kailash_align.rl_bridge  # noqa: F401

    from kailash_align.rl_bridge._dpo import DPOAdapter
    from kailash_align.rl_bridge._online_dpo import OnlineDPOAdapter
    from kailash_align.rl_bridge._ppo_rlhf import PPORLHFAdapter
    from kailash_align.rl_bridge._rloo import RLOOAdapter
    from kailash_ml.rl.align_adapter import BRIDGE_ADAPTERS

    assert BRIDGE_ADAPTERS["dpo"] is DPOAdapter
    assert BRIDGE_ADAPTERS["ppo-rlhf"] is PPORLHFAdapter
    assert BRIDGE_ADAPTERS["rloo"] is RLOOAdapter
    assert BRIDGE_ADAPTERS["online-dpo"] is OnlineDPOAdapter


def test_resolve_bridge_adapter_returns_class():
    """km.rl_train's resolver finds every registered adapter by name."""
    import kailash_align.rl_bridge  # noqa: F401

    from kailash_ml.rl.align_adapter import resolve_bridge_adapter

    for name in ("dpo", "ppo-rlhf", "rloo", "online-dpo"):
        cls = resolve_bridge_adapter(name)
        assert cls is not None
        assert cls.name == name


def test_re_register_same_class_idempotent():
    """Re-calling register_bridge_adapters doesn't raise — registry is idempotent."""
    from kailash_align.rl_bridge import register_bridge_adapters

    # Second call MUST NOT raise ValueError (raises only on DIFFERENT class).
    register_bridge_adapters()
    register_bridge_adapters()


def test_all_exports_include_adapter_symbols():
    """__all__ advertises all four adapter classes for downstream consumers."""
    import kailash_align.rl_bridge as bridge

    for expected in (
        "DPOAdapter",
        "PPORLHFAdapter",
        "RLOOAdapter",
        "OnlineDPOAdapter",
        "register_bridge_adapters",
        "BRIDGE_ADAPTERS",
        "FeatureNotAvailableError",
        "register_bridge_adapter",
    ):
        assert expected in bridge.__all__, (
            f"kailash_align.rl_bridge.__all__ missing {expected!r}; "
            f"current __all__: {bridge.__all__!r}"
        )
