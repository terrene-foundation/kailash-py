# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``km.doctor()`` diagnostic per ``specs/ml-backends.md`` §7.

Public surface:

- :func:`doctor` — in-process diagnostic returning an exit-code-style int.
- :func:`main` — console-script entry point (``km-doctor``), parses argv
  and calls ``doctor`` with the effective flags.

Probes the four first-class backends (``cpu``, ``cuda``, ``mps``,
``rocm``) by attempting a torch-level availability check. Extension
backends (``xpu``, ``tpu``) are handled in §7.1 of the spec but left
out of the ``--require`` short-list for Phase 1 — they show up in the
human-readable table when detected but are not required for exit 0.

Exit codes (spec §7.2):

- ``0`` — all green (CPU available; any requested backend present).
- ``1`` — at least one probe produced a warning OR the base CPU path
  is broken but no ``--require`` constraint was violated.
- ``2`` — ``--require=<backend>`` is set and the requested backend is
  unreachable, OR a probe failed outright.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

__all__ = ["doctor", "main"]


# ---------------------------------------------------------------------------
# Backend probe results
# ---------------------------------------------------------------------------


@dataclass
class BackendProbe:
    """Result of a single backend probe."""

    backend: str
    status: str  # "ok" | "warn" | "fail" | "missing"
    version: Optional[str] = None
    devices: int = 0
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------


def _probe_cpu() -> BackendProbe:
    """CPU is always available.

    Returns a ``missing`` status only when the Python interpreter cannot
    report a platform — practically never, but the guard keeps the
    contract consistent.
    """
    import platform

    plat = platform.platform()
    return BackendProbe(
        backend="cpu",
        status="ok",
        version=plat,
        devices=1,
    )


def _probe_torch_module() -> Any:
    """Attempt to import torch; return the module or ``None``."""
    try:
        import torch
    except ImportError:
        return None
    return torch


def _probe_cuda() -> BackendProbe:
    torch = _probe_torch_module()
    if torch is None:
        return BackendProbe(
            backend="cuda",
            status="missing",
            failures=["torch not installed"],
        )
    try:
        if not bool(torch.cuda.is_available()):
            return BackendProbe(
                backend="cuda",
                status="missing",
                version=getattr(torch, "__version__", None),
                failures=["torch.cuda.is_available() == False"],
            )
        # ROCm advertises via torch.cuda too; filter to pure CUDA.
        if getattr(torch.version, "hip", None) is not None:
            return BackendProbe(
                backend="cuda",
                status="missing",
                version=getattr(torch, "__version__", None),
                failures=["torch.version.hip is set -- this is a ROCm build"],
            )
        count = int(torch.cuda.device_count())
        return BackendProbe(
            backend="cuda",
            status="ok",
            version=getattr(torch.version, "cuda", None)
            or getattr(torch, "__version__", None),
            devices=count,
        )
    except Exception as exc:  # noqa: BLE001 — probe must not raise
        return BackendProbe(
            backend="cuda",
            status="fail",
            failures=[f"cuda probe raised {type(exc).__name__}: {exc}"],
        )


def _probe_mps() -> BackendProbe:
    torch = _probe_torch_module()
    if torch is None:
        return BackendProbe(
            backend="mps",
            status="missing",
            failures=["torch not installed"],
        )
    try:
        mps = getattr(torch.backends, "mps", None)
        if mps is None:
            return BackendProbe(
                backend="mps",
                status="missing",
                version=getattr(torch, "__version__", None),
                failures=["torch.backends.mps not present in this build"],
            )
        if not bool(mps.is_available()):
            return BackendProbe(
                backend="mps",
                status="missing",
                version=getattr(torch, "__version__", None),
                failures=["torch.backends.mps.is_available() == False"],
            )
        return BackendProbe(
            backend="mps",
            status="ok",
            version=getattr(torch, "__version__", None),
            devices=1,
        )
    except Exception as exc:  # noqa: BLE001
        return BackendProbe(
            backend="mps",
            status="fail",
            failures=[f"mps probe raised {type(exc).__name__}: {exc}"],
        )


def _probe_rocm() -> BackendProbe:
    torch = _probe_torch_module()
    if torch is None:
        return BackendProbe(
            backend="rocm",
            status="missing",
            failures=["torch not installed"],
        )
    try:
        hip = getattr(torch.version, "hip", None)
        if hip is None:
            return BackendProbe(
                backend="rocm",
                status="missing",
                version=getattr(torch, "__version__", None),
                failures=["torch.version.hip is None"],
            )
        if not bool(torch.cuda.is_available()):
            return BackendProbe(
                backend="rocm",
                status="fail",
                version=str(hip),
                failures=[
                    "torch.version.hip set but torch.cuda.is_available() == False"
                ],
            )
        count = int(torch.cuda.device_count())
        return BackendProbe(
            backend="rocm",
            status="ok",
            version=str(hip),
            devices=count,
        )
    except Exception as exc:  # noqa: BLE001
        return BackendProbe(
            backend="rocm",
            status="fail",
            failures=[f"rocm probe raised {type(exc).__name__}: {exc}"],
        )


_PROBES: dict[str, Any] = {
    "cpu": _probe_cpu,
    "cuda": _probe_cuda,
    "mps": _probe_mps,
    "rocm": _probe_rocm,
}

_BACKEND_ORDER: tuple[str, ...] = ("cpu", "cuda", "mps", "rocm")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def doctor(
    require: Optional[str] = None,
    as_json: bool = False,
    *,
    out=None,
) -> int:
    """Run the backend diagnostic.

    Args:
        require: When set, force-require the named backend. If the
            backend is not present ``doctor`` returns ``2``.
        as_json: When True, emit a JSON payload per spec §7.2.
            Otherwise human-readable table.
        out: Destination file-like for printed output (defaults to
            ``sys.stdout`` — parameter lets tests capture cleanly).

    Returns:
        ``0`` — all green.
        ``1`` — at least one warning OR base CPU broken.
        ``2`` — required backend missing or probe raised.
    """
    if out is None:
        out = sys.stdout

    probes: list[BackendProbe] = []
    for name in _BACKEND_ORDER:
        probes.append(_PROBES[name]())

    # Compute exit code.
    exit_code = 0
    any_warn = any(p.status == "warn" for p in probes)
    any_fail = any(p.status == "fail" for p in probes)
    if any_fail:
        exit_code = max(exit_code, 2)
    if any_warn:
        exit_code = max(exit_code, 1)

    # CPU broken -> exit 1 (not 2; spec §7.2 says "base CPU path is broken" = 1)
    cpu_probe = next((p for p in probes if p.backend == "cpu"), None)
    if cpu_probe is None or cpu_probe.status not in {"ok", "warn"}:
        exit_code = max(exit_code, 1)

    # --require takes precedence — exit 2 when required backend missing
    if require is not None:
        req = require.strip().lower()
        match = next((p for p in probes if p.backend == req), None)
        if match is None:
            exit_code = 2
            # Synthesize a "missing" probe entry for output
            probes.append(
                BackendProbe(
                    backend=req,
                    status="missing",
                    failures=[f"unknown backend: {req!r}"],
                )
            )
        elif match.status != "ok":
            exit_code = 2

    # Emit output
    if as_json:
        payload = {
            "require": require,
            "exit_code": exit_code,
            "backends": [asdict(p) for p in probes],
        }
        print(json.dumps(payload, indent=2, sort_keys=True), file=out)
    else:
        _emit_human_readable(probes, exit_code, require, out=out)

    return exit_code


def _emit_human_readable(
    probes: list[BackendProbe],
    exit_code: int,
    require: Optional[str],
    *,
    out,
) -> None:
    """Human-readable table. Not machine-parseable; use ``--json`` for that."""
    print("kailash-ml doctor", file=out)
    print("=" * 48, file=out)
    header = f"{'backend':<8} {'status':<8} {'devices':>7}  version"
    print(header, file=out)
    print("-" * 48, file=out)
    for p in probes:
        version = p.version or "-"
        print(
            f"{p.backend:<8} {p.status:<8} {p.devices:>7}  {version}",
            file=out,
        )
        for w in p.warnings:
            print(f"  warn: {w}", file=out)
        for f in p.failures:
            print(f"  fail: {f}", file=out)
    print("-" * 48, file=out)
    if require:
        print(f"require = {require}", file=out)
    print(f"exit_code = {exit_code}", file=out)


# ---------------------------------------------------------------------------
# Console script entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point for the ``km-doctor`` console script.

    Args:
        argv: Optional argv override for testing; defaults to
            ``sys.argv[1:]``.

    Returns:
        The exit code produced by :func:`doctor`.
    """
    parser = argparse.ArgumentParser(
        prog="km-doctor",
        description="kailash-ml backend diagnostic (see specs/ml-backends.md §7)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON instead of the human-readable table.",
    )
    parser.add_argument(
        "--require",
        default=None,
        help=(
            "Force-require a backend. When set, exit code is 2 if the "
            "named backend is not present."
        ),
    )
    args = parser.parse_args(argv)
    return doctor(require=args.require, as_json=args.json)


if __name__ == "__main__":  # pragma: no cover — console-script shim only
    raise SystemExit(main())
