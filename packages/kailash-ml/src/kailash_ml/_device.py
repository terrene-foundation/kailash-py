# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Backend / device / precision resolver (kailash-ml 2.0 Phase 2).

Implements `specs/ml-backends.md` §2 (priority resolver), §3 (precision
auto-selection), §8 (typed error hierarchy). This is the SOLE detection
point for the compute backend — every engine that places tensors, invokes
a Trainer, or serves inference MUST route through `detect_backend()`.

The resolver is graceful: if `torch` is not importable (base install with
no DL extras) it still returns a valid `BackendInfo(backend="cpu", ...)`.
No ImportError escapes to the caller.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

__all__ = [
    "BackendInfo",
    "BackendError",
    "BackendUnavailable",
    "UnsupportedFamily",
    "PrecisionUnsupported",
    "detect_backend",
    "resolve_precision",
    "KNOWN_BACKENDS",
]

logger = logging.getLogger(__name__)

# Priority order per ml-backends.md §2.2. Exposed as a module constant so
# future sessions can introduce a user-configurable override without
# hunting through the resolver body.
KNOWN_BACKENDS: tuple[str, ...] = ("cuda", "mps", "rocm", "xpu", "tpu", "cpu")

BackendName = Literal["cpu", "cuda", "mps", "rocm", "xpu", "tpu"]


# ---------------------------------------------------------------------------
# Error hierarchy (ml-backends.md §8.1)
# ---------------------------------------------------------------------------


class BackendError(RuntimeError):
    """Base class for all backend-selection errors."""


class BackendUnavailable(BackendError):
    """Requested backend is not present in the current environment.

    Per ml-backends.md §8.2 this carries: requested, detected_backends,
    install_hint, diagnostic_source.
    """

    def __init__(
        self,
        message: str,
        *,
        requested: Optional[str] = None,
        detected_backends: Optional[tuple[str, ...]] = None,
        install_hint: Optional[str] = None,
        diagnostic_source: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.requested = requested
        self.detected_backends = detected_backends or ()
        self.install_hint = install_hint
        self.diagnostic_source = diagnostic_source


class UnsupportedFamily(BackendError):
    """The requested family cannot run on the requested backend.

    Per ml-backends.md §8.2 this carries: family, backend,
    supported_backends_for_family.
    """

    def __init__(
        self,
        message: str,
        *,
        family: Optional[str] = None,
        backend: Optional[str] = None,
        supported_backends_for_family: Optional[tuple[str, ...]] = None,
    ) -> None:
        super().__init__(message)
        self.family = family
        self.backend = backend
        self.supported_backends_for_family = supported_backends_for_family or ()


class PrecisionUnsupported(BackendError):
    """The requested precision is not supported by the detected hardware.

    Per ml-backends.md §8.2 this carries: requested_precision,
    device_string, cuda_capability, supported_precisions,
    suggested_precision.
    """

    def __init__(
        self,
        message: str,
        *,
        requested_precision: Optional[str] = None,
        device_string: Optional[str] = None,
        cuda_capability: Optional[tuple[int, int]] = None,
        supported_precisions: Optional[tuple[str, ...]] = None,
        suggested_precision: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.requested_precision = requested_precision
        self.device_string = device_string
        self.cuda_capability = cuda_capability
        self.supported_precisions = supported_precisions or ()
        self.suggested_precision = suggested_precision


# ---------------------------------------------------------------------------
# BackendInfo (ml-backends.md §2.4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackendInfo:
    """Resolved backend state carrying decision evidence.

    Every field is derived from runtime probes; nothing is hard-coded per
    vendor. See ml-backends.md §2.4 for the contract.
    """

    backend: BackendName
    accelerator: str  # Lightning accelerator ("cuda", "mps", "tpu", "cpu")
    device_string: str  # torch device string ("cuda:0", "mps", "xpu:0", "cpu")
    device_count: int
    devices: object = "auto"  # Lightning `devices=` (int | list[int] | "auto")
    capabilities: frozenset[str] = field(default_factory=frozenset)
    diagnostic_source: str = ""
    rocm_version: Optional[str] = None
    xpu_via_ipex: Optional[bool] = None
    cuda_capability: Optional[tuple[int, int]] = None
    # Precision auto-selected for this backend; populated by
    # detect_backend() for convenience and echoed by resolve_precision()
    # when requested="auto".
    precision: str = "32-true"


# ---------------------------------------------------------------------------
# Probes
#
# All probes are defensive: each runs inside a try/except so a broken
# extension (e.g. a half-installed torch_xla) cannot take down
# detect_backend(). A failed probe records `available=False` with the
# failure reason in the diagnostic_source string.
# ---------------------------------------------------------------------------


def _probe_torch() -> tuple[Optional[object], Optional[str]]:
    """Import torch; return (module_or_None, version_or_None).

    Graceful: returns (None, None) if torch is not installed. No
    ImportError propagates — a base install (no DL extras) still yields a
    valid BackendInfo via the CPU fallback.
    """
    try:
        import torch  # noqa: PLC0415
    except ImportError:
        return None, None
    return torch, getattr(torch, "__version__", None)


def _probe_cuda(torch: object) -> tuple[bool, str]:
    """Return (available, diagnostic_source)."""
    try:
        is_avail = bool(torch.cuda.is_available())  # type: ignore[attr-defined]
        hip = getattr(torch.version, "hip", None)  # type: ignore[attr-defined]
        if is_avail and hip is None:
            return True, "torch.cuda.is_available"
        return False, "torch.cuda.is_available=false"
    except Exception as exc:  # noqa: BLE001 — probe MUST NOT raise
        return False, f"torch.cuda.probe_failed:{type(exc).__name__}"


def _probe_mps(torch: object) -> tuple[bool, str]:
    try:
        backends_mps = getattr(torch.backends, "mps", None)  # type: ignore[attr-defined]
        if backends_mps is None:
            return False, "torch.backends.mps.missing"
        if not backends_mps.is_available():
            return False, "torch.backends.mps.is_available=false"
        if not backends_mps.is_built():
            return False, "torch.backends.mps.is_built=false"
        return True, "torch.backends.mps.is_available+is_built"
    except Exception as exc:  # noqa: BLE001
        return False, f"torch.backends.mps.probe_failed:{type(exc).__name__}"


def _probe_rocm(torch: object) -> tuple[bool, str, Optional[str]]:
    """Return (available, diagnostic_source, rocm_version)."""
    try:
        hip = getattr(torch.version, "hip", None)  # type: ignore[attr-defined]
        if hip is None:
            return False, "torch.version.hip=None", None
        if not torch.cuda.is_available():  # type: ignore[attr-defined]
            return False, "torch.cuda.is_available=false (hip set)", hip
        return True, "torch.version.hip+torch.cuda.is_available", hip
    except Exception as exc:  # noqa: BLE001
        return False, f"torch.version.hip.probe_failed:{type(exc).__name__}", None


def _probe_xpu(torch: object) -> tuple[bool, str]:
    """XPU native probe.

    Per ml-backends.md §1.1 we intentionally do NOT fall back to
    intel-extension-for-pytorch. Native `torch.xpu` requires torch ≥ 2.5;
    on older torch versions or hosts without Intel GPU support, XPU is
    unavailable.
    """
    try:
        xpu = getattr(torch, "xpu", None)
        if xpu is None:
            return False, "torch.xpu.missing (requires torch>=2.5)"
        if not xpu.is_available():
            return False, "torch.xpu.is_available=false"
        return True, "torch.xpu.is_available"
    except Exception as exc:  # noqa: BLE001
        return False, f"torch.xpu.probe_failed:{type(exc).__name__}"


def _probe_tpu() -> tuple[bool, str]:
    """Probe torch_xla for TPU availability.

    torch_xla is a separate package; importable only when the `[tpu]`
    extra is installed.
    """
    try:
        import torch_xla.core.xla_model as xm  # type: ignore[import]  # noqa: PLC0415
    except ImportError:
        return False, "torch_xla.import_failed"
    except Exception as exc:  # noqa: BLE001
        return False, f"torch_xla.probe_failed:{type(exc).__name__}"
    try:
        devices = xm.get_xla_supported_devices() or []
        if devices:
            return True, "torch_xla.get_xla_supported_devices"
        return False, "torch_xla.get_xla_supported_devices=[]"
    except Exception as exc:  # noqa: BLE001
        return False, f"torch_xla.devices.probe_failed:{type(exc).__name__}"


def _cuda_capability(torch: object, index: int = 0) -> Optional[tuple[int, int]]:
    """Return (major, minor) compute capability for CUDA device `index`."""
    try:
        cap = torch.cuda.get_device_capability(index)  # type: ignore[attr-defined]
        return (int(cap[0]), int(cap[1]))
    except Exception:  # noqa: BLE001
        return None


def _cuda_device_count(torch: object) -> int:
    try:
        return int(torch.cuda.device_count())  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return 0


def _xpu_device_count(torch: object) -> int:
    try:
        return int(torch.xpu.device_count())  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return 0


def _capabilities_for_cuda(
    cap: Optional[tuple[int, int]],
) -> frozenset[str]:
    """Derive fp16/bf16/int8/distributed capabilities from CC.

    Per ml-backends.md §1 footnotes: bf16 requires CC ≥ 8.0 (Ampere+);
    V100 (7.0) and T4 (7.5) support fp16 but NOT bf16.
    """
    caps: set[str] = {"int8", "distributed"}
    if cap is None:
        # Unknown CC — conservative: assume fp16 only (Volta/Turing class).
        caps.add("fp16")
        return frozenset(caps)
    major = cap[0]
    if major >= 7:
        caps.add("fp16")
    if major >= 8:
        caps.add("bf16")
    return frozenset(caps)


def _capabilities_for_mps() -> frozenset[str]:
    # Per ml-backends.md §1: fp32 + fp16 (bf16 experimental, int8 N/A at 2.0).
    return frozenset({"fp16"})


def _capabilities_for_rocm(cap: Optional[tuple[int, int]]) -> frozenset[str]:
    # Conservative: treat as CUDA-equivalent for capability derivation.
    return _capabilities_for_cuda(cap)


def _capabilities_for_xpu() -> frozenset[str]:
    # Conservative: fp16 guaranteed; bf16 presence probed via precision step.
    return frozenset({"fp16", "bf16", "int8"})


def _capabilities_for_tpu() -> frozenset[str]:
    # TPU XLA supports bf16 natively; fp16 not typical; int8 limited.
    return frozenset({"bf16"})


def _capabilities_for_cpu() -> frozenset[str]:
    # CPU int8 via torch quantization; fp16/bf16 autocast exists but is
    # slower than fp32 on most CPUs (§1 footnote *).
    return frozenset({"int8"})


# ---------------------------------------------------------------------------
# Precision resolver (ml-backends.md §3)
# ---------------------------------------------------------------------------


def _auto_precision_for(info: BackendInfo) -> str:
    """Resolve `precision="auto"` to a concrete Lightning string.

    See ml-backends.md §3.2 for the auto-selection table.
    """
    if info.backend == "cuda":
        if info.cuda_capability is None:
            # Unknown CC — default conservative fp32.
            return "32-true"
        major = info.cuda_capability[0]
        if major >= 8:
            return "bf16-mixed"
        if major >= 7:
            return "16-mixed"
        return "32-true"
    if info.backend == "mps":
        # bf16 op coverage is incomplete (§1 footnote ***) — default fp16.
        return "16-mixed"
    if info.backend == "rocm":
        if info.cuda_capability is None:
            return "16-mixed"
        major = info.cuda_capability[0]
        if major >= 9:  # MI300-class and later
            return "bf16-mixed"
        if major >= 8:
            return "16-mixed"
        return "32-true"
    if info.backend == "xpu":
        # Native torch.xpu: bf16 supported on PVC-class; Arc-class falls
        # back to fp16. Without a device-line probe we default to
        # bf16-mixed (PVC is the datacenter target); Arc users who need
        # fp16 pass `precision="16-mixed"` explicitly.
        if "bf16" in info.capabilities:
            return "bf16-mixed"
        return "16-mixed"
    if info.backend == "tpu":
        return "bf16-true"
    # cpu — fp16/bf16 autocast is slower than fp32 on most CPUs.
    return "32-true"


def resolve_precision(info: BackendInfo, requested: str = "auto") -> str:
    """Resolve `requested` precision against a detected `BackendInfo`.

    `requested="auto"` returns the auto-selected precision for the
    backend. Explicit requests are validated against the backend's
    capabilities; unsupported combinations raise `PrecisionUnsupported`
    rather than silently downgrade (ml-backends.md §3.3).
    """
    valid_precisions = {
        "auto",
        "32-true",
        "64-true",
        "16-mixed",
        "16-true",
        "bf16-mixed",
        "bf16-true",
    }
    if requested not in valid_precisions:
        raise PrecisionUnsupported(
            f"Unknown precision '{requested}'. Valid: {sorted(valid_precisions)}.",
            requested_precision=requested,
            device_string=info.device_string,
            cuda_capability=info.cuda_capability,
            supported_precisions=tuple(sorted(valid_precisions - {"auto"})),
        )
    if requested == "auto":
        return _auto_precision_for(info)

    # Validate explicit requests against capabilities.
    if requested in ("bf16-mixed", "bf16-true") and "bf16" not in info.capabilities:
        suggested = "16-mixed" if "fp16" in info.capabilities else "32-true"
        raise PrecisionUnsupported(
            f"Requested precision '{requested}' but device "
            f"{info.device_string} (cuda_capability={info.cuda_capability}) "
            f"does not support bf16. Use precision='{suggested}' or 'auto'.",
            requested_precision=requested,
            device_string=info.device_string,
            cuda_capability=info.cuda_capability,
            supported_precisions=tuple(sorted(info.capabilities)),
            suggested_precision=suggested,
        )
    if requested in ("16-mixed", "16-true") and "fp16" not in info.capabilities:
        if info.backend == "cpu":
            suggested = "32-true"
        elif "bf16" in info.capabilities:
            suggested = "bf16-mixed"
        else:
            suggested = "32-true"
        raise PrecisionUnsupported(
            f"Requested precision '{requested}' but device "
            f"{info.device_string} does not support fp16 mixed/true. "
            f"Use precision='{suggested}' or 'auto'.",
            requested_precision=requested,
            device_string=info.device_string,
            cuda_capability=info.cuda_capability,
            supported_precisions=tuple(sorted(info.capabilities)),
            suggested_precision=suggested,
        )
    # fp32 / fp64 are universally supported — no further validation.
    return requested


# ---------------------------------------------------------------------------
# detect_backend (ml-backends.md §2.1)
# ---------------------------------------------------------------------------


def _build_cpu_info(reason: str) -> BackendInfo:
    info = BackendInfo(
        backend="cpu",
        accelerator="cpu",
        device_string="cpu",
        device_count=1,
        devices=1,
        capabilities=_capabilities_for_cpu(),
        diagnostic_source=reason,
        precision="32-true",
    )
    return info


def _build_cuda_info(torch: object) -> BackendInfo:
    count = _cuda_device_count(torch)
    cap = _cuda_capability(torch, 0) if count > 0 else None
    caps = _capabilities_for_cuda(cap)
    info = BackendInfo(
        backend="cuda",
        accelerator="cuda",
        device_string="cuda:0",
        device_count=count,
        devices=1,
        capabilities=caps,
        diagnostic_source="torch.cuda.is_available",
        cuda_capability=cap,
    )
    # Pre-compute precision so BackendInfo.precision is never "auto".
    return _with_precision(info)


def _build_mps_info() -> BackendInfo:
    info = BackendInfo(
        backend="mps",
        accelerator="mps",
        device_string="mps",
        device_count=1,
        devices=1,
        capabilities=_capabilities_for_mps(),
        diagnostic_source="torch.backends.mps.is_available+is_built",
    )
    return _with_precision(info)


def _build_rocm_info(torch: object, rocm_version: Optional[str]) -> BackendInfo:
    count = _cuda_device_count(torch)
    cap = _cuda_capability(torch, 0) if count > 0 else None
    caps = _capabilities_for_rocm(cap)
    info = BackendInfo(
        backend="rocm",
        accelerator="cuda",  # Lightning dispatches ROCm through the CUDA accelerator (HIP).
        device_string="cuda:0",
        device_count=count,
        devices=1,
        capabilities=caps,
        diagnostic_source="torch.version.hip+torch.cuda.is_available",
        rocm_version=rocm_version,
        cuda_capability=cap,
    )
    return _with_precision(info)


def _build_xpu_info(torch: object) -> BackendInfo:
    count = _xpu_device_count(torch)
    info = BackendInfo(
        backend="xpu",
        accelerator="xpu",
        device_string="xpu:0",
        device_count=count,
        devices=1,
        capabilities=_capabilities_for_xpu(),
        diagnostic_source="torch.xpu.is_available",
        xpu_via_ipex=False,  # Native torch.xpu only at 2.0 per spec §1.1.
    )
    return _with_precision(info)


def _build_tpu_info() -> BackendInfo:
    info = BackendInfo(
        backend="tpu",
        accelerator="tpu",
        device_string="xla:0",
        device_count=1,
        devices="auto",
        capabilities=_capabilities_for_tpu(),
        diagnostic_source="torch_xla.get_xla_supported_devices",
    )
    return _with_precision(info)


def _with_precision(info: BackendInfo) -> BackendInfo:
    """Attach the auto-selected precision to a BackendInfo.

    Frozen dataclasses require a replace-style rebuild.
    """
    precision = _auto_precision_for(info)
    return BackendInfo(
        backend=info.backend,
        accelerator=info.accelerator,
        device_string=info.device_string,
        device_count=info.device_count,
        devices=info.devices,
        capabilities=info.capabilities,
        diagnostic_source=info.diagnostic_source,
        rocm_version=info.rocm_version,
        xpu_via_ipex=info.xpu_via_ipex,
        cuda_capability=info.cuda_capability,
        precision=precision,
    )


_INSTALL_HINTS: dict[str, str] = {
    "cuda": "pip install kailash-ml[dl] plus NVIDIA GPU + CUDA driver",
    "mps": "Apple Silicon host with torch universal2 wheel (base install)",
    "rocm": "pip install torch --index-url https://download.pytorch.org/whl/rocm6.0 on AMD Instinct host",
    "xpu": "Intel Data Center GPU host with torch>=2.5 built-in XPU support",
    "tpu": "pip install torch_xla on a Google Cloud TPU VM",
    "cpu": "always available in the base install",
}


def _probe_all() -> dict[str, tuple[bool, str, Optional[str]]]:
    """Run every probe once; return a map of backend → (available, source, extra).

    `extra` holds rocm_version for rocm, None otherwise.
    """
    torch, _torch_version = _probe_torch()
    results: dict[str, tuple[bool, str, Optional[str]]] = {}
    if torch is None:
        results["cuda"] = (False, "torch.import_failed", None)
        results["mps"] = (False, "torch.import_failed", None)
        results["rocm"] = (False, "torch.import_failed", None)
        results["xpu"] = (False, "torch.import_failed", None)
    else:
        cuda_ok, cuda_src = _probe_cuda(torch)
        results["cuda"] = (cuda_ok, cuda_src, None)
        mps_ok, mps_src = _probe_mps(torch)
        results["mps"] = (mps_ok, mps_src, None)
        rocm_ok, rocm_src, rocm_ver = _probe_rocm(torch)
        results["rocm"] = (rocm_ok, rocm_src, rocm_ver)
        xpu_ok, xpu_src = _probe_xpu(torch)
        results["xpu"] = (xpu_ok, xpu_src, None)
    tpu_ok, tpu_src = _probe_tpu()
    results["tpu"] = (tpu_ok, tpu_src, None)
    results["cpu"] = (True, "always_available", None)
    return results


def detect_backend(prefer: Optional[str] = None) -> BackendInfo:
    """Resolve the compute backend to use for training/inference.

    Args:
        prefer: Backend name (one of KNOWN_BACKENDS), "auto", or None.
            `None` / `"auto"` triggers the priority-order resolver. An
            explicit backend name MUST be one of KNOWN_BACKENDS; passing
            an unknown string raises ValueError.

    Returns:
        BackendInfo with concrete backend, accelerator, device_string,
        device_count, capabilities, diagnostic_source, and pre-resolved
        precision.

    Raises:
        BackendUnavailable: if `prefer` names a known backend that is not
            present in the current environment (per ml-backends.md §2.3).
        ValueError: if `prefer` is a string outside KNOWN_BACKENDS
            and not "auto".
    """
    if prefer is not None and prefer != "auto" and prefer not in KNOWN_BACKENDS:
        raise ValueError(
            f"Unknown backend '{prefer}'. Valid: {list(KNOWN_BACKENDS)} or 'auto'."
        )

    probes = _probe_all()
    torch, _ = _probe_torch()
    detected_available = tuple(name for name, (ok, _, _) in probes.items() if ok)

    # Explicit preference: fail fast if unavailable (§2.3).
    if prefer is not None and prefer != "auto":
        available, source, extra = probes[prefer]
        if not available:
            raise BackendUnavailable(
                f"Requested backend '{prefer}' is not available. "
                f"Detected backends: {list(detected_available)}. "
                f"Install hint: {_INSTALL_HINTS.get(prefer, 'n/a')}. "
                f"Or use prefer='auto' to let the resolver pick the best "
                f"available backend.",
                requested=prefer,
                detected_backends=detected_available,
                install_hint=_INSTALL_HINTS.get(prefer),
                diagnostic_source=source,
            )
        info = _build_info_for(prefer, torch, extra)
        logger.info(
            "backend.selected",
            extra={
                "backend": info.backend,
                "accelerator": info.accelerator,
                "device_string": info.device_string,
                "devices": info.devices,
                "precision": info.precision,
                "diagnostic_source": info.diagnostic_source,
                "requested": prefer,
            },
        )
        return info

    # Auto: iterate priority order; return first available.
    for name in KNOWN_BACKENDS:
        available, _source, extra = probes[name]
        if available:
            info = _build_info_for(name, torch, extra)
            logger.info(
                "backend.selected",
                extra={
                    "backend": info.backend,
                    "accelerator": info.accelerator,
                    "device_string": info.device_string,
                    "devices": info.devices,
                    "precision": info.precision,
                    "diagnostic_source": info.diagnostic_source,
                    "requested": "auto",
                },
            )
            return info

    # KNOWN_BACKENDS includes "cpu" which always probes True, so this is
    # unreachable except when the probe map is corrupted — treat as a
    # defensive fallback rather than silent success.
    return _build_cpu_info("fallback:no_probe_succeeded")


def _build_info_for(
    name: str, torch: object | None, extra: Optional[str]
) -> BackendInfo:
    """Dispatch helper: build BackendInfo for a named backend.

    `torch` may be None on a base install (no DL extras); in that case
    only "cpu" should reach this function (guarded by the probes above).
    """
    if name == "cpu":
        return _build_cpu_info("priority_resolver")
    if torch is None:
        # Defensive: caller should never hit this because every non-cpu
        # backend's probe returns False when torch is missing.
        return _build_cpu_info("fallback:torch_unavailable")
    if name == "cuda":
        return _build_cuda_info(torch)
    if name == "mps":
        return _build_mps_info()
    if name == "rocm":
        return _build_rocm_info(torch, extra)
    if name == "xpu":
        return _build_xpu_info(torch)
    if name == "tpu":
        return _build_tpu_info()
    # Defensive: every KNOWN_BACKENDS name is handled above.
    raise ValueError(f"Unhandled backend name: {name!r}")
