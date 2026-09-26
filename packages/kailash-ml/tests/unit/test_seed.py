# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for ``kailash_ml.seed`` + :class:`SeedReport`.

Exercises the per-subsystem applied/skipped contract, opt-out kwargs,
idempotence, and the torch_deterministic downstream dependency.
"""
from __future__ import annotations

import os
import random
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import kailash_ml
from kailash_ml._seed import SeedReport, seed


@pytest.fixture
def optional_seed_modules(monkeypatch):
    """Keep dispatch tests independent of optional ML import costs."""
    modules = {
        "numpy.random": SimpleNamespace(seed=Mock()),
        "torch": SimpleNamespace(
            manual_seed=Mock(),
            cuda=SimpleNamespace(is_available=lambda: False),
            use_deterministic_algorithms=Mock(),
        ),
        "pytorch_lightning": SimpleNamespace(seed_everything=Mock()),
        "sklearn": SimpleNamespace(),
        "numpy": SimpleNamespace(
            show_config=lambda **kwargs: {
                "Build Dependencies": {"blas": {"name": "openblas"}}
            }
        ),
    }
    monkeypatch.setattr(kailash_ml._seed, "_try_import", modules.__getitem__)
    return modules


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


def test_torch_deterministic_false_when_torch_opted_out(optional_seed_modules):
    # torch_deterministic only fires when torch was actually seeded.
    r = seed(42, torch=False)
    assert r.torch_deterministic is False, "torch opt-out reported determinism"
    assert dict(r.skipped)["torch"] == "opt_out"
    optional_seed_modules["torch"].manual_seed.assert_not_called()
    optional_seed_modules["torch"].use_deterministic_algorithms.assert_not_called()
    # Lightning's flag is independent of torch's flag.
    optional_seed_modules["pytorch_lightning"].seed_everything.assert_called_once_with(
        42, workers=True
    )


def test_torch_deterministic_true_when_torch_seeded(optional_seed_modules):
    r = seed(42)
    assert r.torch_deterministic is True, "seeded torch did not report determinism"
    optional_seed_modules["torch"].manual_seed.assert_called_once_with(42)
    optional_seed_modules["torch"].use_deterministic_algorithms.assert_called_once_with(
        True
    )


def test_seed_report_is_hashable():
    # Frozen dataclass → hashable. Enables use as a dict key.
    r = SeedReport(seed=42, applied=("python",))
    {r: "ok"}  # does not raise


def test_applied_list_order_deterministic(optional_seed_modules):
    """Applied list order is a public contract — reproducibility audits
    grep for specific strings in specific positions."""
    r = seed(42, python=True, numpy=True, torch=True, lightning=True, sklearn=True)
    assert r.applied == (
        "pythonhashseed",
        "python",
        "numpy",
        "torch",
        "lightning",
        "sklearn",
    ), "unexpected seed application order"


# --- blas_backend (ml-engines-v2.md §11.2 MUST 5) ---------------------------


def test_seed_report_carries_blas_backend_field():
    """The field exists, defaults to None, and does not break positional
    construction of the pre-existing fields (it is appended last)."""
    r = SeedReport(seed=42, applied=("python",))
    assert r.blas_backend is None
    assert "blas_backend" in SeedReport.__dataclass_fields__


def test_blas_backend_detected_when_numpy_present():
    """With numpy installed the probe MUST name a backend, not None.

    Falsifying result: a None here would mean the probe never reads
    numpy.show_config and the field is decorative.
    """
    from kailash_ml._seed import _detect_blas_backend

    pytest.importorskip("numpy")
    detected = _detect_blas_backend()
    assert detected is not None
    assert detected == detected.lower()


def test_blas_backend_is_none_when_numpy_absent(monkeypatch):
    """Negative control — the probe MUST return None rather than a stale
    or hardcoded backend name when numpy cannot be imported."""
    import kailash_ml._seed as seed_mod

    monkeypatch.setattr(seed_mod, "_try_import", lambda _p: None)
    assert seed_mod._detect_blas_backend() is None


def test_blas_backend_probe_never_raises(monkeypatch):
    """A reproducibility annotation MUST NOT be able to break seeding:
    an exploding show_config degrades to None."""
    import kailash_ml._seed as seed_mod

    class _Exploding:
        def show_config(self, *a, **k):
            raise RuntimeError("probe blew up")

    monkeypatch.setattr(
        seed_mod, "_try_import", lambda p: _Exploding() if p == "numpy" else None
    )
    assert seed_mod._detect_blas_backend() is None


def test_seed_populates_blas_backend_on_the_report():
    """End-to-end: km.seed() MUST populate the field, not leave the default."""
    pytest.importorskip("numpy")
    r = seed(42, torch=False, lightning=False, sklearn=False)
    assert r.blas_backend is not None
