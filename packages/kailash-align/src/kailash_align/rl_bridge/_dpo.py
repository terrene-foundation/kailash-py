# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DPOAdapter — Direct Preference Optimization bridge adapter.

Per ``specs/ml-rl-align-unification.md`` v1.0.0 §3 + §9, DPO is one of
the v1-scope bridge adapters. This module wraps ``trl.DPOTrainer``
behind the :class:`RLLifecycleProtocol` contract so ``km.rl_train(
algo="dpo", ...)`` routes into this adapter and emits the canonical
``rl.*`` metrics via the same tracker + diagnostics fan-out used by
classical SB3 adapters.

DPO reference-temperature contract (spec §3.4b)
----------------------------------------------

DPO distinguishes TWO temperatures the canonical TRL API silently
conflates via a single ``temperature`` knob:

* **``ref_temperature``** (default ``1.0``) — the temperature used
  when extracting log-probabilities from the reference-policy for the
  DPO loss. MUST be ``1.0`` to match TRL's native log-prob path; any
  other value would bias the reference-policy KL term.
* **``sampling_temperature``** (default ``0.0``) — the temperature
  used if the DPO run sampling-generates completions (rare but
  supported). Distinct knob per spec §3.4b.

The adapter emits ``rl.train.update.ref_temperature`` as a categorical
tag on every update so downstream tracker dashboards can audit
log-prob-extraction drift across runs.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, ClassVar, Literal, Optional

from kailash_align.rl_bridge._base import _BridgeAdapterBase

logger = logging.getLogger(__name__)

__all__ = ["DPOAdapter"]


class DPOAdapter(_BridgeAdapterBase):
    """Direct Preference Optimization adapter wrapping ``trl.DPOTrainer``.

    Per spec §2: satisfies :class:`RLLifecycleProtocol` via structural
    duck typing (no Protocol subclassing). Runtime-checkable
    ``isinstance(adapter, RLLifecycleProtocol)`` holds for every
    constructed instance because the class-level ``name`` / ``paradigm``
    / ``buffer_kind`` are set AND ``__init__`` populates ``run_id`` /
    ``tenant_id`` / ``device`` AND the build / learn / save / load /
    checkpoint / resume / emit_metric method slots are all defined.

    Parameters
    ----------
    policy
        Tunable policy model (HuggingFace ``AutoModelForCausalLM`` or
        PEFT-wrapped variant). Required.
    reference_model
        Frozen reference policy for the DPO KL-divergence term. Required.
    preference_dataset
        HuggingFace ``datasets.Dataset`` with columns ``prompt`` /
        ``chosen`` / ``rejected`` (validated by
        :mod:`kailash_align.method_registry` at build time).
    hyperparameters
        Dict of TRL ``DPOConfig`` hyperparameters. Merged with the
        temperature kwargs before being passed to the trainer.
    device
        Optional :class:`kailash_ml.DeviceReport`. Concrete device /
        precision / fallback evidence per spec §3.2.
    tenant_id
        Optional tenant scope. Logged on every metric per
        ``rules/tenant-isolation.md``.
    ref_temperature
        Log-probability extraction temperature for the reference policy.
        Default ``1.0`` (TRL-canonical). Per spec §3.4b this MUST stay
        distinct from ``sampling_temperature``.
    sampling_temperature
        Generation sampling temperature. Default ``0.0`` (deterministic;
        DPO runs rarely sample). Distinct from ``ref_temperature``.
    """

    name: ClassVar[str] = "dpo"
    paradigm: ClassVar[Literal["on-policy", "off-policy", "offline", "rlhf"]] = "rlhf"
    buffer_kind: ClassVar[Literal["rollout", "replay", "dataset", "preference"]] = (
        "preference"
    )

    def __init__(
        self,
        *,
        policy: Any = None,
        reference_model: Any = None,
        preference_dataset: Any = None,
        hyperparameters: Optional[dict[str, Any]] = None,
        device: Any = None,
        tenant_id: Optional[str] = None,
        ref_temperature: float = 1.0,
        sampling_temperature: float = 0.0,
        run_id: Optional[str] = None,
    ) -> None:
        super().__init__(run_id=run_id, tenant_id=tenant_id, device=device)

        # Validate the temperature separation contract from spec §3.4b
        # eagerly so misconfiguration surfaces at construction time, not
        # deep inside TRL's trainer loop. Type-annotation narrows both
        # params to `float`; only value-bounds checks are needed.
        if ref_temperature <= 0:
            raise ValueError(
                f"DPOAdapter.ref_temperature must be > 0 " f"(got {ref_temperature!r})"
            )
        if sampling_temperature < 0:
            raise ValueError(
                f"DPOAdapter.sampling_temperature must be >= 0 "
                f"(got {sampling_temperature!r})"
            )

        self._policy = policy
        self._reference_model = reference_model
        self._preference_dataset = preference_dataset
        self._hyperparameters = dict(hyperparameters or {})
        self.ref_temperature = float(ref_temperature)
        self.sampling_temperature = float(sampling_temperature)
        self._resume_from: Any = None

    # ------------------------------------------------------------------

    def build(self) -> None:
        """Construct the underlying ``trl.DPOTrainer`` via method_registry.

        Wires the preference dataset through the method registry's
        shared validator + TRL-config builder so this adapter inherits
        the same column-check and metrics-extractor that the
        ``AlignmentPipeline`` path uses.
        """
        from kailash_align.method_registry import get_method

        method = get_method("dpo")
        method.dataset_validator(self._preference_dataset)

        # Lazy-import TRL — keeps the adapter importable without the
        # ``[rl-bridge]`` extra satisfied at test collection time.
        try:
            trainer_cls = __import__(
                method.trainer_module,
                fromlist=[method.trainer_class_name],
            )
            DPOTrainer = getattr(trainer_cls, method.trainer_class_name)
            config_cls = __import__(
                method.config_module,
                fromlist=[method.config_class_name],
            )
            DPOConfig = getattr(config_cls, method.config_class_name)
        except (ImportError, AttributeError) as exc:
            raise ImportError(
                f"DPOAdapter.build requires TRL DPOTrainer. "
                f"Install via 'pip install kailash-align[rl-bridge]' "
                f"(pulls trl>=1.0). Underlying error: {exc}"
            ) from exc

        # Build TRL config. Temperature kwargs are routed per spec §3.4b:
        # the reference-model log-prob path uses ``ref_temperature``,
        # the sampling path uses ``sampling_temperature``. TRL's DPOConfig
        # only exposes a generic ``temperature`` field — we set it to
        # the sampling value (since TRL uses it on the generate path)
        # and surface the ref_temperature separately on this adapter
        # so the trainer's native log-prob path (which is hardcoded to
        # 1.0 in TRL) stays canonical.
        config_kwargs = {**self._hyperparameters}
        config_kwargs.setdefault("temperature", self.sampling_temperature)
        trl_config = DPOConfig(**config_kwargs)

        self._trainer = DPOTrainer(
            model=self._policy,
            ref_model=self._reference_model,
            args=trl_config,
            train_dataset=self._preference_dataset,
        )
        self._built = True
        logger.info(
            "rl_bridge.dpo.build.ok",
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
        """Drive ``DPOTrainer.train`` and emit canonical ``rl.*`` metrics.

        Returns an :class:`~kailash_ml.rl.trainer.RLTrainingResult`
        populated with:

        * ``algorithm="dpo"``, ``env_name="text:preferences"``
        * Canonical metric keys from TRL's ``trainer.state.log_history``
          remapped into the spec §3.4 ``rl.train.update`` family
        * :class:`RLLineage` with ``sdk_source="kailash-align"``,
          ``paradigm="rlhf"``, ``algorithm="dpo"``
        * ``device=self.device``

        Per spec §3.4b, every update tags
        ``rl.train.update.ref_temperature`` = ``self.ref_temperature``
        so dashboards can audit log-prob-extraction drift.
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

        # Harvest TRL's log history and forward through emit_metric for
        # the dual tracker + diagnostics fan-out defined in the base.
        log_history = (
            getattr(getattr(self._trainer, "state", None), "log_history", []) or []
        )
        for step_idx, entry in enumerate(log_history):
            if not isinstance(entry, dict):
                continue
            step = int(entry.get("step", step_idx))
            # DPO-specific metrics; spec §3.4 maps these into the
            # canonical `rl.train.update.*` family.
            for trl_key, rl_key in (
                ("loss", "rl.train.update.loss"),
                ("rewards/chosen", "rl.train.update.rewards_chosen"),
                ("rewards/rejected", "rl.train.update.rewards_rejected"),
                ("rewards/margins", "rl.train.update.rewards_margin"),
                ("rewards/accuracies", "rl.train.update.accuracy"),
                ("logps/chosen", "rl.train.update.logps_chosen"),
                ("logps/rejected", "rl.train.update.logps_rejected"),
            ):
                if trl_key in entry and entry[trl_key] is not None:
                    self.emit_metric(rl_key, float(entry[trl_key]), step=step)
            # Spec §3.4b: ref_temperature tag on every update.
            self.emit_metric(
                "rl.train.update.ref_temperature",
                self.ref_temperature,
                step=step,
            )

        # Build result. Metrics dict honours the cross-algo parity key
        # set from kailash_ml.rl.trainer; non-applicable RL keys default
        # to None (never hallucinated zero — zero-tolerance Rule 2).
        metrics: dict[str, float | None] = {k: None for k in METRIC_KEYS}
        if hasattr(train_output, "metrics") and isinstance(train_output.metrics, dict):
            # The TRL runtime metrics become the canonical reward_mean
            # approximation for preference-pair training (no env → no
            # classical reward; reward_margin is the signal).
            margin = train_output.metrics.get("train_rewards/margins")
            if margin is not None:
                metrics["reward_mean"] = float(margin)
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
            reward_model_ref=None,
            dataset_ref=f"preferences:rows={len(self._preference_dataset) if self._preference_dataset is not None else 0}",
            env_spec="text:preferences",
            algorithm=self.name,
            paradigm=self.paradigm,
            parent_run_id=None,
            sdk_source="kailash-align",
            sdk_version=_align_version,
            created_at=datetime.now(timezone.utc),
        )

        training_loss = getattr(train_output, "training_loss", None)
        result = RLTrainingResult(
            policy_name=getattr(self._policy, "name_or_path", self.name),
            algorithm=self.name,
            total_timesteps=int(total_timesteps),
            mean_reward=float(metrics.get("reward_mean") or 0.0),
            std_reward=0.0,
            training_time_seconds=training_time,
            metrics=metrics,
            env_name="text:preferences",
            lineage=lineage,
            device=self.device,
        )
        logger.info(
            "rl_bridge.dpo.learn.ok",
            extra={
                "rl_algo": self.name,
                "rl_run_id": self.run_id,
                "rl_training_time_s": training_time,
                "rl_training_loss": (
                    float(training_loss) if training_loss is not None else None
                ),
                "tenant_id": self.tenant_id,
                "mode": "real",
            },
        )
        return result
