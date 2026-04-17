# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""GPU setup CLI -- detect CUDA version and print the correct install command.

Entry point: ``kailash-ml-gpu-setup`` (registered in pyproject.toml).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)

__all__ = ["main", "detect_cuda_version", "resolve_torch_wheel"]

# Maps CUDA major.minor to the PyTorch index URL suffix
_CUDA_INDEX_MAP: dict[str, str] = {
    "11.8": "cu118",
    "12.1": "cu121",
    "12.4": "cu124",
    "12.6": "cu126",
}


def detect_cuda_version() -> str | None:
    """Detect the installed CUDA toolkit version.

    Returns
    -------
    str or None
        CUDA version string (e.g. ``"12.4"``) or ``None`` if not found.
    """
    # 1. Check CUDA_VERSION env var (set in NVIDIA Docker images)
    env_ver = os.environ.get("CUDA_VERSION")
    if env_ver:
        parts = env_ver.split(".")
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}"

    # 2. Try nvidia-smi
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                # nvidia-smi reports driver version, not CUDA version directly.
                # Use nvcc for the actual toolkit version.
                pass
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # 3. Try nvcc --version (most reliable for toolkit version)
    nvcc = shutil.which("nvcc")
    if nvcc:
        try:
            result = subprocess.run(
                [nvcc, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                # Output contains: "release 12.4, V12.4.131"
                for line in result.stdout.splitlines():
                    if "release" in line.lower():
                        # Extract "12.4" from "release 12.4,"
                        parts = line.split("release")
                        if len(parts) > 1:
                            ver = parts[1].strip().rstrip(",").split(",")[0].strip()
                            dot_parts = ver.split(".")
                            if len(dot_parts) >= 2:
                                return f"{dot_parts[0]}.{dot_parts[1]}"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # 4. Check for libcudart.so
    for cuda_home in [
        "/usr/local/cuda",
        "/usr/lib/cuda",
        os.environ.get("CUDA_HOME", ""),
    ]:
        version_file = os.path.join(cuda_home, "version.txt") if cuda_home else ""
        if cuda_home and os.path.isfile(version_file):
            try:
                with open(version_file) as f:
                    content = f.read()
                # Format: "CUDA Version 12.4.0"
                for token in content.split():
                    if "." in token:
                        parts = token.split(".")
                        if len(parts) >= 2 and parts[0].isdigit():
                            return f"{parts[0]}.{parts[1]}"
            except OSError:
                pass

    return None


def _best_cuda_tag(version: str) -> str:
    """Find the best matching PyTorch CUDA index tag for a version.

    Falls back to the closest available version.
    """
    if version in _CUDA_INDEX_MAP:
        return _CUDA_INDEX_MAP[version]

    # Try major.minor match by rounding down
    major, minor = version.split(".")[:2]
    major_i, minor_i = int(major), int(minor)

    # Find closest available version that doesn't exceed installed CUDA
    best = None
    for known_ver, tag in sorted(_CUDA_INDEX_MAP.items(), reverse=True):
        k_major, k_minor = known_ver.split(".")
        if int(k_major) < major_i or (
            int(k_major) == major_i and int(k_minor) <= minor_i
        ):
            best = tag
            break

    return best or "cu121"  # safe default


_ROCM_INDEX_MAP: dict[str, str] = {
    # PyTorch publishes ROCm wheels for a few recent versions. Keep in sync
    # with https://download.pytorch.org/whl/rocm*/.
    "5.7": "rocm5.7",
    "6.0": "rocm6.0",
    "6.1": "rocm6.1",
    "6.2": "rocm6.2",
}


def resolve_torch_wheel(
    accelerator: str,
    *,
    cuda_version: str | None = None,
    rocm_version: str | None = None,
) -> dict[str, str | None]:
    """Return the recommended torch install recipe for `accelerator`.

    Plain-data helper: does NOT execute pip. Callers can print the `command`
    field, or parse `package` + `extra_index_url` independently (e.g. for
    generating a requirements.txt or constructing a uv install invocation).

    Supported accelerators match ``KNOWN_BACKENDS`` in ``_device.py``:
    ``cuda``, ``mps``, ``rocm``, ``xpu``, ``tpu``, ``cpu``.

    Parameters
    ----------
    accelerator:
        One of ``"cuda"``, ``"mps"``, ``"rocm"``, ``"xpu"``, ``"tpu"``, ``"cpu"``.
    cuda_version:
        Optional CUDA version override (e.g. ``"12.1"``). If omitted and
        ``accelerator == "cuda"``, ``detect_cuda_version()`` is used.
    rocm_version:
        Optional ROCm version override (e.g. ``"6.1"``). Required when
        ``accelerator == "rocm"`` — we cannot auto-detect ROCm at pip time.

    Returns
    -------
    dict
        ``{"accelerator": str, "package": str, "extra_index_url": str | None,
          "command": str, "notes": str}``.

    Raises
    ------
    ValueError
        If ``accelerator`` is not one of the supported values.
    """
    known = {"cuda", "mps", "rocm", "xpu", "tpu", "cpu"}
    if accelerator not in known:
        raise ValueError(
            f"Unknown accelerator '{accelerator}'. " f"Valid: {sorted(known)}."
        )

    if accelerator == "cuda":
        version = cuda_version or detect_cuda_version()
        tag = _best_cuda_tag(version) if version else "cu121"
        index = f"https://download.pytorch.org/whl/{tag}"
        return {
            "accelerator": "cuda",
            "package": "kailash-ml[dl-gpu]",
            "extra_index_url": index,
            "command": (
                f"{sys.executable} -m pip install 'kailash-ml[dl-gpu]' "
                f"--extra-index-url {index}"
            ),
            "notes": (
                f"CUDA {version or 'unknown (defaulted to cu121)'} — " f"{tag} wheel"
            ),
        }

    if accelerator == "rocm":
        # Only the user knows their ROCm install; nvcc-style probes do not
        # exist on AMD hosts, so we require an explicit version.
        ver = rocm_version or "6.1"
        tag = _ROCM_INDEX_MAP.get(ver, "rocm6.1")
        index = f"https://download.pytorch.org/whl/{tag}"
        return {
            "accelerator": "rocm",
            "package": "kailash-ml[dl]",
            "extra_index_url": index,
            "command": (
                f"{sys.executable} -m pip install 'kailash-ml[dl]' "
                f"--extra-index-url {index}"
            ),
            "notes": f"ROCm {ver} — {tag} wheel (AMD Instinct)",
        }

    if accelerator == "xpu":
        # PyTorch >=2.5 ships native XPU support in the default wheel.
        return {
            "accelerator": "xpu",
            "package": "kailash-ml[dl]",
            "extra_index_url": None,
            "command": f"{sys.executable} -m pip install 'kailash-ml[dl]'",
            "notes": (
                "Intel XPU native support ships with the default torch wheel "
                "(torch>=2.5). No --extra-index-url required."
            ),
        }

    if accelerator == "tpu":
        return {
            "accelerator": "tpu",
            "package": "kailash-ml[dl]",
            "extra_index_url": None,
            "command": (f"{sys.executable} -m pip install 'kailash-ml[dl]' torch_xla"),
            "notes": (
                "TPU support requires torch_xla — install alongside [dl] on a "
                "Google Cloud TPU VM."
            ),
        }

    # mps + cpu both use the default wheel.
    return {
        "accelerator": accelerator,
        "package": "kailash-ml[dl]",
        "extra_index_url": None,
        "command": f"{sys.executable} -m pip install 'kailash-ml[dl]'",
        "notes": (
            "Apple Silicon MPS is built into the default torch universal2 wheel."
            if accelerator == "mps"
            else "CPU-only install (default torch wheel)."
        ),
    }


def main() -> None:
    """CLI entry point: detect CUDA and print install instructions."""
    print("kailash-ml GPU Setup")
    print("=" * 40)
    print()

    cuda_version = detect_cuda_version()

    if cuda_version is None:
        print("No CUDA toolkit detected.")
        print()
        print("If you have an NVIDIA GPU, install the CUDA toolkit first:")
        print("  https://developer.nvidia.com/cuda-downloads")
        print()
        print("For CPU-only deep learning:")
        print(f"  {sys.executable} -m pip install 'kailash-ml[dl]'")
        sys.exit(0)

    tag = _best_cuda_tag(cuda_version)
    index_url = f"https://download.pytorch.org/whl/{tag}"

    print(f"Detected CUDA version: {cuda_version}")
    print(f"Recommended PyTorch index: {tag}")
    print()
    print("Install command:")
    print(
        f"  {sys.executable} -m pip install 'kailash-ml[dl-gpu]' "
        f"--extra-index-url {index_url}"
    )
    print()
    print("Or for the full GPU suite (includes RL, agents, XGBoost, CatBoost):")
    print(
        f"  {sys.executable} -m pip install 'kailash-ml[all-gpu]' "
        f"--extra-index-url {index_url}"
    )


if __name__ == "__main__":
    main()
