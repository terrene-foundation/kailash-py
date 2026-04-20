# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for InterpretabilityDiagnostics.

Per ``rules/orphan-detection.md`` §1, this file imports
``InterpretabilityDiagnostics`` through the ``kaizen.interpretability``
facade (NOT the concrete module path) and drives real forward passes
on ``sshleifer/tiny-gpt2`` — a tiny GPT-2 variant already vendored in
the HuggingFace cache for CI. We assert externally-observable effects
(report() shape, DataFrame row counts, recorded deque populations)
rather than mocked internals.

The file also checks Protocol conformance at runtime against a real
model — the whole point of the PR is for ``isinstance(diag,
Diagnostic)`` to hold, so a unit test of the class in isolation would
prove the class-shape contract but NOT the Protocol-conformance
contract that downstream consumers rely on.

``transformers`` is an optional extra; when absent, every test here
skips cleanly via ``importorskip``.
"""
from __future__ import annotations

import pytest

# Tier 2 requires real model weights; skip cleanly when the
# [interpretability] extra is not installed.
torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from kailash.diagnostics.protocols import Diagnostic  # noqa: E402

# Import through the facade — NOT `from kaizen.interpretability.core import ...`
# per orphan-detection §1 (downstream consumers see the public
# attribute, so the wiring test MUST exercise the same surface).
from kaizen.interpretability import InterpretabilityDiagnostics  # noqa: E402


TINY_MODEL = "sshleifer/tiny-gpt2"


# ---------------------------------------------------------------------------
# Protocol conformance against a real construction
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_protocol_conformance_on_real_construction() -> None:
    """``InterpretabilityDiagnostics`` satisfies the cross-SDK Protocol.

    Load-bearing structural test. The tokenizer + model load is
    deferred to first method call, so construction alone is safe to
    run on every CI runner regardless of HF cache state.
    """
    diag = InterpretabilityDiagnostics(model_name=TINY_MODEL)
    assert isinstance(diag, Diagnostic)
    assert isinstance(diag.run_id, str) and len(diag.run_id) > 0


@pytest.mark.integration
def test_explicit_run_id_honored_through_protocol() -> None:
    """User-supplied ``run_id`` is preserved across the Protocol surface."""
    diag = InterpretabilityDiagnostics(model_name=TINY_MODEL, run_id="correlation-abc")
    assert diag.run_id == "correlation-abc"
    report = diag.report()
    assert report["run_id"] == "correlation-abc"
    assert isinstance(diag, Diagnostic)


# ---------------------------------------------------------------------------
# Real forward pass + report assertions (requires HF cache OR network)
# ---------------------------------------------------------------------------


def _can_load_tiny_gpt2() -> bool:
    """Return True when ``sshleifer/tiny-gpt2`` is cached locally.

    We do NOT trigger a download at module import. The skipif guard
    checks the HF cache AND the HOME/.cache/huggingface path without
    fetching. This keeps `local_files_only=True` as the session
    default AND keeps CI green when the runner lacks the model.
    """
    try:
        from transformers import AutoConfig

        AutoConfig.from_pretrained(TINY_MODEL, local_files_only=True)
        return True
    except Exception:
        return False


TINY_GPT2_AVAILABLE = _can_load_tiny_gpt2()


@pytest.mark.integration
@pytest.mark.skipif(
    not TINY_GPT2_AVAILABLE,
    reason="sshleifer/tiny-gpt2 not in HF cache; set HF_HOME or pre-download",
)
def test_report_shape_on_empty_real_session() -> None:
    """An empty real session reports zero recorded readings."""
    with InterpretabilityDiagnostics(model_name=TINY_MODEL) as diag:
        report = diag.report()
    assert report["run_id"] == diag.run_id
    assert report["model_name"] == TINY_MODEL
    assert report["mode"] == "real"
    assert report["attention_heatmaps"] == 0
    assert report["logit_lens_sweeps"] == 0
    assert report["linear_probes"] == {"count": 0}
    assert report["sae_feature_reads"] == 0
    assert isinstance(report["messages"], list)
    assert len(report["messages"]) == 1  # "no readings" placeholder


@pytest.mark.integration
@pytest.mark.skipif(
    not TINY_GPT2_AVAILABLE,
    reason="sshleifer/tiny-gpt2 not in HF cache; set HF_HOME or pre-download",
)
def test_real_attention_heatmap_records_reading() -> None:
    """A real forward pass records an attention reading in the deque."""
    import plotly.graph_objects as go

    with InterpretabilityDiagnostics(model_name=TINY_MODEL) as diag:
        assert isinstance(diag, Diagnostic)
        fig = diag.attention_heatmap("The cat sat", layer=0, head=0)
        report = diag.report()

    assert isinstance(fig, go.Figure)
    assert report["attention_heatmaps"] == 1
    assert report["mode"] == "real"
    assert "attention:" in " ".join(report["messages"])


@pytest.mark.integration
@pytest.mark.skipif(
    not TINY_GPT2_AVAILABLE,
    reason="sshleifer/tiny-gpt2 not in HF cache; set HF_HOME or pre-download",
)
def test_real_logit_lens_produces_dataframe() -> None:
    """A real forward pass yields a non-empty logit-lens DataFrame."""
    with InterpretabilityDiagnostics(model_name=TINY_MODEL) as diag:
        df = diag.logit_lens("Hello world", top_k=3)
        report = diag.report()

    assert df.height > 0
    # One row per (layer, rank) pair.
    assert {"layer", "rank", "token", "prob", "mode"} <= set(df.columns)
    # All rows tagged as real (not the API-only fallback shape).
    assert df["mode"].to_list() == ["real"] * df.height
    assert report["logit_lens_sweeps"] == 1


@pytest.mark.integration
@pytest.mark.skipif(
    not TINY_GPT2_AVAILABLE,
    reason="sshleifer/tiny-gpt2 not in HF cache; set HF_HOME or pre-download",
)
def test_real_probe_on_tiny_model() -> None:
    """Linear probe runs end-to-end on tiny-gpt2 hidden states."""
    with InterpretabilityDiagnostics(model_name=TINY_MODEL) as diag:
        result = diag.probe(
            prompts=[
                "the cat is small",
                "the dog runs fast",
                "the sky is blue",
                "the ocean is deep",
            ],
            labels=[0, 0, 1, 1],
            layer=1,
        )

    assert result["mode"] == "real"
    assert result["layer"] == 1
    assert result["n_prompts"] == 4
    assert result["n_classes"] == 2
    assert 0.0 <= result["cv_accuracy"] <= 1.0


@pytest.mark.integration
@pytest.mark.skipif(
    not TINY_GPT2_AVAILABLE,
    reason="sshleifer/tiny-gpt2 not in HF cache; set HF_HOME or pre-download",
)
def test_bounded_memory_via_deque_maxlen() -> None:
    """The logit-lens deque honours ``maxlen=window`` bounded-memory cap."""
    with InterpretabilityDiagnostics(model_name=TINY_MODEL, window=2) as diag:
        for i in range(4):
            diag.logit_lens(f"prompt {i}", top_k=2)
        # Only the most recent 2 readings are retained.
        assert len(diag._logit_log) == 2


@pytest.mark.integration
def test_api_only_mode_via_facade_no_model_load() -> None:
    """Facade import + API-only refusal works without loading weights.

    This test exercises the full wiring (facade → refusal → empty
    DataFrame) without requiring the HF cache, so it runs on every
    CI runner regardless of model availability.
    """
    from kaizen.interpretability import (
        InterpretabilityDiagnostics as FacadeImport,
    )

    diag = FacadeImport(model_name="gpt-4-turbo")
    assert isinstance(diag, Diagnostic)
    df = diag.logit_lens("anything")
    assert df.height == 0
    report = diag.report()
    assert report["mode"] == "not_applicable"
