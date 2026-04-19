# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: every Trainable.predict MUST return Predictions carrying device=.

Sibling invariant of ``test_trainable_device_report_invariant.py`` for
the predict-side half of the GPU-first Phase 1 transparency contract
(see ``workspaces/kailash-ml-gpu-stack/journal/0005-GAP-predictions-device-field-missing.md``).

Spec: ``workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md``
§ "Transparency contract" — every predict returns a Predictions whose
``device`` attribute is the DeviceReport cached at fit-time. Adapters
MUST construct ``Predictions(..., device=self._last_device_report)``
and MUST cache ``self._last_device_report = device_report`` right
before returning TrainingResult from fit().

This is a mechanical AST guard — no per-family unit test can catch
"the fit() site dropped the cache" or "the predict() site dropped the
kwarg" structurally. Each drop is a silent orphan of the predict-side
transparency contract.

Origin: kailash-ml 0.12.1 — Predictions.device field landed in this
release; the 0.12.0 punch list deferred it to 0.12.1.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


def _trainable_module_path() -> Path:
    """Path to packages/kailash-ml/src/kailash_ml/trainable.py."""
    here = Path(__file__).resolve()
    # tests/regression/test_*.py -> packages/kailash-ml
    pkg_root = here.parent.parent.parent
    return pkg_root / "src" / "kailash_ml" / "trainable.py"


@pytest.mark.regression
def test_every_return_predictions_has_device_kwarg() -> None:
    """Every Predictions() constructor inside a predict() method MUST pass device=.

    Mechanical AST guard: a refactor that drops the ``device=`` kwarg
    silently ships Predictions with ``device=None``, which breaks every
    downstream caller that inspects ``pred.device.backend`` /
    ``pred.device.fallback_reason``. This test catches the drop at
    test-collection time.

    Scope: Predictions() calls appear in 7 predict() methods (one per
    family). This test walks the AST, filters to Predictions calls that
    are inside a function whose name is 'predict', and asserts each one
    passes device= as a kwarg.
    """
    src = _trainable_module_path().read_text()
    tree = ast.parse(src)

    offenders: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "predict":
            continue
        # Walk the predict body looking for Predictions(...) constructor calls.
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            if not isinstance(func, ast.Name) or func.id != "Predictions":
                continue
            kwarg_names = {kw.arg for kw in inner.keywords if kw.arg is not None}
            if "device" not in kwarg_names:
                line_text = src.splitlines()[inner.lineno - 1].strip()
                offenders.append((inner.lineno, line_text))

    assert not offenders, (
        "Every Predictions(...) constructor inside a predict() method in "
        "trainable.py MUST pass device=<DeviceReport> per "
        "workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md "
        "§ 'Transparency contract'. Sites missing the device kwarg:\n"
        + "\n".join(f"  line {ln}: {txt}" for ln, txt in offenders)
    )


@pytest.mark.regression
def test_every_fit_caches_last_device_report() -> None:
    """Every Trainable.fit MUST assign self._last_device_report before returning.

    The predict() path references ``self._last_device_report`` — that
    attribute is set ONLY by fit(). A fit() path that constructs a
    DeviceReport but never caches it leaves predict() reading a stale
    or missing attribute.

    Mechanical AST guard: walk each fit() FunctionDef; assert there is
    at least one ``self._last_device_report = ...`` Assign statement in
    its body (including nested blocks).
    """
    src = _trainable_module_path().read_text()
    tree = ast.parse(src)

    fit_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "fit"
    ]

    # Phase 1 ships 7 families; each class has one fit(). Protocol definition
    # Trainable.fit (a `...` body) brings the total to 8 — filter it out.
    real_fits = [
        f
        for f in fit_functions
        if not (
            len(f.body) == 1
            and isinstance(f.body[0], ast.Expr)
            and isinstance(f.body[0].value, ast.Constant)
        )
    ]
    assert len(real_fits) == 7, (
        f"Expected 7 concrete fit() methods (one per Phase 1 family); "
        f"found {len(real_fits)}. If a family was added/removed, update "
        f"this invariant."
    )

    missing: list[tuple[int, str]] = []
    for fit in real_fits:
        found = False
        for inner in ast.walk(fit):
            if not isinstance(inner, ast.Assign):
                continue
            for target in inner.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and target.attr == "_last_device_report"
                ):
                    found = True
                    break
            if found:
                break
        if not found:
            missing.append((fit.lineno, fit.name))

    assert not missing, (
        "Every Trainable.fit() method MUST cache the DeviceReport via "
        "``self._last_device_report = device_report`` before returning "
        "TrainingResult. Without it, predict() reads a missing attribute. "
        f"Fits missing the cache: {missing}"
    )


@pytest.mark.regression
def test_predictions_class_has_device_slot_and_property() -> None:
    """Predictions MUST declare _device in __slots__ and expose a device property.

    Belt-and-suspenders: the field addition is both a slots entry
    (runtime enforcement) and a property (API surface). A refactor that
    drops either half silently breaks the contract — slots drop makes
    assignment fail with AttributeError at construction time; property
    drop makes ``pred.device`` inaccessible.
    """
    from kailash_ml.trainable import Predictions

    # __slots__ MUST contain _device
    assert "_device" in Predictions.__slots__, (
        "Predictions.__slots__ MUST include '_device' for the device "
        "field. Current __slots__: " + repr(Predictions.__slots__)
    )

    # .device property MUST be accessible
    assert hasattr(
        Predictions, "device"
    ), "Predictions MUST expose a public 'device' attribute/property."

    # Constructing without device gives None (optional at API level)
    p = Predictions([0, 1, 2])
    assert p.device is None, (
        "Predictions() with no device kwarg MUST return device=None "
        "(backward-compat for direct callers; Phase 1 adapters always "
        "populate device via self._last_device_report)."
    )
