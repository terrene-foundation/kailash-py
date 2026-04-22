# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.e Tier-2 wiring test — Lightning autolog end-to-end.

Per ``specs/ml-autolog.md §8.1`` MUST:

- Fit a TOY model (small, CPU-only, ≤1 second).
- File-backed SQLite (NOT ``:memory:``) so ``list_metrics`` +
  ``list_artifacts`` exercise the full write/read round-trip.
- Assert ≥3 metrics + 1 artifact emitted under the ambient run.
- Verify ``Trainer.__init__`` is restored on CM exit (detach
  discipline per §3.2 + §1.3 non-goal).

Per ``rules/testing.md §Tier 2`` — real Lightning + real torch, real
disk SQLite, no mocks. The only non-real bit is the toy dataset
shape (8 rows × 4 features) and a 1-layer Linear model, chosen so
``trainer.fit`` completes in well under 1 second on CPU.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from kailash_ml.autolog import autolog
from kailash_ml.tracking import SqliteTrackerStore, track


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def backend(tmp_path: Path):
    """File-backed SqliteTrackerStore per spec §8.1 MUST."""
    be = SqliteTrackerStore(tmp_path / "autolog_lightning_tracker.db")
    await be.initialize()
    try:
        yield be
    finally:
        await be.close()


def _build_toy_module():
    """Tiny LightningModule — 1-layer linear over 4-feat toy regression.

    Emits a ``train_loss`` metric per step + epoch via ``self.log``
    so the Tier-2 wiring test can assert ≥3 metric rows round-trip.
    """
    import torch
    from lightning.pytorch import LightningModule

    class ToyModule(LightningModule):
        def __init__(self):
            super().__init__()
            self.linear = torch.nn.Linear(4, 1)

        def training_step(self, batch, batch_idx):
            x, y = batch
            pred = self.linear(x).squeeze(-1)
            loss = torch.nn.functional.mse_loss(pred, y)
            self.log("train_loss", loss, on_step=True, on_epoch=True, prog_bar=False)
            return loss

        def configure_optimizers(self):
            return torch.optim.SGD(self.parameters(), lr=0.1)

    return ToyModule()


def _build_toy_loader():
    """Tiny DataLoader — 2 batches of 4 rows × 4 features."""
    import torch
    from torch.utils.data import DataLoader, TensorDataset

    torch.manual_seed(42)
    X = torch.randn(8, 4)
    y = X[:, 0] + 0.5 * X[:, 1]
    ds = TensorDataset(X, y)
    return DataLoader(ds, batch_size=4, shuffle=False)


async def test_lightning_autolog_emits_metrics_params_and_checkpoint(
    backend: SqliteTrackerStore,
    tmp_path: Path,
) -> None:
    """trainer.fit inside km.autolog("lightning") emits metrics +
    params + checkpoint artifact per §3.1 row 1 + §8.1.
    """
    from lightning.pytorch import Trainer
    from lightning.pytorch.callbacks import ModelCheckpoint

    ckpt_dir = tmp_path / "ckpts"
    ckpt_dir.mkdir()

    async with track("w23e-lightning-wiring", backend=backend) as run:
        async with autolog("lightning") as handle:
            assert handle.attached_integrations == ("lightning",)

            module = _build_toy_module()
            loader = _build_toy_loader()
            trainer = Trainer(
                max_epochs=2,
                accelerator="cpu",
                devices=1,
                log_every_n_steps=1,
                enable_progress_bar=False,
                enable_model_summary=False,
                logger=False,
                callbacks=[
                    ModelCheckpoint(
                        dirpath=str(ckpt_dir),
                        filename="epoch={epoch}",
                        save_last=True,
                        save_top_k=1,
                        monitor="train_loss_epoch",
                        mode="min",
                    ),
                ],
            )
            trainer.fit(module, loader)
        run_id = run.run_id

    # Assertions per §8.1 MUST — metrics + params + artifacts all
    # round-tripped through real on-disk SQLite.
    metrics = await backend.list_metrics(run_id)
    artifacts = await backend.list_artifacts(run_id)
    run_row = await backend.get_run(run_id)
    assert run_row is not None, "run row should exist post-exit"
    persisted_params = run_row.get("params") or {}

    # ≥3 metric rows — Lightning fires on_train_batch_end +
    # on_train_epoch_end across 2 epochs × 2 batches = plenty.
    metric_keys = {row["key"] for row in metrics}
    assert len(metrics) >= 3, f"expected ≥3 metric rows per §8.1, got {len(metrics)}"
    assert any(
        "train_loss" in k for k in metric_keys
    ), f"expected train_loss-* metrics, got {metric_keys}"
    assert any(
        k.startswith("lr-") for k in metric_keys
    ), f"expected lr-<i> metrics, got {metric_keys}"

    # Params — prefixed with `trainer.` per spec §3.1 row 1.
    param_keys = set(persisted_params.keys())
    assert any(
        k.startswith("trainer.") for k in param_keys
    ), f"expected trainer.* params, got {sorted(param_keys)[:10]}"
    assert (
        "trainer.max_epochs" in param_keys
    ), f"trainer.max_epochs missing from {sorted(param_keys)[:10]}"

    # Artifacts — best + last checkpoint per spec §3.1 row 1.
    artifact_names = {row["name"] for row in artifacts}
    assert any(
        "lightning." in n and "_checkpoint.ckpt" in n for n in artifact_names
    ), f"expected lightning.*_checkpoint.ckpt artifact, got {artifact_names}"


async def test_lightning_autolog_restores_trainer_init_on_exit(
    backend: SqliteTrackerStore,
) -> None:
    """Per §3.2 + §1.3: detach MUST restore ``Trainer.__init__``.

    Class-level wrap means ``Trainer.__init__`` becomes a different
    callable during the block; detach restores the identity. This
    guards against the cross-test contamination failure mode called
    out in §1.3.
    """
    from lightning.pytorch import Trainer

    original_init = Trainer.__init__

    async with track("w23e-lightning-restore", backend=backend):
        async with autolog("lightning"):
            assert (
                Trainer.__init__ is not original_init
            ), "LightningIntegration.attach did NOT replace Trainer.__init__; wrap is a no-op"
    # After exit, Trainer.__init__ is restored.
    assert (
        Trainer.__init__ is original_init
    ), "LightningIntegration.detach did NOT restore Trainer.__init__; class-level patch LEAKED per §1.3"


async def test_lightning_autolog_restores_trainer_init_even_when_body_raises(
    backend: SqliteTrackerStore,
) -> None:
    """Per §8.5 + §3.2: detach runs in ``finally:`` even when the
    wrapped block raises, and Trainer.__init__ is still restored.
    """
    from lightning.pytorch import Trainer

    original_init = Trainer.__init__

    async with track("w23e-lightning-restore-on-raise", backend=backend):
        with pytest.raises(ValueError, match="user body error"):
            async with autolog("lightning"):
                raise ValueError("user body error")
    assert (
        Trainer.__init__ is original_init
    ), "LightningIntegration.detach did NOT restore Trainer.__init__ after raising body"
