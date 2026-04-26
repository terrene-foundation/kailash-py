# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Per-episode + per-eval records for :class:`RLTrainingResult`.

Per ``specs/ml-rl-core.md`` §3.2 + §10.2 every RL training run populates
typed lists of these records on the returned
:class:`~kailash_ml.rl.trainer.RLTrainingResult`:

* :class:`EpisodeRecord` — one per completed training episode, populated
  from the SB3 ``ep_info_buffer``. Closes HIGH-1 finding ("zero-length
  episodes is a Rule 2 violation"). MUST be non-empty at training end
  for any run that completed at least one rollout.
* :class:`EvalRecord` — one per scheduled evaluation, populated by the
  SB3 ``EvalCallback``. Closes HIGH-2 ("``eval_freq`` declared but never
  wired"). MUST be non-empty when ``eval_freq <= total_timesteps``.

Both are pure stdlib dataclasses — no SB3 / Gymnasium imports — so they
load without the ``[rl]`` extra. Both are frozen so downstream code can
hold them by reference without defensive copies and use them as
hash/cache keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__ = ["EpisodeRecord", "EvalRecord"]


@dataclass(frozen=True)
class EpisodeRecord:
    """One completed training episode.

    Per ``specs/ml-rl-core.md`` §3.2 invariant 1 — every ``rl_train()``
    call that runs at least one complete rollout MUST populate
    ``RLTrainingResult.episodes`` with length ≥ 1. Hallucinated zero-
    length lists are a ``rules/zero-tolerance.md`` Rule 2 violation
    (mirror of HIGH-1 finding).

    Parameters
    ----------
    episode_index:
        Monotonic 0-indexed counter assigned in the order episodes
        complete in the training loop.
    reward:
        Cumulative reward over the episode.
    length:
        Number of environment steps the episode ran.
    timestamp:
        UTC timestamp at which the episode ended.
    """

    episode_index: int
    reward: float
    length: int
    timestamp: datetime


@dataclass(frozen=True)
class EvalRecord:
    """One scheduled evaluation rollout.

    Per ``specs/ml-rl-core.md`` §10.2 — every eval produces an
    EvalRecord. Appended to ``RLTrainingResult.eval_history`` and
    emitted via ``tracker.log_metric("rl.eval.*", value, step=eval_step)``.

    Parameters
    ----------
    eval_step:
        Total environment steps elapsed when the evaluation ran.
    mean_reward:
        Mean episode reward across the eval rollout.
    std_reward:
        Standard deviation of episode reward across the eval rollout.
    mean_length:
        Mean episode length across the eval rollout.
    success_rate:
        Proportion of episodes flagged as successful by the env (when
        the env reports ``info["is_success"]``); ``None`` otherwise.
    n_episodes:
        Number of evaluation episodes that contributed to the means.
    timestamp:
        UTC timestamp at which the evaluation completed.
    """

    eval_step: int
    mean_reward: float
    std_reward: float
    mean_length: float
    success_rate: float | None
    n_episodes: int
    timestamp: datetime
