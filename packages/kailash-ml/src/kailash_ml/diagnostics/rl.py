# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Reinforcement-learning diagnostics for kailash-ml.

``RLDiagnostics`` is the concrete ML adapter that satisfies the
``kailash.diagnostics.protocols.Diagnostic`` Protocol for a classical
or RLHF training loop. It captures per-episode rewards, policy/value
updates, replay-buffer state, and evaluation rollouts; routes every
emission through a multi-axis rank-0 gate (``DP × TP × PP ×
Accelerate``); and surfaces a severity-tagged reward-hacking / reward-
collapse finding from :meth:`report`.

Public surface::

    from kailash_ml.diagnostics import RLDiagnostics

    with RLDiagnostics(algo="ppo") as diag:
        # Manual driving
        diag.record_episode(reward=200.0, length=500)
        diag.record_policy_update(loss=0.12, kl=0.01, entropy=0.8,
                                  clip_fraction=0.18)
        # OR: hand diag.as_sb3_callback() to SB3's .learn()
        model.learn(total_timesteps=10_000, callback=diag.as_sb3_callback())
        findings = diag.report()

Metric namespace (matches ``specs/ml-rl-core.md §8.5`` and cross-SDK
``kailash-rs`` / ``kailash-align``)::

    rl.episode.reward        # per episode, step=episode index
    rl.episode.length        # per episode
    rl.policy.loss           # per policy update
    rl.policy.kl_from_ref    # per policy update (any estimator)
    rl.policy.entropy        # per policy update
    rl.policy.clip_fraction  # PPO only; None elsewhere (never 0 hallucination)
    rl.value.loss            # per value update
    rl.value.explained_variance  # per value update when available
    rl.q.loss                # off-policy Q loss (DQN / SAC / TD3)
    rl.replay.size           # per emission, step=step counter
    rl.eval.reward           # per EvalCallback trigger
    rl.eval.length           # per EvalCallback trigger

When the run is bridged through ``km.rl_train(algo="dpo", ...)`` the
RLHF-adjacent keys from ``specs/ml-rl-align-unification.md §4`` also
land here under ``rl.train.update.*`` — the reward-hacking signal
emitted by ``kailash-align.AlignmentDiagnostics`` lifts into
:meth:`report` as a CRIT severity finding so the classical-RL and
RLHF dashboards catch the same alert filter.

Rank-gate: every emission routes through
:func:`kailash_ml.autolog._distribution.is_main_process` so DP × TP ×
PP × Accelerate fan-outs emit exactly once per step-index.

Plotting and ``[rl]`` / ``[dl]`` extras are deliberately NOT required
at session construction. ``record_*`` / ``report()`` / ``as_sb3_callback``
work against the base install; Stable-Baselines3 is imported lazily
inside :meth:`as_sb3_callback` with a loud failure naming the
``[rl]`` extra when absent.

See ``specs/ml-rl-core.md §§7–8`` for the full class surface;
``specs/ml-rl-align-unification.md §6`` for RLHF parity; and
``src/kailash/diagnostics/protocols.py`` for the cross-SDK Protocol.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from kailash_ml.autolog._distribution import is_main_process

logger = logging.getLogger(__name__)

__all__ = ["RLDiagnostics", "RLDiagnosticFinding"]


# Metric-name schema — single source of truth; downstream tests grep for
# these exact strings.  Spec §8.5 pins the keys; any drift here breaks
# cross-run comparison + cross-SDK forensic correlation.
_METRIC_EPISODE_REWARD = "rl.episode.reward"
_METRIC_EPISODE_LENGTH = "rl.episode.length"
_METRIC_POLICY_LOSS = "rl.policy.loss"
_METRIC_POLICY_KL = "rl.policy.kl_from_ref"
_METRIC_POLICY_ENTROPY = "rl.policy.entropy"
_METRIC_POLICY_CLIP = "rl.policy.clip_fraction"
_METRIC_VALUE_LOSS = "rl.value.loss"
_METRIC_VALUE_EXPLAINED_VARIANCE = "rl.value.explained_variance"
_METRIC_Q_LOSS = "rl.q.loss"
_METRIC_Q_OVERESTIMATION = "rl.q.overestimation_gap"
_METRIC_REPLAY_SIZE = "rl.replay.size"
_METRIC_EVAL_REWARD = "rl.eval.reward"
_METRIC_EVAL_LENGTH = "rl.eval.length"

# Reward-collapse thresholds per spec §8.7.  Tunable via constructor; the
# defaults match the kailash-rs + kailash-align parity contract so a
# single dashboard alert filter catches both classical and RLHF collapse.
_REWARD_COLLAPSE_DROP_FRACTION = 0.5  # 50% drop over window → CRIT
_REWARD_COLLAPSE_PEAK_FRACTION = 0.10  # AND current < 10% of peak


@dataclass(frozen=True)
class RLDiagnosticFinding:
    """One severity-tagged diagnostic finding surfaced by :meth:`report`.

    Severity taxonomy matches ``specs/ml-rl-core.md §8.7`` + cross-SDK
    parity with ``kailash-align.AlignmentDiagnostics`` so the same
    dashboard alert filter catches classical and RLHF collapses.
    """

    severity: str  # "CRIT" | "HIGH" | "MED" | "LOW"
    category: str  # e.g. "episode_reward_collapse"
    message: str  # human-readable summary
    suggestion: str = ""  # remediation hint


# ---------------------------------------------------------------------------
# Duck-typed tracker contract
# ---------------------------------------------------------------------------
#
# RLDiagnostics accepts any object exposing ``log_metric(key, value, *,
# step=None)``.  The async + sync ExperimentTracker handles both satisfy
# the contract; mirrors DLDiagnostics.as_lightning_callback's design.
# We do NOT import ExperimentTracker so this module stays importable
# without the tracking storage backend.


def _require_stable_baselines3() -> Any:
    """Import and return ``stable_baselines3`` or raise with the ``[rl]`` extra."""
    try:
        import stable_baselines3  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover — covered by [rl] install
        raise ImportError(
            "RLDiagnostics.as_sb3_callback() requires stable-baselines3. "
            "Install the RL extras: pip install kailash-ml[rl]"
        ) from exc
    return stable_baselines3


class RLDiagnostics:
    """Reinforcement-learning training diagnostics (Diagnostic Protocol).

    Collects per-episode, per-update, and per-eval metrics; emits
    rank-0-only into a duck-typed tracker; surfaces severity-tagged
    findings from :meth:`report`.

    The adapter satisfies the cross-SDK
    :class:`kailash.diagnostics.protocols.Diagnostic` Protocol
    (``run_id`` + ``__enter__`` + ``__exit__`` + ``report()``).
    ``isinstance(diag, Diagnostic)`` returns ``True`` at runtime because
    the Protocol is ``@runtime_checkable``.

    Args:
        algo: Optional algorithm tag. When set to a PPO-family string
            (``"ppo"`` / ``"ppo-lm"`` / ``"maskable-ppo"``) the callback
            will emit ``clip_fraction``; non-PPO algos emit ``None`` for
            ``clip_fraction`` rather than hallucinate zero.
        window: Rolling window length used for reward-collapse
            detection.  Must be ``>= 2``.  Defaults to ``100``.
        tracker: Optional duck-typed tracker with ``log_metric(key,
            value, *, step=None)``.  When absent, metrics are still
            recorded in-memory (``report()`` works) but no external
            emission happens.
        run_id: Optional correlation identifier for this diagnostic
            session.  UUID4 hex when omitted.  Matches
            :class:`Diagnostic.run_id` in the cross-SDK Protocol.
        collapse_drop_fraction: Override for the reward-collapse drop
            threshold (default ``0.5`` — 50% drop over window).
        collapse_peak_fraction: Override for the reward-collapse peak-
            relative threshold (default ``0.10`` — below 10% of peak).

    Raises:
        ValueError: If ``window < 2``, ``run_id`` is an empty string, or
            either collapse fraction lies outside ``(0, 1]``.
    """

    def __init__(
        self,
        *,
        algo: Optional[str] = None,
        window: int = 100,
        tracker: Optional[Any] = None,
        run_id: Optional[str] = None,
        collapse_drop_fraction: float = _REWARD_COLLAPSE_DROP_FRACTION,
        collapse_peak_fraction: float = _REWARD_COLLAPSE_PEAK_FRACTION,
    ) -> None:
        if window < 2:
            raise ValueError("window must be >= 2")
        if run_id is not None and not run_id:
            raise ValueError("run_id must be a non-empty string when provided")
        if not 0.0 < collapse_drop_fraction <= 1.0:
            raise ValueError("collapse_drop_fraction must lie in (0, 1]")
        if not 0.0 < collapse_peak_fraction <= 1.0:
            raise ValueError("collapse_peak_fraction must lie in (0, 1]")

        self.algo: Optional[str] = algo.lower() if isinstance(algo, str) else algo
        self.window = window
        self._tracker = tracker
        # Satisfies kailash.diagnostics.protocols.Diagnostic.run_id.
        self.run_id: str = run_id if run_id is not None else uuid.uuid4().hex
        self._collapse_drop_fraction = collapse_drop_fraction
        self._collapse_peak_fraction = collapse_peak_fraction

        # Counters — monotonic across the whole session, used as step indices.
        self._episode_counter = 0
        self._step_counter = 0
        self._update_counter = 0
        self._eval_counter = 0

        # In-memory log rows; converted to a dict list on report().
        self._episode_log: list[dict[str, Any]] = []
        self._policy_update_log: list[dict[str, Any]] = []
        self._value_update_log: list[dict[str, Any]] = []
        self._q_update_log: list[dict[str, Any]] = []
        self._replay_log: list[dict[str, Any]] = []
        self._eval_log: list[dict[str, Any]] = []

        # Rolling window of episode rewards for collapse detection.
        self._reward_window: list[float] = []
        self._peak_reward: Optional[float] = None

        # Field names are ``rl_*``-prefixed per rules/observability.md MUST Rule 9
        # (LogRecord reserves ``module``; domain prefix prevents KeyError
        # on frameworks that configure the root logger).
        logger.info(
            "rldiagnostics.init",
            extra={
                "rl_run_id": self.run_id,
                "rl_algo": self.algo,
                "rl_window": window,
            },
        )

    # ── Context-manager support ────────────────────────────────────────────

    def __enter__(self) -> "RLDiagnostics":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> Optional[bool]:
        # Nothing to detach — RLDiagnostics does not install hooks on a
        # user model (unlike DLDiagnostics).  Cleanup is a no-op.
        return None

    # ── Rank-0 emission gate ───────────────────────────────────────────────

    def _emit_metric(self, key: str, value: Any, step: int) -> None:
        """Single enforcement point for multi-axis rank-0 gate + tracker emit.

        Per ``specs/ml-rl-core.md §8.8`` + Decision 4, rank-0-only
        emission is HARDCODED, not configurable.  Non-rank-0 processes
        continue to accumulate in-memory DataFrames (for report()
        aggregation) but emit zero tracker writes.
        """
        if value is None:
            return
        if not is_main_process():
            return
        if self._tracker is None:
            return
        try:
            self._tracker.log_metric(key, float(value), step=step)
        except Exception as exc:  # noqa: BLE001 — tracker backends vary
            # Tracker emission is best-effort; the in-memory log is the
            # source of truth for report().  Log at DEBUG so forensic
            # grep ("rldiagnostics.tracker_emit_failed") is possible but
            # operators are not alerted on an expected-during-shutdown
            # tracker error.
            logger.debug(
                "rldiagnostics.tracker_emit_failed",
                extra={
                    "rl_run_id": self.run_id,
                    "rl_metric": key,
                    "rl_step": step,
                    "error": str(exc),
                },
            )

    # ── Record methods ─────────────────────────────────────────────────────

    def record_episode(
        self,
        reward: float,
        length: int,
        info: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record a completed episode.

        Emits ``rl.episode.reward`` and ``rl.episode.length`` at step =
        episode index.  Updates the rolling reward window used for
        collapse detection.
        """
        idx = self._episode_counter
        row = {
            "episode": idx,
            "reward": float(reward),
            "length": int(length),
            "info": dict(info) if info else {},
        }
        self._episode_log.append(row)
        self._emit_metric(_METRIC_EPISODE_REWARD, reward, step=idx)
        self._emit_metric(_METRIC_EPISODE_LENGTH, length, step=idx)
        self._episode_counter += 1

        # Update rolling window + peak for report()'s collapse finding.
        self._reward_window.append(float(reward))
        if len(self._reward_window) > self.window:
            self._reward_window.pop(0)
        if self._peak_reward is None or reward > self._peak_reward:
            self._peak_reward = float(reward)

    def record_policy_update(
        self,
        loss: float,
        *,
        kl: Optional[float] = None,
        entropy: Optional[float] = None,
        clip_fraction: Optional[float] = None,
    ) -> None:
        """Record a policy-update step.

        Emits ``rl.policy.loss``, ``rl.policy.kl_from_ref``,
        ``rl.policy.entropy``, and (PPO-family only)
        ``rl.policy.clip_fraction``.  Non-PPO algorithms pass
        ``clip_fraction=None`` — we do NOT emit ``0.0`` for the PPO key
        on algorithms that don't have a clip concept.
        """
        idx = self._update_counter
        self._policy_update_log.append(
            {
                "update": idx,
                "loss": float(loss),
                "kl": None if kl is None else float(kl),
                "entropy": None if entropy is None else float(entropy),
                "clip_fraction": (
                    None if clip_fraction is None else float(clip_fraction)
                ),
            }
        )
        self._emit_metric(_METRIC_POLICY_LOSS, loss, step=idx)
        self._emit_metric(_METRIC_POLICY_KL, kl, step=idx)
        self._emit_metric(_METRIC_POLICY_ENTROPY, entropy, step=idx)
        self._emit_metric(_METRIC_POLICY_CLIP, clip_fraction, step=idx)
        self._update_counter += 1

    def record_value_update(
        self,
        loss: float,
        *,
        explained_variance: Optional[float] = None,
    ) -> None:
        """Record a value-function update (on-policy actor-critic).

        Emits ``rl.value.loss`` plus ``rl.value.explained_variance``
        when the caller supplied it.
        """
        idx = max(self._update_counter - 1, 0)
        self._value_update_log.append(
            {
                "update": idx,
                "loss": float(loss),
                "explained_variance": (
                    None if explained_variance is None else float(explained_variance)
                ),
            }
        )
        self._emit_metric(_METRIC_VALUE_LOSS, loss, step=idx)
        self._emit_metric(
            _METRIC_VALUE_EXPLAINED_VARIANCE, explained_variance, step=idx
        )

    def record_q_update(
        self,
        loss: float,
        *,
        overestimation_gap: Optional[float] = None,
    ) -> None:
        """Record an off-policy Q-function update (DQN / SAC / TD3).

        Emits ``rl.q.loss`` plus ``rl.q.overestimation_gap`` only when
        the adapter computes a twin-Q gap (SAC / TD3); DQN passes
        ``None`` rather than hallucinate zero.
        """
        idx = max(self._update_counter - 1, 0)
        self._q_update_log.append(
            {
                "update": idx,
                "loss": float(loss),
                "overestimation_gap": (
                    None if overestimation_gap is None else float(overestimation_gap)
                ),
            }
        )
        self._emit_metric(_METRIC_Q_LOSS, loss, step=idx)
        self._emit_metric(_METRIC_Q_OVERESTIMATION, overestimation_gap, step=idx)

    def record_replay(self, size: int) -> None:
        """Record replay-buffer size at the current step."""
        idx = self._step_counter
        self._replay_log.append({"step": idx, "size": int(size)})
        self._emit_metric(_METRIC_REPLAY_SIZE, size, step=idx)
        self._step_counter += 1

    def record_eval_rollout(
        self,
        reward: float,
        length: int,
        *,
        deterministic: bool = True,
    ) -> None:
        """Record one evaluation rollout outcome (mean reward + length)."""
        idx = self._eval_counter
        self._eval_log.append(
            {
                "eval": idx,
                "reward": float(reward),
                "length": int(length),
                "deterministic": bool(deterministic),
            }
        )
        self._emit_metric(_METRIC_EVAL_REWARD, reward, step=idx)
        self._emit_metric(_METRIC_EVAL_LENGTH, length, step=idx)
        if not deterministic:
            # Spec §8.2.8 — stochastic eval emits a WARN so operators can
            # distinguish deterministic evals from sampled ones in
            # dashboard drill-down.
            logger.warning(
                "rldiagnostics.stochastic_eval_warning",
                extra={"rl_run_id": self.run_id, "rl_eval_index": idx},
            )
        self._eval_counter += 1

    # ── Stable-Baselines3 callback factory ─────────────────────────────────

    def as_sb3_callback(self) -> Any:
        """Return a Stable-Baselines3 ``BaseCallback`` wired to this session.

        The callback drives :meth:`record_episode` from
        ``Monitor``-wrapped episode info, :meth:`record_policy_update`
        from ``logger.name_to_value`` at ``_on_rollout_end``, and
        :meth:`record_replay` from ``self.model.replay_buffer`` when
        present (off-policy algorithms).

        Requires the ``[rl]`` extra.  Raises
        :class:`ImportError` naming the extra when SB3 is absent.

        The callback satisfies spec §7.1 MUST 3 and registers
        automatically when passed to ``model.learn(..., callback=...)``.
        """
        sb3 = _require_stable_baselines3()
        BaseCallback = sb3.common.callbacks.BaseCallback

        diag = self

        class _KailashRLCallback(BaseCallback):
            """SB3 BaseCallback that routes metrics into the parent ``diag``."""

            def __init__(self) -> None:
                super().__init__(verbose=0)
                self._last_reported_update = -1

            def _on_step(self) -> bool:  # noqa: D401 — SB3 interface
                # Episode completion signalled by Monitor wrapper's `infos`.
                infos = self.locals.get("infos") or []
                for info in infos:
                    episode = info.get("episode") if isinstance(info, dict) else None
                    if not episode:
                        continue
                    reward = float(episode.get("r", 0.0))
                    length = int(episode.get("l", 0))
                    diag.record_episode(reward=reward, length=length, info=info)
                # Replay buffer size for off-policy algos (SAC / DQN / TD3 / DDPG).
                buf = getattr(self.model, "replay_buffer", None)
                if buf is not None:
                    try:
                        size = (
                            int(buf.size())
                            if callable(getattr(buf, "size", None))
                            else int(getattr(buf, "pos", 0))
                        )
                    except Exception:  # noqa: BLE001 — defensive for mock buffers
                        size = 0
                    diag.record_replay(size=size)
                return True

            def _on_rollout_end(self) -> None:  # noqa: D401 — SB3 interface
                # SB3's BaseAlgorithm.logger.name_to_value holds the latest
                # train/* metrics; each algorithm's train() writes them
                # before `rollout/...` values land, so _on_rollout_end is
                # the earliest consistent read point.
                logger_obj = getattr(self.model, "logger", None)
                if logger_obj is None:
                    return
                values = getattr(logger_obj, "name_to_value", {}) or {}
                loss = values.get("train/policy_gradient_loss") or values.get(
                    "train/loss"
                )
                kl = values.get("train/approx_kl")
                entropy = values.get("train/entropy_loss")
                if entropy is not None:
                    # SB3 reports entropy_loss as the negative entropy term
                    # (coef * -H); we expose positive entropy so
                    # comparisons across algorithms are consistent.
                    entropy = -float(entropy)
                clip_fraction = values.get("train/clip_fraction")
                # Only emit a policy update when the rollout produced any
                # metric — avoids spurious zero-step rows for algorithms
                # whose logger is not yet populated.
                if loss is not None:
                    diag.record_policy_update(
                        loss=float(loss),
                        kl=None if kl is None else float(kl),
                        entropy=None if entropy is None else float(entropy),
                        clip_fraction=(
                            None if clip_fraction is None else float(clip_fraction)
                        ),
                    )
                value_loss = values.get("train/value_loss")
                explained_variance = values.get("train/explained_variance")
                if value_loss is not None:
                    diag.record_value_update(
                        loss=float(value_loss),
                        explained_variance=(
                            None
                            if explained_variance is None
                            else float(explained_variance)
                        ),
                    )
                q_loss = values.get("train/critic_loss") or values.get("train/q_loss")
                if q_loss is not None:
                    diag.record_q_update(loss=float(q_loss))

        return _KailashRLCallback()

    # ── Reporting ──────────────────────────────────────────────────────────

    def report(self) -> dict[str, Any]:
        """Return a severity-tagged diagnostic summary.

        Returns a dict with:

        - ``run_id`` — Protocol correlation id.
        - ``kind`` — literal ``"rl"``.
        - ``algo`` — the algorithm tag passed to the constructor.
        - ``metrics`` — dict of summary scalars (episode_reward_mean,
          episode_reward_peak, update_count, eval_reward_mean, ...).
        - ``findings`` — list of :class:`RLDiagnosticFinding` records,
          severity-tagged.  Empty when no issue is detected.

        Never raises on empty state.  The reward-collapse finding is
        emitted at CRIT severity matching classical RL's
        ``episode_reward_collapse`` + RLHF's reward-hacking signal per
        ``specs/ml-rl-align-unification.md §6`` — one dashboard alert
        filter catches both.
        """
        # Aggregate metrics — plain Python, no numpy dependency at import.
        if self._reward_window:
            reward_mean = sum(self._reward_window) / len(self._reward_window)
            reward_recent = self._reward_window[-1]
        else:
            reward_mean = None
            reward_recent = None
        eval_rewards = [r["reward"] for r in self._eval_log]
        eval_reward_mean = (
            sum(eval_rewards) / len(eval_rewards) if eval_rewards else None
        )
        metrics: dict[str, Any] = {
            "episode_count": self._episode_counter,
            "episode_reward_mean": reward_mean,
            "episode_reward_peak": self._peak_reward,
            "update_count": self._update_counter,
            "eval_count": self._eval_counter,
            "eval_reward_mean": eval_reward_mean,
            "replay_samples_observed": len(self._replay_log),
        }

        findings: list[RLDiagnosticFinding] = []
        # Reward collapse — spec §8.7 CRIT severity, matches RLHF
        # reward-hacking signal in kailash-align for dashboard parity.
        if (
            reward_recent is not None
            and reward_mean is not None
            and self._peak_reward is not None
            and len(self._reward_window) == self.window
            and self._peak_reward > 0.0
        ):
            drop_ratio = 1.0 - (reward_recent / self._peak_reward)
            below_peak = reward_recent / self._peak_reward
            if (
                drop_ratio >= self._collapse_drop_fraction
                and below_peak < self._collapse_peak_fraction
            ):
                findings.append(
                    RLDiagnosticFinding(
                        severity="CRIT",
                        category="episode_reward_collapse",
                        message=(
                            f"episode reward collapsed from peak "
                            f"{self._peak_reward:.2f} to {reward_recent:.2f} "
                            f"({below_peak * 100:.1f}% of peak) over last "
                            f"{self.window} episodes"
                        ),
                        suggestion=(
                            "reduce learning rate, check reward shaping, or "
                            "restore from last stable checkpoint"
                        ),
                    )
                )

        return {
            "run_id": self.run_id,
            "kind": "rl",
            "algo": self.algo,
            "metrics": metrics,
            "findings": [
                {
                    "severity": f.severity,
                    "category": f.category,
                    "message": f.message,
                    "suggestion": f.suggestion,
                }
                for f in findings
            ],
        }
