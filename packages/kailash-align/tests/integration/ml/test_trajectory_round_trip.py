# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 round-trip test for the shared trajectory schema (W6-016, F-E1-50).

Per ``specs/ml-rl-align-unification.md`` v1.0.0 §3.2 + §4 the bridge
contract is: an RL producer emits a ``TrajectorySchema`` and an Align
consumer accepts it byte-stably. This test rides BOTH halves through
the public facades — kailash-ml side ``RLTrainer.collect_trajectories``
and kailash-align side ``AlignmentPipeline.consume_trajectories`` —
mirroring the ``rules/orphan-detection.md`` §2a crypto-pair-round-trip
discipline applied to the trajectory schema.

The test is Tier 2 per ``rules/testing.md`` § "Tier 2 (Integration):
Real infrastructure recommended" — uses real polars / real datetime
serialisation / real json.dumps; no mocks. Both packages must be
installed (kailash-align declares kailash-ml as a runtime dep).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from kailash_align.ml import TrajectorySchema as AlignTrajectorySchema
from kailash_align.config import AlignmentConfig
from kailash_align.exceptions import TrainingError
from kailash_align.pipeline import AlignmentPipeline
from kailash_ml.rl import (
    EpisodeRecord,
    EvalRecord,
    RLLineage,
    RLTrainer,
    TrajectorySchema,
)
from kailash_ml.rl.trainer import RLTrainingResult


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


def _make_lineage() -> RLLineage:
    return RLLineage(
        run_id="rl_train:cartpole:v1",
        experiment_name="W6-016-round-trip",
        tenant_id="t-rl",
        base_model_ref=None,
        reference_model_ref=None,
        reward_model_ref=None,
        dataset_ref=None,
        env_spec="CartPole-v1",
        algorithm="ppo",
        paradigm="on-policy",
        parent_run_id=None,
        sdk_source="kailash-ml",
        sdk_version="1.2.0",
        created_at=datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc),
    )


def _make_episode(idx: int) -> EpisodeRecord:
    return EpisodeRecord(
        episode_index=idx,
        reward=100.0 + idx,
        length=200 + idx,
        timestamp=datetime(2026, 4, 27, 12, 0, idx, tzinfo=timezone.utc),
    )


def _make_eval(step: int) -> EvalRecord:
    # Encode the step into a microsecond field so multiple evals at
    # different ``eval_step`` values yield distinct timestamps without
    # blowing past the seconds-in-minute bound (``step`` can be 500+).
    return EvalRecord(
        eval_step=step,
        mean_reward=180.0 + step,
        std_reward=12.0,
        mean_length=210.5,
        success_rate=0.7,
        n_episodes=10,
        timestamp=datetime(2026, 4, 27, 12, 5, 0, step, tzinfo=timezone.utc),
    )


def _make_result_with_lineage() -> RLTrainingResult:
    return RLTrainingResult(
        algorithm="ppo",
        env_spec="CartPole-v1",
        total_timesteps=1000,
        episode_reward_mean=120.5,
        episode_reward_std=18.2,
        episode_length_mean=205.0,
        total_env_steps=1000,
        episodes=[_make_episode(i) for i in range(3)],
        eval_history=[_make_eval(0), _make_eval(500)],
        lineage=_make_lineage(),
        elapsed_seconds=42.0,
        device_used="cpu",
        tenant_id="t-rl",
    )


# ----------------------------------------------------------------------
# 1. Single-source-in-ml mandate (spec §7)
# ----------------------------------------------------------------------


@pytest.mark.integration
def test_align_re_export_is_canonical_ml_type() -> None:
    """``kailash_align.ml.TrajectorySchema`` MUST be the kailash-ml type.

    Per spec §7 the trajectory schema lives in kailash_ml.rl. align
    re-exports the type — it MUST NOT define a parallel one. This test
    is the structural defense against future drift toward a parallel
    align-side definition.
    """
    assert AlignTrajectorySchema is TrajectorySchema


# ----------------------------------------------------------------------
# 2. RL producer emits a TrajectorySchema (collect_trajectories)
# ----------------------------------------------------------------------


@pytest.mark.integration
def test_rl_trainer_collect_trajectories_returns_schema() -> None:
    result = _make_result_with_lineage()
    trajectory = RLTrainer.collect_trajectories(result, metadata={"note": "smoke"})

    assert isinstance(trajectory, TrajectorySchema)
    assert trajectory.n_episodes == 3
    assert trajectory.n_evals == 2
    assert trajectory.lineage.run_id == "rl_train:cartpole:v1"
    # Producer-supplied metadata survives the bundle contract.
    assert trajectory.metadata["note"] == "smoke"
    # Auto-populated metadata from the result is present.
    assert trajectory.metadata["algorithm"] == "ppo"
    assert trajectory.metadata["env_spec"] == "CartPole-v1"
    assert trajectory.metadata["tenant_id"] == "t-rl"


@pytest.mark.integration
def test_rl_trainer_collect_trajectories_requires_lineage() -> None:
    """Result with lineage=None MUST raise — no silent provenance loss."""
    from kailash_ml.errors import RLError

    result = _make_result_with_lineage()
    result.lineage = None
    with pytest.raises(RLError) as excinfo:
        RLTrainer.collect_trajectories(result)
    assert excinfo.value.reason == "missing_lineage"


# ----------------------------------------------------------------------
# 3. Byte-stable round-trip through to_dict / from_dict
# ----------------------------------------------------------------------


@pytest.mark.integration
def test_trajectory_round_trip_dict_form_byte_stable() -> None:
    """Round-trip 1: schema -> to_dict -> from_dict -> schema.

    Asserts every typed sub-field re-materialises with the exact same
    value, including datetime parsing.
    """
    original = RLTrainer.collect_trajectories(_make_result_with_lineage())
    payload = original.to_dict()

    # The dict-form carries the schema discriminator and version.
    assert payload["schema"] == "kailash_ml.rl.TrajectorySchema"
    assert payload["schema_version"] == 1
    assert len(payload["episodes"]) == 3
    assert len(payload["eval_history"]) == 2
    assert payload["lineage"]["run_id"] == "rl_train:cartpole:v1"

    restored = TrajectorySchema.from_dict(payload)
    assert restored.n_episodes == original.n_episodes
    assert restored.n_evals == original.n_evals
    assert restored.lineage.run_id == original.lineage.run_id
    assert restored.lineage.algorithm == original.lineage.algorithm
    assert restored.lineage.created_at == original.lineage.created_at

    # Episode-level equality
    for orig_ep, new_ep in zip(original.episodes, restored.episodes):
        assert orig_ep.episode_index == new_ep.episode_index
        assert orig_ep.reward == new_ep.reward
        assert orig_ep.length == new_ep.length
        assert orig_ep.timestamp == new_ep.timestamp

    # Eval-level equality
    for orig_ev, new_ev in zip(original.eval_history, restored.eval_history):
        assert orig_ev.eval_step == new_ev.eval_step
        assert orig_ev.mean_reward == new_ev.mean_reward
        assert orig_ev.success_rate == new_ev.success_rate
        assert orig_ev.timestamp == new_ev.timestamp


@pytest.mark.integration
def test_trajectory_round_trip_json_byte_stable() -> None:
    """Round-trip 2: schema -> JSON -> schema produces byte-identical JSON.

    The test serialises twice with ``sort_keys=True`` and asserts the
    bytes are identical. This is the canonical contract for cross-
    process / cross-machine handoff.
    """
    original = RLTrainer.collect_trajectories(_make_result_with_lineage())
    payload_first = original.to_dict()
    blob_first = json.dumps(payload_first, sort_keys=True).encode("utf-8")

    restored = TrajectorySchema.from_dict(json.loads(blob_first))
    payload_second = restored.to_dict()
    blob_second = json.dumps(payload_second, sort_keys=True).encode("utf-8")

    assert blob_first == blob_second, (
        "byte-stable round-trip violated — TrajectorySchema must "
        "serialise identically across to_dict -> from_dict cycles"
    )


@pytest.mark.integration
def test_trajectory_from_dict_rejects_wrong_schema() -> None:
    """Foreign payloads (missing discriminator) MUST raise."""
    with pytest.raises(ValueError, match="schema discriminator"):
        TrajectorySchema.from_dict({"episodes": [], "lineage": {}})


@pytest.mark.integration
def test_trajectory_from_dict_rejects_unsupported_version() -> None:
    """Future schema_version MUST raise — no silent forward-compat."""
    payload = RLTrainer.collect_trajectories(_make_result_with_lineage()).to_dict()
    payload["schema_version"] = 99
    with pytest.raises(ValueError, match="schema_version"):
        TrajectorySchema.from_dict(payload)


# ----------------------------------------------------------------------
# 4. Align consumer accepts a TrajectorySchema (consume_trajectories)
# ----------------------------------------------------------------------


@pytest.mark.integration
def test_alignment_pipeline_consume_single_trajectory() -> None:
    """End-to-end producer -> consumer through both public facades."""
    config = AlignmentConfig(method="sft", base_model_id="distilgpt2")
    pipeline = AlignmentPipeline(config=config)

    trajectory = RLTrainer.collect_trajectories(_make_result_with_lineage())
    pipeline.consume_trajectories(trajectory)

    assert pipeline.consumed_trajectories == (trajectory,)
    # The consumed trajectory's lineage MUST survive the handoff
    consumed = pipeline.consumed_trajectories[0]
    assert consumed.lineage.run_id == "rl_train:cartpole:v1"
    assert consumed.n_episodes == 3


@pytest.mark.integration
def test_alignment_pipeline_consume_iterable_of_trajectories() -> None:
    """Iterable callers MAY pass a list/tuple of trajectories."""
    config = AlignmentConfig(method="sft", base_model_id="distilgpt2")
    pipeline = AlignmentPipeline(config=config)

    t1 = RLTrainer.collect_trajectories(_make_result_with_lineage())
    t2 = RLTrainer.collect_trajectories(_make_result_with_lineage())
    pipeline.consume_trajectories([t1, t2])

    assert len(pipeline.consumed_trajectories) == 2
    # Repeated calls accumulate
    pipeline.consume_trajectories(t1)
    assert len(pipeline.consumed_trajectories) == 3


@pytest.mark.integration
def test_alignment_pipeline_rejects_wrong_type() -> None:
    """Non-TrajectorySchema items MUST raise TrainingError."""
    config = AlignmentConfig(method="sft", base_model_id="distilgpt2")
    pipeline = AlignmentPipeline(config=config)

    with pytest.raises(TrainingError, match="TrajectorySchema"):
        pipeline.consume_trajectories({"not": "a trajectory"})

    with pytest.raises(TrainingError, match="not a TrajectorySchema"):
        pipeline.consume_trajectories(["bad item"])


# ----------------------------------------------------------------------
# 5. Full bridge: RL produces -> serialise -> deserialise -> Align consumes
# ----------------------------------------------------------------------


@pytest.mark.integration
def test_full_bridge_rl_to_align_via_json() -> None:
    """The canonical cross-machine handoff: RL -> JSON blob -> Align.

    This is the real-world bridge contract. RL training runs on a
    GPU host, emits the trajectory as a JSON blob, an alignment
    pipeline on a different host deserialises it and consumes it.
    """
    # Producer side
    result = _make_result_with_lineage()
    produced = RLTrainer.collect_trajectories(result, metadata={"transport": "json"})
    blob = json.dumps(produced.to_dict(), sort_keys=True).encode("utf-8")

    # Wire transport simulated; deserialise on consumer side
    received = TrajectorySchema.from_dict(json.loads(blob))

    # Consumer side
    config = AlignmentConfig(method="dpo", base_model_id="distilgpt2")
    pipeline = AlignmentPipeline(config=config)
    pipeline.consume_trajectories(received)

    # Assert externally-observable effects on the consumer
    assert len(pipeline.consumed_trajectories) == 1
    consumed = pipeline.consumed_trajectories[0]
    assert consumed.lineage.run_id == "rl_train:cartpole:v1"
    assert consumed.lineage.algorithm == "ppo"
    assert consumed.metadata["transport"] == "json"
    assert consumed.n_episodes == 3
    assert consumed.n_evals == 2
