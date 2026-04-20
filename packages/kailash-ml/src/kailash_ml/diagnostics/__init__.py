# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Diagnostics adapters for kailash-ml.

Every adapter in this package conforms to the
``kailash.diagnostics.protocols.Diagnostic`` Protocol (context manager +
``run_id`` attribute + ``report() -> dict``). The Protocol itself lives
in the core SDK (``src/kailash/diagnostics/protocols.py``) and has zero
runtime logic and zero optional dependencies; this sub-package hosts
the concrete, ML-specific adapters that emit reports during training.

Public surface:

    from kailash_ml.diagnostics import DLDiagnostics

    with DLDiagnostics(model) as diag:
        diag.track_gradients()
        diag.track_activations()
        diag.track_dead_neurons()
        for batch in dataloader:
            loss = train_step(model, batch)
            diag.record_batch(loss=loss.item(), lr=opt.param_groups[0]["lr"])
        diag.record_epoch(val_loss=val)
        findings = diag.report()

Module-level helpers (``run_diagnostic_checkpoint``, ``diagnose_classifier``,
``diagnose_regressor``) are thin wrappers that attach every instrument
and replay epoch-level history onto a trained model for a read-only
diagnostic pass.

Plotting surface (``diag.plot_*()`` methods + interactive dashboard)
requires ``pip install kailash-ml[dl]`` — plotly is declared under the
``[dl]`` extra. ``report()`` and every ``*_df()`` accessor always work
on the base install.

See ``specs/ml-diagnostics.md`` for the full API contract and
``src/kailash/diagnostics/protocols.py`` for the cross-SDK Protocol.
"""
from __future__ import annotations

from kailash_ml.diagnostics.dl import (
    DLDiagnostics,
    diagnose_classifier,
    diagnose_regressor,
    run_diagnostic_checkpoint,
)

__all__ = [
    "DLDiagnostics",
    "run_diagnostic_checkpoint",
    "diagnose_classifier",
    "diagnose_regressor",
]
