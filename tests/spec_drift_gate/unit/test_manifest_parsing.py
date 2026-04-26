"""Tier-1 unit tests for the manifest parser (SDG-201).

Verifies:
- Valid manifest loads to a typed ``Manifest`` dataclass per spec § 2.4.
- Missing manifest raises ``ManifestNotFoundError`` (no implicit defaults).
- Malformed TOML raises ``ManifestSchemaError`` with a descriptive message.
- Missing required field raises ``ManifestSchemaError`` naming the field.
- Path validation is performed at parse time (typos surface immediately).
- Errors derive from ``SpecDriftGateError``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from spec_drift_gate import (
    ErrorsOverride,
    Exclusions,
    Manifest,
    ManifestNotFoundError,
    ManifestSchemaError,
    SourceRoot,
    SpecDriftGateError,
)


def _write_minimal_manifest(
    tmp_path: Path, source_dir: Path, errors_file: Path
) -> Path:
    manifest_path = tmp_path / ".spec-drift-gate.toml"
    manifest_path.write_text(
        f"""
[gate]
version = "1.0"
spec_glob = "specs/**/*.md"

[[source_roots]]
package = "demo"
path = "{source_dir.as_posix()}"

[errors_modules]
default = "{errors_file.as_posix()}"

[exclusions]
test_specs = ["tests/fixtures/spec_drift_gate/*.md"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_valid_manifest_loads(tmp_path: Path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    errors_file = tmp_path / "errors.py"
    errors_file.write_text("class FooError(Exception): pass\n", encoding="utf-8")
    manifest_path = _write_minimal_manifest(tmp_path, source_dir, errors_file)

    manifest = Manifest.load(manifest_path)

    assert isinstance(manifest, Manifest)
    assert manifest.version == "1.0"
    assert manifest.spec_glob == "specs/**/*.md"
    assert len(manifest.source_roots) == 1
    sr = manifest.source_roots[0]
    assert isinstance(sr, SourceRoot)
    assert sr.package == "demo"
    assert sr.path == source_dir
    assert manifest.errors_default == errors_file
    assert manifest.errors_overrides == ()
    assert isinstance(manifest.exclusions, Exclusions)
    assert manifest.exclusions.test_specs == ("tests/fixtures/spec_drift_gate/*.md",)


def test_manifest_with_errors_overrides_loads(tmp_path: Path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    default_errors = tmp_path / "errors.py"
    default_errors.write_text("", encoding="utf-8")
    pact_errors = tmp_path / "pact_errors.py"
    pact_errors.write_text("", encoding="utf-8")

    manifest_path = tmp_path / ".spec-drift-gate.toml"
    manifest_path.write_text(
        f"""
[gate]
version = "1.0"
spec_glob = "specs/**/*.md"

[[source_roots]]
package = "demo"
path = "{source_dir.as_posix()}"

[errors_modules]
default = "{default_errors.as_posix()}"
overrides = [
  {{ package = "kailash-pact", path = "{pact_errors.as_posix()}" }},
]

[exclusions]
test_specs = []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = Manifest.load(manifest_path)

    assert len(manifest.errors_overrides) == 1
    override = manifest.errors_overrides[0]
    assert isinstance(override, ErrorsOverride)
    assert override.package == "kailash-pact"
    assert override.path == pact_errors


def test_missing_manifest_raises_typed_error(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-manifest.toml"

    with pytest.raises(ManifestNotFoundError) as exc:
        Manifest.load(missing)

    assert "manifest not found" in str(exc.value)
    assert "specs/spec-drift-gate.md" in str(exc.value)
    assert isinstance(exc.value, SpecDriftGateError)


def test_malformed_toml_raises_schema_error(tmp_path: Path) -> None:
    manifest_path = tmp_path / ".spec-drift-gate.toml"
    manifest_path.write_text('[gate\nversion = "1.0"\n', encoding="utf-8")

    with pytest.raises(ManifestSchemaError) as exc:
        Manifest.load(manifest_path)

    assert "malformed TOML" in str(exc.value)
    assert isinstance(exc.value, SpecDriftGateError)


def test_missing_gate_table_raises(tmp_path: Path) -> None:
    manifest_path = tmp_path / ".spec-drift-gate.toml"
    manifest_path.write_text(
        '[[source_roots]]\npackage = "demo"\npath = "."\n', encoding="utf-8"
    )

    with pytest.raises(ManifestSchemaError) as exc:
        Manifest.load(manifest_path)

    assert "[gate]" in str(exc.value)


def test_missing_gate_version_raises(tmp_path: Path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    manifest_path = tmp_path / ".spec-drift-gate.toml"
    manifest_path.write_text(
        f"""
[gate]
spec_glob = "specs/**/*.md"

[[source_roots]]
package = "demo"
path = "{source_dir.as_posix()}"

[errors_modules]
default = "{source_dir.as_posix()}"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestSchemaError) as exc:
        Manifest.load(manifest_path)

    assert "[gate].version" in str(exc.value)


def test_missing_source_roots_raises(tmp_path: Path) -> None:
    errors_file = tmp_path / "errors.py"
    errors_file.write_text("", encoding="utf-8")
    manifest_path = tmp_path / ".spec-drift-gate.toml"
    manifest_path.write_text(
        f"""
[gate]
version = "1.0"
spec_glob = "specs/**/*.md"

[errors_modules]
default = "{errors_file.as_posix()}"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestSchemaError) as exc:
        Manifest.load(manifest_path)

    assert "[[source_roots]]" in str(exc.value)


def test_source_root_missing_field_raises(tmp_path: Path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    errors_file = tmp_path / "errors.py"
    errors_file.write_text("", encoding="utf-8")
    manifest_path = tmp_path / ".spec-drift-gate.toml"
    manifest_path.write_text(
        f"""
[gate]
version = "1.0"
spec_glob = "specs/**/*.md"

[[source_roots]]
path = "{source_dir.as_posix()}"

[errors_modules]
default = "{errors_file.as_posix()}"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestSchemaError) as exc:
        Manifest.load(manifest_path)

    msg = str(exc.value)
    assert "[[source_roots]][0]" in msg
    assert "'package'" in msg


def test_nonexistent_source_root_path_raises(tmp_path: Path) -> None:
    errors_file = tmp_path / "errors.py"
    errors_file.write_text("", encoding="utf-8")
    bogus = tmp_path / "does-not-exist"
    manifest_path = tmp_path / ".spec-drift-gate.toml"
    manifest_path.write_text(
        f"""
[gate]
version = "1.0"
spec_glob = "specs/**/*.md"

[[source_roots]]
package = "demo"
path = "{bogus.as_posix()}"

[errors_modules]
default = "{errors_file.as_posix()}"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestSchemaError) as exc:
        Manifest.load(manifest_path)

    assert "does not exist" in str(exc.value)
    assert str(bogus) in str(exc.value)


def test_nonexistent_errors_default_raises(tmp_path: Path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    bogus_errors = tmp_path / "no_errors.py"
    manifest_path = tmp_path / ".spec-drift-gate.toml"
    manifest_path.write_text(
        f"""
[gate]
version = "1.0"
spec_glob = "specs/**/*.md"

[[source_roots]]
package = "demo"
path = "{source_dir.as_posix()}"

[errors_modules]
default = "{bogus_errors.as_posix()}"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestSchemaError) as exc:
        Manifest.load(manifest_path)

    assert "[errors_modules].default" in str(exc.value)
    assert "does not exist" in str(exc.value)


def test_repo_manifest_loads_and_paths_resolve() -> None:
    """The committed `.spec-drift-gate.toml` at repo root MUST load cleanly.

    Acts as a structural invariant test: any future edit to the manifest
    that introduces a typo'd path or removes a required field surfaces here
    immediately rather than on the next sweep run.
    """

    manifest = Manifest.load()  # default path = .spec-drift-gate.toml

    assert manifest.version == "1.0"
    assert len(manifest.source_roots) >= 1
    for sr in manifest.source_roots:
        assert sr.path.exists(), f"source root {sr.package} path missing: {sr.path}"
    assert manifest.errors_default.exists()
    for override in manifest.errors_overrides:
        assert (
            override.path.exists()
        ), f"errors override {override.package} path missing: {override.path}"
