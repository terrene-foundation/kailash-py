# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Trajectory unification entry — convert :class:`AlignmentResult` to W30 RLLineage.

Per ``specs/ml-rl-align-unification.md`` v1.0.0 §5 + §7, the cross-SDK
unified provenance schema lives on the kailash-ml side as
:class:`kailash_ml.rl.RLLineage`. kailash-align MUST NOT define a
parallel copy (spec §7 "single source in ml, per W30") and MUST NOT
re-export the type either — downstream callers import the type from
``kailash_ml.rl`` directly.

This module provides :func:`trajectory_from_alignment_run`, the
conversion entry the 32b todo mandates. It takes an
:class:`~kailash_align.AlignmentResult` and returns an
:class:`~kailash_ml.rl.RLLineage` populated with:

* ``sdk_source="kailash-align"`` (spec §5.2);
* ``paradigm="rlhf"`` for every align-produced trajectory (spec §5);
* ``algorithm`` drawn from the alignment method (``sft``, ``dpo``, ...);
* ``run_id`` derived from the adapter_name + version (kailash-align's
  natural run identifier — the registry already guarantees uniqueness).

Spec-deviation note (specs-authority.md MUST Rule 6)
----------------------------------------------------

The 32b amendment uses the word "Trajectory" to describe the unified
schema. The W30 implementation named it ``RLLineage`` to match spec §5
field names. This module retains the ``trajectory_from_alignment_run``
callable name (caller-facing vocabulary) but returns the actual W30
dataclass — no parallel "Trajectory" class is introduced because
introducing one would violate spec §7's single-source-in-ml mandate.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover — typing only
    from kailash_align.pipeline import AlignmentResult
    from kailash_ml.rl import RLLineage

logger = logging.getLogger(__name__)

__all__ = ["trajectory_from_alignment_run"]


# The spec §5.1 enumerates ``paradigm in {"on-policy", "off-policy",
# "offline", "rlhf"}`` and RLLineage.__post_init__ enforces the set.
# Every method the alignment pipeline runs is classified as "rlhf"
# because alignment IS preference/reward-driven fine-tuning even when
# the loss surface (SFT, DPO, ORPO, ...) differs.
_ALIGN_PARADIGM = "rlhf"


def trajectory_from_alignment_run(run: Any) -> "RLLineage":
    """Convert an :class:`AlignmentResult` into the W30 cross-SDK schema.

    Spec references: ``ml-rl-align-unification.md`` v1.0.0 §5 (lineage
    fields), §7 (dependency topology — align imports from ml, not vice
    versa), §3.2 (result type parity).

    Parameters
    ----------
    run
        :class:`kailash_align.AlignmentResult` — dataclass returned by
        :meth:`AlignmentPipeline.train`. Required fields consumed:
        ``adapter_name`` (str), ``adapter_path`` (str), ``method``
        (str), ``training_metrics`` (dict), ``adapter_version``
        (Optional[AdapterVersion]).

    Returns
    -------
    :class:`kailash_ml.rl.RLLineage`
        Populated cross-SDK provenance record. ``sdk_source`` is fixed
        to ``"kailash-align"`` per spec §5.2.

    Raises
    ------
    ImportError
        When ``kailash-ml`` is not installed. kailash-align declares
        ``kailash-ml>=0.11`` as a runtime dep so this should not fire
        in practice; when it does, the error message names the missing
        package for the caller.
    ValueError
        When the ``run`` object is missing required fields
        (duck-typed — any object with the listed attributes works).
    """
    # Lazy import to keep the ml→align direction one-way at import time
    # (align -> ml is spec-sanctioned, §7). Using the public top-level
    # re-export so drift in the storage module doesn't break callers.
    try:
        from kailash_ml.rl import RLLineage
    except ImportError as exc:
        raise ImportError(
            "trajectory_from_alignment_run requires kailash-ml to be "
            "installed. kailash-align declares kailash-ml>=0.11 as a "
            "runtime dependency; reinstall kailash-align or explicitly "
            "'pip install kailash-ml>=0.11'."
        ) from exc

    adapter_name = _require_attr(run, "adapter_name", str)
    method = _require_attr(run, "method", str)
    adapter_version = getattr(run, "adapter_version", None)

    run_id = _derive_run_id(adapter_name, adapter_version)
    sdk_version = _load_align_version()

    # spec §5.1 — dataset / model refs are optional; for an AlignmentResult
    # we do not have the raw dataset path back (it was consumed by
    # AlignmentPipeline.train) so we record ``None`` for env_spec /
    # dataset_ref and leave downstream enrichment (e.g. by kailash-ml
    # ExperimentRun metadata) to populate them when richer context is
    # available.
    lineage = RLLineage(
        run_id=run_id,
        experiment_name=adapter_name,
        tenant_id=getattr(run, "tenant_id", None),
        base_model_ref=getattr(run, "base_model_id", None),
        reference_model_ref=getattr(run, "reference_model_id", None),
        reward_model_ref=getattr(run, "reward_model_id", None),
        dataset_ref=getattr(run, "dataset_ref", None),
        env_spec=None,
        algorithm=method,
        paradigm=_ALIGN_PARADIGM,
        parent_run_id=getattr(run, "parent_run_id", None),
        sdk_source="kailash-align",
        sdk_version=sdk_version,
        created_at=datetime.now(timezone.utc),
    )
    logger.info(
        "align.ml.trajectory_from_alignment_run",
        extra={
            "run_id": run_id,
            "adapter_name": adapter_name,
            "algorithm": method,
            "paradigm": _ALIGN_PARADIGM,
            "sdk_version": sdk_version,
            "mode": "real",
        },
    )
    return lineage


def _require_attr(obj: Any, name: str, expected_type: type) -> Any:
    """Duck-typed field extraction that raises a typed ValueError on miss."""
    if not hasattr(obj, name):
        raise ValueError(
            f"trajectory_from_alignment_run: run object is missing "
            f"required attribute {name!r}"
        )
    value = getattr(obj, name)
    if not isinstance(value, expected_type) or (expected_type is str and not value):
        raise ValueError(
            f"trajectory_from_alignment_run: run.{name} must be a "
            f"non-empty {expected_type.__name__}, got {value!r}"
        )
    return value


_SAFE_TOKEN_RE = re.compile(r"[^\w.:-]+")


def _derive_run_id(adapter_name: str, adapter_version: Any) -> str:
    """Derive an RLLineage.run_id from adapter name + version.

    The registry's AdapterVersion has a ``version`` integer; when absent
    we fall back to the adapter name alone plus a timestamp fingerprint
    so run_ids stay unique within a session even without a registry.
    Security: the adapter_name is sanitized with the same shell-token
    regex the rl_bridge uses (``[^\\w.:-]`` → ``_``) so a malicious
    adapter_name never corrupts downstream log / filesystem consumers.
    """
    safe_name = _SAFE_TOKEN_RE.sub("_", adapter_name)
    if adapter_version is not None:
        version_num = getattr(adapter_version, "version", None)
        if isinstance(version_num, int):
            return f"align:{safe_name}:v{version_num}"
    # No AdapterVersion — derive a deterministic suffix from the UTC
    # timestamp for run_id uniqueness within a session.
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"align:{safe_name}:{ts}"


def _load_align_version() -> str:
    """Read kailash-align's __version__ for the RLLineage.sdk_version field."""
    try:
        from kailash_align._version import __version__
    except ImportError:  # pragma: no cover — defensive
        return "unknown"
    return str(__version__)
