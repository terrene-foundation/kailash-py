# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W33 Tier-1 — ``kailash_ml.__all__`` membership + 6-group ordering.

Per ``specs/ml-engines-v2.md §15.9``, the package-level ``__all__``
MUST be organised into 6 groups in the exact order documented there.
Group 1 is ``track, autolog, train, diagnose, register, serve, watch,
dashboard, seed, reproduce, resume, lineage, rl_train`` (13 entries
per §15.9) plus ``erase_subject`` per W15 FP-MED-2 → 14. Groups 2-6
sum to 27 (15 + 5 + 2 + 3 + 2). Total: 41 + 7 Phase-1 Trainable
adapters + ``CatBoostTrainable`` (W6-013) = 49.

This test locks the ordering so a future refactor that silently
reorders the list — or drops one of the canonical verbs — fails
loudly at the unit tier instead of at the downstream consumer's
``from kailash_ml import *`` path.
"""
from __future__ import annotations

import kailash_ml


# Canonical ordering per spec §15.9 plus W15 clarification.
EXPECTED_GROUP_1 = (
    "track",
    "autolog",
    "train",
    "diagnose",
    "register",
    "serve",
    "watch",
    "dashboard",
    "seed",
    "reproduce",
    "resume",
    "lineage",
    "rl_train",
    "erase_subject",  # W15 FP-MED-2
)
EXPECTED_GROUP_2 = (
    "Engine",
    "Trainable",
    # Phase 1 family adapters (specs/ml-engines.md §3.0)
    "SklearnTrainable",
    "XGBoostTrainable",
    "LightGBMTrainable",
    "CatBoostTrainable",
    "TorchTrainable",
    "LightningTrainable",
    "UMAPTrainable",
    "HDBSCANTrainable",
    "TrainingResult",
    "MLError",
    "TrackingError",
    "AutologError",
    "RLError",
    "BackendError",
    "DriftMonitorError",
    "InferenceServerError",
    "ModelRegistryError",
    "FeatureStoreError",
    "AutoMLError",
    "DiagnosticsError",
    "DashboardError",
)
EXPECTED_GROUP_3 = (
    "DLDiagnostics",
    "RAGDiagnostics",
    "RLDiagnostics",
    "diagnose_classifier",
    "diagnose_regressor",
)
EXPECTED_GROUP_4 = ("detect_backend", "DeviceReport")
EXPECTED_GROUP_5 = ("ExperimentTracker", "ExperimentRun", "ModelRegistry")
EXPECTED_GROUP_6 = ("engine_info", "list_engines")

EXPECTED_ALL = (
    EXPECTED_GROUP_1
    + EXPECTED_GROUP_2
    + EXPECTED_GROUP_3
    + EXPECTED_GROUP_4
    + EXPECTED_GROUP_5
    + EXPECTED_GROUP_6
)


def test_all_has_expected_total_symbol_count() -> None:
    """``__all__`` MUST have exactly 49 symbols.

    40 §15.9 + W15 ``erase_subject`` + 7 Phase-1 Trainable adapters +
    ``CatBoostTrainable`` (W6-013 / F-E1-01).
    """
    assert len(kailash_ml.__all__) == 49, (
        f"expected 49 symbols (§15.9 40 + W15 erase_subject + 7 ml-engines.md §3.0 adapters "
        f"+ CatBoostTrainable W6-013), got {len(kailash_ml.__all__)}: {kailash_ml.__all__}"
    )


def test_all_is_exactly_expected_ordering() -> None:
    """``__all__`` MUST match the canonical sequence (ordering is load-bearing)."""
    actual = tuple(kailash_ml.__all__)
    assert actual == EXPECTED_ALL, (
        "kailash_ml.__all__ diverged from spec §15.9 canonical ordering.\n"
        f"expected: {EXPECTED_ALL}\n"
        f"actual:   {actual}"
    )


def test_group_1_lifecycle_verbs_come_first() -> None:
    """Verbs Group 1 MUST occupy positions 0..13 (verbs first per §15.9)."""
    for idx, name in enumerate(EXPECTED_GROUP_1):
        assert kailash_ml.__all__[idx] == name, (
            f"Group 1 verb at position {idx} expected {name!r}, "
            f"got {kailash_ml.__all__[idx]!r}"
        )


def test_group_6_discovery_comes_last() -> None:
    """``engine_info`` + ``list_engines`` MUST be the last two entries."""
    assert kailash_ml.__all__[-2:] == list(
        EXPECTED_GROUP_6
    ), f"Group 6 (discovery) MUST be last; got {kailash_ml.__all__[-2:]}"


def test_all_has_no_duplicates() -> None:
    """Every ``__all__`` entry MUST appear exactly once."""
    seen = set()
    dupes = []
    for name in kailash_ml.__all__:
        if name in seen:
            dupes.append(name)
        seen.add(name)
    assert not dupes, f"duplicate entries in __all__: {dupes}"


def test_group_2_primitives_and_errors() -> None:
    """Group 2 is primitives + the 12-class MLError hierarchy per §15.9."""
    # Start index = len(Group 1).
    start = len(EXPECTED_GROUP_1)
    end = start + len(EXPECTED_GROUP_2)
    assert tuple(kailash_ml.__all__[start:end]) == EXPECTED_GROUP_2


def test_group_3_diagnostics() -> None:
    """Group 3 is the 5 diagnostic adapters/helpers."""
    start = len(EXPECTED_GROUP_1) + len(EXPECTED_GROUP_2)
    end = start + len(EXPECTED_GROUP_3)
    assert tuple(kailash_ml.__all__[start:end]) == EXPECTED_GROUP_3


def test_group_4_backend_pair() -> None:
    """Group 4 is the (detect_backend, DeviceReport) pair."""
    start = len(EXPECTED_GROUP_1) + len(EXPECTED_GROUP_2) + len(EXPECTED_GROUP_3)
    end = start + len(EXPECTED_GROUP_4)
    assert tuple(kailash_ml.__all__[start:end]) == EXPECTED_GROUP_4


def test_group_5_tracker_primitives() -> None:
    """Group 5 is the tracker primitives trio."""
    start = (
        len(EXPECTED_GROUP_1)
        + len(EXPECTED_GROUP_2)
        + len(EXPECTED_GROUP_3)
        + len(EXPECTED_GROUP_4)
    )
    end = start + len(EXPECTED_GROUP_5)
    assert tuple(kailash_ml.__all__[start:end]) == EXPECTED_GROUP_5
