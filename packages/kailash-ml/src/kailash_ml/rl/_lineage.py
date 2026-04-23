# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Cross-SDK RL lineage dataclass for ``kailash-ml`` <-> ``kailash-align``.

Per ``specs/ml-rl-align-unification.md`` §5, every
:class:`~kailash_ml.rl.trainer.RLTrainingResult` carries an optional
:class:`RLLineage` describing the training run's provenance: base model,
reference model, reward model, dataset, env spec, paradigm, parent run
chain, and the SDK that produced the run (``"kailash-ml"`` for
first-party classical adapters; ``"kailash-align"`` for TRL-backed
RLHF bridge adapters).

``MLDashboard`` renders the lineage as a provenance breadcrumb so
researchers comparing experiments can trace "SAC → DPO fine-tune" from a
single view regardless of which SDK ran which stage.

Zero backend imports
--------------------

This module is pure dataclass + stdlib. It does NOT import
``kailash_align``, ``stable_baselines3``, or ``trl``. The
``sdk_source`` field is a ``Literal`` label, not a reference to the
producing framework.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

__all__ = ["RLLineage"]


_ALLOWED_PARADIGMS: tuple[str, ...] = (
    "on-policy",
    "off-policy",
    "offline",
    "rlhf",
)
_ALLOWED_SDK_SOURCES: tuple[str, ...] = ("kailash-ml", "kailash-align")


@dataclass(frozen=True)
class RLLineage:
    """Provenance record for an RL training run.

    Populated by ``km.rl_train`` (for classical adapters) or by the
    align-bridge adapter (for RLHF runs). Frozen so the lineage cannot
    drift after emission — it is part of the :class:`RLTrainingResult`
    contract.

    Fields
    ------
    run_id:
        Correlation id for the run; matches the tracker run_id.
    experiment_name:
        Human-readable experiment label. May be ``None`` for ad-hoc runs.
    tenant_id:
        Tenant scope; ``None`` when single-tenant.
    base_model_ref:
        The policy's starting checkpoint (e.g. ``"sshleifer/tiny-gpt2"``
        for RLHF, or ``None`` for classical RL starting from random
        weights).
    reference_model_ref:
        RLHF reference policy name + SHA; ``None`` for classical RL.
    reward_model_ref:
        RLHF reward model name + SHA; ``None`` for classical RL.
    dataset_ref:
        Preference dataset ref (name + row count); ``None`` for env-
        based classical RL.
    env_spec:
        Gymnasium env id (``"CartPole-v1"``) or text-dataset ref
        (``"text:preferences"``); ``None`` for dataset-only offline RL.
    algorithm:
        Canonical algorithm name — ``"ppo"``, ``"dpo"``, ``"rloo"``, ...
    paradigm:
        One of ``"on-policy"`` / ``"off-policy"`` / ``"offline"`` /
        ``"rlhf"``. Enforced at construction.
    parent_run_id:
        Prior run this one resumes from OR fine-tunes from; ``None``
        for from-scratch runs.
    sdk_source:
        ``"kailash-ml"`` for first-party classical adapters;
        ``"kailash-align"`` for TRL-backed bridge adapters. Enforced at
        construction.
    sdk_version:
        Version string of the producing SDK (e.g. ``"1.1.0"`` for
        kailash-ml, ``"0.5.0"`` for kailash-align).
    created_at:
        UTC timestamp at which the lineage was emitted.
    """

    run_id: str
    experiment_name: str | None
    tenant_id: str | None
    base_model_ref: str | None
    reference_model_ref: str | None
    reward_model_ref: str | None
    dataset_ref: str | None
    env_spec: str | None
    algorithm: str
    paradigm: Literal["on-policy", "off-policy", "offline", "rlhf"]
    parent_run_id: str | None
    sdk_source: Literal["kailash-ml", "kailash-align"]
    sdk_version: str
    created_at: datetime

    def __post_init__(self) -> None:
        # ``Literal`` type hints are NOT enforced by dataclasses at runtime;
        # the spec §5.1 contract requires both ``paradigm`` and ``sdk_source``
        # to be one of the enumerated values, so we gate explicitly.
        if self.paradigm not in _ALLOWED_PARADIGMS:
            raise ValueError(
                f"RLLineage.paradigm must be one of {_ALLOWED_PARADIGMS!r}, "
                f"got {self.paradigm!r}"
            )
        if self.sdk_source not in _ALLOWED_SDK_SOURCES:
            raise ValueError(
                f"RLLineage.sdk_source must be one of {_ALLOWED_SDK_SOURCES!r}, "
                f"got {self.sdk_source!r}"
            )
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("RLLineage.run_id must be a non-empty string")
        if not isinstance(self.algorithm, str) or not self.algorithm:
            raise ValueError("RLLineage.algorithm must be a non-empty string")
        if not isinstance(self.sdk_version, str) or not self.sdk_version:
            raise ValueError("RLLineage.sdk_version must be a non-empty string")
        if not isinstance(self.created_at, datetime):
            raise ValueError(
                "RLLineage.created_at must be a datetime instance "
                f"(got {type(self.created_at).__name__!r})"
            )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dict representation.

        ``datetime`` is rendered as an ISO-8601 string so the lineage
        can be persisted / emitted over the event bus without extra
        serializer hops.
        """
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload

    @classmethod
    def from_dict(cls, payload: Any) -> "RLLineage":
        """Round-trip complement of :meth:`to_dict`.

        Parses ``created_at`` back into a ``datetime`` via
        :meth:`datetime.fromisoformat`. Raises ``ValueError`` on
        malformed payloads the same way :meth:`__post_init__` does.
        """
        if not isinstance(payload, dict):
            raise ValueError(
                "RLLineage.from_dict expects a dict, " f"got {type(payload).__name__!r}"
            )
        data = dict(payload)
        created = data.get("created_at")
        if isinstance(created, str):
            data["created_at"] = datetime.fromisoformat(created)
        # Allow unexpected extra keys to surface as a TypeError from
        # the dataclass __init__ (clearer than silent drop).
        return cls(**data)
