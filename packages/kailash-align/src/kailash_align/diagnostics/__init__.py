# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Diagnostics adapters for kailash-align.

Every adapter in this package conforms to the
``kailash.diagnostics.protocols.Diagnostic`` Protocol (context manager +
``run_id`` attribute + ``report() -> dict``). The Protocol itself lives
in the core SDK (``src/kailash/diagnostics/protocols.py``) and has zero
runtime logic and zero optional dependencies; this sub-package hosts
the concrete, alignment-specific adapter that observes LLM fine-tuning
runs.

Public surface:

    from kailash_align.diagnostics import AlignmentDiagnostics

    with AlignmentDiagnostics(label="dpo_run42") as diag:
        diag.evaluate_pair(base_logprobs, tuned_logprobs, preferences)
        diag.track_training(pipeline.metrics_stream())
        diag.detect_reward_hacking(threshold=2.5)
        report = diag.report()

The adapter does NO model loading — it consumes preference tuples,
per-token log-probability arrays, and training metric streams emitted
by the Align trainer (``kailash_align.AlignmentPipeline`` or equivalent).

Plotting surface (``diag.plot_*()``) uses plotly, which is a transitive
dependency of the base install. ``report()`` and every ``*_df()``
accessor work without plotting deps.

See ``specs/alignment-diagnostics.md`` for the full API contract and
``src/kailash/diagnostics/protocols.py`` for the cross-SDK Protocol.
"""
from __future__ import annotations

from kailash_align.diagnostics.alignment import AlignmentDiagnostics

__all__ = ["AlignmentDiagnostics"]
