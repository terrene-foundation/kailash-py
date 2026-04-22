# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Multi-axis rank-0-only emission gate for autolog integrations.

Implements ``specs/ml-autolog.md §3.3`` (Decision 4) — every framework
integration MUST emit autolog events (metrics, params, models, figures,
datasets) ONLY when the process is the global main process across ALL
parallelism axes (DP rank-0 AND TP rank-0 AND PP rank-0 AND Accelerate
is_main_process).

The spec names this gate ``DistributionEnv.is_main_process`` at
``ml-diagnostics.md §5.5``. That central class is pending; this module
is the autolog-local implementation that every W23 integration
(Lightning, transformers, xgboost, lightgbm, sklearn, statsmodels,
polars) routes through. When the full :class:`DistributionEnv` lands,
this module's :func:`is_main_process` will delegate to it — same
public surface, single source of truth.

The existing :func:`kailash_ml.tracking.runner._is_rank_zero` covers the
single-axis DP path (``torch.distributed.get_rank() == 0``). This
helper is strictly wider — it also catches:

- **Accelerate** single-GPU-per-node runs where
  ``torch.distributed.is_initialized() is False`` on every process
  but ``accelerate.PartialState().is_main_process is False`` on
  every non-main worker.
- **Tensor parallel** ranks — a DP rank 0 with TP rank 1 would
  otherwise emit, duplicating metrics N-way where N = TP world size.
- **Pipeline parallel** ranks — same shape as TP.

The TP / PP detection is env-var-based because torch's DTensor /
DeviceMesh launchers commonly expose them; integrations that use a
custom mesh launcher SHOULD set the standard env vars so this gate
fires correctly. Absence of the env vars treats the process as
rank 0 on that axis (single-axis deployment).
"""
from __future__ import annotations

import logging
import os


__all__ = ["is_main_process"]


logger = logging.getLogger(__name__)


def is_main_process() -> bool:
    """Return True iff the current process is the GLOBAL main process
    across every parallelism axis.

    Checks, in order (short-circuit on first False):

    1. ``torch.distributed.get_rank() == 0`` — DP rank gate.
    2. ``accelerate.PartialState().is_main_process`` — Accelerate gate
       (required because Accelerate single-GPU-per-node does NOT
       initialise torch.distributed).
    3. ``TENSOR_PARALLEL_RANK`` / ``TP_RANK`` env var == "0" — TP gate.
    4. ``PIPELINE_PARALLEL_RANK`` / ``PP_RANK`` env var == "0" — PP gate.

    Missing / unavailable probes are treated as rank 0 on that axis
    (single-axis or single-process deployment). Exceptions during
    probing are swallowed and logged at DEBUG — we fail-open to
    rank-0 rather than silently dropping every log on a probe bug.
    """
    # Axis 1: torch.distributed DP rank.
    try:
        import torch.distributed as dist  # noqa: PLC0415

        if dist.is_available() and dist.is_initialized():
            if int(dist.get_rank()) != 0:
                return False
    except Exception as exc:  # noqa: BLE001 — absence is expected
        logger.debug(
            "autolog.distribution.torch_probe_failed",
            extra={"error": str(exc)},
        )

    # Axis 2: Accelerate single-GPU-per-node fan-out.
    try:
        from accelerate import PartialState  # noqa: PLC0415

        state = PartialState()
        if not state.is_main_process:
            return False
    except Exception as exc:  # noqa: BLE001 — accelerate is optional
        logger.debug(
            "autolog.distribution.accelerate_probe_failed",
            extra={"error": str(exc)},
        )

    # Axis 3: Tensor parallel.
    tp_rank = os.environ.get("TENSOR_PARALLEL_RANK") or os.environ.get("TP_RANK")
    if tp_rank is not None:
        try:
            if int(tp_rank) != 0:
                return False
        except ValueError:
            logger.debug(
                "autolog.distribution.tp_rank_invalid",
                extra={"tp_rank": tp_rank},
            )

    # Axis 4: Pipeline parallel.
    pp_rank = os.environ.get("PIPELINE_PARALLEL_RANK") or os.environ.get("PP_RANK")
    if pp_rank is not None:
        try:
            if int(pp_rank) != 0:
                return False
        except ValueError:
            logger.debug(
                "autolog.distribution.pp_rank_invalid",
                extra={"pp_rank": pp_rank},
            )

    return True
