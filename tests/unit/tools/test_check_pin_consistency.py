"""Unit tests for tools/check_pin_consistency.py (issue #1183).

The detector is the structural defense that makes silent first-party pin drift
loud. These fixtures pin down each verdict class so the logic cannot regress:

* defensive cap on a first-party sibling      -> ERROR (exit 1)
* floor exceeding the sibling's current ver   -> ERROR (exit 1)
* same dep at divergent floors within one mfst-> ERROR (exit 1)
* cross-manifest floor divergence             -> ADVISORY only (exit 0)
* semantically-equal floors (1.1 == 1.1.0)    -> NOT flagged as drift
* a clean monorepo                            -> exit 0
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[3] / "tools" / "check_pin_consistency.py"
_spec = importlib.util.spec_from_file_location("check_pin_consistency", _TOOL)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
sys.modules["check_pin_consistency"] = mod  # dataclass introspection needs this
_spec.loader.exec_module(mod)


def _write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")


def _root_manifest(
    name: str, version: str, deps: list[str], optional: dict | None = None
) -> str:
    lines = [
        "[project]",
        f'name = "{name}"',
        f'version = "{version}"',
        "dependencies = [",
        *[f'    "{d}",' for d in deps],
        "]",
    ]
    if optional:
        lines.append("[project.optional-dependencies]")
        for group, specs in optional.items():
            lines.append(f"{group} = [")
            lines.extend(f'    "{s}",' for s in specs)
            lines.append("]")
    return "\n".join(lines) + "\n"


@pytest.fixture
def clean_repo(tmp_path: Path) -> Path:
    # kailash 1.0.0 published; both siblings floor at >=1.0 consistently.
    _write(tmp_path, "pyproject.toml", _root_manifest("kailash", "1.0.0", []))
    _write(
        tmp_path,
        "packages/kailash-ml/pyproject.toml",
        _root_manifest("kailash-ml", "2.0.0", ["kailash>=1.0"]),
    )
    _write(
        tmp_path,
        "packages/kailash-nexus/pyproject.toml",
        _root_manifest("kailash-nexus", "2.0.0", ["kailash>=1.0"]),
    )
    return tmp_path


def test_clean_repo_exits_zero(clean_repo: Path):
    assert mod.main(["--root", str(clean_repo)]) == 0
    rep = mod.build_report(clean_repo)
    assert not rep["caps_errors"]
    assert not rep["unsatisfiable"]
    assert not rep["intra_manifest"]


def test_defensive_cap_on_sibling_is_error(tmp_path: Path):
    _write(tmp_path, "pyproject.toml", _root_manifest("kailash", "1.0.0", []))
    _write(
        tmp_path,
        "packages/kailash-ml/pyproject.toml",
        _root_manifest("kailash-ml", "2.0.0", ["kailash>=1.0"]),
    )
    # align caps the current ml out: >=1.1,<2.0 while ml is 2.0.0
    _write(
        tmp_path,
        "packages/kailash-align/pyproject.toml",
        _root_manifest(
            "kailash-align",
            "0.7.0",
            ["kailash>=1.0"],
            {"rl": ["kailash-ml[rl]>=1.1,<2.0"]},
        ),
    )
    rep = mod.build_report(tmp_path)
    caps = {n for n, _ in rep["caps_errors"]}
    assert "kailash-ml" in caps
    # the cap excludes the current version
    _, site = rep["caps_errors"][0]
    assert mod._cap_excludes(site.caps, "2.0.0") is True
    assert mod.main(["--root", str(tmp_path)]) == 1


def test_floor_exceeding_current_is_unsatisfiable(tmp_path: Path):
    _write(tmp_path, "pyproject.toml", _root_manifest("kailash", "1.0.0", []))
    # nexus floors kailash-ml at 3.0 but ml is only 2.0.0 in-repo
    _write(
        tmp_path,
        "packages/kailash-ml/pyproject.toml",
        _root_manifest("kailash-ml", "2.0.0", ["kailash>=1.0"]),
    )
    _write(
        tmp_path,
        "packages/kailash-nexus/pyproject.toml",
        _root_manifest("kailash-nexus", "2.0.0", ["kailash>=1.0", "kailash-ml>=3.0"]),
    )
    rep = mod.build_report(tmp_path)
    names = {n for n, _, _ in rep["unsatisfiable"]}
    assert "kailash-ml" in names
    assert mod.main(["--root", str(tmp_path)]) == 1


def test_intra_manifest_divergence_is_error(tmp_path: Path):
    _write(tmp_path, "pyproject.toml", _root_manifest("kailash", "1.0.0", []))
    # ml pins kailash-kaizen at two different floors in two extras
    _write(
        tmp_path,
        "packages/kailash-ml/pyproject.toml",
        _root_manifest(
            "kailash-ml",
            "2.0.0",
            ["kailash>=1.0"],
            {"a": ["kailash-kaizen>=2.7"], "b": ["kailash-kaizen>=2.7.5"]},
        ),
    )
    _write(
        tmp_path,
        "packages/kailash-kaizen/pyproject.toml",
        _root_manifest("kailash-kaizen", "2.8.0", ["kailash>=1.0"]),
    )
    rep = mod.build_report(tmp_path)
    names = {n for n, _, _ in rep["intra_manifest"]}
    assert "kailash-kaizen" in names
    assert mod.main(["--root", str(tmp_path)]) == 1


def test_cross_manifest_divergence_is_advisory_not_error(tmp_path: Path):
    # two packages floor kailash differently — legitimate per dependencies.md
    _write(tmp_path, "pyproject.toml", _root_manifest("kailash", "3.0.0", []))
    _write(
        tmp_path,
        "packages/kailash-ml/pyproject.toml",
        _root_manifest("kailash-ml", "2.0.0", ["kailash>=2.0"]),
    )
    _write(
        tmp_path,
        "packages/kailash-nexus/pyproject.toml",
        _root_manifest("kailash-nexus", "2.0.0", ["kailash>=2.9"]),
    )
    rep = mod.build_report(tmp_path)
    assert not rep["caps_errors"]
    assert not rep["intra_manifest"]
    cross = {n for n, _, _ in rep["cross_manifest"]}
    assert "kailash" in cross  # surfaced as advisory
    assert mod.main(["--root", str(tmp_path)]) == 0  # advisory does not fail
    # but --strict-advisory does
    assert mod.main(["--root", str(tmp_path), "--strict-advisory"]) == 1


def test_semantically_equal_floors_not_flagged(tmp_path: Path):
    # >=1.1 and >=1.1.0 are the SAME PEP 440 floor — must NOT be intra-manifest drift
    _write(tmp_path, "pyproject.toml", _root_manifest("kailash", "1.0.0", []))
    _write(
        tmp_path,
        "packages/kailash-ml/pyproject.toml",
        _root_manifest("kailash-ml", "2.0.0", ["kailash>=1.0"]),
    )
    _write(
        tmp_path,
        "packages/kailash-align/pyproject.toml",
        _root_manifest(
            "kailash-align",
            "0.7.0",
            ["kailash>=1.0"],
            {"a": ["kailash-ml>=1.1"], "b": ["kailash-ml>=1.1.0"]},
        ),
    )
    rep = mod.build_report(tmp_path)
    intra = {n for n, _, _ in rep["intra_manifest"]}
    assert "kailash-ml" not in intra  # 1.1 == 1.1.0, no drift


def test_version_equality_helper():
    assert mod._veq("1.1", "1.1.0") is True
    assert mod._veq("2.0", "2.0.0") is True
    assert mod._veq("2.7", "2.7.5") is False
    assert mod._vgt("3.0", "2.0.0") is True
    assert mod._vgt("1.0", "2.0.0") is False


def test_self_extra_reference_ignored(tmp_path: Path):
    # a package referencing its own extras (kailash-ml[dl]) is not a cross-pin
    _write(tmp_path, "pyproject.toml", _root_manifest("kailash", "1.0.0", []))
    _write(
        tmp_path,
        "packages/kailash-ml/pyproject.toml",
        _root_manifest(
            "kailash-ml",
            "2.0.0",
            ["kailash>=1.0"],
            {"all": ["kailash-ml[dl,rl]"]},
        ),
    )
    rep = mod.build_report(tmp_path)
    assert "kailash-ml" not in rep["deps"]  # self-reference excluded
