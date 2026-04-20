# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Diagnostics adapters for kailash-ml.

Every adapter in this package conforms to the
``kailash.diagnostics.protocols.Diagnostic`` Protocol (context manager +
``run_id`` attribute + ``report() -> dict``). The Protocol itself lives
in the core SDK (``src/kailash/diagnostics/protocols.py``) and has zero
runtime logic and zero optional dependencies; this sub-package hosts
the concrete, ML-specific adapters that emit reports during training
and evaluation.

Public surface:

    from kailash_ml.diagnostics import DLDiagnostics, RAGDiagnostics

    # DL training-loop diagnostics
    with DLDiagnostics(model) as diag:
        diag.track_gradients()
        diag.track_activations()
        diag.track_dead_neurons()
        for batch in dataloader:
            loss = train_step(model, batch)
            diag.record_batch(loss=loss.item(), lr=opt.param_groups[0]["lr"])
        diag.record_epoch(val_loss=val)
        findings = diag.report()

    # RAG retrieval + generation evaluation
    with RAGDiagnostics() as rag:
        df = rag.evaluate(
            queries=["What is X?"],
            retrieved_contexts=[[...]],
            answers=["X is ..."],
            retrieved_ids=[[...]],
            ground_truth_ids=[[...]],
        )
        board = rag.compare_retrievers(
            retrievers={"bm25": bm25_fn, "dense": dense_fn},
            eval_set=eval_set,
            k=5,
        )
        findings = rag.report()

Module-level DL helpers (``run_diagnostic_checkpoint``,
``diagnose_classifier``, ``diagnose_regressor``) are thin wrappers that
attach every instrument and replay epoch-level history onto a trained
model for a read-only diagnostic pass.

Plotting surface (``diag.plot_*()`` methods + interactive dashboards)
requires ``pip install kailash-ml[dl]`` — plotly is declared under the
``[dl]`` extra. ``report()`` and every ``*_df()`` / ``metrics_df()`` /
``leaderboard_df()`` accessor always works on the base install.

RAG-specific optional backends (``ragas``, ``trulens-eval``) are gated
by ``pip install kailash-ml[rag]`` — ``RAGDiagnostics.evaluate()`` falls
back to a pluggable ``JudgeCallable`` + deterministic heuristic when
``[rag]`` is absent; ``ragas_scores()`` / ``trulens_scores()`` raise
``ImportError`` naming the extra.

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
from kailash_ml.diagnostics.rag import RAGDiagnostics

__all__ = [
    "DLDiagnostics",
    "RAGDiagnostics",
    "run_diagnostic_checkpoint",
    "diagnose_classifier",
    "diagnose_regressor",
]
