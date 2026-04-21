# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W8 regression — Trainable Protocol + TrainingResult device wiring.

Mechanical invariant from `todos/active/W08-trainable-protocol-training-result.md`
invariant 7:

    grep -c "return TrainingResult(" src/  ==  grep -cE "device=DeviceReport|device=device_report|device=report" src/

Every TrainingResult-return site MUST pass ``device=`` so that
downstream consumers (ModelRegistry, MLDashboard, RL trainer) can
distinguish genuine GPU runs from silent CPU fallback.

This test is a LOC-invariant-style guard (per
`rules/refactor-invariants.md`): any future refactor that extracts
a new return site without plumbing ``device=`` breaks the parity gate
immediately, NOT at the next /redteam.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TRAINABLE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "kailash_ml" / "trainable.py"
)


@pytest.mark.regression
@pytest.mark.invariant
def test_trainable_path_exists():
    """Guard: trainable.py MUST exist at the canonical location."""
    assert TRAINABLE_PATH.is_file(), f"trainable.py missing at {TRAINABLE_PATH}"


@pytest.mark.regression
@pytest.mark.invariant
def test_every_training_result_return_passes_device_kwarg():
    """Parity: # of `return TrainingResult(` == # of `device=device_report` sites.

    Per W8 invariant 7: every TrainingResult return site in the
    adapter module MUST populate the ``device`` field so callers
    can distinguish genuine GPU runs from CPU fallback.
    """
    src = TRAINABLE_PATH.read_text()

    return_sites = len(re.findall(r"return TrainingResult\(", src))
    device_kwargs = len(
        re.findall(r"device=(?:device_report|DeviceReport|report)\b", src)
    )

    assert return_sites > 0, "expected at least one TrainingResult return"
    assert return_sites == device_kwargs, (
        f"parity broken: {return_sites} `return TrainingResult(` sites but "
        f"{device_kwargs} `device=device_report` kwargs. Every site MUST "
        f"pass `device=` so GPU/CPU fallback is observable "
        f"(W8 invariant 7)."
    )


@pytest.mark.regression
@pytest.mark.invariant
def test_trainable_protocol_is_runtime_checkable():
    """Trainable Protocol MUST be @runtime_checkable so isinstance() works.

    Per W8 invariant 1 + `specs/ml-engines.md §3.1`.
    """
    from kailash_ml.trainable import Trainable

    # _is_runtime_protocol is the internal flag set by @runtime_checkable.
    # The Protocol will allow isinstance checks only when runtime_checkable.
    class _Dummy:
        family_name = "dummy"

        def fit(self, data, *, hyperparameters, context):  # pragma: no cover
            raise NotImplementedError

        def predict(self, X):  # pragma: no cover
            raise NotImplementedError

        def to_lightning_module(self):  # pragma: no cover
            raise NotImplementedError

        def get_param_distribution(self):  # pragma: no cover
            raise NotImplementedError

    assert isinstance(_Dummy(), Trainable), (
        "Trainable is not runtime_checkable; add @runtime_checkable "
        "decorator above the Protocol definition."
    )


@pytest.mark.regression
@pytest.mark.invariant
def test_training_result_requires_device_field_wired():
    """TrainingResult has a `device: Optional[DeviceReport]` field.

    Soft guard that a refactor removing the field surfaces loudly.
    """
    from dataclasses import fields

    from kailash_ml._result import TrainingResult

    names = {f.name for f in fields(TrainingResult)}
    assert "device" in names, (
        "TrainingResult.device field removed; W8 invariant 5 broken. "
        "Restore the field so GPU/CPU fallback evidence reaches callers."
    )
