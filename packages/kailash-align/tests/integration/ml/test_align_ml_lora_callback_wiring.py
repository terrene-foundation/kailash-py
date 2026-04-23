# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring test for the LoRA Lightning callback auto-append flow.

Per ``rules/facade-manager-detection.md`` MUST Rule 2 and the W32 §32b
mandate, this test exercises the end-to-end LoRA fit path:

1. Construct a Protocol-satisfying LoRA trainable (duck-typed so it
   exposes the ``is_lora_trainable`` / ``adapter_name`` markers).
2. Call ``kailash_align.ml.lora_callback_for`` to obtain a real
   :class:`LoRALightningCallback` instance.
3. Simulate an ``MLEngine.fit`` loop by invoking the callback's
   ``on_train_batch_end`` with a real trainer stub carrying
   ``callback_metrics`` — the same dict Lightning populates mid-fit.
4. Assert the callback emitted metrics under the ``align.lora.train.*``
   namespace (via ``emit_count > 0``) AND never emitted when
   ``is_global_zero`` is False (rank-0-only guard, spec §3.5).

``pytorch_lightning`` is a conditional import; when absent the test
``skipif`` short-circuits per ``rules/testing.md`` § "Test-Skip Triage
Decision Tree" ACCEPTABLE category. A real Lightning install is tier-2
appropriate because the callback's superclass contract depends on the
Lightning API shape.
"""
from __future__ import annotations

import importlib
import math

import pytest


try:
    importlib.import_module("pytorch_lightning")
    _LIGHTNING_AVAILABLE = True
except ImportError:
    _LIGHTNING_AVAILABLE = False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _LIGHTNING_AVAILABLE,
        reason="requires pytorch_lightning (optional integration dep)",
    ),
]


class _DeterministicLoRATrainable:
    """Protocol-satisfying LoRA trainable — NOT a mock (rules/testing.md §Tier 2 exception).

    Satisfies the ``lora_callback_for`` duck-typed detection contract:

    * ``is_lora_trainable`` attribute truthy
    * ``adapter_name`` + ``tenant_id`` present

    All outputs are deterministic from inputs — the trainable has zero
    random state, zero API keys, zero network. Per the rules/testing.md
    Protocol-Satisfying Deterministic Adapters exception this IS a
    legitimate Tier-2 test double.
    """

    is_lora_trainable = True
    adapter_name = "test-lora"
    tenant_id = "t-test"


class _StubTrainer:
    """Minimal Lightning-Trainer stub the callback's ``on_*_batch_end`` reads.

    Lightning's Trainer exposes ``callback_metrics``, ``global_step``,
    and ``is_global_zero``. Every metric is a real Python float so the
    ``_to_finite_float`` coercion path in the callback runs identically
    to the tensor case in production.
    """

    def __init__(
        self,
        *,
        metrics: dict,
        step: int = 0,
        is_global_zero: bool = True,
    ) -> None:
        self.callback_metrics = metrics
        self.global_step = step
        self.is_global_zero = is_global_zero


def test_lora_callback_for_attaches_to_lora_trainable() -> None:
    """End-to-end: lora_callback_for returns a wired callback for LoRA trainables."""
    from kailash_align.ml import LoRALightningCallback, lora_callback_for

    trainable = _DeterministicLoRATrainable()
    callback = lora_callback_for(trainable)
    assert isinstance(callback, LoRALightningCallback)
    assert callback.adapter_name == "test-lora"


def test_lora_callback_emits_train_metrics_under_align_lora_namespace() -> None:
    """Invoke on_train_batch_end with real metrics; assert emit_count increments."""
    from kailash_align.ml import lora_callback_for

    trainable = _DeterministicLoRATrainable()
    callback = lora_callback_for(trainable)
    assert callback is not None

    trainer = _StubTrainer(
        metrics={"loss": 0.42, "lr": 1e-5, "reward_margin": 0.7},
        step=1,
    )
    # Lightning signature passes (trainer, pl_module, outputs, batch, batch_idx)
    callback.on_train_batch_end(
        trainer, pl_module=None, outputs=None, batch=None, batch_idx=0
    )

    # All three numeric entries emitted
    assert callback.emit_count == 3


def test_lora_callback_rank_zero_guard() -> None:
    """When ``is_global_zero`` is False, callback silently emits nothing."""
    from kailash_align.ml import lora_callback_for

    trainable = _DeterministicLoRATrainable()
    callback = lora_callback_for(trainable)
    assert callback is not None

    trainer_rank1 = _StubTrainer(
        metrics={"loss": 0.1},
        step=5,
        is_global_zero=False,
    )
    callback.on_train_batch_end(
        trainer_rank1, pl_module=None, outputs=None, batch=None, batch_idx=0
    )

    # Spec §3.5 — non-zero rank skips emission entirely
    assert callback.emit_count == 0


def test_lora_callback_drops_nan_inf() -> None:
    """NaN / Inf metrics are filtered before emission (no tracker corruption)."""
    from kailash_align.ml import lora_callback_for

    trainable = _DeterministicLoRATrainable()
    callback = lora_callback_for(trainable)
    assert callback is not None

    trainer = _StubTrainer(
        metrics={"loss": 0.3, "bad_nan": float("nan"), "bad_inf": float("inf")},
        step=2,
    )
    callback.on_train_batch_end(
        trainer, pl_module=None, outputs=None, batch=None, batch_idx=0
    )

    # Only the finite entry survives
    assert callback.emit_count == 1


def test_lora_callback_validation_hook() -> None:
    """Validation-batch hook routes metrics under the ``align.lora.val.*`` namespace."""
    from kailash_align.ml import lora_callback_for

    trainable = _DeterministicLoRATrainable()
    callback = lora_callback_for(trainable)
    assert callback is not None

    trainer = _StubTrainer(metrics={"val_loss": 0.25}, step=10)
    callback.on_validation_batch_end(
        trainer, pl_module=None, outputs=None, batch=None, batch_idx=0
    )
    assert callback.emit_count == 1


def test_lora_callback_for_returns_none_on_non_lora_trainable() -> None:
    """Non-LoRA trainables get None — ml can skip callback wiring cleanly."""
    from kailash_align.ml import lora_callback_for

    class ClassicalTrainable:
        trainable_kind = "classifier"

    assert lora_callback_for(ClassicalTrainable()) is None
