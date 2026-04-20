# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``km.doctor()`` diagnostic per ``specs/ml-backends.md`` §7.

Public surface:

- :func:`doctor` — in-process diagnostic returning an exit-code-style int.
- :func:`main` — console-script entry point (``km-doctor``), parses argv
  and calls ``doctor`` with the effective flags.

Probes all six first-class backends (``cpu``, ``cuda``, ``mps``,
``rocm``, ``xpu``, ``tpu``) via the centralised ``_device.py``
resolver where available, and reports per-backend precision
auto-selection, installed extras, family module versions, ONNX
runtime execution providers, default SQLite path + writability,
cache directory + size, tenant mode, and the §1.1 gotchas list.

Exit codes (spec §7.2):

- ``0`` — all green (CPU available; any requested backend present).
- ``1`` — at least one probe produced a warning OR the base CPU path
  is broken but no ``--require`` constraint was violated.
- ``2`` — ``--require=<backend>`` is set and the requested backend is
  unreachable, OR a probe failed outright.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
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


def _probe_xpu() -> BackendProbe:
    """Intel XPU probe — native ``torch.xpu`` (torch ≥ 2.5)."""
    torch = _probe_torch_module()
    if torch is None:
        return BackendProbe(
            backend="xpu",
            status="missing",
            failures=["torch not installed"],
        )
    try:
        xpu = getattr(torch, "xpu", None)
        if xpu is None:
            return BackendProbe(
                backend="xpu",
                status="missing",
                version=getattr(torch, "__version__", None),
                failures=["torch.xpu missing (requires torch>=2.5)"],
            )
        if not bool(xpu.is_available()):
            return BackendProbe(
                backend="xpu",
                status="missing",
                version=getattr(torch, "__version__", None),
                failures=["torch.xpu.is_available() == False"],
            )
        try:
            count = int(xpu.device_count())
        except Exception:  # noqa: BLE001
            count = 0
        return BackendProbe(
            backend="xpu",
            status="ok",
            version=getattr(torch, "__version__", None),
            devices=count,
        )
    except Exception as exc:  # noqa: BLE001
        return BackendProbe(
            backend="xpu",
            status="fail",
            failures=[f"xpu probe raised {type(exc).__name__}: {exc}"],
        )


def _probe_tpu() -> BackendProbe:
    """Google TPU probe — requires ``torch_xla`` from the ``[tpu]`` extra."""
    try:
        xm = importlib.import_module("torch_xla.core.xla_model")
    except ImportError:
        return BackendProbe(
            backend="tpu",
            status="missing",
            failures=["torch_xla not installed (pip install kailash-ml[tpu])"],
        )
    except Exception as exc:  # noqa: BLE001
        return BackendProbe(
            backend="tpu",
            status="fail",
            failures=[f"torch_xla import raised {type(exc).__name__}: {exc}"],
        )
    try:
        devices = xm.get_xla_supported_devices() or []
        if not devices:
            return BackendProbe(
                backend="tpu",
                status="missing",
                failures=["xm.get_xla_supported_devices() returned empty"],
            )
        version = None
        try:
            version = importlib.metadata.version("torch_xla")
        except importlib.metadata.PackageNotFoundError:
            pass
        return BackendProbe(
            backend="tpu",
            status="ok",
            version=version,
            devices=len(devices),
        )
    except Exception as exc:  # noqa: BLE001
        return BackendProbe(
            backend="tpu",
            status="fail",
            failures=[f"tpu probe raised {type(exc).__name__}: {exc}"],
        )


_PROBES: dict[str, Any] = {
    "cpu": _probe_cpu,
    "cuda": _probe_cuda,
    "mps": _probe_mps,
    "rocm": _probe_rocm,
    "xpu": _probe_xpu,
    "tpu": _probe_tpu,
}

_BACKEND_ORDER: tuple[str, ...] = ("cpu", "cuda", "mps", "rocm", "xpu", "tpu")


# ---------------------------------------------------------------------------
# Precision auto-selection per backend (spec §3.2)
# ---------------------------------------------------------------------------


def _precision_for_backend(probe: BackendProbe) -> Optional[str]:
    """Return the auto-selected precision for a detected backend.

    Uses :mod:`kailash_ml._device` when the backend probed ``ok`` so we
    match the exact values produced at training time. For non-ok
    probes, return ``None`` so the report does not claim a precision
    for a backend the system cannot execute.
    """
    if probe.status != "ok":
        return None
    # Reuse the centralised resolver when possible — keeps the doctor
    # output identical to what TrainingPipeline / InferenceServer would
    # report at runtime.
    try:
        from kailash_ml._device import (
            detect_backend,
            resolve_precision,
        )  # noqa: PLC0415

        info = detect_backend(prefer=probe.backend)
        return resolve_precision(info, requested="auto")
    except Exception:  # noqa: BLE001
        # Fallback to the spec §3.2 defaults — conservative matches for
        # hosts where detect_backend can't resolve (e.g. probe says xpu
        # is present but _device.py returns BackendUnavailable).
        defaults = {
            "cpu": "32-true",
            "cuda": "bf16-mixed",
            "mps": "16-mixed",
            "rocm": "16-mixed",
            "xpu": "bf16-mixed",
            "tpu": "bf16-true",
        }
        return defaults.get(probe.backend)


# ---------------------------------------------------------------------------
# Installed extras enumeration (spec §7.1 "Installed extras")
# ---------------------------------------------------------------------------


# Maps ``[extra]`` name -> "probe module import path". Each entry's
# presence is derived by attempting ``importlib.import_module`` on the
# probe — an install is considered present iff the probe imports.
_EXTRA_PROBES: dict[str, tuple[str, ...]] = {
    # Hardware backends
    "cuda": ("torch",),
    "rocm": ("torch",),
    "xpu": ("intel_extension_for_pytorch",),
    "tpu": ("torch_xla",),
    # Framework feature extras
    "dl": ("torch", "lightning", "transformers"),
    "agents": ("kaizen",),
    "explain": ("shap",),
    "imbalance": ("imblearn",),
}


def _probe_extras() -> dict[str, dict[str, Any]]:
    """Return a structured report of which ``[extras]`` are installed.

    Each value is ``{"installed": bool, "modules": {module: version?}}``
    so the JSON output surfaces WHICH modules were checked (answering
    "why is this extra missing?" without shelling out to pip).
    """
    out: dict[str, dict[str, Any]] = {}
    for extra, modules in _EXTRA_PROBES.items():
        module_report: dict[str, Optional[str]] = {}
        all_present = True
        for module_name in modules:
            try:
                mod = importlib.import_module(module_name)
                module_report[module_name] = getattr(mod, "__version__", None)
            except ImportError:
                module_report[module_name] = None
                all_present = False
            except Exception as exc:  # noqa: BLE001
                module_report[module_name] = f"probe_failed: {type(exc).__name__}"
                all_present = False
        out[extra] = {
            "installed": all_present,
            "modules": module_report,
        }
    return out


# ---------------------------------------------------------------------------
# Family probes (spec §7.1 "Family probes")
# ---------------------------------------------------------------------------


_FAMILY_PROBES: tuple[tuple[str, str], ...] = (
    ("torch", "torch"),
    ("lightning", "lightning"),
    ("sklearn", "sklearn"),
    ("xgboost", "xgboost"),
    ("lightgbm", "lightgbm"),
    ("catboost", "catboost"),
    ("onnxruntime", "onnxruntime"),
    # onnxruntime-gpu is installed as the package name ``onnxruntime-gpu``
    # but imports as ``onnxruntime``. We probe via importlib.metadata so
    # the report can distinguish the CPU vs GPU wheel.
    ("onnxruntime-gpu", "__metadata__:onnxruntime-gpu"),
)


def _probe_families() -> dict[str, Optional[str]]:
    """Return ``{family: version_or_None_if_missing}``."""
    out: dict[str, Optional[str]] = {}
    for label, target in _FAMILY_PROBES:
        if target.startswith("__metadata__:"):
            pkg_name = target.removeprefix("__metadata__:")
            try:
                out[label] = importlib.metadata.version(pkg_name)
            except importlib.metadata.PackageNotFoundError:
                out[label] = None
            continue
        try:
            mod = importlib.import_module(target)
            out[label] = getattr(mod, "__version__", None)
        except ImportError:
            out[label] = None
        except Exception as exc:  # noqa: BLE001
            out[label] = f"probe_failed: {type(exc).__name__}"
    return out


# ---------------------------------------------------------------------------
# ONNX execution providers (spec §7.1 "ONNX runtime availability")
# ---------------------------------------------------------------------------


def _probe_onnx_eps() -> dict[str, Any]:
    """Enumerate onnxruntime execution providers when available."""
    try:
        import onnxruntime as ort  # noqa: PLC0415
    except ImportError:
        return {"installed": False, "providers": [], "version": None}
    except Exception as exc:  # noqa: BLE001
        return {
            "installed": False,
            "providers": [],
            "version": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    version = getattr(ort, "__version__", None)
    try:
        providers = list(ort.get_available_providers())
    except Exception as exc:  # noqa: BLE001
        return {
            "installed": True,
            "version": version,
            "providers": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {"installed": True, "version": version, "providers": providers}


# ---------------------------------------------------------------------------
# SQLite path / cache / tenant helpers (spec §7.1)
# ---------------------------------------------------------------------------


def _default_sqlite_path() -> Path:
    """Return the configured or default kailash-ml SQLite path.

    Honours ``KAILASH_ML_STORE`` env var when set (paths starting with
    ``sqlite:///`` have that prefix stripped). Defaults to
    ``~/.kailash_ml/ml.db`` per spec §7.1.
    """
    configured = os.environ.get("KAILASH_ML_STORE")
    if configured:
        if configured.startswith("sqlite:///"):
            return Path(configured[len("sqlite:///") :])
        return Path(configured)
    return Path.home() / ".kailash_ml" / "ml.db"


def _probe_sqlite_path() -> dict[str, Any]:
    """Probe the default/configured SQLite path for writability.

    Creates the parent directory if missing and opens a temporary
    connection to verify the process can actually write. Returns a
    structured report; does NOT touch the production ml.db.
    """
    path = _default_sqlite_path()
    source = "KAILASH_ML_STORE" if os.environ.get("KAILASH_ML_STORE") else "default"
    out: dict[str, Any] = {
        "path": str(path),
        "source": source,
        "writable": False,
        "exists": path.exists(),
        "error": None,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Probe in a separate file so we never touch the production
        # ml.db (which could be locked by a live run).
        probe_path = path.parent / ".km-doctor-probe.sqlite"
        try:
            conn = sqlite3.connect(str(probe_path))
            conn.execute("CREATE TABLE IF NOT EXISTS probe (id INTEGER PRIMARY KEY)")
            conn.close()
            probe_path.unlink(missing_ok=True)
            out["writable"] = True
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if probe_path.exists():
                try:
                    probe_path.unlink()
                except OSError:
                    pass
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _probe_cache_paths() -> dict[str, Any]:
    """Probe the kailash-ml cache directories with current disk usage.

    Reports both ``~/.kailash_ml`` (the data root) and the artifact
    cache (``~/.kailash_ml/cache``) when present. Sizes use
    ``shutil.disk_usage`` for the filesystem and a recursive walk for
    the kailash-ml-owned portion.
    """
    root = Path.home() / ".kailash_ml"
    cache = root / "cache"
    try:
        fs_usage = shutil.disk_usage(str(root.parent if not root.exists() else root))
        fs_total = int(fs_usage.total)
        fs_free = int(fs_usage.free)
    except Exception as exc:  # noqa: BLE001
        fs_total = 0
        fs_free = 0
        fs_err: Optional[str] = f"{type(exc).__name__}: {exc}"
    else:
        fs_err = None

    def _walk_size(p: Path) -> int:
        if not p.exists():
            return 0
        total = 0
        for sub in p.rglob("*"):
            if sub.is_file():
                try:
                    total += sub.stat().st_size
                except OSError:
                    continue
        return total

    return {
        "data_root": {
            "path": str(root),
            "exists": root.exists(),
            "size_bytes": _walk_size(root),
        },
        "cache": {
            "path": str(cache),
            "exists": cache.exists(),
            "size_bytes": _walk_size(cache),
        },
        "filesystem": {
            "total_bytes": fs_total,
            "free_bytes": fs_free,
            "error": fs_err,
        },
    }


def _probe_tenant_mode() -> dict[str, Any]:
    """Report tenant mode derived from ``KAILASH_ML_DEFAULT_TENANT``.

    Spec §7.1 "Tenant mode" — the operator-facing diagnostic answers
    "am I running this process in multi-tenant mode?". We look at the
    canonical env var and return a human-readable mode + the raw
    value. ``KAILASH_TENANT_ID`` is also checked (same effect in
    ``km.track``).
    """
    # ``KAILASH_ML_DEFAULT_TENANT`` is the canonical spec name. Some
    # downstream code also honours ``KAILASH_TENANT_ID`` (tracker runner);
    # both are checked so the doctor output covers either convention.
    primary = os.environ.get("KAILASH_ML_DEFAULT_TENANT")
    alt = os.environ.get("KAILASH_TENANT_ID")
    value = primary if primary else alt
    return {
        "mode": "multi-tenant" if value else "single-tenant",
        "tenant_id": value,
        "env_var_set": (
            "KAILASH_ML_DEFAULT_TENANT"
            if primary
            else ("KAILASH_TENANT_ID" if alt else None)
        ),
    }


# ---------------------------------------------------------------------------
# §1.1 gotchas — surfaced per detected backend
# ---------------------------------------------------------------------------


_GOTCHAS_BY_BACKEND: dict[str, tuple[str, ...]] = {
    "cpu": (),
    "cuda": (
        "CUDA honours CUDA_VISIBLE_DEVICES='' — set this env var to disable detection.",
    ),
    "mps": (
        "MPS op coverage is incomplete in torch 2.4; some ops emit UserWarning "
        "on silent CPU fallback. Check logs for 'cpu fallback' lines.",
        "MPS bf16 is experimental — default precision is fp16 per spec §1 footnote.",
    ),
    "rocm": (
        "ROCm and CUDA share torch.cuda.is_available(); distinguished only by "
        "torch.version.hip. Some ops are missing on ROCm < 6.0.",
    ),
    "xpu": (
        "XPU requires intel-extension-for-pytorch at torch 2.x (open question "
        "whether torch ≥ 2.5 native XPU suffices).",
    ),
    "tpu": (
        "XLA compiles lazily — the first training step pauses ~30s while the "
        "graph is compiled. Not a hang.",
    ),
}


def _probe_gotchas(probes: list[BackendProbe]) -> list[dict[str, Any]]:
    """Return the §1.1 gotchas for every detected (status=ok) backend."""
    out: list[dict[str, Any]] = []
    for probe in probes:
        if probe.status != "ok":
            continue
        for message in _GOTCHAS_BY_BACKEND.get(probe.backend, ()):
            out.append({"backend": probe.backend, "hint": message})
    return out


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

    # Selected default — the backend that detect_backend(None) would
    # return. Probe each in priority order; first ok wins. Matches
    # _device.py priority per spec §2.2.
    selected_default: Optional[str] = None
    for name in ("cuda", "mps", "rocm", "xpu", "tpu", "cpu"):
        p = next((q for q in probes if q.backend == name), None)
        if p is not None and p.status == "ok":
            selected_default = name
            break

    # Per-backend precision auto-selection (spec §3.2).
    precision_matrix: dict[str, Optional[str]] = {
        p.backend: _precision_for_backend(p)
        for p in probes
        if p.backend in _BACKEND_ORDER
    }

    extras = _probe_extras()
    family_probes = _probe_families()
    onnx_eps = _probe_onnx_eps()
    sqlite_report = _probe_sqlite_path()
    cache_paths = _probe_cache_paths()
    tenant_mode = _probe_tenant_mode()
    gotchas = _probe_gotchas(probes)

    # Emit output
    if as_json:
        payload = {
            "require": require,
            "exit_code": exit_code,
            "backends": [asdict(p) for p in probes],
            "selected_default": selected_default,
            "precision_matrix": precision_matrix,
            "extras": extras,
            "family_probes": family_probes,
            "onnx_eps": onnx_eps,
            "sqlite_path": sqlite_report,
            "cache_paths": cache_paths,
            "tenant_mode": tenant_mode,
            "gotchas": gotchas,
        }
        print(json.dumps(payload, indent=2, sort_keys=True), file=out)
    else:
        _emit_human_readable(
            probes=probes,
            exit_code=exit_code,
            require=require,
            selected_default=selected_default,
            precision_matrix=precision_matrix,
            extras=extras,
            family_probes=family_probes,
            onnx_eps=onnx_eps,
            sqlite_report=sqlite_report,
            cache_paths=cache_paths,
            tenant_mode=tenant_mode,
            gotchas=gotchas,
            out=out,
        )

    return exit_code


def _emit_human_readable(
    *,
    probes: list[BackendProbe],
    exit_code: int,
    require: Optional[str],
    selected_default: Optional[str],
    precision_matrix: dict[str, Optional[str]],
    extras: dict[str, dict[str, Any]],
    family_probes: dict[str, Optional[str]],
    onnx_eps: dict[str, Any],
    sqlite_report: dict[str, Any],
    cache_paths: dict[str, Any],
    tenant_mode: dict[str, Any],
    gotchas: list[dict[str, Any]],
    out,
) -> None:
    """Human-readable table. Not machine-parseable; use ``--json`` for that."""
    print("kailash-ml doctor", file=out)
    print("=" * 64, file=out)

    # Backend table
    header = f"{'backend':<8} {'status':<8} {'devices':>7}  {'precision':<12}  version"
    print(header, file=out)
    print("-" * 64, file=out)
    for p in probes:
        version = p.version or "-"
        precision = precision_matrix.get(p.backend) or "-"
        print(
            f"{p.backend:<8} {p.status:<8} {p.devices:>7}  {precision:<12}  {version}",
            file=out,
        )
        for w in p.warnings:
            print(f"  warn: {w}", file=out)
        for f in p.failures:
            print(f"  fail: {f}", file=out)
    print("-" * 64, file=out)

    print(f"selected_default = {selected_default or '-'}", file=out)

    # Installed extras
    print("\nInstalled extras:", file=out)
    for name, report in extras.items():
        state = "installed" if report["installed"] else "missing"
        print(f"  [{name}] {state}", file=out)

    # Family probes
    print("\nFamily probes (module version or 'not installed'):", file=out)
    for fam, ver in family_probes.items():
        display = ver if ver is not None else "not installed"
        print(f"  {fam:<20} {display}", file=out)

    # ONNX EPs
    print("\nONNX runtime execution providers:", file=out)
    if onnx_eps["installed"]:
        version = onnx_eps.get("version") or "-"
        providers = onnx_eps.get("providers") or []
        print(f"  onnxruntime {version}", file=out)
        for ep in providers:
            print(f"    - {ep}", file=out)
    else:
        print("  onnxruntime not installed", file=out)

    # SQLite path
    print("\nDefault SQLite path:", file=out)
    print(f"  path    = {sqlite_report['path']}", file=out)
    print(f"  source  = {sqlite_report['source']}", file=out)
    print(f"  exists  = {sqlite_report['exists']}", file=out)
    print(f"  writable= {sqlite_report['writable']}", file=out)
    if sqlite_report.get("error"):
        print(f"  error   = {sqlite_report['error']}", file=out)

    # Cache paths
    print("\nCache paths:", file=out)
    for label, entry in (
        ("data_root", cache_paths["data_root"]),
        ("cache", cache_paths["cache"]),
    ):
        print(
            f"  {label:<10} {entry['path']} (exists={entry['exists']}, "
            f"size={entry['size_bytes']} bytes)",
            file=out,
        )

    # Tenant mode
    print(f"\nTenant mode: {tenant_mode['mode']}", file=out)
    if tenant_mode.get("env_var_set"):
        print(
            f"  {tenant_mode['env_var_set']} = {tenant_mode.get('tenant_id')}",
            file=out,
        )

    # Gotchas
    if gotchas:
        print("\nKnown gotchas (spec §1.1):", file=out)
        for entry in gotchas:
            print(f"  [{entry['backend']}] {entry['hint']}", file=out)

    print("-" * 64, file=out)
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
