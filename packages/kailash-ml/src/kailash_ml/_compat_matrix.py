# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Load + expose the ``backend-compat-matrix.yaml`` package-data file.

The matrix is authored at
``src/kailash_ml/data/backend-compat-matrix.yaml`` and shipped as
package-data so ``km.doctor gpu`` can read it at runtime (not
import-time). Per Decision 6, the file has its own semver so operators
can patch new GPUs / macOS bumps / torch versions without a kailash-ml
SDK release.

See ``specs/ml-backends.md § GPU Arch Cutoff``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "CompatMatrix",
    "BackendEntry",
    "load_matrix",
    "matrix_path",
    "REQUIRED_TOP_LEVEL_KEYS",
    "REQUIRED_BACKEND_KEYS",
]

# Schema contract — any breaking change here bumps the yaml file's
# format_version major.
REQUIRED_TOP_LEVEL_KEYS = ("format_version", "updated", "backends")
REQUIRED_BACKEND_KEYS = (
    "name",
    "min_torch_version",
    "archs",
    "platform_requirement",
    "install_hint",
    "gotchas",
)


@dataclass(frozen=True)
class BackendEntry:
    """Canonical shape for a single backend row in the matrix."""

    key: str  # "cpu" / "cuda" / "mps" / "rocm" / "xpu" / "tpu"
    name: str
    min_torch_version: str
    archs: Optional[tuple[str, ...]]
    platform_requirement: str
    install_hint: str
    gotchas: tuple[str, ...] = field(default_factory=tuple)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompatMatrix:
    """Parsed + validated compatibility matrix."""

    format_version: str
    updated: str
    backends: dict[str, BackendEntry]
    source: Path

    def get(self, backend_key: str) -> Optional[BackendEntry]:
        return self.backends.get(backend_key)


def matrix_path() -> Path:
    """Resolved absolute path to the shipped matrix file."""
    here = Path(__file__).resolve().parent
    return here / "data" / "backend-compat-matrix.yaml"


@lru_cache(maxsize=1)
def load_matrix(path: Optional[Path] = None) -> CompatMatrix:
    """Load the matrix from ``path`` (defaults to the shipped file).

    Cached — the file is package-data and doesn't change at runtime.
    Pass an explicit path to override in tests (``lru_cache`` keyed on
    positional args will return a fresh parse for a different path).

    Raises:
        FileNotFoundError: when the matrix file is absent.
        ValueError: when the file fails schema validation. The error
            message names the missing key so operators can patch the
            yaml file in place.
    """
    target = path or matrix_path()
    if not target.exists():
        raise FileNotFoundError(
            f"backend-compat-matrix.yaml not found at {target}; "
            "reinstall kailash-ml or pass an explicit --matrix path"
        )
    try:
        import yaml  # PyYAML — bundled dep of kailash via pydantic extras
    except ImportError as e:  # pragma: no cover — yaml is a direct dep
        raise ImportError(
            "PyYAML is required to load the backend compatibility matrix; "
            "install via: pip install pyyaml"
        ) from e

    raw = yaml.safe_load(target.read_text())
    _validate_schema(raw, target)

    backends: dict[str, BackendEntry] = {}
    for key, row in raw["backends"].items():
        extra = {k: v for k, v in row.items() if k not in REQUIRED_BACKEND_KEYS}
        archs = row["archs"]
        if archs is not None:
            archs = tuple(archs)
        backends[key] = BackendEntry(
            key=key,
            name=row["name"],
            min_torch_version=row["min_torch_version"],
            archs=archs,
            platform_requirement=row["platform_requirement"],
            install_hint=row["install_hint"],
            gotchas=tuple(row["gotchas"]),
            extra=extra,
        )
    return CompatMatrix(
        format_version=raw["format_version"],
        updated=raw["updated"],
        backends=backends,
        source=target,
    )


def _validate_schema(raw: Any, source: Path) -> None:
    if not isinstance(raw, dict):
        raise ValueError(
            f"compat matrix at {source} must be a mapping at the top level"
        )
    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in raw:
            raise ValueError(
                f"compat matrix at {source} missing required top-level key {key!r}"
            )
    if not isinstance(raw["backends"], dict):
        raise ValueError(
            f"compat matrix at {source} ``backends`` must be a mapping "
            f"from backend-key to entry"
        )
    for backend_key, row in raw["backends"].items():
        if not isinstance(row, dict):
            raise ValueError(f"compat matrix backend {backend_key!r} must be a mapping")
        for required in REQUIRED_BACKEND_KEYS:
            if required not in row:
                raise ValueError(
                    f"compat matrix backend {backend_key!r} missing required "
                    f"key {required!r}"
                )
