# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PPORLHFAdapter — PPO + reward-model bridge adapter.

Per ``specs/ml-rl-align-unification.md`` v1.0.0 §3 + §9, PPO-RLHF is
one of the v1-scope bridge adapters. This module wraps
``trl.PPOTrainer`` behind the :class:`RLLifecycleProtocol` contract so
``km.rl_train(algo="ppo-rlhf", ...)`` routes into this adapter.

Per spec §3.4 PPO-RLHF is the most metric-rich bridge adapter:
clip-fraction, KL-from-reference, explained-variance, rollout reward
are all live. The adapter emits the full canonical ``rl.rollout.step``,
``rl.train.update``, and ``rl.eval`` families to the ambient tracker.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, ClassVar, Literal, Optional

from kailash_align.rl_bridge._base import _BridgeAdapterBase

logger = logging.getLogger(__name__)

__all__ = ["PPORLHFAdapter"]


class PPORLHFAdapter(_BridgeAdapterBase):
    """PPO + reward-model RLHF adapter wrapping ``trl.PPOTrainer``.

    Parameters
    ----------
    policy
        Tunable policy (HuggingFace ``AutoModelForCausalLM``). Required.
    reward_model
        Reward-model used to score rollouts during training. Required.
    reference_model
        Frozen reference policy for the KL penalty. Required.
    hyperparameters
        Dict of TRL ``PPOConfig`` hyperparameters.
    device
        Optional :class:`kailash_ml.DeviceReport`.
    tenant_id
        Optional tenant scope.
    """

    name: ClassVar[str] = "ppo-rlhf"
    paradigm: ClassVar[Literal["on-policy", "off-policy", "offline", "rlhf"]] = "rlhf"
    buffer_kind: ClassVar[Literal["rollout", "replay", "dataset", "preference"]] = (
        "rollout"
    )

    def __init__(
        self,
        *,
        policy: Any = None,
        reward_model: Any = None,
        reference_model: Any = None,
        hyperparameters: Optional[dict[str, Any]] = None,
        device: Any = None,
        tenant_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        super().__init__(run_id=run_id, tenant_id=tenant_id, device=device)
        self._policy = policy
        self._reward_model = reward_model
        self._reference_model = reference_model
        self._hyperparameters = dict(hyperparameters or {})
        self._resume_from: Any = None

    # ------------------------------------------------------------------

    def build(self) -> None:
        """Construct the underlying ``trl.PPOTrainer`` via method_registry."""
        from kailash_align.method_registry import get_method

        method = get_method("ppo")

        try:
            trainer_cls = __import__(
                method.trainer_module, fromlist=[method.trainer_class_name]
            )
            PPOTrainer = getattr(trainer_cls, method.trainer_class_name)
            config_cls = __import__(
                method.config_module, fromlist=[method.config_class_name]
            )
            PPOConfig = getattr(config_cls, method.config_class_name)
        except (ImportError, AttributeError) as exc:
            raise ImportError(
                f"PPORLHFAdapter.build requires TRL PPOTrainer. "
                f"Install via 'pip install kailash-align[rl-bridge]' "
                f"(pulls trl>=1.0). Underlying error: {exc}"
            ) from exc

        trl_config = PPOConfig(**self._hyperparameters)
        self._trainer = PPOTrainer(
            model=self._policy,
            ref_model=self._reference_model,
            reward_model=self._reward_model,
            args=trl_config,
        )
        self._built = True
        logger.info(
            "rl_bridge.ppo_rlhf.build.ok",
            extra={
                "rl_algo": self.name,
                "rl_run_id": self.run_id,
                "tenant_id": self.tenant_id,
                "mode": "real",
            },
        )

    def learn(
        self,
        total_timesteps: int,
        *,
        callbacks: list[Any] | None = None,
        eval_env_fn: Callable[[], Any] | None = None,
        eval_freq: int = 0,
        n_eval_episodes: int = 0,
    ) -> Any:
        """Drive PPO training, emit the full ``rl.*`` metric family.

        PPO-RLHF is the metric-rich case per spec §3.4: clip-fraction,
        KL-from-reference, explained-variance, rollout reward are all
        available from TRL's log history. Each is remapped into the
        canonical ``rl.rollout.step.*`` / ``rl.train.update.*`` family.
        """
        from datetime import datetime, timezone

        from kailash_ml.rl._lineage import RLLineage
        from kailash_ml.rl.trainer import METRIC_KEYS, RLTrainingResult

        if not self._built:
            self.build()
        self._require_trainer("learn")

        start = time.perf_counter()
        train_output = self._trainer.train(
            resume_from_checkpoint=(
                str(self._resume_from) if self._resume_from else None
            ),
        )
        training_time = time.perf_counter() - start

        log_history = (
            getattr(getattr(self._trainer, "state", None), "log_history", []) or []
        )
        for step_idx, entry in enumerate(log_history):
            if not isinstance(entry, dict):
                continue
            step = int(entry.get("step", step_idx))
            for trl_key, rl_key in (
                # Rollout-side
                ("objective/reward", "rl.rollout.step.reward_mean"),
                ("objective/kl", "rl.rollout.step.kl_from_reference"),
                ("objective/non_score_reward", "rl.rollout.step.non_score_reward"),
                ("objective/entropy", "rl.rollout.step.entropy"),
                # Train-side
                ("loss/policy_avg", "rl.train.update.policy_loss"),
                ("loss/value_avg", "rl.train.update.value_loss"),
                ("policy/approxkl_avg", "rl.train.update.approx_kl"),
                ("policy/clipfrac_avg", "rl.train.update.clip_fraction"),
                ("val/explained_variance", "rl.train.update.explained_variance"),
            ):
                if trl_key in entry and entry[trl_key] is not None:
                    self.emit_metric(rl_key, float(entry[trl_key]), step=step)

        # Build parity-key metrics dict.
        metrics: dict[str, float | None] = {k: None for k in METRIC_KEYS}
        if log_history:
            # Harvest final-update values for the parity keys that apply.
            last = log_history[-1] if isinstance(log_history[-1], dict) else {}
            if "objective/reward" in last:
                metrics["reward_mean"] = float(last["objective/reward"])
            if "objective/kl" in last:
                metrics["kl"] = float(last["objective/kl"])
            if "policy/clipfrac_avg" in last:
                metrics["clip_frac"] = float(last["policy/clipfrac_avg"])
        metrics["training_time_seconds"] = training_time

        from kailash_align._version import __version__ as _align_version

        lineage = RLLineage(
            run_id=self.run_id,
            experiment_name=None,
            tenant_id=self.tenant_id,
            base_model_ref=getattr(self._policy, "name_or_path", None),
            reference_model_ref=getattr(self._reference_model, "name_or_path", None),
            reward_model_ref=getattr(self._reward_model, "name_or_path", None),
            dataset_ref=None,
            env_spec="text:rollouts",
            algorithm=self.name,
            paradigm=self.paradigm,
            parent_run_id=None,
            sdk_source="kailash-align",
            sdk_version=_align_version,
            created_at=datetime.now(timezone.utc),
        )

        result = RLTrainingResult(
            policy_name=getattr(self._policy, "name_or_path", self.name),
            algorithm=self.name,
            total_timesteps=int(total_timesteps),
            mean_reward=float(metrics.get("reward_mean") or 0.0),
            std_reward=0.0,
            training_time_seconds=training_time,
            metrics=metrics,
            env_name="text:rollouts",
            lineage=lineage,
            device=self.device,
        )
        logger.info(
            "rl_bridge.ppo_rlhf.learn.ok",
            extra={
                "rl_algo": self.name,
                "rl_run_id": self.run_id,
                "rl_training_time_s": training_time,
                "tenant_id": self.tenant_id,
                "mode": "real",
            },
        )
        return result
