# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: GH issue #752 — `pytorch-lightning` is the canonical Lightning distribution.

Before kailash-ml 1.7.0, this package depended on the umbrella ``lightning``
package (``packages/kailash-ml/pyproject.toml`` declared ``lightning>=2.2``
on lines 52 + 71). On 2026-04, PyPI flagged ``lightning`` with
``pypi:project-status="quarantined"`` (visible at
https://pypi.org/simple/lightning/), which hides every version from
resolvers. Every fresh ``pip install kailash-ml`` from PyPI broke at dep
resolution; CI on every PR touching ``packages/kailash-ml/**`` /
``packages/kailash-align/**`` failed at the install step.

kailash-ml 1.7.0 migrated to the standalone ``pytorch-lightning`` distribution
(active on PyPI, latest 2.6.1) which has full API parity at every call site
this package uses (``Trainer``, ``LightningModule``, ``Callback``,
``ModelCheckpoint``).

This regression test gates against future re-quarantine of either
distribution by asserting that the canonical Lightning surface
kailash-ml depends on is importable from the active distribution. If
``pytorch-lightning`` is ever quarantined, this test fails at
``--collect-only`` time in CI — the same gating mechanism #752 wishes
had existed before the umbrella package's quarantine reached users via
broken installs.

Per ``rules/cross-sdk-inspection.md``: ``kailash-rs`` does not depend on
the ``lightning`` Python package; this incident is Python-only and no
cross-SDK companion test is required.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.regression
def test_pytorch_lightning_distribution_is_installable() -> None:
    """``pytorch_lightning`` MUST be importable.

    The umbrella ``lightning`` package quarantine on PyPI (#752) was
    invisible to CI until users hit broken installs. This test makes
    the equivalent failure mode loud at collection time.
    """
    pl = importlib.import_module("pytorch_lightning")
    assert hasattr(pl, "Trainer"), (
        "pytorch_lightning.Trainer missing — Lightning distribution may have "
        "broken or been re-quarantined; see #752 for the migration history."
    )
    assert hasattr(pl, "LightningModule"), "pytorch_lightning.LightningModule missing"


@pytest.mark.regression
def test_pytorch_lightning_callbacks_surface_is_importable() -> None:
    """The callbacks submodule MUST resolve.

    ``packages/kailash-ml/src/kailash_ml/engine.py`` line 82 +
    ``packages/kailash-ml/src/kailash_ml/autolog/_lightning.py`` line ~143
    +
    ``packages/kailash-ml/src/kailash_ml/diagnostics/dl.py`` line ~544
    all import ``Callback`` / ``ModelCheckpoint`` from this submodule.
    """
    callbacks = importlib.import_module("pytorch_lightning.callbacks")
    assert hasattr(callbacks, "Callback"), (
        "pytorch_lightning.callbacks.Callback missing — engine.auto_checkpoint "
        "+ autolog + DLDiagnostics break without it"
    )
    assert hasattr(callbacks, "ModelCheckpoint"), (
        "pytorch_lightning.callbacks.ModelCheckpoint missing — "
        "TrainingPipeline._train_lightning auto-checkpoint breaks"
    )


@pytest.mark.regression
def test_pytorch_lightning_dep_declared_in_pyproject() -> None:
    """``pyproject.toml`` MUST declare ``pytorch-lightning``, not the umbrella.

    Locks the dep declaration against accidental revert to the
    quarantined ``lightning`` package. If a future refactor reintroduces
    ``lightning>=`` as a base / [dl] dep, this test fails loudly with
    a pointer back to #752.
    """
    import pathlib

    here = pathlib.Path(__file__).resolve()
    # tests/regression/<this>.py → packages/kailash-ml/pyproject.toml
    pyproject_path = here.parents[2] / "pyproject.toml"
    assert pyproject_path.is_file(), f"pyproject.toml not found at {pyproject_path}"
    text = pyproject_path.read_text()
    assert '"pytorch-lightning>=' in text, (
        "pyproject.toml MUST declare pytorch-lightning>=X.Y as the Lightning "
        "dep (#752 migration). The umbrella `lightning` package was "
        "quarantined on PyPI; reverting to it breaks every fresh install."
    )
    # The base + dl extras both pin pytorch-lightning. The umbrella name
    # MUST NOT appear as a pinned dependency (a fallback `lightning>=` line
    # would re-introduce the broken-resolver failure).
    base_dep_line = '"lightning>='
    assert base_dep_line not in text, (
        f"pyproject.toml contains `{base_dep_line}` — the umbrella `lightning` "
        "package was quarantined on PyPI in 2026-04 (#752). Use "
        "`pytorch-lightning>=` instead."
    )
