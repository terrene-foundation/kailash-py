# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""OnlineDPOAdapter — online Direct Preference Optimization bridge.

Per ``specs/ml-rl-align-unification.md`` v1.0.0 §3 + §9, Online-DPO is
a v1-scope bridge adapter. Wraps ``trl.OnlineDPOTrainer`` behind
:class:`RLLifecycleProtocol` so ``km.rl_train(algo="online-dpo", ...)``
routes through the bridge.

Unlike offline DPO (``dpo``) which trains on a pre-collected
preference dataset, Online-DPO generates completions on the fly and
uses pairwise preferences derived from a judge / reward-model.
Per spec §3.4b it typically uses ``sampling_temperature=0.9`` for
diverse completions; this adapter keeps that distinct from
``ref_temperature`` (log-prob extraction).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, ClassVar, Literal, Optional

from kailash_align.rl_bridge._base import _BridgeAdapterBase

logger = logging.getLogger(__name__)

__all__ = ["OnlineDPOAdapter"]


class OnlineDPOAdapter(_BridgeAdapterBase):
    """Online-DPO adapter wrapping ``trl.OnlineDPOTrainer``.

    Parameters
    ----------
    policy, reference_model
        Tunable + frozen reference policies (HuggingFace
        ``AutoModelForCausalLM``).
    reward_model
        Optional — used to score on-the-fly generated pairs when a
        human / judge is not available.
    prompt_dataset
        Prompt-only HuggingFace dataset.
    hyperparameters
        TRL ``OnlineDPOConfig`` hyperparameters.
    ref_temperature
        Log-prob extraction temperature. Default ``1.0``.
    sampling_temperature
        Generation sampling temperature. Default ``0.9`` — Online-DPO's
        canonical value for diverse on-the-fly completions. Per spec
        §3.4b this MUST stay distinct from ``ref_temperature``.
    """

    name: ClassVar[str] = "online-dpo"
    paradigm: ClassVar[Literal["on-policy", "off-policy", "offline", "rlhf"]] = "rlhf"
    buffer_kind: ClassVar[Literal["rollout", "replay", "dataset", "preference"]] = (
        "preference"
    )

    def __init__(
        self,
        *,
        policy: Any = None,
        reference_model: Any = None,
        reward_model: Any = None,
        prompt_dataset: Any = None,
        hyperparameters: Optional[dict[str, Any]] = None,
        device: Any = None,
        tenant_id: Optional[str] = None,
        ref_temperature: float = 1.0,
        sampling_temperature: float = 0.9,
        run_id: Optional[str] = None,
    ) -> None:
        super().__init__(run_id=run_id, tenant_id=tenant_id, device=device)

        if not isinstance(ref_temperature, (int, float)) or ref_temperature <= 0:
            raise ValueError(
                f"OnlineDPOAdapter.ref_temperature must be a positive number "
                f"(got {ref_temperature!r})"
            )
        if (
            not isinstance(sampling_temperature, (int, float))
            or sampling_temperature < 0
        ):
            raise ValueError(
                f"OnlineDPOAdapter.sampling_temperature must be a non-negative "
                f"number (got {sampling_temperature!r})"
            )

        self._policy = policy
        self._reference_model = reference_model
        self._reward_model = reward_model
        self._prompt_dataset = prompt_dataset
        self._hyperparameters = dict(hyperparameters or {})
        self.ref_temperature = float(ref_temperature)
        self.sampling_temperature = float(sampling_temperature)
        self._resume_from: Any = None

    def build(self) -> None:
        from kailash_align.method_registry import get_method

        method = get_method("online_dpo")
        if self._prompt_dataset is not None:
            method.dataset_validator(self._prompt_dataset)

        try:
            trainer_cls = __import__(
                method.trainer_module, fromlist=[method.trainer_class_name]
            )
            OnlineDPOTrainer = getattr(trainer_cls, method.trainer_class_name)
            config_cls = __import__(
                method.config_module, fromlist=[method.config_class_name]
            )
            OnlineDPOConfig = getattr(config_cls, method.config_class_name)
        except (ImportError, AttributeError) as exc:
            raise ImportError(
                f"OnlineDPOAdapter.build requires TRL OnlineDPOTrainer. "
                f"Install via 'pip install kailash-align[rl-bridge]' "
                f"(pulls trl>=1.0). Underlying error: {exc}"
            ) from exc

        config_kwargs = {**self._hyperparameters}
        config_kwargs.setdefault("temperature", self.sampling_temperature)
        trl_config = OnlineDPOConfig(**config_kwargs)

        trainer_kwargs = {
            "model": self._policy,
            "ref_model": self._reference_model,
            "args": trl_config,
            "train_dataset": self._prompt_dataset,
        }
        if self._reward_model is not None:
            trainer_kwargs["reward_model"] = self._reward_model
        self._trainer = OnlineDPOTrainer(**trainer_kwargs)
        self._built = True
        logger.info(
            "rl_bridge.online_dpo.build.ok",
            extra={
                "rl_algo": self.name,
                "rl_run_id": self.run_id,
                "rl_ref_temperature": self.ref_temperature,
                "rl_sampling_temperature": self.sampling_temperature,
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
                ("loss", "rl.train.update.loss"),
                ("rewards/chosen", "rl.train.update.rewards_chosen"),
                ("rewards/rejected", "rl.train.update.rewards_rejected"),
                ("rewards/margins", "rl.train.update.rewards_margin"),
                ("rewards/accuracies", "rl.train.update.accuracy"),
                ("logps/chosen", "rl.train.update.logps_chosen"),
                ("logps/rejected", "rl.train.update.logps_rejected"),
                ("objective/kl", "rl.rollout.step.kl_from_reference"),
            ):
                if trl_key in entry and entry[trl_key] is not None:
                    self.emit_metric(rl_key, float(entry[trl_key]), step=step)
            # Spec §3.4b: temperature separation audit tags.
            self.emit_metric(
                "rl.train.update.ref_temperature", self.ref_temperature, step=step
            )
            self.emit_metric(
                "rl.train.update.sampling_temperature",
                self.sampling_temperature,
                step=step,
            )

        metrics: dict[str, float | None] = {k: None for k in METRIC_KEYS}
        if log_history and isinstance(log_history[-1], dict):
            last = log_history[-1]
            margin = last.get("rewards/margins")
            if margin is not None:
                metrics["reward_mean"] = float(margin)
            if "objective/kl" in last:
                metrics["kl"] = float(last["objective/kl"])
        metrics["training_time_seconds"] = training_time
        metrics["ref_temperature"] = self.ref_temperature
        metrics["sampling_temperature"] = self.sampling_temperature

        from kailash_align._version import __version__ as _align_version

        lineage = RLLineage(
            run_id=self.run_id,
            experiment_name=None,
            tenant_id=self.tenant_id,
            base_model_ref=getattr(self._policy, "name_or_path", None),
            reference_model_ref=getattr(self._reference_model, "name_or_path", None),
            reward_model_ref=(
                getattr(self._reward_model, "name_or_path", None)
                if self._reward_model is not None
                else None
            ),
            dataset_ref=f"prompts:rows={len(self._prompt_dataset) if self._prompt_dataset is not None else 0}",
            env_spec="text:preferences",
            algorithm=self.name,
            paradigm=self.paradigm,
            parent_run_id=None,
            sdk_source="kailash-align",
            sdk_version=_align_version,
            created_at=datetime.now(timezone.utc),
        )

        # W6-015: populate spec §3.2 canonical fields. Online DPO is
        # an RLHF preference-learning algo — no episode rollouts, no
        # replay buffer, classical metrics stay None.
        result = RLTrainingResult(
            algorithm=self.name,
            env_spec="text:preferences",
            total_timesteps=int(total_timesteps),
            episode_reward_mean=float(metrics.get("reward_mean") or 0.0),
            episode_reward_std=0.0,
            episode_length_mean=0.0,
            total_env_steps=int(total_timesteps),
            policy_entropy=None,
            value_loss=None,
            kl_divergence=metrics.get("kl"),
            explained_variance=None,
            replay_buffer_size=None,
            metrics=metrics,
            elapsed_seconds=float(training_time),
            tenant_id=self.tenant_id,
            artifact_uris={},
            episodes=[],
            eval_history=[],
            policy_artifact=None,
            lineage=lineage,
            device=self.device,
            # Back-compat kwargs (resolved by __post_init__):
            policy_name=getattr(self._policy, "name_or_path", self.name),
        )
        logger.info(
            "rl_bridge.online_dpo.learn.ok",
            extra={
                "rl_algo": self.name,
                "rl_run_id": self.run_id,
                "rl_training_time_s": training_time,
                "tenant_id": self.tenant_id,
                "mode": "real",
            },
        )
        return result
