# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 identity tests for ``kailash_ml/__init__.py`` ``__getattr__`` map.

W6-018 (todo ``W6-018-flip-getattr-canonical-automl``) flipped the
``_LAZY_MAP["AutoMLEngine"]`` entry from the deleted legacy scaffold
``kailash_ml.engines.automl_engine`` to the canonical surface
``kailash_ml.automl.engine``. The identity invariant below pins that
flip: ``from kailash_ml import AutoMLEngine`` and
``from kailash_ml.automl import AutoMLEngine`` MUST resolve to the same
class object. If the lazy map drifts back to a legacy path or a parallel
implementation lands, this test fires loudly.

See ``specs/ml-automl.md`` § 1.3 for the canonical surface contract and
``rules/orphan-detection.md`` § 3 (Removed = Deleted) for the deletion
discipline behind W6-018.
"""
from __future__ import annotations

import importlib


def test_kailash_ml_AutoMLEngine_resolves_to_canonical() -> None:
    """``km.AutoMLEngine`` IS ``kailash_ml.automl.AutoMLEngine`` (W6-018)."""
    from kailash_ml import AutoMLEngine as via_lazy
    from kailash_ml.automl import AutoMLEngine as via_direct

    assert via_lazy is via_direct, (
        "kailash_ml.AutoMLEngine MUST resolve to kailash_ml.automl.AutoMLEngine. "
        "If a parallel implementation has landed under kailash_ml.engines.* or "
        "elsewhere, the W6-018 canonicalization has regressed — see "
        "specs/ml-automl.md § 1.3 and rules/orphan-detection.md § 3."
    )


def test_kailash_ml_AutoMLEngine_resolves_to_canonical_module() -> None:
    """The resolved class lives under ``kailash_ml.automl.engine``."""
    from kailash_ml import AutoMLEngine

    canonical_module = importlib.import_module("kailash_ml.automl.engine")
    assert AutoMLEngine.__module__ == "kailash_ml.automl.engine"
    assert AutoMLEngine is canonical_module.AutoMLEngine


def test_legacy_engines_automl_engine_is_deleted() -> None:
    """``kailash_ml.engines.automl_engine`` MUST NOT be importable (W6-018).

    Per ``rules/orphan-detection.md`` § 3, the legacy scaffold was deleted
    rather than deprecated. If a future change reintroduces the module,
    canonical resolution drift is silently possible — fail loudly here.
    """
    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("kailash_ml.engines.automl_engine")
