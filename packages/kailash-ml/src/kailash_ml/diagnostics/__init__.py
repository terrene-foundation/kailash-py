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

    from kailash_ml.diagnostics import (
        DLDiagnostics,
        RLDiagnostics,
        RAGDiagnostics,
        InterpretabilityDiagnostics,  # optional — requires kailash-ml[agents]
        LLMDiagnostics,                # optional — requires kailash-ml[agents]
    )

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

    # RL training-loop diagnostics
    with RLDiagnostics(algo="ppo", tracker=run) as rl:
        model.learn(total_timesteps=10_000, callback=rl.as_sb3_callback())
        findings = rl.report()

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

    # Interpretability + LLM-as-judge re-exports from kaizen — requires
    # kailash-ml[agents] (which pulls kailash-kaizen).  Importing these
    # names from kailash_ml.diagnostics without the extra raises
    # ImportError naming the extra, per rules/dependencies.md.

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

from kailash_ml.diagnostics.classical import (
    ClassifierReport,
    RegressorReport,
    diagnose_classifier,
    diagnose_regressor,
)
from kailash_ml.diagnostics.dl import (
    DLDiagnostics,
    run_diagnostic_checkpoint,
)
from kailash_ml.diagnostics.rag import RAGDiagnostics
from kailash_ml.diagnostics.rl import RLDiagnostics, RLDiagnosticFinding

# Optional re-exports from kaizen — pulled only when kailash-ml[agents]
# is installed (which declares the kailash-kaizen>=2.7.5 dependency).
# Per rules/dependencies.md § "Optional Extras with Loud Failure", a
# missing extra raises ImportError naming the [agents] extra instead of
# silently degrading to ``None``.
try:
    from kaizen.interpretability import (
        InterpretabilityDiagnostics as _InterpretabilityDiagnostics,
    )
    from kaizen.judges import LLMDiagnostics as _LLMDiagnostics
except ImportError:  # kailash-kaizen not installed
    _InterpretabilityDiagnostics = None  # type: ignore[misc]
    _LLMDiagnostics = None  # type: ignore[misc]


def __getattr__(name: str):
    """Lazy-attribute loader for optional kaizen re-exports.

    Raising at attribute-access time (not at import time) keeps
    ``from kailash_ml.diagnostics import DLDiagnostics`` working without
    the ``[agents]`` extra.  Accessing the optional name surfaces a
    descriptive ImportError naming the extra per
    ``rules/dependencies.md``.
    """
    if name == "InterpretabilityDiagnostics":
        if _InterpretabilityDiagnostics is None:
            raise ImportError(
                "InterpretabilityDiagnostics requires kailash-kaizen. "
                "Install the agents extras: pip install kailash-ml[agents]"
            )
        return _InterpretabilityDiagnostics
    if name == "LLMDiagnostics":
        if _LLMDiagnostics is None:
            raise ImportError(
                "LLMDiagnostics requires kailash-kaizen. "
                "Install the agents extras: pip install kailash-ml[agents]"
            )
        return _LLMDiagnostics
    raise AttributeError(f"module 'kailash_ml.diagnostics' has no attribute {name!r}")


# ``InterpretabilityDiagnostics`` and ``LLMDiagnostics`` are deliberately
# NOT in ``__all__`` because they are optional extras re-exported via
# ``__getattr__``.  ``rules/orphan-detection.md §6`` bans module-scope
# public imports that are absent from ``__all__``; placing a lazy-
# resolved name in ``__all__`` has been flagged by CodeQL in prior
# kailash-py releases (PR #523/#529).  Documentation in the module
# docstring announces both names; ``from kailash_ml.diagnostics import
# InterpretabilityDiagnostics`` resolves via ``__getattr__`` when
# ``kailash-ml[agents]`` is installed, raising a descriptive
# ``ImportError`` otherwise.
__all__ = [
    "DLDiagnostics",
    "RLDiagnostics",
    "RLDiagnosticFinding",
    "RAGDiagnostics",
    "ClassifierReport",
    "RegressorReport",
    "run_diagnostic_checkpoint",
    "diagnose_classifier",
    "diagnose_regressor",
]
