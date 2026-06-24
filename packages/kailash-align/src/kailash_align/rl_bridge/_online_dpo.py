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

from typing import Any, Callable, ClassVar, Literal, Optional

from kailash_align.rl_bridge._base import _BridgeAdapterBase

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
        """Online DPO is unavailable under trl >=1.0.

        trl >=1.0 removed ``OnlineDPOTrainer``/``OnlineDPOConfig`` upstream (the
        classes no longer exist in any trl 1.x release) and kailash-align's trl
        floor is >=1.0, so the bridge can never instantiate a trainer — the
        ``online_dpo`` method is intentionally NOT registered in
        ``method_registry`` (see issue #1426). This raises the SAME informative
        :class:`~kailash_align.exceptions.TrainingError` as
        :meth:`OnlineDPOConfig.to_trl_config` (``config.py``), pointing users to
        DPO or GRPO — rather than the opaque ``AlignmentError: Unknown training
        method 'online_dpo'`` the un-registered registry lookup produced. See
        issue #1429.
        """
        from kailash_align.exceptions import TrainingError

        raise TrainingError(
            "Online DPO is unavailable: trl >=1.0 removed OnlineDPOConfig/"
            "OnlineDPOTrainer upstream (the class no longer exists in any trl 1.x "
            "release). Use DPO (method='dpo', offline paired preference data) or "
            "GRPO (method='grpo', online RL with reward functions) instead."
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
        """Online DPO is unavailable under trl >=1.0 — see :meth:`build`.

        ``learn`` must build the trainer before training; :meth:`build` raises an
        informative :class:`~kailash_align.exceptions.TrainingError` (trl >=1.0
        removed ``OnlineDPOTrainer``; use 'dpo' or 'grpo'), so calling ``learn``
        surfaces the same actionable error rather than an opaque registry miss.
        See issue #1429.
        """
        self.build()
