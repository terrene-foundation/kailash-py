# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Interpretability diagnostics adapters for kailash-kaizen.

Every adapter in this package conforms to the
``kailash.diagnostics.protocols.Diagnostic`` Protocol (context manager +
``run_id`` attribute + ``report() -> dict``). The Protocol itself lives
in the core SDK (``src/kailash/diagnostics/protocols.py``) and has zero
runtime logic and zero optional dependencies; this sub-package hosts
the concrete, open-weight-LLM-specific interpretability adapters that
emit reports during post-hoc analysis of a trained model.

Public surface:

    from kaizen.interpretability import InterpretabilityDiagnostics

    with InterpretabilityDiagnostics(model_name="google/gemma-2-2b") as diag:
        diag.attention_heatmap("The cat sat on the mat", layer=0, head=0)
        logit_df = diag.logit_lens("The capital of France is", top_k=5)
        probe_row = diag.probe(prompts, labels, layer=3)
        feats_df = diag.sae_features("Hello world", layer=8)
        findings = diag.report()

The ``plot_*()`` methods return :class:`plotly.graph_objects.Figure`
objects gated by ``pip install kailash-kaizen[interpretability]``.
``report()`` and ``*_df()`` accessors work on the base install after
transformers is available (transformers is only required when a method
actually loads the model; constructing the session is cheap).

Open-weight model requirement:

    The adapter operates on local open-weight model weights
    (Llama / Gemma / Phi / Mistral families). API-only models (GPT,
    Claude, Gemini) are structurally incompatible — the adapter refuses
    to load them and returns ``{"mode": "not_applicable"}`` from every
    method that would need model internals. This is honest failure per
    ``rules/zero-tolerance.md`` Rule 2 (no fake readings).

Security posture:

    ``from_pretrained`` runs with ``local_files_only=True`` by default
    so a diagnostic call never silently downloads multi-GB weights from
    the network. Operators who want to fetch fresh weights opt in
    explicitly via ``allow_download=True``.

See ``specs/kaizen-interpretability.md`` for the full API contract and
``src/kailash/diagnostics/protocols.py`` for the cross-SDK Protocol.
"""
from __future__ import annotations

from kaizen.interpretability.core import InterpretabilityDiagnostics

__all__ = [
    "InterpretabilityDiagnostics",
]
