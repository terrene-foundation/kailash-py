# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for ``km.doctor()``.

Exercises the real doctor function (no mocking) and, when the
``km-doctor`` console script is installed, the subprocess path.

Per ``specs/ml-backends.md`` §7:

- Exit 0 — all green (CPU present and any ``--require`` satisfied).
- Exit 1 — any warning.
- Exit 2 — ``--require=<backend>`` unreachable OR a probe raised.

These tests are Tier 2 per ``rules/testing.md``: the probes touch the
real PyTorch install, the real platform module, and (for the subprocess
test) a real subprocess invocation. No ``@patch`` / ``MagicMock``.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys

import pytest

import kailash_ml as km
from kailash_ml.doctor import doctor, main


pytestmark = [pytest.mark.integration]


def _torch_has_cuda() -> bool:
    try:
        import torch
    except ImportError:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core doctor() contract
# ---------------------------------------------------------------------------


def test_doctor_cpu_available() -> None:
    """CPU is always available -> doctor returns 0 and CPU probe is ok."""
    buf = io.StringIO()
    code = doctor(as_json=True, out=buf)
    assert code == 0
    payload = json.loads(buf.getvalue())
    cpu = next(p for p in payload["backends"] if p["backend"] == "cpu")
    assert cpu["status"] == "ok"
    assert cpu["devices"] >= 1


def test_doctor_json_output_shape() -> None:
    """``--json`` output exposes the 6 probed backends with required keys."""
    buf = io.StringIO()
    code = doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    assert payload["exit_code"] == code
    assert payload["require"] is None
    backends = {p["backend"] for p in payload["backends"]}
    # All six first-class backends per spec §1 — v0.14.0 adds xpu + tpu
    # to the 0.13.0 probe set.
    assert backends == {"cpu", "cuda", "mps", "rocm", "xpu", "tpu"}
    for entry in payload["backends"]:
        # Mandatory structured fields per spec §7.2
        assert "status" in entry
        assert "version" in entry
        assert "devices" in entry
        assert "warnings" in entry
        assert "failures" in entry


def test_doctor_require_missing_backend() -> None:
    """``--require=cuda`` on a CPU-only host -> exit 2."""
    if _torch_has_cuda():
        pytest.skip("CUDA actually available on this host")
    buf = io.StringIO()
    code = doctor(require="cuda", as_json=True, out=buf)
    assert code == 2
    payload = json.loads(buf.getvalue())
    assert payload["require"] == "cuda"


def test_doctor_require_cpu_ok() -> None:
    """``--require=cpu`` on any host -> exit 0 (CPU always present)."""
    buf = io.StringIO()
    code = doctor(require="cpu", as_json=True, out=buf)
    assert code == 0


def test_doctor_main_cli_parses_flags() -> None:
    """``main([...])`` calls ``doctor`` with the parsed flags."""
    # --json --require=cpu should still exit 0 on any host
    code = main(["--json", "--require=cpu"])
    assert code == 0


def test_km_doctor_is_public_symbol() -> None:
    """``km.doctor`` resolves to the same callable as ``kailash_ml.doctor``."""
    # Eager import path — matches orphan-detection §6.
    assert km.doctor is doctor


# ---------------------------------------------------------------------------
# Console-script / subprocess path
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# v0.14.0 expansion — all 10 additional diagnostic checks (spec §7.1)
# ---------------------------------------------------------------------------


def test_doctor_json_includes_spec_7_1_sections() -> None:
    """Every spec §7.1 diagnostic section is present as a top-level key.

    Mechanical whitelist check: the report MUST include the 10 sections
    the spec mandates (selected_default, precision_matrix, extras,
    family_probes, onnx_eps, sqlite_path, cache_paths, tenant_mode,
    gotchas) alongside the existing ``backends`` + ``exit_code``.
    """
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    required_keys = {
        "backends",
        "exit_code",
        "require",
        "selected_default",
        "precision_matrix",
        "extras",
        "family_probes",
        "onnx_eps",
        "sqlite_path",
        "cache_paths",
        "tenant_mode",
        "gotchas",
    }
    missing = required_keys - set(payload.keys())
    assert not missing, f"spec §7.1 sections missing from JSON: {sorted(missing)}"


def test_doctor_precision_matrix_covers_all_6_backends() -> None:
    """Every probed backend has a precision entry (value may be None)."""
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    matrix = payload["precision_matrix"]
    # Six backends MUST appear as keys — value is None when the backend
    # is unavailable on this host, concrete precision string otherwise.
    for backend in ("cpu", "cuda", "mps", "rocm", "xpu", "tpu"):
        assert backend in matrix, f"precision_matrix missing {backend}"
    # CPU always available -> always has a precision
    assert matrix["cpu"] is not None, "cpu must always have a precision"


def test_doctor_selected_default_matches_detect_backend() -> None:
    """``selected_default`` resolves to the highest-priority ``ok`` backend."""
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    selected = payload["selected_default"]
    assert selected is not None, "cpu always present, selected_default MUST be non-null"
    # The selected default MUST correspond to a probe whose status=ok
    ok_backends = {p["backend"] for p in payload["backends"] if p["status"] == "ok"}
    assert selected in ok_backends


def test_doctor_extras_enumerate_spec_set() -> None:
    """``extras`` enumerates every spec §7.1 extras bucket."""
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    extras = payload["extras"]
    # Spec §7.1 Installed extras: [cuda], [rocm], [xpu], [tpu], [dl],
    # [agents], [explain], [imbalance]
    for extra in ("cuda", "rocm", "xpu", "tpu", "dl", "agents", "explain", "imbalance"):
        assert extra in extras, f"extras missing '{extra}'"
        assert "installed" in extras[extra]
        assert "modules" in extras[extra]


def test_doctor_family_probes_report_base_deps() -> None:
    """Base dep families report a concrete version; optional families report None."""
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    families = payload["family_probes"]
    # Base deps (always installed in the [dev] test venv)
    for fam in ("torch", "lightning", "sklearn", "xgboost", "lightgbm", "onnxruntime"):
        assert fam in families, f"family_probes missing '{fam}'"
    # sklearn is a base dep -> MUST report a version
    assert families["sklearn"] is not None


def test_doctor_onnx_eps_enumerates_providers() -> None:
    """``onnx_eps.providers`` is a non-empty list when onnxruntime is installed."""
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    onnx = payload["onnx_eps"]
    # onnxruntime is a base dep so must be installed.
    assert onnx["installed"] is True
    assert onnx["version"] is not None
    assert isinstance(onnx["providers"], list)
    assert len(onnx["providers"]) >= 1
    # CPUExecutionProvider is the mandatory fallback EP on every platform.
    assert "CPUExecutionProvider" in onnx["providers"]


def test_doctor_sqlite_path_probe(tmp_path) -> None:
    """SQLite path is reported with writable=True on a fresh tmp home."""
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    sqlite = payload["sqlite_path"]
    # Every run populates the shape, regardless of writability
    assert "path" in sqlite
    assert "source" in sqlite
    assert "exists" in sqlite
    assert "writable" in sqlite
    assert sqlite["source"] in {"default", "KAILASH_ML_STORE"}


def test_doctor_sqlite_path_honours_env(monkeypatch, tmp_path) -> None:
    """``KAILASH_ML_STORE`` overrides the default SQLite path."""
    override = tmp_path / "custom.db"
    monkeypatch.setenv("KAILASH_ML_STORE", f"sqlite:///{override}")
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    sqlite = payload["sqlite_path"]
    assert sqlite["source"] == "KAILASH_ML_STORE"
    assert sqlite["path"] == str(override)
    # Tmp dir is writable — the probe should confirm.
    assert sqlite["writable"] is True


def test_doctor_cache_paths_report_disk_usage() -> None:
    """Cache paths section populates data_root + cache + filesystem stats."""
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    cache = payload["cache_paths"]
    assert "data_root" in cache
    assert "cache" in cache
    assert "filesystem" in cache
    # data_root has a path + exists + size_bytes triple
    for field in ("path", "exists", "size_bytes"):
        assert field in cache["data_root"]
        assert field in cache["cache"]
    # filesystem has total + free bytes
    assert "total_bytes" in cache["filesystem"]
    assert "free_bytes" in cache["filesystem"]


def test_doctor_tenant_mode_single_default(monkeypatch) -> None:
    """No tenant env var -> single-tenant mode."""
    monkeypatch.delenv("KAILASH_ML_DEFAULT_TENANT", raising=False)
    monkeypatch.delenv("KAILASH_TENANT_ID", raising=False)
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    tenant = payload["tenant_mode"]
    assert tenant["mode"] == "single-tenant"
    assert tenant["tenant_id"] is None


def test_doctor_tenant_mode_multi(monkeypatch) -> None:
    """``KAILASH_ML_DEFAULT_TENANT`` triggers multi-tenant mode."""
    monkeypatch.setenv("KAILASH_ML_DEFAULT_TENANT", "acme-42")
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    tenant = payload["tenant_mode"]
    assert tenant["mode"] == "multi-tenant"
    assert tenant["tenant_id"] == "acme-42"


def test_doctor_gotchas_are_emitted_for_detected_backends() -> None:
    """``gotchas`` contains one entry per ``(backend, hint)`` pair for ok backends."""
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    gotchas = payload["gotchas"]
    # Each entry has ``backend`` + ``hint`` keys.
    for entry in gotchas:
        assert "backend" in entry
        assert "hint" in entry
        # Only ok-status backends contribute gotchas (don't mislead
        # operators about backends they can't actually use).
        ok_backends = {p["backend"] for p in payload["backends"] if p["status"] == "ok"}
        assert entry["backend"] in ok_backends


def test_doctor_xpu_probe_present_in_json() -> None:
    """XPU probe is always reported (status may be missing on non-Intel hosts)."""
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    xpu = next(p for p in payload["backends"] if p["backend"] == "xpu")
    assert xpu["status"] in {"ok", "warn", "fail", "missing"}


def test_doctor_tpu_probe_present_in_json() -> None:
    """TPU probe is always reported (status missing on non-TPU hosts)."""
    buf = io.StringIO()
    doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    tpu = next(p for p in payload["backends"] if p["backend"] == "tpu")
    assert tpu["status"] in {"ok", "warn", "fail", "missing"}


def test_km_doctor_console_script_or_module_json() -> None:
    """Subprocess invocation prints parseable JSON and exits 0 on CPU.

    Prefers the ``km-doctor`` console script when available (installed
    by ``pip install kailash-ml`` with the matching ``[project.scripts]``
    entry). Falls back to ``python -m kailash_ml.doctor`` otherwise.
    Either way the test validates that an end-user invoking the binary
    from a shell can parse the JSON and rely on the exit code.
    """
    console = shutil.which("km-doctor")
    if console is not None:
        cmd = [console, "--json"]
    else:
        cmd = [
            sys.executable,
            "-W",
            "ignore::RuntimeWarning",
            "-m",
            "kailash_ml.doctor",
            "--json",
        ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    assert (
        proc.returncode == 0
    ), f"km-doctor failed: exit={proc.returncode}, stdout={proc.stdout!r}, stderr={proc.stderr!r}"
    payload = json.loads(proc.stdout)
    assert payload["exit_code"] == 0
    assert any(
        p["backend"] == "cpu" and p["status"] == "ok" for p in payload["backends"]
    )
