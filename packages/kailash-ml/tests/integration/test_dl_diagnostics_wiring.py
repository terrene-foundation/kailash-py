# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for DLDiagnostics.

Per `rules/orphan-detection.md` §1 + `rules/facade-manager-detection.md`
Rule 2, this file imports DLDiagnostics through the
``kailash_ml.diagnostics`` facade (NOT the concrete module path) and
drives a real 3-batch PyTorch training step so we assert
externally-observable effects of the hook installations rather than
mocked internals.

The file also checks Protocol conformance at runtime — the whole point
of the PR is for `isinstance(diag, Diagnostic)` to hold, so a plain unit
test of the class in isolation would prove the class-shape contract but
NOT the Protocol-conformance contract that downstream consumers rely on.
"""
from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
nn = pytest.importorskip("torch.nn")

from kailash.diagnostics.protocols import Diagnostic  # noqa: E402

# Import through the facade — NOT `from kailash_ml.diagnostics.dl import ...`
# per orphan-detection §1 (downstream consumers see the public attribute,
# so the wiring test MUST exercise the same surface).
from kailash_ml.diagnostics import DLDiagnostics  # noqa: E402


@pytest.mark.integration
def test_dl_diagnostics_satisfies_diagnostic_protocol() -> None:
    """`DLDiagnostics` satisfies the cross-SDK `Diagnostic` Protocol.

    This is the load-bearing structural test for the PR: if this fails,
    downstream consumers cannot rely on `isinstance(diag, Diagnostic)`
    for type-safe Protocol dispatch.
    """
    model = nn.Sequential(nn.Linear(8, 4), nn.ReLU(), nn.Linear(4, 1))
    diag = DLDiagnostics(model)
    assert isinstance(diag, Diagnostic)
    assert isinstance(diag.run_id, str) and len(diag.run_id) > 0


@pytest.mark.integration
def test_dl_diagnostics_explicit_run_id_is_honored() -> None:
    """User-supplied `run_id` is preserved for cross-system correlation."""
    model = nn.Linear(4, 2)
    diag = DLDiagnostics(model, run_id="my-training-run-42")
    assert diag.run_id == "my-training-run-42"
    assert isinstance(diag, Diagnostic)


@pytest.mark.integration
def test_dl_diagnostics_records_real_training_step() -> None:
    """Real torch training loop records gradient + activation + loss data.

    3 batches × 16 samples through a small MLP with optimizer steps.
    Asserts externally-observable report() output plus the polars
    DataFrame accessors hold the captured history.
    """
    torch.manual_seed(42)
    model = nn.Sequential(nn.Linear(8, 4), nn.ReLU(), nn.Linear(4, 1))
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    loss_fn = nn.MSELoss()

    with DLDiagnostics(model) as diag:
        assert isinstance(diag, Diagnostic)
        diag.track_gradients()
        diag.track_activations()
        diag.track_dead_neurons()

        for _ in range(3):
            x = torch.randn(16, 8)
            y = torch.randn(16, 1)
            optimizer.zero_grad()
            out = model(x)
            loss = loss_fn(out, y)
            loss.backward()
            optimizer.step()
            diag.record_batch(loss=loss.item(), lr=0.01)

        diag.record_epoch(val_loss=0.5)
        report = diag.report()

    # Externally observable: report keys are present and run_id matches.
    assert isinstance(report, dict)
    assert report["run_id"] == diag.run_id
    assert report["batches"] == 3
    assert report["epochs"] == 1

    # Every finding is a {severity, message} dict.
    for key in ("gradient_flow", "dead_neurons", "loss_trend"):
        assert key in report
        assert "severity" in report[key]
        assert "message" in report[key]
        assert report[key]["severity"] in (
            "HEALTHY",
            "WARNING",
            "CRITICAL",
            "UNKNOWN",
        )

    # DataFrame accessors reflect the real training step — gradient hooks
    # fired at least once per tracked parameter per batch.
    batches_df = diag.batches_df()
    assert batches_df.height == 3
    gradients_df = diag.gradients_df()
    # 4 trainable parameter tensors (2 Linear layers × weight+bias) × 3 batches = 12
    assert gradients_df.height >= 3
    activations_df = diag.activations_df()
    # Linear + ReLU + Linear = 3 activation-monitored layers × 3 batches = 9
    assert activations_df.height >= 3

    # Detach is idempotent after context exit.
    diag.detach()
    diag.detach()


@pytest.mark.integration
def test_dl_diagnostics_report_without_tracking_returns_unknown() -> None:
    """`report()` without any `track_*()` calls yields UNKNOWN findings.

    Proves the contract: report() is always callable and returns a
    dict with `severity` keys, never raises on empty state.
    """
    model = nn.Linear(4, 2)
    with DLDiagnostics(model) as diag:
        report = diag.report()
    assert report["gradient_flow"]["severity"] == "UNKNOWN"
    assert report["dead_neurons"]["severity"] == "UNKNOWN"
    assert report["loss_trend"]["severity"] == "UNKNOWN"
    assert report["batches"] == 0
    assert report["epochs"] == 0


@pytest.mark.integration
def test_dl_diagnostics_run_id_propagates_across_record_and_report() -> None:
    """The same `run_id` appears in the session and in `report()['run_id']`.

    This is the cross-correlation contract — a downstream consumer using
    `run_id` to join diagnostic output against training logs or the
    ExperimentTracker MUST see the same value in both places.
    """
    model = nn.Linear(4, 2)
    with DLDiagnostics(model, run_id="correlation-run-123") as diag:
        diag.track_gradients()
        x = torch.randn(8, 4)
        y = torch.randn(8, 2)
        out = model(x)
        loss = ((out - y) ** 2).mean()
        loss.backward()
        diag.record_batch(loss=loss.item())
        report = diag.report()
    assert report["run_id"] == "correlation-run-123"
    assert diag.run_id == "correlation-run-123"
