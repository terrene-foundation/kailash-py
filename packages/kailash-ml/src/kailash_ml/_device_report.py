# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DeviceReport dataclass for kailash-ml GPU-first Phase 1.

Every call that trains or predicts via a ``Trainable`` MUST return (or
carry) a ``DeviceReport`` so callers can distinguish between a run that
actually executed on a GPU and a run that fell back to CPU silently.
The report also captures the pre-resolved precision and whether the
sklearn Array API dispatch was engaged on the call.

Implements `workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md`
§ "DeviceReport contract" (lines 54-78 of the revised-stack doc).

Surface contract:

    DeviceReport.family              "sklearn" | "xgboost" | "torch" | "rl" | ...
    DeviceReport.backend             "cuda" | "mps" | "rocm" | "xpu" | "tpu" | "cpu"
    DeviceReport.device_string       "cuda:0" | "mps" | "cpu"
    DeviceReport.precision           "fp32" | "bf16" | "fp16" | Lightning shortcut
    DeviceReport.fallback_reason     non-None when GPU -> CPU fallback fired
    DeviceReport.array_api           True if sklearn Array API was engaged

Lives alongside ``BackendInfo`` (``_device.py``). The two differ by
scope: ``BackendInfo`` is environment-level (what the host CAN do),
``DeviceReport`` is call-level (what this specific fit/predict ACTUALLY
did).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from kailash_ml._device import BackendInfo

__all__ = [
    "DeviceReport",
    "device_report_from_backend_info",
]


@dataclass(frozen=True)
class DeviceReport:
    """Per-call evidence of what backend / precision / path ran.

    Attributes:
        family: The Trainable family label (e.g. ``"sklearn"``,
            ``"xgboost"``, ``"torch"``, ``"rl"``). Free-form string so
            new families can add themselves without a registry hop.
        backend: One of the detected backends from ``_device.KNOWN_BACKENDS``
            (``"cuda"``, ``"mps"``, ``"rocm"``, ``"xpu"``, ``"tpu"``,
            ``"cpu"``). Matches the value that actually executed, not
            the value requested.
        device_string: Torch device string (``"cuda:0"``, ``"mps"``,
            ``"cpu"``). Echoes the string that was actually passed to
            ``.to(...)`` / Trainer ``devices=`` on the hot path.
        precision: Concrete precision string (``"fp32"``, ``"bf16"``,
            ``"fp16"``, or a Lightning shortcut like ``"bf16-mixed"``).
            Never ``"auto"``; callers that start with ``"auto"`` MUST
            resolve to a concrete value before constructing this
            report.
        fallback_reason: ``None`` when the call ran on the initially
            requested backend. A short machine-parseable string when a
            GPU → CPU (or higher-tier → lower-tier) fallback fired:

              * ``"oom"``                 OOM on the GPU path; retried CPU.
              * ``"cuml_eviction"``       UMAP/HDBSCAN on CPU because cuML
                                          was evicted in Phase 1.
              * ``"array_api_offlist"``   sklearn estimator not on the
                                          Array API allowlist; CPU numpy path.
              * ``"driver_missing"``      runtime driver probe failed.
              * ``"unsupported_family"``  family cannot run on the detected
                                          backend.
        array_api: ``True`` iff the sklearn Array API dispatch was
            engaged for this call (``sklearn.config_context(array_api_dispatch=True)``).
            ``False`` for non-sklearn families and for sklearn calls
            that fell off the allowlist.
    """

    family: str
    backend: str
    device_string: str
    precision: str
    fallback_reason: Optional[str] = None
    array_api: bool = False

    def __post_init__(self) -> None:  # type: ignore[override]
        # Concrete values only (mirrors TrainingResult.__post_init__ §4.2
        # MUST 2). Runtime reports MUST carry evidence, not intent.
        if not isinstance(self.family, str) or not self.family:
            raise ValueError(
                "DeviceReport.family must be a non-empty string "
                "(e.g. 'sklearn', 'xgboost', 'torch')."
            )
        if not isinstance(self.backend, str) or not self.backend:
            raise ValueError(
                "DeviceReport.backend must be a non-empty string "
                "(e.g. 'cuda', 'cpu')."
            )
        if self.backend == "auto":
            raise ValueError(
                "DeviceReport.backend='auto' is BLOCKED. Resolve 'auto' "
                "to a concrete value via detect_backend() before "
                "constructing the report."
            )
        if not isinstance(self.device_string, str) or not self.device_string:
            raise ValueError(
                "DeviceReport.device_string must be a non-empty string "
                "(e.g. 'cuda:0', 'mps', 'cpu')."
            )
        if not isinstance(self.precision, str) or not self.precision:
            raise ValueError(
                "DeviceReport.precision must be a non-empty string "
                "(e.g. 'fp32', 'bf16', '16-mixed')."
            )
        if self.precision == "auto":
            raise ValueError(
                "DeviceReport.precision='auto' is BLOCKED. Resolve 'auto' "
                "to a concrete value via resolve_precision() before "
                "constructing the report."
            )
        if self.fallback_reason is not None and not isinstance(
            self.fallback_reason, str
        ):
            raise ValueError(
                "DeviceReport.fallback_reason must be None or a short "
                "machine-parseable string."
            )
        if not isinstance(self.array_api, bool):
            raise ValueError(
                "DeviceReport.array_api must be a bool."
            )

    def as_log_extra(self) -> dict[str, Any]:
        """Return a dict suitable for ``logger.info(..., extra=...)``.

        The six fields are the minimum structured log payload every
        adapter emits on fit/predict, per the revised-stack spec. Using
        ``asdict`` keeps this deterministic as new optional fields are
        added to the contract.
        """
        return asdict(self)


def device_report_from_backend_info(
    info: BackendInfo,
    *,
    family: str,
    fallback_reason: Optional[str] = None,
    array_api: bool = False,
) -> DeviceReport:
    """Construct a ``DeviceReport`` from a ``BackendInfo`` plus family.

    Convenience for the 90% case where the adapter just ran on the
    resolved backend and wants to hand the report to its
    ``TrainingResult``. Callers that had a fallback should pass the
    POST-fallback ``BackendInfo`` (typically a CPU info) plus the
    ``fallback_reason`` describing why — the report captures what
    ACTUALLY ran, not what was requested.
    """
    return DeviceReport(
        family=family,
        backend=info.backend,
        device_string=info.device_string,
        precision=info.precision,
        fallback_reason=fallback_reason,
        array_api=array_api,
    )
