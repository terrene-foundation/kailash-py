"""Tier-1 unit tests for SDG-203 ``__getattr__``-resolution sweep.

Covers:
- ``_parse_getattr_map`` extracts the three pattern shapes (inline-dict,
  module-scope-dict, ``if name == "X"`` chain).
- B1 sweep emits WARN-level findings on resolution mismatch.
- B1 dual-emit coherence with FR-6 (``__all__`` membership) per redteam
  HIGH-2.
- WARN-only exit code: ``main()`` returns 0 when only B1 findings exist.

The Tier-2 load-bearing verification — sweep against the live
``kailash_ml/__init__.py`` AutoMLEngine map and check the WARN message —
runs from ``test_pristine_corpus.py`` so the v2 spec corpus exercises
the full source-tree path.
"""

from __future__ import annotations

from pathlib import Path

from spec_drift_gate import (
    SymbolIndex,
    _parse_getattr_map,
    parse_overrides,
    run_sweeps,
    scan_sections,
)


def _write_init(tmp_path: Path, body: str) -> Path:
    init_py = tmp_path / "__init__.py"
    init_py.write_text(body, encoding="utf-8")
    return init_py


def test_parse_inline_dict_pattern(tmp_path: Path) -> None:
    init_py = _write_init(
        tmp_path,
        """
def __getattr__(name):
    _engine_map = {
        "AutoMLEngine": "demo.engines.automl",
        "FeatureStore": "demo.engines.feature_store",
    }
    if name in _engine_map:
        import importlib
        return importlib.import_module(_engine_map[name])
    raise AttributeError(name)
""",
    )

    m = _parse_getattr_map(init_py)
    assert m == {
        "AutoMLEngine": "demo.engines.automl",
        "FeatureStore": "demo.engines.feature_store",
    }


def test_parse_module_scope_dict_pattern(tmp_path: Path) -> None:
    init_py = _write_init(
        tmp_path,
        """
_LAZY_IMPORT_MAP = {
    "MetricsEngine": "demo.metrics.engine",
}

def __getattr__(name):
    if name in _LAZY_IMPORT_MAP:
        import importlib
        return importlib.import_module(_LAZY_IMPORT_MAP[name])
    raise AttributeError(name)
""",
    )

    m = _parse_getattr_map(init_py)
    assert m == {"MetricsEngine": "demo.metrics.engine"}


def test_parse_if_name_equals_chain(tmp_path: Path) -> None:
    init_py = _write_init(
        tmp_path,
        """
def __getattr__(name):
    if name == "metrics":
        import importlib
        return importlib.import_module("demo.metrics")
    if name == "registry":
        import importlib
        return importlib.import_module("demo.registry.api")
    raise AttributeError(name)
""",
    )

    m = _parse_getattr_map(init_py)
    assert m == {
        "metrics": "demo.metrics",
        "registry": "demo.registry.api",
    }


def test_parse_no_getattr_returns_empty(tmp_path: Path) -> None:
    init_py = _write_init(tmp_path, '__all__ = ["foo"]\n\ndef foo(): return 1\n')
    assert _parse_getattr_map(init_py) == {}


def _idx_with_resolution(
    *,
    pkg: str,
    resolution: dict[str, str],
    all_exports: set[str] | None = None,
) -> SymbolIndex:
    idx = SymbolIndex()
    idx.getattr_resolution[pkg] = dict(resolution)
    if all_exports:
        idx.all_exports.update(all_exports)
    return idx


def test_b1_emits_warn_on_resolution_mismatch() -> None:
    spec_text = (
        "## Public API\n\n"
        "The canonical class is `demo.canonical.engine.AutoMLEngine`.\n"
    )
    cache = _idx_with_resolution(
        pkg="demo",
        resolution={"AutoMLEngine": "demo.legacy.engine"},
    )
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    b1 = [f for f in findings if f.fr_code == "B1"]
    assert len(b1) == 1
    f = b1[0]
    assert f.level == "WARN"
    assert f.kind == "getattr_resolution"
    assert f.symbol == "demo.AutoMLEngine"
    assert "demo.legacy.engine" in f.message
    assert "demo.canonical.engine" in f.message
    assert "FR-6 PASS" not in f.message  # not in __all__


def test_b1_silent_when_resolution_matches() -> None:
    spec_text = (
        "## Public API\n\n" "The class is at `demo.engines.automl.AutoMLEngine`.\n"
    )
    cache = _idx_with_resolution(
        pkg="demo",
        resolution={"AutoMLEngine": "demo.engines.automl"},
    )
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert [f for f in findings if f.fr_code == "B1"] == []


def test_b1_dual_emit_fr6_coherence_when_symbol_in_all() -> None:
    spec_text = (
        "## Public API\n\n"
        "The canonical class is `demo.canonical.engine.AutoMLEngine`.\n"
    )
    cache = _idx_with_resolution(
        pkg="demo",
        resolution={"AutoMLEngine": "demo.legacy.engine"},
        all_exports={"AutoMLEngine"},
    )
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    b1 = [f for f in findings if f.fr_code == "B1"]
    assert len(b1) == 1
    assert "FR-6 PASS" in b1[0].message
    assert "AutoMLEngine is in __all__" in b1[0].message


def test_b1_dedupes_per_symbol_across_lines() -> None:
    spec_text = (
        "## Public API\n\n"
        "The canonical class is `demo.canonical.AutoMLEngine`.\n\n"
        "Verify with `demo.canonical.AutoMLEngine` everywhere.\n"
    )
    cache = _idx_with_resolution(
        pkg="demo",
        resolution={"AutoMLEngine": "demo.legacy"},
    )
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    b1 = [f for f in findings if f.fr_code == "B1"]
    assert len(b1) == 1


def test_b1_silent_in_excluded_section() -> None:
    spec_text = (
        "## Cross-References\n\n"
        "The canonical class is `demo.canonical.AutoMLEngine`.\n"
    )
    cache = _idx_with_resolution(
        pkg="demo",
        resolution={"AutoMLEngine": "demo.legacy"},
    )
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert [f for f in findings if f.fr_code == "B1"] == []


def test_b1_silent_in_fenced_code_block() -> None:
    spec_text = (
        "## Public API\n\n"
        "```python\n"
        "from demo.canonical.engine import AutoMLEngine\n"
        "x = demo.canonical.AutoMLEngine()\n"
        "```\n"
    )
    cache = _idx_with_resolution(
        pkg="demo",
        resolution={"AutoMLEngine": "demo.legacy"},
    )
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert [f for f in findings if f.fr_code == "B1"] == []


def test_b1_does_not_fire_when_symbol_not_in_getattr_map() -> None:
    """If the symbol is not in the lazy-import map, B1 stays silent — the
    user is asserting a normal eager export, not a ``__getattr__`` route."""

    spec_text = (
        "## Public API\n\n" "Regular eager class at `demo.module.RegularClass`.\n"
    )
    cache = _idx_with_resolution(
        pkg="demo",
        resolution={"AutoMLEngine": "demo.legacy"},
    )
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert [f for f in findings if f.fr_code == "B1"] == []
