# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""TrainingResult dataclass (kailash-ml 2.0 Phase 2).

Implements `specs/ml-engines.md` §4 as the single envelope every
training path produces. Fields are a frozen contract; adding,
renaming, or reordering requires a spec amendment.

The dataclass is frozen (`dataclass(frozen=True)`) and validates its
inputs in `__post_init__`. `to_dict()` / `from_dict()` follow the EATP
convention for cross-SDK wire compatibility (a Python-trained model
registered from kailash-py MUST be loadable by a kailash-rs registry
reader per `ml-engines.md` §10.1).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Any, Mapping, Optional

from kailash_ml._device_report import DeviceReport

__all__ = [
    "TrainingResult",
    "IncompleteTrainingResultError",
]


class IncompleteTrainingResultError(ValueError):
    """Raised when a required TrainingResult field is missing or invalid.

    Per ml-engines.md §4.2 MUST 1: every code path that produces a
    TrainingResult MUST populate all ten required fields. Leaving a
    required field as None is BLOCKED; the path MUST raise rather than
    return a partially-populated result.
    """


_REQUIRED_FIELDS: tuple[str, ...] = (
    "model_uri",
    "metrics",
    "device_used",
    "accelerator",
    "precision",
    "elapsed_seconds",
    # tracker_run_id is explicitly nullable (§4.1: "set when an
    # ExperimentTracker was bound")
    "tenant_id",  # nullable in single-tenant mode per §4.2 MUST 3
    "artifact_uris",
    "lightning_trainer_config",
)

# Fields that may legitimately be None:
#   tracker_run_id — None when no tracker bound
#   tenant_id — None in single-tenant mode (echoes engine.tenant_id)
_NULLABLE_REQUIRED: frozenset[str] = frozenset({"tracker_run_id", "tenant_id"})


@dataclass(frozen=True)
class TrainingResult:
    """Single envelope every training path produces.

    Per `specs/ml-engines.md` §4.1. Required fields are the first ten;
    optional fields follow. `__post_init__` validates all required
    fields are populated (§4.2 MUST 1) and that the precision/accelerator
    strings are concrete (§4.2 MUST 2 — never "auto").
    """

    # --- Required fields (§4.1) --------------------------------------------
    model_uri: str
    metrics: Mapping[str, float]
    device_used: str
    accelerator: str
    precision: str
    elapsed_seconds: float
    # tracker_run_id is nullable (§4.1 comment: "set when an
    # ExperimentTracker was bound")
    tracker_run_id: Optional[str]
    # tenant_id is nullable in single-tenant mode (§4.2 MUST 3)
    tenant_id: Optional[str]
    artifact_uris: Mapping[str, str]
    lightning_trainer_config: Mapping[str, Any]

    # --- Optional / recommended fields (§4.1) ------------------------------
    family: Optional[str] = None
    hyperparameters: Optional[Mapping[str, Any]] = None
    split_info: Optional[Any] = None
    calibration: Optional[Any] = None
    feature_importance: Optional[Mapping[str, float]] = None
    # --- Per-call device evidence (GPU-first Phase 1) ----------------------
    # Populated by every family adapter (SklearnTrainable first — see
    # `workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md` lines
    # 54-78). Optional at the dataclass level so older callers (and
    # from_dict payloads that pre-date this field) continue to validate;
    # new family adapters MUST populate it. XGBoost / LightGBM adapters
    # populate `.device.fallback_reason="oom"` when they survived a GPU
    # OOM and retried on CPU (revised-stack.md § "Transparency contract").
    device: Optional[DeviceReport] = None

    def __post_init__(self) -> None:
        # Populated-required-field check (§4.2 MUST 1).
        for name in _REQUIRED_FIELDS:
            value = getattr(self, name)
            if value is None and name not in _NULLABLE_REQUIRED:
                raise IncompleteTrainingResultError(
                    f"TrainingResult.{name} is None but is required. "
                    f"Every training path MUST populate this field; see "
                    f"ml-engines.md §4.2 MUST 1."
                )

        # model_uri must be a non-empty string.
        if not isinstance(self.model_uri, str) or not self.model_uri:
            raise IncompleteTrainingResultError(
                "TrainingResult.model_uri must be a non-empty string "
                "(e.g. 'models://User/v3')."
            )

        # metrics must be a mapping of str -> finite float. Non-finite
        # values silently poison every downstream aggregation; rule them
        # out at construction time.
        if not isinstance(self.metrics, Mapping):
            raise IncompleteTrainingResultError(
                f"TrainingResult.metrics must be a Mapping[str, float]; "
                f"got {type(self.metrics).__name__}."
            )
        for key, val in self.metrics.items():
            if not isinstance(key, str):
                raise IncompleteTrainingResultError(
                    f"TrainingResult.metrics key must be str; got "
                    f"{type(key).__name__} ({key!r})."
                )
            try:
                fval = float(val)
            except (TypeError, ValueError) as exc:
                raise IncompleteTrainingResultError(
                    f"TrainingResult.metrics[{key!r}]={val!r} cannot be "
                    f"coerced to float."
                ) from exc
            if not math.isfinite(fval):
                raise IncompleteTrainingResultError(
                    f"TrainingResult.metrics[{key!r}]={val!r} is not finite. "
                    f"NaN/Inf metrics poison downstream aggregation; see "
                    f"ml-tracking.md §2.5."
                )

        # device_used / accelerator / precision must be concrete strings.
        # "auto" in any of these violates §4.2 MUST 2 (lightning_trainer_config
        # carries what ACTUALLY ran, not the user's intent).
        for name in ("device_used", "accelerator", "precision"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise IncompleteTrainingResultError(
                    f"TrainingResult.{name} must be a non-empty string; "
                    f"got {value!r}."
                )
            if value == "auto":
                raise IncompleteTrainingResultError(
                    f"TrainingResult.{name}='auto' is BLOCKED. "
                    f"Resolve 'auto' to a concrete value before "
                    f"constructing TrainingResult; see ml-engines.md "
                    f"§4.2 MUST 2."
                )

        # elapsed_seconds must be a finite non-negative number.
        try:
            elapsed = float(self.elapsed_seconds)
        except (TypeError, ValueError) as exc:
            raise IncompleteTrainingResultError(
                f"TrainingResult.elapsed_seconds={self.elapsed_seconds!r} "
                f"is not a number."
            ) from exc
        if not math.isfinite(elapsed) or elapsed < 0:
            raise IncompleteTrainingResultError(
                f"TrainingResult.elapsed_seconds={elapsed!r} must be "
                f"finite and non-negative."
            )

        # artifact_uris + lightning_trainer_config must be mappings.
        if not isinstance(self.artifact_uris, Mapping):
            raise IncompleteTrainingResultError(
                f"TrainingResult.artifact_uris must be a Mapping[str, str]; "
                f"got {type(self.artifact_uris).__name__}."
            )
        for key, val in self.artifact_uris.items():
            if not isinstance(key, str) or not isinstance(val, str):
                raise IncompleteTrainingResultError(
                    f"TrainingResult.artifact_uris must be str->str; got "
                    f"{type(key).__name__}={type(val).__name__}."
                )
        if not isinstance(self.lightning_trainer_config, Mapping):
            raise IncompleteTrainingResultError(
                f"TrainingResult.lightning_trainer_config must be a "
                f"Mapping[str, Any]; got "
                f"{type(self.lightning_trainer_config).__name__}."
            )

    # ------------------------------------------------------------------
    # Serialization (EATP wire contract)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for wire/registry persistence.

        Only shallow conversion: nested Mapping objects become plain
        dicts; dataclass fields (split_info / calibration) keep their
        type. The cross-SDK loader handles nested types.
        """
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, Mapping):
                out[f.name] = dict(value)
            else:
                out[f.name] = value
        return out

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TrainingResult":
        """Deserialize a `to_dict()` payload into a TrainingResult.

        Unknown keys are rejected so that wire-format drift surfaces at
        read time rather than silently dropping fields.
        """
        known_names = {f.name for f in fields(cls)}
        unknown = set(data.keys()) - known_names
        if unknown:
            raise IncompleteTrainingResultError(
                f"TrainingResult.from_dict received unknown keys: "
                f"{sorted(unknown)}. Known fields: {sorted(known_names)}."
            )
        kwargs = {k: data[k] for k in data if k in known_names}
        # Backward-compatibility: allow missing optional fields to use
        # their defaults; required fields are validated in __post_init__.
        return cls(**kwargs)
