# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.f Tier-2 wiring test — transformers autolog end-to-end.

Per ``specs/ml-autolog.md §8.1`` MUST:

- Fit a TOY model (small, CPU-only, ≤1 second).
- File-backed SQLite (NOT ``:memory:``) so ``list_metrics`` +
  ``list_artifacts`` exercise the full write/read round-trip.
- Assert ≥3 metrics + 1 artifact emitted under the ambient run.
- Verify ``transformers.Trainer.__init__`` is restored on CM exit
  (detach discipline per §3.2 + §1.3 non-goal).

Per ``rules/testing.md §Tier 2`` — real transformers Trainer, real
torch model, real disk SQLite, no mocks. Uses a micro BertConfig
(hidden_size=8, 1 layer, 1 head) so a full ``trainer.train()`` on a
16-row dummy dataset completes in well under 1 second on CPU.

Also covers §3.1.1 PEFT split when peft is available — PEFT-wrapped
model produces ``base.*`` + ``lora.*`` params + both fingerprints.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import torch
from kailash_ml.autolog import autolog
from kailash_ml.tracking import SqliteTrackerStore, track


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# Silence transformers/hf noise that leaks into the test log pipeline.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


@pytest.fixture
async def backend(tmp_path: Path):
    be = SqliteTrackerStore(tmp_path / "autolog_transformers_tracker.db")
    await be.initialize()
    try:
        yield be
    finally:
        await be.close()


def _build_tiny_bert():
    """Build a micro BertForSequenceClassification (1-layer, 8-hidden).

    Small enough that a full 4-step train() completes in well under 1s
    on CPU. Large enough that PEFT's LoRA targeting finds q_proj/v_proj
    on the attention layers.
    """
    from transformers import BertConfig, BertForSequenceClassification

    cfg = BertConfig(
        vocab_size=30,
        hidden_size=8,
        num_hidden_layers=1,
        num_attention_heads=1,
        intermediate_size=16,
        max_position_embeddings=16,
        num_labels=2,
        pad_token_id=0,
    )
    return BertForSequenceClassification(cfg)


def _build_toy_dataset(num_samples: int = 16, seq_len: int = 8):
    """Tiny tokenised dataset — random input_ids + alternating labels.

    Uses ``torch.utils.data.Dataset`` so HF Trainer can drive it with
    a default data collator.
    """
    from torch.utils.data import Dataset

    torch.manual_seed(42)
    input_ids = torch.randint(1, 30, (num_samples, seq_len))
    attention_mask = torch.ones_like(input_ids)
    labels = torch.tensor([i % 2 for i in range(num_samples)])

    class ToyDataset(Dataset):
        def __len__(self):
            return num_samples

        def __getitem__(self, idx):
            return {
                "input_ids": input_ids[idx],
                "attention_mask": attention_mask[idx],
                "labels": labels[idx],
            }

    return ToyDataset()


async def test_transformers_autolog_emits_metrics_params_and_fingerprint(
    backend: SqliteTrackerStore,
    tmp_path: Path,
) -> None:
    """Trainer.train inside km.autolog("transformers") emits metrics +
    params to the ambient run per §3.1 row 3 + §3.1.3 on_log cadence
    + §3.1.2 rolling tokens/sec + §8.1.
    """
    from transformers import Trainer, TrainingArguments

    async with track("w23f-transformers-wiring", backend=backend) as run:
        async with autolog("transformers") as handle:
            assert handle.attached_integrations == ("transformers",)

            model = _build_tiny_bert()
            dataset = _build_toy_dataset()

            trainer = Trainer(
                model=model,
                args=TrainingArguments(
                    output_dir=str(tmp_path / "trainer_out"),
                    num_train_epochs=1,
                    max_steps=2,
                    per_device_train_batch_size=4,
                    logging_steps=1,
                    save_strategy="no",
                    eval_strategy="no",
                    report_to=[],  # type: ignore[arg-type]  # silence default integrations
                    disable_tqdm=True,
                    use_cpu=True,
                ),
                train_dataset=dataset,
            )
            trainer.train()
        run_id = run.run_id

    metrics = await backend.list_metrics(run_id)
    run_row = await backend.get_run(run_id)
    assert run_row is not None
    persisted_params = run_row.get("params") or {}

    # Metrics — per-step on_log emissions respect logging_steps=1.
    metric_keys = {row["key"] for row in metrics}
    assert len(metrics) >= 3, f"expected ≥3 metric rows per §8.1, got {len(metrics)}"
    # HF logs at least `loss` + `learning_rate` + `epoch` + train_runtime.
    assert any(
        "loss" in k for k in metric_keys
    ), f"expected loss metric, got {metric_keys}"

    # Rolling tokens/sec — emitted once `train_samples_per_second` or
    # `train_tokens_per_second` shows up in logs (typically in the
    # final summary entry from HF's on_log).
    assert any(
        k.startswith("tokens_per_second_rolling_") for k in metric_keys
    ), f"expected tokens_per_second_rolling_N metric per §3.1.2, got {metric_keys}"

    # Params — training_args.* + model.* (non-PEFT path).
    param_keys = set(persisted_params.keys())
    assert any(
        k.startswith("training_args.") for k in param_keys
    ), f"expected training_args.* params, got {sorted(param_keys)[:10]}"
    assert any(
        k.startswith("model.") for k in param_keys
    ), f"expected model.* config params, got {sorted(param_keys)[:10]}"


async def test_transformers_autolog_peft_split_params_and_fingerprints(
    backend: SqliteTrackerStore,
    tmp_path: Path,
) -> None:
    """PEFT-wrapped model emits base.* + lora.* prefixed params AND
    base_model_fingerprint + adapter_fingerprint as separate params
    per §3.1.1 MUST rules 1 + 2.
    """
    peft = pytest.importorskip("peft")  # noqa: F841 — skip if unavailable
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import Trainer, TrainingArguments

    async with track("w23f-transformers-peft", backend=backend) as run:
        async with autolog("transformers"):
            base_model = _build_tiny_bert()
            lora_cfg = LoraConfig(
                task_type=TaskType.SEQ_CLS,
                r=2,
                lora_alpha=4,
                lora_dropout=0.0,
                target_modules=["query", "value"],  # attention projections
            )
            model = get_peft_model(base_model, lora_cfg)
            dataset = _build_toy_dataset()

            trainer = Trainer(
                model=model,
                args=TrainingArguments(
                    output_dir=str(tmp_path / "peft_out"),
                    num_train_epochs=1,
                    max_steps=1,
                    per_device_train_batch_size=4,
                    logging_steps=1,
                    save_strategy="no",
                    eval_strategy="no",
                    report_to=[],  # type: ignore[arg-type]
                    disable_tqdm=True,
                    use_cpu=True,
                ),
                train_dataset=dataset,
            )
            trainer.train()
        run_id = run.run_id

    run_row = await backend.get_run(run_id)
    assert run_row is not None
    params = run_row.get("params") or {}
    param_keys = set(params.keys())

    assert any(
        k.startswith("base.") for k in param_keys
    ), f"expected base.* params for PEFT per §3.1.1, got {sorted(param_keys)[:10]}"
    assert any(
        k.startswith("lora.") for k in param_keys
    ), f"expected lora.* params for PEFT per §3.1.1, got {sorted(param_keys)[:10]}"
    assert (
        "base_model_fingerprint" in param_keys
    ), f"expected base_model_fingerprint per §3.1.1, got {sorted(param_keys)[:10]}"
    assert (
        "adapter_fingerprint" in param_keys
    ), f"expected adapter_fingerprint per §3.1.1, got {sorted(param_keys)[:10]}"
    # Fingerprints MUST differ — adapter adds params the base doesn't have.
    assert (
        params["base_model_fingerprint"] != params["adapter_fingerprint"]
    ), "base_model_fingerprint and adapter_fingerprint should differ"


async def test_transformers_autolog_restores_trainer_init_on_exit(
    backend: SqliteTrackerStore,
) -> None:
    """Per §3.2 + §1.3: detach MUST restore ``Trainer.__init__``."""
    from transformers import Trainer

    original_init = Trainer.__init__

    async with track("w23f-transformers-restore", backend=backend):
        async with autolog("transformers"):
            assert (
                Trainer.__init__ is not original_init
            ), "TransformersAutologIntegration.attach did NOT replace Trainer.__init__"
    assert (
        Trainer.__init__ is original_init
    ), "TransformersAutologIntegration.detach did NOT restore Trainer.__init__; class-level patch LEAKED per §1.3"


async def test_transformers_autolog_restores_trainer_init_even_when_body_raises(
    backend: SqliteTrackerStore,
) -> None:
    """Per §8.5 + §3.2: detach runs in ``finally:`` even when the
    wrapped block raises.
    """
    from transformers import Trainer

    original_init = Trainer.__init__

    async with track("w23f-transformers-restore-on-raise", backend=backend):
        with pytest.raises(ValueError, match="user body error"):
            async with autolog("transformers"):
                raise ValueError("user body error")
    assert (
        Trainer.__init__ is original_init
    ), "TransformersAutologIntegration.detach did NOT restore Trainer.__init__ after raising body"
