# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Reproducibility surface — ``km.seed()`` + :class:`SeedReport`.

A single entry point that applies a seed across every random source that
downstream training code can plausibly touch:

- Python's ``random`` module
- ``numpy.random`` (when installed)
- ``torch.manual_seed`` + ``torch.cuda.manual_seed_all`` (when installed)
- ``lightning.seed_everything`` (when installed)
- ``PYTHONHASHSEED`` (the only one that MUST be set before interpreter
  start to have full effect — we still set the env var for subprocess
  children)

Every subsystem can be individually opted out with a keyword argument.
The returned :class:`SeedReport` records which subsystems were applied
and which were skipped (with a reason), so reproducibility audits have a
per-run trail. It also captures the linked BLAS backend, which the seed
does not pin (``ml-engines-v2.md §11.2 MUST 5``).

See ``specs/ml-engines-v2.md §11.1-§11.3``.
"""
from __future__ import annotations

import contextlib
import io
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Optional, Tuple

__all__ = [
    "SeedReport",
    "seed",
]

logger = logging.getLogger(__name__)

# BLAS backend names numpy reports that we normalise to a canonical token.
# ``ml-engines-v2.md §11.2 MUST 5`` names openblas / mkl / accelerate as the
# backends that matter for 1-ULP reproducibility drift; any other name numpy
# reports is passed through lowercased rather than collapsed to ``None``, so a
# BLIS or generic-reference build stays distinguishable from "numpy absent".
_KNOWN_BLAS_TOKENS: Tuple[str, ...] = (
    "openblas",
    "mkl",
    "accelerate",
    "blis",
    "atlas",
)


@dataclass(frozen=True)
class SeedReport:
    """Frozen summary of a ``km.seed()`` call.

    ``applied`` lists subsystems that received the seed value;
    ``skipped`` lists ``(subsystem, reason)`` pairs — either
    user-opt-out ("opt_out") or dependency-unavailable
    ("missing_dep"). ``torch_deterministic`` reflects whether
    ``torch.use_deterministic_algorithms(True)`` was invoked.
    ``blas_backend`` records the BLAS library numpy is linked against
    (``ml-engines-v2.md §11.2 MUST 5``) — the seed alone does not pin
    reproducibility, because OpenBLAS and MKL differ in sum-of-product
    order and drift at the 1-ULP level on large aggregates.
    """

    seed: int
    applied: Tuple[str, ...] = field(default_factory=tuple)
    skipped: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    torch_deterministic: bool = False
    blas_backend: Optional[str] = None

    def __contains__(self, subsystem: str) -> bool:
        return subsystem in self.applied


def _detect_blas_backend() -> Optional[str]:
    """Return the BLAS backend numpy is linked against, lowercased.

    ``"openblas"`` / ``"mkl"`` / ``"accelerate"`` are the backends
    ``ml-engines-v2.md §11.2 MUST 5`` calls out; ``"blis"`` / ``"atlas"``
    and any other name numpy reports are returned as-is rather than
    collapsed, so an unusual build stays distinguishable from a numpy-less
    environment.

    Returns ``None`` only when numpy is absent or reports no BLAS name.
    Never raises — a probe failure is logged at DEBUG and reported as
    ``None``, because a reproducibility annotation must not be able to
    break ``km.seed()``.
    """
    np = _try_import("numpy")
    if np is None or not hasattr(np, "show_config"):
        return None

    # numpy >= 2.0 exposes a structured form; prefer it.
    try:
        cfg = np.show_config(mode="dicts")
        blas = (cfg or {}).get("Build Dependencies", {}).get("blas", {})
        name = blas.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip().lower()
    except Exception as exc:  # noqa: BLE001 — probe must never break seeding
        # numpy 1.x has no ``mode`` kwarg (TypeError); a patched//broken
        # show_config can raise anything. Either way fall through to the
        # stdout form below rather than propagating out of ``km.seed()``.
        logger.debug(
            "seed.blas_probe.dicts_unavailable",
            extra={"seed_error": str(exc)},
        )

    # numpy 1.x — ``show_config()`` prints to stdout and returns None.
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            np.show_config()
        text = buf.getvalue().lower()
    except Exception as exc:  # noqa: BLE001 — probe must never break seeding
        logger.debug(
            "seed.blas_probe.failed",
            extra={"seed_error": str(exc)},
        )
        return None

    for token in _KNOWN_BLAS_TOKENS:
        if token in text:
            return token
    if text.strip():
        logger.debug("seed.blas_probe.unrecognised_backend")
    return None


def _try_import(module_path: str):
    """Best-effort import. Returns ``None`` when the module is absent —
    we never raise from here; :class:`SeedReport.skipped` records the
    disposition instead."""
    try:
        parts = module_path.split(".")
        mod = __import__(parts[0])
        for p in parts[1:]:
            mod = getattr(mod, p)
        return mod
    except Exception:  # ImportError, AttributeError, or the rare lazy-import edge case
        return None


def seed(
    seed: int,
    *,
    python: bool = True,
    numpy: bool = True,
    torch: bool = True,
    lightning: bool = True,
    sklearn: bool = True,
    torch_deterministic: bool = True,
) -> SeedReport:
    """Apply ``seed`` across every reachable random source.

    Every keyword argument defaults to ``True`` — pass ``False`` to skip
    a subsystem (the skip is recorded in the returned
    :class:`SeedReport` with reason ``"opt_out"``). When a subsystem's
    library is not installed the skip reason is ``"missing_dep"``.

    Args:
        seed: The seed value. Integer; downstream libraries normalise
            to their own size.
        python: Apply to :mod:`random`.
        numpy: Apply to ``numpy.random.seed``.
        torch: Apply to ``torch.manual_seed`` and (when CUDA is present)
            ``torch.cuda.manual_seed_all``.
        lightning: Apply via ``lightning.seed_everything`` (or
            ``pytorch_lightning.seed_everything``).
        sklearn: Sklearn inherits determinism from :mod:`random` +
            :mod:`numpy` — this flag controls whether sklearn's
            ``check_random_state`` is recorded in the applied list.
        torch_deterministic: When ``True`` AND ``torch`` is applied AND
            the torch version supports it, also call
            :func:`torch.use_deterministic_algorithms(True)`.

    Returns:
        A :class:`SeedReport` capturing the applied/skipped subsystems.
    """
    applied: list[str] = []
    skipped: list[Tuple[str, str]] = []

    # PYTHONHASHSEED — applies ONLY to subprocesses started AFTER the
    # env var is set. Set unconditionally because the overhead is nil.
    os.environ["PYTHONHASHSEED"] = str(seed)
    applied.append("pythonhashseed")

    # Python's `random`
    if python:
        random.seed(seed)
        applied.append("python")
    else:
        skipped.append(("python", "opt_out"))

    # Numpy
    if numpy:
        np = _try_import("numpy.random")
        if np is None:
            skipped.append(("numpy", "missing_dep"))
        else:
            np.seed(seed)
            applied.append("numpy")
    else:
        skipped.append(("numpy", "opt_out"))

    # Torch
    torch_applied = False
    if torch:
        torch_module = _try_import("torch")
        if torch_module is None:
            skipped.append(("torch", "missing_dep"))
        else:
            torch_module.manual_seed(seed)
            if hasattr(torch_module, "cuda") and torch_module.cuda.is_available():
                torch_module.cuda.manual_seed_all(seed)
            applied.append("torch")
            torch_applied = True
    else:
        skipped.append(("torch", "opt_out"))

    # torch_deterministic is downstream of torch — only applies when
    # torch was actually seeded. Uses try/except because older torch
    # versions lack use_deterministic_algorithms.
    torch_det_applied = False
    if torch_applied and torch_deterministic:
        torch_module = _try_import("torch")
        if torch_module is not None and hasattr(
            torch_module, "use_deterministic_algorithms"
        ):
            try:
                torch_module.use_deterministic_algorithms(True)
                torch_det_applied = True
            except (RuntimeError, ValueError):
                # Some CUDA ops raise when determinism is requested —
                # best-effort; we still report False.
                pass

    # Lightning — `pytorch-lightning` is the active distribution after the
    # `lightning` umbrella was quarantined on PyPI in 2026-04 (#752). Try
    # `pytorch_lightning` first, then fall back to the umbrella for installs
    # that still have the (quarantined-but-installed) `lightning` package.
    if lightning:
        L = (
            _try_import("pytorch_lightning")
            or _try_import("lightning.pytorch")
            or _try_import("lightning")
        )
        if L is None or not hasattr(L, "seed_everything"):
            skipped.append(("lightning", "missing_dep"))
        else:
            L.seed_everything(seed, workers=True)
            applied.append("lightning")
    else:
        skipped.append(("lightning", "opt_out"))

    # Sklearn — inherits determinism from numpy + python random, but we
    # note it explicitly so the operator sees it in the report.
    if sklearn:
        sk = _try_import("sklearn")
        if sk is None:
            skipped.append(("sklearn", "missing_dep"))
        else:
            applied.append("sklearn")
    else:
        skipped.append(("sklearn", "opt_out"))

    return SeedReport(
        seed=seed,
        applied=tuple(applied),
        skipped=tuple(skipped),
        torch_deterministic=torch_det_applied,
        blas_backend=_detect_blas_backend(),
    )
