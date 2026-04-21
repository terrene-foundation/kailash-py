# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for ``kailash_ml.seed`` + :class:`SeedReport`.

Exercises the per-subsystem applied/skipped contract, opt-out kwargs,
idempotence, and the torch_deterministic downstream dependency.
"""
from __future__ import annotations

import os
import random

import kailash_ml
import pytest
from kailash_ml._seed import SeedReport, seed


def test_seed_report_is_exported_at_package_root():
    assert kailash_ml.SeedReport is SeedReport
    assert kailash_ml.seed is seed


def test_seed_report_is_frozen():
    r = SeedReport(seed=42, applied=("python",))
    with pytest.raises((AttributeError, Exception)):
        r.seed = 99  # frozen dataclass


def test_seed_applies_to_python_random():
    r = seed(42, numpy=False, torch=False, lightning=False, sklearn=False)
    assert "python" in r.applied
    x = random.random()

    seed(42, numpy=False, torch=False, lightning=False, sklearn=False)
    y = random.random()
    assert x == y  # same seed → same draw


def test_seed_records_pythonhashseed_applied():
    r = seed(
        123, python=False, numpy=False, torch=False, lightning=False, sklearn=False
    )
    assert "pythonhashseed" in r.applied
    assert os.environ["PYTHONHASHSEED"] == "123"


def test_opt_out_records_skip_reason():
    r = seed(42, python=False, numpy=False, torch=False, lightning=False, sklearn=False)
    skipped = dict(r.skipped)
    assert skipped["python"] == "opt_out"
    assert skipped["numpy"] == "opt_out"
    assert skipped["torch"] == "opt_out"
    assert skipped["lightning"] == "opt_out"
    assert skipped["sklearn"] == "opt_out"


def test_missing_dep_recorded_as_skip_reason(monkeypatch):
    """Simulate a missing dep via monkeypatch on _try_import."""
    import kailash_ml._seed as seed_mod

    def fake_try_import(path):
        # Force numpy import to "fail"
        if path == "numpy.random":
            return None
        # Everything else uses the real resolver
        return kailash_ml._seed.__class_getitem__ if False else None

    # Block every external dep so we exercise the "missing" path
    monkeypatch.setattr(seed_mod, "_try_import", lambda _p: None)

    r = seed(42)
    skipped = dict(r.skipped)
    assert skipped.get("numpy") == "missing_dep"
    assert skipped.get("torch") == "missing_dep"
    assert skipped.get("lightning") == "missing_dep"
    assert skipped.get("sklearn") == "missing_dep"


def test_idempotent_same_seed_reproduces_python_state():
    r1 = seed(7, numpy=False, torch=False, lightning=False, sklearn=False)
    values_1 = [random.random() for _ in range(5)]

    r2 = seed(7, numpy=False, torch=False, lightning=False, sklearn=False)
    values_2 = [random.random() for _ in range(5)]

    assert values_1 == values_2
    assert r1.seed == r2.seed == 7


def test_different_seeds_produce_different_values():
    seed(1, numpy=False, torch=False, lightning=False, sklearn=False)
    x = random.random()
    seed(2, numpy=False, torch=False, lightning=False, sklearn=False)
    y = random.random()
    assert x != y


def test_seed_report_contains_subsystem_via_in():
    r = SeedReport(seed=42, applied=("python", "numpy"))
    assert "python" in r
    assert "numpy" in r
    assert "torch" not in r


def test_torch_deterministic_false_when_torch_opted_out():
    # torch_deterministic only fires when torch was actually seeded.
    r = seed(42, torch=False)
    assert r.torch_deterministic is False


def test_seed_report_is_hashable():
    # Frozen dataclass → hashable. Enables use as a dict key.
    r = SeedReport(seed=42, applied=("python",))
    {r: "ok"}  # does not raise


def test_applied_list_order_deterministic():
    """Applied list order is a public contract — reproducibility audits
    grep for specific strings in specific positions."""
    r = seed(42, python=True, numpy=True, torch=True, lightning=True, sklearn=True)
    # pythonhashseed is always first
    assert r.applied[0] == "pythonhashseed"
    # python always second (when applied)
    if "python" in r.applied:
        assert r.applied[1] == "python"
