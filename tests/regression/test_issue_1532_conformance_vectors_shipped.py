# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: canonical conformance vectors ship as package data (#1532 RC1).

Before #1532 the canonical vector set lived at
``tests/fixtures/delegate-conformance/canonical.json`` — under ``tests/``, which
is never packaged into the wheel. ``ConformanceVectorLoader.load_canonical()``
resolved it by walking up from ``__file__`` for that ``tests/`` path, so it
raised ``FileNotFoundError`` for every ``pip install``ed (wheel) consumer,
forcing downstream connectors to hand-roll a parent-directory-ascent loader.

RC1 moved the vectors to ``src/kailash/delegate/conformance/data/canonical.json``
and made ``load_canonical()`` resolve them via ``importlib.resources`` so the
public API works identically from a source checkout and an installed wheel.

The load-bearing guard is :func:`test_canonical_vectors_are_package_data` — it
asserts the vectors are reachable as package data through ``importlib.resources``
(False under the old ``tests/`` layout), which is exactly the property a wheel
install requires and the old code lacked.
"""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

import pytest

from kailash.delegate.conformance.schema import (
    ConformanceVectorIntegrityError,
    ConformanceVectorLoader,
)

pytestmark = pytest.mark.regression

_EXPECTED_IDS = {"DV-3-001", "DV-5-001", "DV-7-001", "DV-9-001", "DV-10-001"}


def test_canonical_vectors_are_package_data() -> None:
    """The canonical set is reachable via importlib.resources — i.e. it ships
    inside the installed package, not under ``tests/`` (the #1532 RC1 fix). This
    is the property a wheel install requires; the pre-RC1 ``tests/`` layout made
    this resource absent and load_canonical() FileNotFoundError in every wheel."""
    resource = resources.files("kailash.delegate.conformance").joinpath(
        "data/canonical.json"
    )
    assert resource.is_file(), (
        "canonical.json is not reachable as package data of "
        "kailash.delegate.conformance — it will not ship in the wheel and "
        "load_canonical() will FileNotFoundError for pip-installed consumers "
        "(the #1532 RC1 regression)."
    )


def test_load_canonical_resolves_without_source_tree(monkeypatch, tmp_path) -> None:
    """load_canonical() (no-arg) resolves the packaged vectors independent of the
    current working directory — proving it does NOT depend on a repo/source tree
    being present on the resolution path (the wheel-install scenario)."""
    # Change cwd to an unrelated dir with no tests/ tree; resolution must still
    # succeed via importlib.resources (cwd-independent).
    monkeypatch.chdir(tmp_path)
    vectors = ConformanceVectorLoader.load_canonical()
    assert {v.id for v in vectors} == _EXPECTED_IDS
    assert len(vectors) == 5


def test_load_canonical_passes_digest_integrity() -> None:
    """The packaged fixture's stored digest matches the recomputed digest — the
    move to package data preserved the byte-exact vector set (tamper-evident)."""
    # load_canonical() runs the digest-integrity check internally; a mismatch
    # raises ConformanceVectorIntegrityError. Reaching the assert means it passed.
    vectors = ConformanceVectorLoader.load_canonical()
    assert {v.id for v in vectors} == _EXPECTED_IDS


def test_packaged_resource_not_under_tests_tree() -> None:
    """Pin the shipped location: the resolved resource lives under the installed
    package (``kailash/delegate/conformance/data``), NOT a ``tests/`` tree. A
    refactor moving it back under tests/ (un-shipping it) fails here loudly."""
    resource = resources.files("kailash.delegate.conformance").joinpath(
        "data/canonical.json"
    )
    # Under a real filesystem / editable install the resource is a concrete Path;
    # under zipimport str(resource) is not a filesystem path, so the path-suffix
    # assertion is only meaningful for the filesystem case (which CI uses).
    if not isinstance(resource, Path):
        pytest.skip("resource is not a filesystem Path (zipimport); suffix check N/A")
    resolved = str(resource)
    assert resolved.endswith(
        os.path.join("kailash", "delegate", "conformance", "data", "canonical.json")
    ), f"canonical.json resolved to an unexpected location: {resolved}"
    assert f"{os.sep}tests{os.sep}" not in resolved, (
        "canonical.json resolved under a tests/ tree — it must ship as package "
        "data so the wheel includes it (#1532 RC1)."
    )


def test_packaging_config_declares_conformance_data() -> None:
    """Guard the WHEEL-packaging property (reviewer F2). The importlib.resources
    tests above pass in an editable/source install regardless of packaging config,
    because the file physically lives under src/. THIS test fails if a future edit
    drops the packaging declaration and silently un-ships the vectors from the
    built wheel — the exact regression that source-tree resolution cannot catch.
    (Wheel inclusion is additionally verified end-to-end at /release per
    build-repo-release-discipline Rule 2 clean-venv install.)"""
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert (
        "[tool.setuptools.package-data]" in pyproject
        and '"kailash.delegate.conformance"' in pyproject
        and "data/*.json" in pyproject
    ), (
        "pyproject.toml no longer declares the conformance vectors as package-data "
        'under [tool.setuptools.package-data] "kailash.delegate.conformance"; the '
        "wheel will not ship canonical.json and load_canonical() will "
        "FileNotFoundError for pip-installed consumers (#1532 RC1)."
    )
    manifest = (repo_root / "MANIFEST.in").read_text(encoding="utf-8")
    assert "src/kailash/delegate/conformance/data" in manifest, (
        "MANIFEST.in no longer includes the conformance data dir; the sdist will "
        "not ship canonical.json (#1532 RC1)."
    )


def test_load_canonical_root_override_still_works(tmp_path) -> None:
    """Back-compat: the explicit ``root=`` override reads a vendored copy at
    ``<root>/canonical.json``. Callers with their own layout keep working."""
    packaged = resources.files("kailash.delegate.conformance").joinpath(
        "data/canonical.json"
    )
    (tmp_path / "canonical.json").write_text(
        packaged.read_text(encoding="utf-8"), encoding="utf-8"
    )
    vectors = ConformanceVectorLoader.load_canonical(root=tmp_path)
    assert {v.id for v in vectors} == _EXPECTED_IDS


def test_load_canonical_root_override_missing_raises(tmp_path) -> None:
    """An explicit root with no canonical.json fails closed with a clear path."""
    with pytest.raises(FileNotFoundError, match="canonical conformance fixture"):
        ConformanceVectorLoader.load_canonical(root=tmp_path)


def test_load_from_text_tamper_is_detected() -> None:
    """The shared text loader still enforces digest integrity: a body edit that
    does not re-pin the digest fails closed (the move did not weaken tamper
    evidence)."""
    packaged = resources.files("kailash.delegate.conformance").joinpath(
        "data/canonical.json"
    )
    text = packaged.read_text(encoding="utf-8")
    # Flip a byte in a vector body without re-computing the digest header.
    tampered = text.replace("DV-3-001", "DV-3-XXX", 1)
    with pytest.raises(ConformanceVectorIntegrityError):
        ConformanceVectorLoader._load_from_text(tampered, source="tampered-test")


def test_canonical_json_no_longer_under_tests_fixtures() -> None:
    """The old source location is gone — no stale duplicate that could drift from
    the shipped copy (single source of truth, #1532 RC1)."""
    repo_root = Path(__file__).resolve().parents[2]
    old = repo_root / "tests" / "fixtures" / "delegate-conformance" / "canonical.json"
    assert not old.exists(), (
        f"stale conformance fixture still present at {old}; the canonical set now "
        "ships as package data and the old tests/ copy must not linger (drift risk)."
    )
