# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: every Trainable.fit MUST populate TrainingResult.device.

Locks the spec invariant from
``workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md``
§ "Transparency contract" and orphan-detection §2: every fit returns
a DeviceReport — the public ``DeviceReport`` symbol must be wired
into the production hot path of every Trainable family.

This is a structural guard. The actual fit logic + assertions are
covered by per-family unit tests; this file mechanically asserts that
no return-TrainingResult site drops the ``device`` kwarg.

Origin: round-3 redteam (2026-04-19) found TorchTrainable + Lightning
Trainable returning TrainingResult without ``device=DeviceReport(...)``
— silent orphan of the GPU-first Phase 1 transparency contract.
Fixed in commit-on-feat/ml-gpu-phase1-integration; this test prevents
the next refactor from silently re-dropping it.
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
def test_every_return_trainingresult_has_device_kwarg() -> None:
    """Every TrainingResult constructor in trainable.py MUST pass device=.

    Mechanical AST guard against the round-3 redteam finding: lines
    889 + 1023 (TorchTrainable + LightningTrainable) returned
    TrainingResult without populating the device field, leaving the
    GPU-first Phase 1 transparency contract orphan for those two
    families. Fix landed inline; this test ensures any future refactor
    that drops the kwarg fails loudly at test time.
    """
    src = _trainable_module_path().read_text()
    tree = ast.parse(src)

    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match `TrainingResult(...)` constructor calls (not module-
        # qualified, since the file imports the symbol directly).
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "TrainingResult":
            continue
        kwarg_names = {kw.arg for kw in node.keywords if kw.arg is not None}
        if "device" not in kwarg_names:
            # Capture call site context for the error message.
            line_text = src.splitlines()[node.lineno - 1].strip()
            offenders.append((node.lineno, line_text))

    assert not offenders, (
        "Every TrainingResult(...) constructor call in trainable.py MUST "
        "populate the device=DeviceReport(...) kwarg per "
        "workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md "
        "§ 'Transparency contract'. Sites missing the device kwarg:\n"
        + "\n".join(f"  line {ln}: {txt}" for ln, txt in offenders)
    )


@pytest.mark.regression
def test_all_seven_phase_one_trainables_in_kailash_ml_all() -> None:
    """specs/ml-engines.md §3.0 — all 7 family adapters MUST be in kailash_ml.__all__.

    Origin: round-3 redteam spec-to-code sweep (2026-04-19) found only 2 of
    7 Trainables (UMAP + HDBSCAN — the new ones from Shard C) were in
    kailash_ml.__all__. The 5 pre-existing (Sklearn/XGBoost/LightGBM/
    Torch/Lightning) were accessible via kailash_ml.trainable but absent
    from the top-level export — silent spec violation that had been
    accumulating since 0.10.x. Fixed in 0.12.0.
    """
    import kailash_ml

    expected = {
        "SklearnTrainable",
        "XGBoostTrainable",
        "LightGBMTrainable",
        "TorchTrainable",
        "LightningTrainable",
        "UMAPTrainable",
        "HDBSCANTrainable",
    }
    actual = {n for n in kailash_ml.__all__ if n.endswith("Trainable")}
    missing = expected - actual
    assert not missing, (
        f"Per specs/ml-engines.md §3.0, all 7 Phase 1 family adapters MUST "
        f"be in kailash_ml.__all__. Missing: {sorted(missing)}. "
        f"Add eager imports to packages/kailash-ml/src/kailash_ml/__init__.py "
        f"AND list them in __all__ (per orphan-detection §6)."
    )
    # Each MUST be reachable as kailash_ml.<X>
    for name in expected:
        assert hasattr(kailash_ml, name), (
            f"{name} is in kailash_ml.__all__ but not on the kailash_ml "
            f"module — eager import missing in __init__.py"
        )


@pytest.mark.regression
def test_every_trainable_class_imports_device_report() -> None:
    """trainable.py MUST import DeviceReport at module scope.

    Belt-and-suspenders: an AST refactor that removes the
    `from kailash_ml._device_report import DeviceReport` line would
    break every device= construction silently (NameError at runtime),
    but only when fit() is actually called. This test catches it at
    import time.
    """
    src = _trainable_module_path().read_text()
    tree = ast.parse(src)

    has_device_report_import = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module == "kailash_ml._device_report":
            for alias in node.names:
                if alias.name == "DeviceReport":
                    has_device_report_import = True
                    break

    assert has_device_report_import, (
        "trainable.py MUST import DeviceReport at module scope from "
        "kailash_ml._device_report. The orphan-detection §1 contract "
        "requires every Trainable.fit() to construct a DeviceReport, "
        "and dropping the import silently breaks every family adapter."
    )
