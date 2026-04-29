# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: GH issue #701 — diagnose(kind='dl', data=loader) silent drop.

Before this fix, ``km.diagnose(model, kind="dl", data=loader)`` accepted
the ``data=`` kwarg in its signature but silently dropped it at the
dispatch site (``_wrappers.py:493``). Spec ``ml-diagnostics.md §3.1``
declared ``DataLoader`` as part of the ``data=`` type union; the
dispatch never honoured the spec.

The user-visible failure mode: ``diagnose(...)`` returned a
``DLDiagnostics`` instance constructed with ``data=None``, so any
subsequent ``.report()`` call had zero loader signal — the canonical
3-line "evaluate a model on a held-out loader" recipe shipped a no-op.

This shard (S3a) fixes the silent drop:

  1. ``DLDiagnostics`` accepts ``data=`` at construction.
  2. ``DLDiagnostics.report(data=loader)`` consumes the loader.
  3. ``_wrappers.py:diagnose(..., kind="dl", data=loader)`` forwards
     ``data=`` to the constructor.

This Tier-2 regression executes the DOCS-EXACT pipeline against real
PyTorch + a real DataLoader and asserts the loader was actually
consumed end-to-end (``n_batches > 0`` and ``n_samples == dataset
size``). Per ``rules/testing.md`` § "End-to-End Pipeline Regression",
the test name encodes "end_to_end" so future maintainers can grep for
it. NO mocking — torch is loaded via ``pytest.importorskip`` and
exercised with a real ``nn.Linear`` + ``TensorDataset`` + ``DataLoader``
exactly as a user would write.
"""

from __future__ import annotations

import pytest


@pytest.mark.regression
@pytest.mark.integration
def test_diagnose_dl_pytorch_dataloader_end_to_end() -> None:
    """DOCS-EXACT: diagnose(model, kind='dl', data=loader) consumes the loader.

    Reproduces issue #701. Before the fix, ``data=loader`` was silently
    dropped at the ``_wrappers.py:diagnose`` dispatch site and the
    DLDiagnostics instance had no loader to iterate. This test fails
    on main pre-fix (``n_batches == 0``) and passes post-fix
    (``n_batches > 0``, ``n_samples == 64``).
    """
    torch = pytest.importorskip("torch")
    from torch.utils.data import DataLoader, TensorDataset

    from kailash_ml import diagnose

    # Deterministic seed — rules/testing.md § Rules: no random data
    # without seeds. The DataLoader's `shuffle=False` default plus a
    # fixed seed gives identical output across runs.
    torch.manual_seed(0)

    # Tiny classifier: 10-dim input, 2-class output. Real nn.Module
    # (Tier 2/3 NO-mocking rule). batch_size=8 over 64 samples ⇒
    # 8 batches.
    model = torch.nn.Linear(10, 2)
    inputs = torch.randn(64, 10)
    targets = torch.randint(0, 2, (64,))
    dataset = TensorDataset(inputs, targets)
    loader = DataLoader(dataset, batch_size=8, shuffle=False)

    # Silent-drop failure mode pre-fix: this returned DLDiagnostics
    # with data=None. Post-fix: data= is plumbed through.
    diag = diagnose(model, kind="dl", data=loader)

    # Both call shapes work:
    #   - report() with no arg consumes the construction-time data.
    #   - report(data=loader) accepts the loader at call time.
    # Exercise both to lock the contract.
    report_a = diag.report()
    assert report_a["n_batches"] == 8, (
        f"data= supplied at construction should be iterated by report() — "
        f"got n_batches={report_a['n_batches']}"
    )
    assert (
        report_a["n_samples"] == 64
    ), f"all 64 samples MUST be seen — got n_samples={report_a['n_samples']}"

    # report(data=) overrides construction-time loader. Build a fresh
    # one to confirm the call-time path also works (single-batch loader
    # so n_batches differs from the construction-time value).
    small_loader = DataLoader(TensorDataset(inputs[:16], targets[:16]), batch_size=16)
    report_b = diag.report(data=small_loader)
    assert report_b["n_batches"] == 1
    assert report_b["n_samples"] == 16


@pytest.mark.regression
def test_diagnose_dl_unknown_kwarg_raises_typeerror() -> None:
    """1.1.x kwargs removed in 1.5.0 surface as TypeError, not silent drop.

    The signature is fixed-arity (no **kwargs); Python's argument binder
    enforces the contract automatically. This test pins the behaviour so
    a future refactor adding **kwargs (and re-introducing the silent-
    drop failure mode #701 was filed to close) fails loudly here.
    """
    from kailash_ml import diagnose

    # Subject can be anything dispatchable; the kwarg rejection happens
    # before any dispatch logic runs. Use a string to avoid pulling
    # torch into a unit-tier test.
    with pytest.raises(TypeError, match=r"unexpected keyword argument 'title'"):
        diagnose("subject", kind="dl", title="Some Title")  # type: ignore[call-arg]

    with pytest.raises(TypeError, match=r"unexpected keyword argument 'n_batches'"):
        diagnose("subject", kind="dl", n_batches=10)  # type: ignore[call-arg]

    with pytest.raises(TypeError, match=r"unexpected keyword argument 'train_losses'"):
        diagnose("subject", kind="dl", train_losses=[0.1])  # type: ignore[call-arg]

    with pytest.raises(TypeError, match=r"unexpected keyword argument 'val_losses'"):
        diagnose("subject", kind="dl", val_losses=[0.2])  # type: ignore[call-arg]

    with pytest.raises(
        TypeError, match=r"unexpected keyword argument 'forward_returns_tuple'"
    ):
        diagnose("subject", kind="dl", forward_returns_tuple=True)  # type: ignore[call-arg]


@pytest.mark.regression
def test_dldiagnostics_data_constructor_param_is_optional() -> None:
    """Legacy zero-data construction path still works (no breaking change).

    Before #701 the constructor had no ``data=`` parameter; existing
    callers that construct ``DLDiagnostics(model)`` without a loader
    MUST keep working unchanged. The shard adds ``data=`` as a keyword-
    only optional arg with default ``None``.
    """
    torch = pytest.importorskip("torch")

    from kailash_ml.diagnostics.dl import DLDiagnostics

    model = torch.nn.Linear(10, 2)

    # Zero-data construction — legacy path, no data=.
    diag_legacy = DLDiagnostics(model)
    assert diag_legacy._data is None

    # report() with no loader and no construction-time data returns
    # the legacy shape with n_batches/n_samples == 0 (loader skip
    # path preserved).
    report = diag_legacy.report()
    assert report["n_batches"] == 0
    assert report["n_samples"] == 0
    # All the legacy keys still present.
    assert "run_id" in report
    assert "gradient_flow" in report
    assert "dead_neurons" in report
    assert "loss_trend" in report
