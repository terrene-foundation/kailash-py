# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for the backend-compat-matrix yaml loader + doctor subcommands.

Covers the shipped file's schema, the validation contract, the
``run_subcommand`` dispatch, and the ``lru_cache`` path-keying so a
test-supplied override does not poison subsequent default reads.
"""
from __future__ import annotations

import pytest
from kailash_ml._compat_matrix import (
    REQUIRED_BACKEND_KEYS,
    REQUIRED_TOP_LEVEL_KEYS,
    BackendEntry,
    CompatMatrix,
    load_matrix,
    matrix_path,
)
from kailash_ml.doctor import run_subcommand

# --- Shipped matrix loads cleanly ----------------------------------


def test_shipped_matrix_exists():
    assert matrix_path().exists(), (
        f"backend-compat-matrix.yaml missing at {matrix_path()} — "
        "package-data not shipping."
    )


def test_load_matrix_returns_compat_matrix():
    m = load_matrix()
    assert isinstance(m, CompatMatrix)
    assert m.format_version  # non-empty
    assert m.backends  # non-empty


def test_six_canonical_backends_present():
    m = load_matrix()
    for key in ("cpu", "cuda", "mps", "rocm", "xpu", "tpu"):
        assert key in m.backends, f"matrix missing required backend {key!r}"


def test_cuda_cutoff_is_sm70_minimum():
    m = load_matrix()
    cuda = m.backends["cuda"]
    assert cuda.archs is not None
    # sm_70 (Volta) is the minimum per ml-backends.md
    assert "sm_70" in cuda.archs
    # Pascal and older MUST NOT appear
    for forbidden in ("sm_60", "sm_61", "sm_50"):
        assert forbidden not in cuda.archs


def test_mps_requires_macos_14():
    m = load_matrix()
    mps = m.backends["mps"]
    min_macos = mps.extra.get("min_macos_version")
    assert min_macos == "14.0"


def test_rocm_excludes_pre_gfx908():
    m = load_matrix()
    rocm = m.backends["rocm"]
    assert rocm.archs is not None
    for arch in rocm.archs:
        # gfx8xx / gfx9xx pre-gfx908 unsupported by torch 2.1+
        assert not arch.startswith(
            "gfx8"
        ), f"matrix has unsupported pre-gfx908 ROCm arch {arch!r}"


# --- Schema validation (invariants) --------------------------------


def test_top_level_schema_required_keys():
    assert set(REQUIRED_TOP_LEVEL_KEYS) == {"format_version", "updated", "backends"}


def test_backend_entry_required_keys():
    assert set(REQUIRED_BACKEND_KEYS) == {
        "name",
        "min_torch_version",
        "archs",
        "platform_requirement",
        "install_hint",
        "gotchas",
    }


def test_every_backend_has_required_keys():
    m = load_matrix()
    for key, entry in m.backends.items():
        assert isinstance(entry, BackendEntry)
        assert entry.name
        assert entry.min_torch_version
        assert entry.platform_requirement
        assert entry.install_hint
        assert isinstance(entry.gotchas, tuple)


# --- Validation rejects malformed matrices -------------------------


def test_load_raises_on_missing_top_level_key(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("format_version: 1.0.0\nbackends: {}\n")
    with pytest.raises(ValueError, match="updated"):
        load_matrix(bad)


def test_load_raises_on_missing_backend_key(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "format_version: '1.0.0'\n"
        "updated: '2026-04-21'\n"
        "backends:\n"
        "  cpu:\n"
        "    name: CPU\n"
    )
    with pytest.raises(ValueError, match="missing required key"):
        load_matrix(bad)


def test_load_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_matrix(tmp_path / "does-not-exist.yaml")


# --- run_subcommand dispatch --------------------------------------


def test_subcommand_matrix_returns_full_dict():
    result = run_subcommand("matrix")
    assert result["subcommand"] == "matrix"
    assert "format_version" in result
    assert "backends" in result
    assert "cpu" in result["backends"]
    assert "cuda" in result["backends"]


def test_subcommand_backends_enumerates_keys():
    result = run_subcommand("backends")
    assert result["subcommand"] == "backends"
    assert set(result["backends"]) >= {"cpu", "cuda", "mps", "rocm", "xpu", "tpu"}


def test_subcommand_gpu_excludes_cpu():
    result = run_subcommand("gpu")
    assert result["subcommand"] == "gpu"
    assert "cpu" not in result["gpu_backends"]
    for key in ("cuda", "mps", "rocm", "xpu", "tpu"):
        assert key in result["gpu_backends"]


def test_subcommand_gpu_includes_cuda_archs():
    result = run_subcommand("gpu")
    cuda = result["gpu_backends"]["cuda"]
    assert "sm_70" in cuda["archs"]
    assert cuda["name"] == "NVIDIA CUDA"
    assert cuda["min_torch_version"]


def test_unknown_subcommand_raises_valueerror():
    with pytest.raises(ValueError, match="unknown doctor subcommand"):
        run_subcommand("nonexistent")


def test_unknown_subcommand_lists_valid_options():
    with pytest.raises(ValueError) as exc:
        run_subcommand("wrong")
    # Error message must enumerate valid subcommands so ops can
    # self-correct without reading source.
    assert "gpu" in str(exc.value)
    assert "matrix" in str(exc.value)
    assert "backends" in str(exc.value)


# --- Format version semver -----------------------------------------


def test_format_version_is_semver_shape():
    m = load_matrix()
    parts = m.format_version.split(".")
    assert len(parts) == 3
    for part in parts:
        assert part.isdigit()


def test_matrix_runtime_read_not_import_time(tmp_path):
    """The loader reads at call time — a custom path override exercises
    the load_matrix(path) argument path without poisoning the default."""
    override = tmp_path / "override.yaml"
    override.write_text(
        "format_version: '0.9.0'\n"
        "updated: '2026-01-01'\n"
        "backends:\n"
        "  cpu:\n"
        "    name: Custom CPU\n"
        "    min_torch_version: '2.0.0'\n"
        "    archs: null\n"
        "    platform_requirement: 'test'\n"
        "    install_hint: 'test'\n"
        "    gotchas: []\n"
    )
    m = load_matrix(override)
    assert m.format_version == "0.9.0"
    assert m.backends["cpu"].name == "Custom CPU"

    # The default-path matrix is unaffected (lru_cache keys on path).
    m_default = load_matrix()
    assert m_default.format_version != "0.9.0"
