# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for the ``kailash_align.ml`` namespace.

Validates the W32 §32b contract that ``kailash_align.ml`` is a stable
re-export of the four W30 RL bridge adapters PLUS the three new
integration entry points (``LoRALightningCallback``,
``lora_callback_for``, ``trajectory_from_alignment_run``). These tests
are pure Python — no torch, no pytorch_lightning, no kailash-ml
tracking infrastructure required. Tier 2 tests in the sibling
integration/ml/ tree exercise the runtime contracts.
"""
from __future__ import annotations

import inspect

import pytest


def test_align_ml_exports_four_bridge_adapters() -> None:
    """The four W30 rl_bridge adapters re-export under spec §2 names."""
    from kailash_align.ml import (
        DPOTrainer,
        OnlineDPOTrainer,
        PPOTrainer,
        RLOOTrainer,
    )

    # Spec §2 canonical names MUST resolve to the W30 storage-module classes
    from kailash_align.rl_bridge import (
        DPOAdapter,
        OnlineDPOAdapter,
        PPORLHFAdapter,
        RLOOAdapter,
    )

    assert DPOTrainer is DPOAdapter
    assert PPOTrainer is PPORLHFAdapter
    assert RLOOTrainer is RLOOAdapter
    assert OnlineDPOTrainer is OnlineDPOAdapter


def test_align_ml_exposes_lora_callback_entries() -> None:
    """``LoRALightningCallback`` class + ``lora_callback_for`` entry exist."""
    from kailash_align.ml import LoRALightningCallback, lora_callback_for

    # Class present (even when Lightning isn't installed — constructor
    # is the loud-fail point, not the import)
    assert inspect.isclass(LoRALightningCallback)

    # Entry function is a callable
    assert callable(lora_callback_for)
    sig = inspect.signature(lora_callback_for)
    params = list(sig.parameters.keys())
    assert params == ["trainable"], f"unexpected signature: {sig}"


def test_align_ml_exposes_trajectory_entry() -> None:
    """``trajectory_from_alignment_run`` exists and takes one positional."""
    from kailash_align.ml import trajectory_from_alignment_run

    assert callable(trajectory_from_alignment_run)
    sig = inspect.signature(trajectory_from_alignment_run)
    params = list(sig.parameters.keys())
    assert params == ["run"], f"unexpected signature: {sig}"


def test_align_ml_all_matches_exports() -> None:
    """Every ``__all__`` entry resolves at module-scope (orphan-detection §6)."""
    import kailash_align.ml as ml_mod

    for name in ml_mod.__all__:
        assert hasattr(ml_mod, name), (
            f"align.ml.__all__ advertises {name!r} but the symbol is "
            f"not present at module scope"
        )


def test_lora_callback_for_returns_none_for_non_lora_trainable() -> None:
    """Non-LoRA trainables get ``None`` — ml can skip wiring cleanly."""
    from kailash_align.ml import lora_callback_for

    class NotALoraTrainable:
        """Plain trainable with no LoRA markers."""

        trainable_kind = "classifier"

    # The entry silently returns None (not raises) for non-LoRA trainables
    assert lora_callback_for(NotALoraTrainable()) is None


def test_lora_callback_for_returns_none_for_none() -> None:
    """Explicit ``None`` trainable is accepted and returns ``None``."""
    from kailash_align.ml import lora_callback_for

    assert lora_callback_for(None) is None


def test_trajectory_rejects_run_missing_required_fields() -> None:
    """Duck-typed run object without ``adapter_name`` raises ``ValueError``."""
    from kailash_align.ml import trajectory_from_alignment_run

    class IncompleteRun:
        method = "dpo"

    with pytest.raises(ValueError, match="adapter_name"):
        trajectory_from_alignment_run(IncompleteRun())


def test_trajectory_rejects_run_missing_method() -> None:
    """Run with adapter_name but no ``method`` raises ``ValueError``."""
    from kailash_align.ml import trajectory_from_alignment_run

    class IncompleteRun:
        adapter_name = "my-lora"

    with pytest.raises(ValueError, match="method"):
        trajectory_from_alignment_run(IncompleteRun())


def test_trajectory_from_complete_alignment_result() -> None:
    """End-to-end conversion: happy-path duck-typed run → RLLineage."""
    from kailash_align.ml import trajectory_from_alignment_run

    class FakeAlignmentResult:
        """Minimal duck-typed AlignmentResult satisfying _require_attr."""

        adapter_name = "sft-tiny"
        adapter_path = "/tmp/adapter"
        adapter_version = None
        training_metrics = {"loss": 0.5}
        experiment_dir = "/tmp/exp"
        method = "sft"
        tenant_id = "t-1"
        base_model_id = "sshleifer/tiny-gpt2"
        dataset_ref = None

    lineage = trajectory_from_alignment_run(FakeAlignmentResult())

    # Spec §5.2 — align-produced trajectories ALWAYS mark sdk_source
    assert lineage.sdk_source == "kailash-align"
    # Spec §5.1 — align runs are "rlhf" paradigm
    assert lineage.paradigm == "rlhf"
    assert lineage.algorithm == "sft"
    assert lineage.experiment_name == "sft-tiny"
    assert lineage.tenant_id == "t-1"
    assert lineage.base_model_ref == "sshleifer/tiny-gpt2"
    # run_id derived-and-sanitized
    assert lineage.run_id.startswith("align:sft-tiny:")
    # sdk_version populated from kailash-align's _version
    assert lineage.sdk_version
    assert lineage.created_at is not None


def test_trajectory_sanitizes_adapter_name_in_run_id() -> None:
    """Adapter names with shell-unsafe chars get sanitized in run_id."""
    from kailash_align.ml import trajectory_from_alignment_run

    class EvilRun:
        adapter_name = "evil; rm -rf /"
        adapter_version = None
        method = "dpo"

    lineage = trajectory_from_alignment_run(EvilRun())
    # Every unsafe token replaced by underscore; colon is permitted only
    # as the top-level "align:<name>:<suffix>" separator
    assert ";" not in lineage.run_id
    assert "/" not in lineage.run_id
    assert "rm" not in lineage.run_id or lineage.run_id.count(":") <= 2
    assert lineage.run_id.startswith("align:")


def test_trajectory_uses_adapter_version_when_available() -> None:
    """When AdapterVersion is present its ``version`` drives the run_id."""
    from kailash_align.ml import trajectory_from_alignment_run

    class FakeAdapterVersion:
        version = 7

    class RunWithVersion:
        adapter_name = "my-lora"
        adapter_version = FakeAdapterVersion()
        method = "dpo"

    lineage = trajectory_from_alignment_run(RunWithVersion())
    assert lineage.run_id == "align:my-lora:v7"
