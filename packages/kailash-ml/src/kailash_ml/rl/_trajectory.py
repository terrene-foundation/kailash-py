# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared trajectory schema for ``kailash-ml`` <-> ``kailash-align``.

Per ``specs/ml-rl-align-unification.md`` v1.0.0 §3.2 + §4 + §5, a trajectory
produced on EITHER side of the bridge MUST be representable by a single
schema so a researcher can do "baseline RL → fine-tune via RLHF" with one
data carrier between the producer (``RLTrainer``) and the consumer
(``AlignmentPipeline``). The schema lives on the kailash-ml side per the
single-source-in-ml mandate (spec §7); kailash-align re-exports the type,
never redefines it (W6-016 finding F-E1-50 closure).

Conceptual model
----------------

A :class:`TrajectorySchema` is the byte-stable bundle of a finished rollout
session:

* ``episodes`` — every completed episode (:class:`EpisodeRecord`),
  produced by RL rollouts OR by RLHF generations re-cast as episodes
  (one completion = one episode in the spec §3.4 mapping table).
* ``eval_history`` — scheduled evaluations (:class:`EvalRecord`), kept
  even when only a subset of consumers care because the bridge promises
  Protocol-shape parity for both sides.
* ``lineage`` — :class:`RLLineage` provenance record. Carries
  ``sdk_source`` so the consumer can disambiguate classical-RL vs RLHF
  origin without inspecting episode shapes.
* ``metadata`` — frozen mapping (``MappingProxyType``) for extension
  data: env spec, reward-model ref hashes, dataset-row counts, anything
  the producer wants to forward without growing the dataclass surface.

Frozen by construction so the bridge cannot mutate a trajectory between
producer and consumer (spec §5 lineage immutability promise extended to
trajectory state). ``to_dict`` / ``from_dict`` round-trip is byte-stable
under canonical JSON so cross-process / cross-machine handoff is sound
without bespoke serialisers.

Spec-deviation note (specs-authority.md MUST Rule 6)
----------------------------------------------------

Spec §1 (and the W30 0.6.0 changelog) refer to the cross-SDK provenance
record as ``RLLineage`` and intentionally do not define a parallel
"Trajectory" class. ``TrajectorySchema`` is NOT a parallel lineage type —
it is a bundle that *contains* an :class:`RLLineage` plus the actual
episode + eval data. The W6-016 todo's "shared trajectory schema" is the
named bundle the spec implies in §3.2 + §4 (where the test contract
asserts both sides produce data round-trippable through a single shape).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from kailash_ml.rl._lineage import RLLineage
from kailash_ml.rl._records import EpisodeRecord, EvalRecord

__all__ = ["TrajectorySchema"]


_EMPTY_METADATA: Mapping[str, Any] = MappingProxyType({})


def _freeze_metadata(metadata: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return a read-only view of ``metadata``.

    Accepts ``None`` (-> empty), an existing ``MappingProxyType`` (-> as-is),
    or any ``Mapping`` (-> shallow-copied into a fresh ``MappingProxyType``).
    Mutating the original after construction MUST NOT mutate the
    trajectory's view — the schema's immutability promise depends on the
    metadata view being read-only at the trajectory boundary.
    """
    if metadata is None:
        return _EMPTY_METADATA
    if isinstance(metadata, MappingProxyType):
        return metadata
    if not isinstance(metadata, Mapping):
        raise TypeError(
            "TrajectorySchema.metadata must be a Mapping or None, "
            f"got {type(metadata).__name__!r}"
        )
    return MappingProxyType(dict(metadata))


@dataclass(frozen=True)
class TrajectorySchema:
    """Cross-SDK trajectory bundle for the ml<->align bridge.

    Frozen + tuple-backed so producers and consumers can pass instances
    by reference without defensive copies. Round-trips byte-stably
    through :meth:`to_dict` / :meth:`from_dict`.

    Parameters
    ----------
    episodes:
        Completed rollout episodes. MUST be a tuple of
        :class:`EpisodeRecord`. Empty trajectories are allowed at
        construction (e.g. for resumes that have not yet produced an
        episode); consumers that require ≥1 episode MUST raise on their
        own.
    lineage:
        Required :class:`RLLineage` provenance. The schema cannot exist
        without provenance — the bridge promise depends on it.
    eval_history:
        Scheduled evaluation records (:class:`EvalRecord`). Empty when
        ``eval_freq > total_timesteps`` or when no eval ran.
    metadata:
        Producer-supplied extension fields (env spec, reward-model
        refs, dataset row counts, etc.). Stored as a read-only mapping
        so callers cannot mutate it post-handoff. Default empty.
    """

    episodes: tuple[EpisodeRecord, ...]
    lineage: RLLineage
    eval_history: tuple[EvalRecord, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_METADATA)

    def __post_init__(self) -> None:
        # Coerce list/iterable inputs to tuples so the dataclass is
        # frozen-equivalent regardless of caller convenience. Reject
        # anything that isn't a sequence of the expected record type.
        episodes = self.episodes
        if not isinstance(episodes, tuple):
            try:
                episodes = tuple(episodes)
            except TypeError as exc:  # pragma: no cover — defensive
                raise TypeError(
                    "TrajectorySchema.episodes must be iterable of "
                    f"EpisodeRecord, got {type(self.episodes).__name__!r}"
                ) from exc
            object.__setattr__(self, "episodes", episodes)
        for idx, ep in enumerate(episodes):
            if not isinstance(ep, EpisodeRecord):
                raise TypeError(
                    f"TrajectorySchema.episodes[{idx}] must be EpisodeRecord, "
                    f"got {type(ep).__name__!r}"
                )

        eval_history = self.eval_history
        if not isinstance(eval_history, tuple):
            try:
                eval_history = tuple(eval_history)
            except TypeError as exc:  # pragma: no cover — defensive
                raise TypeError(
                    "TrajectorySchema.eval_history must be iterable of "
                    f"EvalRecord, got {type(self.eval_history).__name__!r}"
                ) from exc
            object.__setattr__(self, "eval_history", eval_history)
        for idx, ev in enumerate(eval_history):
            if not isinstance(ev, EvalRecord):
                raise TypeError(
                    f"TrajectorySchema.eval_history[{idx}] must be EvalRecord, "
                    f"got {type(ev).__name__!r}"
                )

        if not isinstance(self.lineage, RLLineage):
            raise TypeError(
                "TrajectorySchema.lineage must be an RLLineage, "
                f"got {type(self.lineage).__name__!r}"
            )

        # Always normalize metadata to a read-only mapping; reject
        # non-mapping inputs at construction so consumers never see a
        # mutable dict at the schema boundary.
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def n_episodes(self) -> int:
        """Number of completed episodes in this trajectory."""
        return len(self.episodes)

    @property
    def n_evals(self) -> int:
        """Number of evaluation rollouts attached to this trajectory."""
        return len(self.eval_history)

    @property
    def is_empty(self) -> bool:
        """True when no episodes AND no evals are attached."""
        return not self.episodes and not self.eval_history

    # ------------------------------------------------------------------
    # Serialisation — byte-stable round-trip contract
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dict representation.

        Round-trip contract (verified by Tier-2 test): ``json.dumps`` of
        ``trajectory.to_dict()`` is byte-identical for two trajectories
        produced from the same inputs, given a stable JSON serialiser
        (``sort_keys=True``). Datetime fields are serialised via
        ``isoformat()``.
        """
        return {
            "schema": "kailash_ml.rl.TrajectorySchema",
            "schema_version": 1,
            "episodes": [_episode_to_dict(ep) for ep in self.episodes],
            "eval_history": [_eval_to_dict(ev) for ev in self.eval_history],
            "lineage": self.lineage.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "TrajectorySchema":
        """Round-trip complement of :meth:`to_dict`.

        Parses the ``episodes``, ``eval_history``, and ``lineage``
        sub-payloads back into their typed forms. Raises ``ValueError``
        on payloads missing the schema discriminator OR with an
        unrecognised ``schema_version``; raises ``TypeError`` on shape
        mismatches via the dataclass ``__post_init__``.
        """
        if not isinstance(payload, dict):
            raise ValueError(
                "TrajectorySchema.from_dict expects a dict, "
                f"got {type(payload).__name__!r}"
            )
        schema = payload.get("schema")
        if schema != "kailash_ml.rl.TrajectorySchema":
            raise ValueError(
                "TrajectorySchema.from_dict: payload schema discriminator is "
                f"{schema!r}, expected 'kailash_ml.rl.TrajectorySchema'"
            )
        version = payload.get("schema_version")
        if version != 1:
            raise ValueError(
                "TrajectorySchema.from_dict: unsupported schema_version "
                f"{version!r}; this build understands schema_version=1"
            )

        episodes_payload = payload.get("episodes", [])
        if not isinstance(episodes_payload, list):
            raise ValueError(
                "TrajectorySchema.from_dict: 'episodes' must be a list, "
                f"got {type(episodes_payload).__name__!r}"
            )
        episodes = tuple(_episode_from_dict(item) for item in episodes_payload)

        eval_payload = payload.get("eval_history", [])
        if not isinstance(eval_payload, list):
            raise ValueError(
                "TrajectorySchema.from_dict: 'eval_history' must be a list, "
                f"got {type(eval_payload).__name__!r}"
            )
        evals = tuple(_eval_from_dict(item) for item in eval_payload)

        lineage_payload = payload.get("lineage")
        if not isinstance(lineage_payload, dict):
            raise ValueError(
                "TrajectorySchema.from_dict: 'lineage' must be a dict, "
                f"got {type(lineage_payload).__name__!r}"
            )
        lineage = RLLineage.from_dict(lineage_payload)

        metadata_payload = payload.get("metadata", {})
        if not isinstance(metadata_payload, dict):
            raise ValueError(
                "TrajectorySchema.from_dict: 'metadata' must be a dict, "
                f"got {type(metadata_payload).__name__!r}"
            )

        return cls(
            episodes=episodes,
            lineage=lineage,
            eval_history=evals,
            metadata=metadata_payload,
        )


# ----------------------------------------------------------------------
# EpisodeRecord / EvalRecord serialisation helpers
#
# These live alongside the schema (not on the records themselves) because
# the records are pure data and the schema owns the contract for how they
# are framed at the bridge boundary. Keeping the helpers private + local
# also avoids growing the EpisodeRecord public surface.
# ----------------------------------------------------------------------


def _episode_to_dict(ep: EpisodeRecord) -> dict[str, Any]:
    return {
        "episode_index": ep.episode_index,
        "reward": ep.reward,
        "length": ep.length,
        "timestamp": ep.timestamp.isoformat(),
    }


def _episode_from_dict(payload: Any) -> EpisodeRecord:
    if not isinstance(payload, dict):
        raise ValueError(
            "TrajectorySchema episode payload must be a dict, "
            f"got {type(payload).__name__!r}"
        )
    ts = payload.get("timestamp")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return EpisodeRecord(
        episode_index=int(payload["episode_index"]),
        reward=float(payload["reward"]),
        length=int(payload["length"]),
        timestamp=ts,
    )


def _eval_to_dict(ev: EvalRecord) -> dict[str, Any]:
    return {
        "eval_step": ev.eval_step,
        "mean_reward": ev.mean_reward,
        "std_reward": ev.std_reward,
        "mean_length": ev.mean_length,
        "success_rate": ev.success_rate,
        "n_episodes": ev.n_episodes,
        "timestamp": ev.timestamp.isoformat(),
    }


def _eval_from_dict(payload: Any) -> EvalRecord:
    if not isinstance(payload, dict):
        raise ValueError(
            "TrajectorySchema eval payload must be a dict, "
            f"got {type(payload).__name__!r}"
        )
    ts = payload.get("timestamp")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return EvalRecord(
        eval_step=int(payload["eval_step"]),
        mean_reward=float(payload["mean_reward"]),
        std_reward=float(payload["std_reward"]),
        mean_length=float(payload["mean_length"]),
        success_rate=(
            float(payload["success_rate"])
            if payload.get("success_rate") is not None
            else None
        ),
        n_episodes=int(payload["n_episodes"]),
        timestamp=ts,
    )
