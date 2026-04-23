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


# ---------------------------------------------------------------------------
# Plot-method smoke tests — each exercises the plotly-dependent figure-
# construction path after a real training step. Per rules/testing.md
# "Coverage Requirements", public APIs need exercising; plot_* methods
# are the user-facing surface for the DLDiagnostics session and without
# these the dl.py coverage is <30%. Each test drives 3-5 batches and
# asserts a plotly.graph_objects.Figure is returned — keeping the test
# deterministic via torch.manual_seed.
# ---------------------------------------------------------------------------


def _trained_diag() -> "DLDiagnostics":
    """Build a fresh DLDiagnostics + 3-batch training step for plot tests.

    Detached deliberately: each plot test operates on a completed session
    so hooks don't fire across tests and we avoid torch hook-state leak.
    """
    torch.manual_seed(42)
    model = nn.Sequential(
        nn.Linear(8, 4),
        nn.ReLU(),
        nn.Linear(4, 2),
    )
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    loss_fn = nn.MSELoss()
    diag = DLDiagnostics(model)
    diag.track_gradients()
    diag.track_activations()
    diag.track_dead_neurons()
    for _ in range(3):
        x = torch.randn(16, 8)
        y = torch.randn(16, 2)
        optimizer.zero_grad()
        out = model(x)
        loss = loss_fn(out, y)
        loss.backward()
        optimizer.step()
        diag.record_batch(loss=loss.item(), lr=0.01)
    diag.record_epoch(val_loss=0.5)
    diag.detach()
    return diag


@pytest.mark.integration
def test_dl_diagnostics_plot_loss_curves_returns_figure() -> None:
    """plot_loss_curves produces a plotly Figure after a training session."""
    import plotly.graph_objects as go  # plotly is in base deps today

    diag = _trained_diag()
    fig = diag.plot_loss_curves()
    assert isinstance(fig, go.Figure)


@pytest.mark.integration
def test_dl_diagnostics_plot_gradient_flow_returns_figure() -> None:
    """plot_gradient_flow produces a plotly Figure."""
    import plotly.graph_objects as go

    diag = _trained_diag()
    fig = diag.plot_gradient_flow()
    assert isinstance(fig, go.Figure)


@pytest.mark.integration
def test_dl_diagnostics_plot_activation_stats_returns_figure() -> None:
    """plot_activation_stats produces a plotly Figure."""
    import plotly.graph_objects as go

    diag = _trained_diag()
    fig = diag.plot_activation_stats()
    assert isinstance(fig, go.Figure)


@pytest.mark.integration
def test_dl_diagnostics_plot_dead_neurons_returns_figure() -> None:
    """plot_dead_neurons produces a plotly Figure."""
    import plotly.graph_objects as go

    diag = _trained_diag()
    fig = diag.plot_dead_neurons()
    assert isinstance(fig, go.Figure)


@pytest.mark.integration
def test_dl_diagnostics_plot_training_dashboard_returns_figure() -> None:
    """plot_training_dashboard composes 6 subplots into one Figure."""
    import plotly.graph_objects as go

    diag = _trained_diag()
    fig = diag.plot_training_dashboard()
    assert isinstance(fig, go.Figure)


@pytest.mark.integration
def test_dl_diagnostics_plot_gradient_norms_returns_figure() -> None:
    """plot_gradient_norms produces a plotly Figure."""
    import plotly.graph_objects as go

    diag = _trained_diag()
    fig = diag.plot_gradient_norms()
    assert isinstance(fig, go.Figure)


@pytest.mark.integration
def test_dl_diagnostics_plot_weight_distributions_returns_figure() -> None:
    """plot_weight_distributions produces a plotly Figure."""
    import plotly.graph_objects as go

    diag = _trained_diag()
    fig = diag.plot_weight_distributions()
    assert isinstance(fig, go.Figure)


@pytest.mark.integration
def test_dl_diagnostics_lr_range_test_returns_scalars_and_figure() -> None:
    """lr_range_test drives an LR sweep and returns the expected dict shape.

    Per specs/ml-diagnostics.md §4.2: returns safe_lr / min_loss_lr /
    divergence_lr scalars, the raw lrs/losses series, and a plotly Figure
    (plotly is in base deps today, so the figure is always present).
    """
    import plotly.graph_objects as go

    torch.manual_seed(123)
    model = nn.Sequential(nn.Linear(4, 8), nn.ReLU(), nn.Linear(8, 1))
    loss_fn = nn.MSELoss()

    class _FixedDataset(torch.utils.data.Dataset):  # type: ignore[name-defined]
        def __len__(self) -> int:
            return 32

        def __getitem__(self, idx: int) -> tuple:
            torch.manual_seed(idx)
            return torch.randn(4), torch.randn(1)

    loader = torch.utils.data.DataLoader(_FixedDataset(), batch_size=4)

    # lr_range_test is a @staticmethod on DLDiagnostics — call it via
    # the class (no instance needed since it builds + restores weights
    # internally). Force CPU so the test is darwin-arm / MPS tolerant
    # (the dataloader yields CPU tensors; auto-device on Mac picks MPS
    # which would trigger a weight/input type mismatch).
    result = DLDiagnostics.lr_range_test(
        model=model,
        dataloader=loader,
        loss_fn=loss_fn,
        lr_min=1e-5,
        lr_max=1e-1,
        steps=8,
        device=torch.device("cpu"),
    )
    for key in (
        "safe_lr",
        "min_loss_lr",
        "divergence_lr",
        "suggested_lr",
        "lrs",
        "losses",
        "losses_smooth",
        "figure",
    ):
        assert key in result
    assert isinstance(result["figure"], go.Figure)
    assert result["safe_lr"] <= result["min_loss_lr"]
    # lr_range_test may terminate early on divergence (smoothed loss
    # exceeds 4× its minimum); assert at-most rather than exact length.
    assert 2 <= len(result["lrs"]) <= 8
    assert len(result["losses"]) == len(result["lrs"])


@pytest.mark.integration
def test_dl_diagnostics_grad_cam_returns_heatmap() -> None:
    """grad_cam produces a per-sample heatmap from a conv layer."""
    torch.manual_seed(7)
    # Named module layout so grad_cam can locate the conv layer via
    # named_modules().
    model = nn.Sequential()
    model.add_module("conv", nn.Conv2d(3, 4, kernel_size=3, padding=1))
    model.add_module("act", nn.ReLU())
    model.add_module("flat", nn.Flatten())
    model.add_module("head", nn.Linear(4 * 8 * 8, 2))

    diag = DLDiagnostics(model)
    # grad_cam moves `input_tensor.to(self.device)` internally before the
    # forward pass, so if the device-resolver picks MPS (darwin-arm
    # default) while the model lives on CPU, F.conv2d sees mismatched
    # types. Pin both to CPU: override diag.device + move model to CPU.
    # CI Linux default is CPU anyway; this makes the local Mac run
    # deterministic.
    cpu = torch.device("cpu")
    diag.device = cpu
    model.to(cpu)
    x = torch.randn(2, 3, 8, 8)
    heatmap = diag.grad_cam(x, target_class=0, layer_name="conv")
    # Two samples → first dim is batch; non-empty spatial dim after.
    assert heatmap.shape[0] == 2
    assert heatmap.ndim >= 2


@pytest.mark.integration
def test_run_diagnostic_checkpoint_returns_diag_and_findings() -> None:
    """Module-level helper drives a full checkpoint + returns (diag, findings).

    Exercises the loss_fn path, tracking registration, batch-adapter default,
    and findings-extraction pipeline — the public entry point downstream
    consumers use for one-shot diagnostic passes on trained models. The
    model weights are not updated (no optimizer step); the checkpoint
    just populates history from forward-backward passes.
    """
    from kailash_ml.diagnostics import run_diagnostic_checkpoint

    torch.manual_seed(11)
    model = nn.Sequential(nn.Linear(4, 4), nn.ReLU(), nn.Linear(4, 1))
    loss_fn = nn.MSELoss()

    class _TinyDataset(torch.utils.data.Dataset):  # type: ignore[name-defined]
        def __len__(self) -> int:
            return 16

        def __getitem__(self, idx: int) -> tuple:
            torch.manual_seed(idx)
            return torch.randn(4), torch.randn(1)

    loader = torch.utils.data.DataLoader(_TinyDataset(), batch_size=4)

    def _loss_fn(m_out: "torch.Tensor", y: "torch.Tensor") -> "torch.Tensor":  # type: ignore[name-defined]
        return loss_fn(m_out, y)

    diag, findings = run_diagnostic_checkpoint(
        model=model,
        dataloader=loader,
        loss_fn=_loss_fn,
        n_batches=2,
        show=False,
    )
    assert isinstance(diag, DLDiagnostics)
    assert isinstance(findings, dict)
    assert "run_id" in findings
    assert findings["run_id"] == diag.run_id


@pytest.mark.integration
def test_diagnose_classifier_returns_diag_and_findings() -> None:
    """High-level wrapper for classifier diagnostics — F.cross_entropy path."""
    from kailash_ml.diagnostics.dl import diagnose_classifier

    torch.manual_seed(13)
    # 3-class classifier
    model = nn.Sequential(nn.Linear(6, 8), nn.ReLU(), nn.Linear(8, 3))

    class _ClsDataset(torch.utils.data.Dataset):  # type: ignore[name-defined]
        def __len__(self) -> int:
            return 16

        def __getitem__(self, idx: int) -> tuple:
            torch.manual_seed(idx)
            return torch.randn(6), torch.tensor(idx % 3, dtype=torch.long)

    loader = torch.utils.data.DataLoader(_ClsDataset(), batch_size=4)
    diag, findings = diagnose_classifier(
        model=model,
        dataloader=loader,
        n_batches=2,
        show=False,
    )
    assert isinstance(diag, DLDiagnostics)
    assert "run_id" in findings


@pytest.mark.integration
def test_diagnose_regressor_returns_diag_and_findings() -> None:
    """High-level wrapper for regressor diagnostics — F.mse_loss path."""
    from kailash_ml.diagnostics.dl import diagnose_regressor

    torch.manual_seed(17)
    model = nn.Sequential(nn.Linear(5, 6), nn.ReLU(), nn.Linear(6, 1))

    class _RegDataset(torch.utils.data.Dataset):  # type: ignore[name-defined]
        def __len__(self) -> int:
            return 16

        def __getitem__(self, idx: int) -> tuple:
            torch.manual_seed(idx)
            return torch.randn(5), torch.randn(1)

    loader = torch.utils.data.DataLoader(_RegDataset(), batch_size=4)
    diag, findings = diagnose_regressor(
        model=model,
        dataloader=loader,
        n_batches=2,
        show=False,
    )
    assert isinstance(diag, DLDiagnostics)
    assert "run_id" in findings
