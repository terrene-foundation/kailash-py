# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""RLTrainer — Stable-Baselines3 wrapper for the RL training lifecycle.

Per W29:

* Manager-shape class (`rules/facade-manager-detection.md`): wiring-test
  required (see ``tests/integration/test_rl_trainer_wiring.py``).
* Cross-algorithm ``RLTrainingResult`` parity: every run populates a
  metrics dict with ``reward_mean``, ``reward_std``, ``ep_len_mean``,
  ``ep_len_std``, ``kl``, and ``clip_frac``; non-applicable metrics
  surface as ``None`` with a documented reason rather than hallucinated
  zeros (``rules/zero-tolerance.md`` Rule 2).
* Error hierarchy: every failure path raises from :mod:`kailash_ml.errors`
  (W29 invariant #7).

The substrate is Stable-Baselines3 + Gymnasium (Decision 8 carve-out —
RL is NOT Lightning-routed). The imports are all local inside methods so
``from kailash_ml.rl.trainer import RLTrainer`` works without the ``[rl]``
extra installed; tests without ``[rl]`` can still exercise import guards.

Requires ``pip install kailash-ml[rl]`` (stable-baselines3, gymnasium).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kailash_ml._device_report import DeviceReport
from kailash_ml._result import TrainingResult
from kailash_ml.errors import RLError
from kailash_ml.rl._lineage import RLLineage
from kailash_ml.rl._records import EpisodeRecord, EvalRecord
from kailash_ml.rl.protocols import PolicyArtifactRef

logger = logging.getLogger(__name__)

__all__ = [
    "RLTrainer",
    "RLTrainingConfig",
    "RLTrainingResult",
    "METRIC_KEYS",
]


# --- Cross-algorithm metric parity (W29 invariant #4) ----------------------

# Every RLTrainingResult.metrics MUST expose exactly these keys. Values
# that are not applicable to the algorithm surface as ``None``; non-finite
# values are BLOCKED by the adapter's callback.
METRIC_KEYS: tuple[str, ...] = (
    "reward_mean",
    "reward_std",
    "ep_len_mean",
    "ep_len_std",
    "kl",
    "clip_frac",
)


# --- Configuration + result dataclasses -----------------------------------


@dataclass
class RLTrainingConfig:
    """Configuration for RL training."""

    algorithm: str = "PPO"
    policy_type: str = "MlpPolicy"
    total_timesteps: int = 100_000
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    n_eval_episodes: int = 10
    eval_freq: int = 10_000
    seed: int | None = 42
    verbose: int = 0
    save_path: str | Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "policy_type": self.policy_type,
            "total_timesteps": self.total_timesteps,
            "hyperparameters": self.hyperparameters,
            "n_eval_episodes": self.n_eval_episodes,
            "eval_freq": self.eval_freq,
            "seed": self.seed,
        }


@dataclass
class RLTrainingResult:
    """Result of an RL training run — RL specialisation of :class:`TrainingResult`.

    Per ``specs/ml-rl-core.md`` §3.2 the canonical declaration is
    ``RLTrainingResult ⊂ TrainingResult`` (subset relationship). This
    dataclass realises the subset relationship by mirroring the
    :class:`~kailash_ml._result.TrainingResult` field surface (``model_uri``,
    ``metrics``, ``device_used``, ``accelerator``, ``precision``,
    ``elapsed_seconds``, ``tracker_run_id``, ``tenant_id``,
    ``artifact_uris``, ``lightning_trainer_config``) AND adds the
    RL-specific spec §3.2 fields:

    * ``algorithm``, ``env_spec``, ``total_timesteps``
    * ``episode_reward_mean``, ``episode_reward_std``,
      ``episode_length_mean``
    * ``policy_entropy``, ``value_loss``, ``kl_divergence``,
      ``explained_variance`` (None when not applicable to the algorithm)
    * ``replay_buffer_size`` (off-policy only)
    * ``total_env_steps``
    * ``episodes`` (list[EpisodeRecord]) — non-empty at training end
    * ``eval_history`` (list[EvalRecord]) — non-empty when
      ``eval_freq <= total_timesteps``
    * ``policy_artifact`` (PolicyArtifactRef) — path + SHA + algo

    The dataclass is intentionally NOT frozen so the W30 lineage
    population path (``result.lineage = _build_lineage(...)``) keeps
    working until those call-sites are migrated to construct the
    lineage upfront. A future major release MAY tighten to
    ``frozen=True`` once all construction sites populate every field at
    the call.

    The ``metrics`` dict carries the W29 invariant #4 keys:
    ``reward_mean``, ``reward_std``, ``ep_len_mean``, ``ep_len_std``,
    ``kl``, ``clip_frac``. Metrics not applicable to the algorithm are
    ``None`` (never hallucinated zero — per zero-tolerance Rule 2).
    """

    # --- Spec §3.2 RL-specific required fields ----------------------------
    algorithm: str = ""
    env_spec: str = ""
    total_timesteps: int = 0
    episode_reward_mean: float = 0.0
    episode_reward_std: float = 0.0
    episode_length_mean: float = 0.0
    total_env_steps: int = 0

    # --- Spec §3.2 RL-specific optional fields (None when N/A) ------------
    policy_entropy: float | None = None
    value_loss: float | None = None
    kl_divergence: float | None = None
    explained_variance: float | None = None
    replay_buffer_size: int | None = None

    # --- TrainingResult-mirrored fields (inherited surface per §3.2) ------
    # ``metrics`` — required cross-SDK metric dict.
    metrics: dict[str, float | None] = field(default_factory=dict)
    # Mirrors of ``TrainingResult`` core fields. Defaults are present so
    # existing positional callers (kailash-align bridge adapters, tests)
    # continue to construct without breakage; the W6-015 sweep populates
    # them at every site.
    model_uri: str = ""
    device_used: str = ""
    accelerator: str = ""
    precision: str = ""
    elapsed_seconds: float = 0.0
    tracker_run_id: str | None = None
    tenant_id: str | None = None
    artifact_uris: dict[str, str] = field(default_factory=dict)
    lightning_trainer_config: dict[str, Any] = field(default_factory=dict)

    # --- RL-specific records + lineage (existing surface) -----------------
    episodes: list[EpisodeRecord] = field(default_factory=list)
    eval_history: list[EvalRecord] = field(default_factory=list)
    policy_artifact: PolicyArtifactRef | None = None
    reward_curve: list[tuple[int, float]] = field(default_factory=list)
    # Cross-SDK Protocol fields per ``specs/ml-rl-align-unification.md``
    # §3.2 (result parity) + §5 (lineage). Both default to ``None`` so
    # existing classical callers continue to work unmodified.
    lineage: RLLineage | None = None
    device: DeviceReport | None = None

    # --- Backwards-compat fields preserved through the W6-015 refactor ----
    # Pre-1.2.0 callers passed ``policy_name`` / ``mean_reward`` /
    # ``std_reward`` / ``training_time_seconds`` / ``artifact_path`` /
    # ``env_name`` positionally or as kwargs. Properties below preserve
    # the read-side surface; the kwargs are accepted by ``__init__``
    # via the explicit alias declarations and resolved in __post_init__.
    policy_name: str = ""
    artifact_path: str | None = None

    # Aliased kwargs — accepted through ``__init__`` via the explicit
    # field declarations below and resolved into the canonical
    # ``episode_reward_mean`` / ``episode_reward_std`` /
    # ``elapsed_seconds`` / ``env_spec`` fields by ``__post_init__``.
    # Spec-rename evidence: spec §3.2 mandates
    # ``episode_reward_mean`` (not ``mean_reward``).
    mean_reward: float | None = None
    std_reward: float | None = None
    training_time_seconds: float | None = None
    env_name: str | None = None

    def __post_init__(self) -> None:
        # Backwards-compat: callers that constructed the pre-1.2.0
        # ``RLTrainingResult(mean_reward=..., std_reward=...,
        # training_time_seconds=..., env_name=...)`` keep working — the
        # legacy kwargs win when the canonical kwarg was left at the
        # zero default.
        if self.mean_reward is not None and self.episode_reward_mean == 0.0:
            object.__setattr__(self, "episode_reward_mean", float(self.mean_reward))
        if self.std_reward is not None and self.episode_reward_std == 0.0:
            object.__setattr__(self, "episode_reward_std", float(self.std_reward))
        if self.training_time_seconds is not None and self.elapsed_seconds == 0.0:
            object.__setattr__(
                self, "elapsed_seconds", float(self.training_time_seconds)
            )
        if self.env_name is not None and not self.env_spec:
            object.__setattr__(self, "env_spec", str(self.env_name))
        # Ensure the back-compat read-side properties below see a
        # non-None value once normalisation completed.
        if self.mean_reward is None:
            object.__setattr__(self, "mean_reward", self.episode_reward_mean)
        if self.std_reward is None:
            object.__setattr__(self, "std_reward", self.episode_reward_std)
        if self.training_time_seconds is None:
            object.__setattr__(self, "training_time_seconds", self.elapsed_seconds)
        if self.env_name is None:
            object.__setattr__(self, "env_name", self.env_spec)

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "env_spec": self.env_spec,
            "total_timesteps": self.total_timesteps,
            "episode_reward_mean": self.episode_reward_mean,
            "episode_reward_std": self.episode_reward_std,
            "episode_length_mean": self.episode_length_mean,
            "total_env_steps": self.total_env_steps,
            "policy_entropy": self.policy_entropy,
            "value_loss": self.value_loss,
            "kl_divergence": self.kl_divergence,
            "explained_variance": self.explained_variance,
            "replay_buffer_size": self.replay_buffer_size,
            "metrics": dict(self.metrics),
            "model_uri": self.model_uri,
            "device_used": self.device_used,
            "accelerator": self.accelerator,
            "precision": self.precision,
            "elapsed_seconds": self.elapsed_seconds,
            "tracker_run_id": self.tracker_run_id,
            "tenant_id": self.tenant_id,
            "artifact_uris": dict(self.artifact_uris),
            "lightning_trainer_config": dict(self.lightning_trainer_config),
            "episodes": [
                {
                    "episode_index": ep.episode_index,
                    "reward": ep.reward,
                    "length": ep.length,
                    "timestamp": ep.timestamp.isoformat(),
                }
                for ep in self.episodes
            ],
            "eval_history": [
                {
                    "eval_step": ev.eval_step,
                    "mean_reward": ev.mean_reward,
                    "std_reward": ev.std_reward,
                    "mean_length": ev.mean_length,
                    "success_rate": ev.success_rate,
                    "n_episodes": ev.n_episodes,
                    "timestamp": ev.timestamp.isoformat(),
                }
                for ev in self.eval_history
            ],
            "policy_artifact": (
                {
                    "path": str(self.policy_artifact.path),
                    "sha": self.policy_artifact.sha,
                    "algorithm": self.policy_artifact.algorithm,
                    "policy_class": self.policy_artifact.policy_class,
                    "created_at": self.policy_artifact.created_at.isoformat(),
                    "tenant_id": self.policy_artifact.tenant_id,
                }
                if self.policy_artifact is not None
                else None
            ),
            "reward_curve": list(self.reward_curve),
            "lineage": self.lineage.to_dict() if self.lineage is not None else None,
            "device": self.device.as_log_extra() if self.device is not None else None,
            # Back-compat read-side keys
            "policy_name": self.policy_name,
            "artifact_path": self.artifact_path,
            "mean_reward": self.episode_reward_mean,
            "std_reward": self.episode_reward_std,
            "training_time_seconds": self.elapsed_seconds,
            "env_name": self.env_spec,
        }


# --- Spec §3.2 typed-field extraction helpers -----------------------------


def _extract_logger_metric(model: Any, key: str) -> float | None:
    """Read a finite float from the SB3 backend logger.

    Returns ``None`` when the key is absent / non-finite — mirrors the
    spec §3.2 invariant 3 ("MAY be ``None`` when not applicable; MUST NOT
    be hallucinated zero").
    """
    import math

    src = getattr(getattr(model, "logger", None), "name_to_value", {}) or {}
    if key not in src:
        return None
    try:
        val = float(src[key])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val):
        return None
    return val


def _safe_replay_buffer_size(model: Any) -> int | None:
    """Return ``len(model.replay_buffer)`` for off-policy algos, else None.

    Off-policy SB3 algorithms (DQN/SAC/TD3/DDPG) expose a
    ``replay_buffer`` attribute with ``size()`` or ``__len__``.
    On-policy algorithms (PPO/A2C/TRPO) do NOT — return ``None`` per
    spec §3.2.
    """
    rb = getattr(model, "replay_buffer", None)
    if rb is None:
        return None
    if hasattr(rb, "size") and callable(rb.size):
        try:
            return int(rb.size())
        except Exception:  # pragma: no cover - defensive
            return None
    try:
        return int(len(rb))
    except Exception:  # pragma: no cover - defensive
        return None


def _build_episode_records(model: Any) -> list[EpisodeRecord]:
    """Snapshot the SB3 ``ep_info_buffer`` into typed EpisodeRecord rows.

    Per spec §3.2 invariant 1 — every ``rl_train()`` call that runs at
    least one complete rollout MUST populate ``episodes`` non-empty. If
    the SB3 buffer is empty (very short runs), the list is also empty
    and the caller's evaluation rollout is the only behavioural signal
    in the result. The caller is responsible for filtering / fail-fast
    per the same spec invariant.
    """
    buf = getattr(model, "ep_info_buffer", None)
    if buf is None:
        return []
    out: list[EpisodeRecord] = []
    now = datetime.now(timezone.utc)
    for idx, ep in enumerate(buf):
        try:
            reward = float(ep["r"])
            length = int(ep["l"])
        except (KeyError, TypeError, ValueError):  # pragma: no cover - defensive
            continue
        out.append(
            EpisodeRecord(
                episode_index=idx,
                reward=reward,
                length=length,
                timestamp=now,
            )
        )
    return out


def _build_policy_artifact_ref(
    *,
    algorithm: str,
    artifact_path: Path | None,
    tenant_id: str | None,
    policy: Any,
) -> PolicyArtifactRef | None:
    """Construct a :class:`PolicyArtifactRef` for the saved SB3 model.

    Per spec §3.2 — every successful run MUST populate
    ``policy_artifact`` with path + SHA + algorithm so the registry +
    lineage layers can fingerprint the artifact without re-reading the
    .zip from disk. ``None`` only when ``artifact_path`` is missing
    (e.g. user passed ``save_path=None`` AND model save failed silently).
    """
    if artifact_path is None:
        return None
    import hashlib

    artifact_dir = Path(artifact_path).parent
    # SB3's ``model.save("…/model")`` writes ``…/model.zip``. Hash the
    # zip if it exists; fall back to the path string fingerprint.
    zip_path = artifact_dir / "model.zip"
    target = zip_path if zip_path.exists() else Path(str(artifact_path))
    try:
        sha = hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError:  # pragma: no cover - defensive (file removed mid-call)
        sha = hashlib.sha256(str(target).encode()).hexdigest()

    if isinstance(policy, str):
        policy_class = f"stable_baselines3.common.policies.{policy}"
    else:
        policy_class = (
            f"{type(policy).__module__}.{type(policy).__name__}"
            if policy is not None
            else "unknown"
        )

    return PolicyArtifactRef(
        path=Path(str(artifact_path)),
        sha=sha,
        algorithm=algorithm,
        policy_class=policy_class,
        created_at=datetime.now(timezone.utc),
        tenant_id=tenant_id,
    )


# --- Metric-capture callback ----------------------------------------------


def _make_callback() -> Any:
    """Construct a ``stable_baselines3.common.callbacks.BaseCallback``.

    Kept as a lazy factory so ``kailash_ml.rl.trainer`` imports without
    SB3 installed. The callback samples the backend logger after each
    rollout + each eval and stores the metrics on ``self.snapshot`` so
    ``RLTrainer.train`` can write them into the ``RLTrainingResult``.
    """
    try:
        from stable_baselines3.common.callbacks import BaseCallback
    except ImportError as exc:  # pragma: no cover - exercised only without [rl]
        raise ImportError(
            "stable-baselines3 is required for RL. "
            "Install with: pip install kailash-ml[rl]"
        ) from exc

    class _KailashRLCallback(BaseCallback):  # type: ignore[misc]
        """Capture the canonical RL metrics from the backend logger."""

        def __init__(self) -> None:
            super().__init__(verbose=0)
            self.snapshot: dict[str, float | None] = {k: None for k in METRIC_KEYS}
            self.reward_curve: list[tuple[int, float]] = []

        def _on_step(self) -> bool:  # pragma: no cover — trivial
            return True

        def _capture(self) -> None:
            """Copy metrics from the backend logger + ep_info_buffer.

            SB3 logs metrics via ``self.logger.name_to_value`` but these
            are dumped AFTER ``_on_rollout_end`` fires for on-policy
            algorithms. As a belt-and-braces signal, we also read
            ``self.model.ep_info_buffer`` which is the deque of completed
            episode (reward, length) pairs — populated immediately.

            Metric keys differ per algorithm:
            * ``rollout/ep_rew_mean`` + ``rollout/ep_len_mean`` — all algos
            * ``train/approx_kl`` — PPO, TRPO, SAC (entropy coef)
            * ``train/clip_fraction`` — PPO
            """
            import math

            src = getattr(self.logger, "name_to_value", {}) or {}

            def _get(key: str) -> float | None:
                if key not in src:
                    return None
                try:
                    val = float(src[key])
                except (TypeError, ValueError):
                    return None
                if not math.isfinite(val):
                    return None
                return val

            # Prefer the episode-info buffer (populated immediately on
            # episode completion); fall back to the logger (populated on
            # dump which is after _on_rollout_end for PPO).
            rew_mean = _get("rollout/ep_rew_mean")
            len_mean = _get("rollout/ep_len_mean")
            rew_std: float | None = None
            len_std: float | None = None
            buf = getattr(getattr(self, "model", None), "ep_info_buffer", None)
            if buf is not None and len(buf) > 0:
                try:
                    import numpy as np

                    rewards = np.array([float(ep["r"]) for ep in buf if "r" in ep])
                    lengths = np.array([float(ep["l"]) for ep in buf if "l" in ep])
                    if rewards.size > 0 and np.isfinite(rewards).all():
                        rew_mean = float(np.mean(rewards))
                        rew_std = float(np.std(rewards))
                    if lengths.size > 0 and np.isfinite(lengths).all():
                        len_mean = float(np.mean(lengths))
                        len_std = float(np.std(lengths))
                except Exception:  # pragma: no cover - defensive
                    pass

            if rew_mean is not None:
                self.snapshot["reward_mean"] = rew_mean
                self.reward_curve.append((int(self.num_timesteps), rew_mean))
            if rew_std is not None:
                self.snapshot["reward_std"] = rew_std
            if len_mean is not None:
                self.snapshot["ep_len_mean"] = len_mean
            if len_std is not None:
                self.snapshot["ep_len_std"] = len_std
            if (kl := _get("train/approx_kl")) is not None:
                self.snapshot["kl"] = kl
            if (clip := _get("train/clip_fraction")) is not None:
                self.snapshot["clip_frac"] = clip

        def _on_rollout_end(self) -> None:  # pragma: no cover — SB3-internal
            self._capture()

        def _on_training_end(self) -> None:  # pragma: no cover — SB3-internal
            self._capture()

    return _KailashRLCallback()


# --- Trainer --------------------------------------------------------------


class RLTrainer:
    """Reinforcement learning trainer wrapping Stable-Baselines3.

    Manager-shape class per ``rules/facade-manager-detection.md``. The
    trainer takes explicit ``env_registry`` + ``policy_registry`` so the
    framework dependency is visible at construction (no global lookups).

    Parameters
    ----------
    env_registry:
        EnvironmentRegistry for resolving environment names.
    policy_registry:
        PolicyRegistry for storing trained policies + reward functions.
    root_dir:
        Root directory for saving model artifacts.
    """

    def __init__(
        self,
        env_registry: Any | None = None,
        policy_registry: Any | None = None,
        *,
        root_dir: str | Path = ".kailash_ml/rl_artifacts",
        tenant_id: str | None = None,
    ) -> None:
        self._env_registry = env_registry
        self._policy_registry = policy_registry
        self._root = Path(root_dir)
        self._tenant_id = tenant_id

    # ------------------------------------------------------------------

    def train(
        self,
        env_name: str,
        policy_name: str,
        config: RLTrainingConfig | None = None,
    ) -> RLTrainingResult:
        """Train an RL agent on the given environment.

        Parameters
        ----------
        env_name:
            Gymnasium environment name (e.g. ``"CartPole-v1"``).
        policy_name:
            Name under which the trained policy is registered.
        config:
            Training configuration. Uses defaults if ``None``.

        Returns
        -------
        RLTrainingResult
            Populated with the W29 metric-parity keys.
        """
        config = config or RLTrainingConfig()
        env = self._make_env(env_name)

        try:
            from kailash_ml.rl.algorithms import load_adapter_class
        except ImportError:  # pragma: no cover — keeps import path clear
            raise

        adapter_cls = load_adapter_class(config.algorithm)
        hp = dict(config.hyperparameters)
        hp.setdefault("verbose", config.verbose)

        adapter = adapter_cls(
            env=env,
            policy=config.policy_type,
            hyperparameters=hp,
            seed=config.seed,
            tenant_id=self._tenant_id,
        )
        callback = _make_callback()

        logger.info(
            "rl_trainer.train.start",
            extra={
                "algorithm": config.algorithm,
                "env": env_name,
                "total_timesteps": config.total_timesteps,
                "policy_name": policy_name,
                "tenant_id": self._tenant_id,
                "mode": "real",
            },
        )

        start = time.perf_counter()
        try:
            model = adapter.learn(config.total_timesteps, callback=callback)
        except Exception as exc:
            logger.exception(
                "rl_trainer.train.error",
                extra={
                    "algorithm": config.algorithm,
                    "env": env_name,
                    "tenant_id": self._tenant_id,
                },
            )
            raise RLError(
                reason="train_failed",
                algorithm=config.algorithm,
                env=env_name,
                cause=str(exc),
                tenant_id=self._tenant_id,
            ) from exc
        training_time = time.perf_counter() - start

        mean_reward, std_reward = self._evaluate(model, env, config.n_eval_episodes)
        artifact_path = self._save_model(model, adapter, policy_name, config)

        # Metrics parity — every RLTrainingResult carries the full key set;
        # missing keys default to None (W29 invariant #4).
        metrics = dict(callback.snapshot)
        # reward_mean / ep_len_mean may be missing for very short runs;
        # fall back to the evaluation mean/std which are always populated.
        if metrics.get("reward_mean") is None:
            metrics["reward_mean"] = mean_reward
        metrics["reward_std"] = std_reward
        for required in METRIC_KEYS:
            metrics.setdefault(required, None)

        # W6-015: extract typed RL fields from the captured metrics +
        # SB3 model state per ``specs/ml-rl-core.md`` §3.2 invariants.
        # ``policy_entropy`` / ``value_loss`` / ``kl_divergence`` /
        # ``explained_variance`` / ``replay_buffer_size`` MAY be ``None``
        # when not applicable to the algorithm; they MUST NOT be
        # hallucinated zero (`rules/zero-tolerance.md` Rule 2).
        episode_length_mean = metrics.get("ep_len_mean") or 0.0
        kl_divergence = metrics.get("kl")
        policy_entropy = _extract_logger_metric(model, "train/entropy_loss")
        value_loss = _extract_logger_metric(model, "train/value_loss")
        explained_variance = _extract_logger_metric(model, "train/explained_variance")
        replay_buffer_size = _safe_replay_buffer_size(model)
        total_env_steps = int(getattr(model, "num_timesteps", config.total_timesteps))

        # Build typed episode + policy-artifact records per spec §3.2
        # ("episodes MUST be non-empty at training end").
        episodes_list = _build_episode_records(model)
        policy_artifact_ref = _build_policy_artifact_ref(
            algorithm=config.algorithm,
            artifact_path=artifact_path,
            tenant_id=self._tenant_id,
            policy=getattr(adapter, "policy", config.policy_type),
        )

        result = RLTrainingResult(
            algorithm=config.algorithm,
            env_spec=env_name,
            total_timesteps=config.total_timesteps,
            episode_reward_mean=float(mean_reward),
            episode_reward_std=float(std_reward),
            episode_length_mean=float(episode_length_mean),
            total_env_steps=total_env_steps,
            policy_entropy=policy_entropy,
            value_loss=value_loss,
            kl_divergence=kl_divergence,
            explained_variance=explained_variance,
            replay_buffer_size=replay_buffer_size,
            metrics=metrics,
            elapsed_seconds=float(training_time),
            tenant_id=self._tenant_id,
            artifact_uris=(
                {"sb3": str(artifact_path)} if artifact_path is not None else {}
            ),
            episodes=episodes_list,
            policy_artifact=policy_artifact_ref,
            reward_curve=list(callback.reward_curve),
            # Back-compat kwargs (resolved by __post_init__):
            policy_name=policy_name,
            artifact_path=str(artifact_path) if artifact_path else None,
        )

        if self._policy_registry is not None:
            self._register_trained(policy_name, result, config)

        try:
            env.close()
        except Exception:  # pragma: no cover — cleanup path
            logger.warning(
                "rl_trainer.env_close_failed",
                extra={"env": env_name, "tenant_id": self._tenant_id},
            )

        logger.info(
            "rl_trainer.train.ok",
            extra={
                "algorithm": config.algorithm,
                "env": env_name,
                "mean_reward": mean_reward,
                "training_time_s": training_time,
                "tenant_id": self._tenant_id,
            },
        )
        return result

    # ------------------------------------------------------------------

    def evaluate(
        self,
        model: Any,
        env_name: str,
        n_episodes: int = 10,
    ) -> tuple[float, float]:
        """Evaluate a trained model on an environment."""
        env = self._make_env(env_name)
        try:
            return self._evaluate(model, env, n_episodes)
        finally:
            try:
                env.close()
            except Exception:  # pragma: no cover
                pass

    def load_and_evaluate(
        self,
        policy_name: str,
        env_name: str,
        version: int | None = None,
        n_episodes: int = 10,
    ) -> tuple[float, float]:
        """Load a policy from the registry and evaluate it."""
        if self._policy_registry is None:
            raise RLError(reason="policy_registry_required", op="load_and_evaluate")
        model = self._policy_registry.load_model(policy_name, version)
        return self.evaluate(model, env_name, n_episodes)

    # ------------------------------------------------------------------

    def _make_env(self, env_name: str) -> Any:
        """Resolve an environment via the registry, falling back to gym."""
        if self._env_registry is not None and env_name in self._env_registry:
            return self._env_registry.make(env_name)
        try:
            import gymnasium as gym
        except ImportError as exc:
            raise ImportError(
                "gymnasium is required for RL. "
                "Install with: pip install kailash-ml[rl]"
            ) from exc
        try:
            return gym.make(env_name)
        except Exception as exc:
            raise RLError(
                reason="env_not_resolvable",
                env_name=env_name,
                tenant_id=self._tenant_id,
                cause=str(exc),
            ) from exc

    @staticmethod
    def _evaluate(model: Any, env: Any, n_episodes: int) -> tuple[float, float]:
        """Run evaluation episodes and return ``(mean_reward, std_reward)``."""
        import numpy as np

        rewards: list[float] = []
        for _ in range(n_episodes):
            obs, _info = env.reset()
            episode_reward = 0.0
            done = False
            while not done:
                action, _ = model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, _info = env.step(action)
                episode_reward += float(reward)
                done = terminated or truncated
            rewards.append(episode_reward)

        if not rewards:
            return 0.0, 0.0
        return float(np.mean(rewards)), float(np.std(rewards))

    def _save_model(
        self,
        model: Any,
        adapter: Any,
        policy_name: str,
        config: RLTrainingConfig,
    ) -> Path | None:
        """Persist the trained model; returns the saved path."""
        save_dir = config.save_path or self._root / policy_name
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        model_path = save_dir / "model"
        try:
            model.save(str(model_path))
        except Exception as exc:
            raise RLError(
                reason="model_save_failed",
                policy_name=policy_name,
                path=str(model_path),
                cause=str(exc),
                tenant_id=self._tenant_id,
            ) from exc
        logger.info(
            "rl_trainer.save.ok",
            extra={
                "policy_name": policy_name,
                "artifact_path": str(model_path),
                "tenant_id": self._tenant_id,
            },
        )
        return model_path

    def _register_trained(
        self,
        policy_name: str,
        result: RLTrainingResult,
        config: RLTrainingConfig,
    ) -> None:
        from kailash_ml.rl.policies import PolicySpec, PolicyVersion

        # Register a spec if one doesn't exist so future load_model works.
        if self._policy_registry.get_spec(policy_name) is None:
            spec = PolicySpec(
                name=policy_name,
                algorithm=config.algorithm,
                policy_type=config.policy_type,
                hyperparameters=dict(config.hyperparameters),
            )
            self._policy_registry.register_spec(spec)
        versions = self._policy_registry.list_versions(policy_name)
        next_version = max((v.version for v in versions), default=0) + 1
        pv = PolicyVersion(
            name=policy_name,
            version=next_version,
            algorithm=config.algorithm,
            artifact_path=result.artifact_path or "",
            # W6-015: prefer canonical spec §3.2 names (`episode_reward_mean`
            # / `episode_reward_std` / `env_spec`) over the back-compat
            # aliases. PolicyVersion's own field names retain the legacy
            # `mean_reward` / `std_reward` shape for cross-SDK parity.
            mean_reward=result.episode_reward_mean,
            std_reward=result.episode_reward_std,
            total_timesteps=result.total_timesteps,
            metadata={
                **config.to_dict(),
                "env_spec": result.env_spec,
                "metrics": dict(result.metrics),
            },
        )
        self._policy_registry.register_version(pv)

    @staticmethod
    def supported_algorithms() -> list[str]:
        """Return the list of supported algorithm names.

        Delegates to the adapter registry so the list stays in sync with
        the actual adapter layer.
        """
        from kailash_ml.rl.algorithms import supported_algorithm_names

        return supported_algorithm_names()
