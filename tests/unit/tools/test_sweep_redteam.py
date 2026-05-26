"""Tier-1 unit tests for tools/sweep-redteam.py (#1129).

Each test sets up a temporary fixture tree (specs/ + source files +
tests/integration/) that emulates the production repo layout the tool
walks, then asserts the JSONL findings + sentinel + exit code.

The tool resolves ROOT via Path(__file__).resolve().parent.parent at
import time (binding ROOT to the kailash-py checkout). For Tier-1
isolation we monkeypatch the module-level ROOT to point at a tmp_path
fixture tree per `rules/testing.md` Tier-1 (mocking allowed, <1s).
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

# --- Module import --------------------------------------------------------
# The tool ships with a hyphen in its filename; load it explicitly so the
# tests can drive its public functions without renaming the script.

_TOOL_PATH = Path(__file__).resolve().parents[3] / "tools" / "sweep-redteam.py"


def _load_tool_module():
    spec = importlib.util.spec_from_file_location("sweep_redteam", _TOOL_PATH)
    assert spec is not None and spec.loader is not None, _TOOL_PATH
    module = importlib.util.module_from_spec(spec)
    sys.modules["sweep_redteam"] = module
    spec.loader.exec_module(module)
    return module


sweep_redteam = _load_tool_module()


# --- Fixture builders ------------------------------------------------------


def _build_workspace_tree(
    root: Path,
    *,
    spec_body: str = "",
    source_files: dict[str, str] | None = None,
    integration_tests: dict[str, str] | None = None,
    workspace_name: str = "ws1",
    spec_filename: str = "spec.md",
) -> Path:
    """Build a fixture tree at root that emulates the real repo layout.

    Returns the spec file's path. The caller monkeypatches the tool's
    ROOT to `root` so candidate_source_files / has_tier2_coverage scan
    the fixture tree instead of the live checkout.
    """
    ws_specs = root / "workspaces" / workspace_name / "specs"
    ws_specs.mkdir(parents=True, exist_ok=True)
    spec_path = ws_specs / spec_filename
    spec_path.write_text(spec_body, encoding="utf-8")

    if source_files:
        for rel, content in source_files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    tests_integration = root / "tests" / "integration"
    tests_integration.mkdir(parents=True, exist_ok=True)
    if integration_tests:
        for rel, content in integration_tests.items():
            target = tests_integration / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    return spec_path


def _run_tool(monkeypatch, root: Path) -> tuple[int, list[dict], str]:
    """Run the tool against `root`; return (exit_code, findings, sentinel).

    Captures stdout via an in-memory buffer; parses every JSONL line as
    a finding except the final HTML-comment sentinel.
    """
    monkeypatch.setattr(sweep_redteam, "ROOT", root)
    specs = list(sweep_redteam.iter_spec_files(None))
    buf = io.StringIO()
    exit_code = sweep_redteam.run(specs, buf)
    lines = [ln for ln in buf.getvalue().splitlines() if ln]
    assert lines, "tool emitted no output (sentinel always required)"
    sentinel = lines[-1]
    assert sentinel.startswith("<!-- sweep-redteam:v1:OK ") and sentinel.endswith(
        " -->"
    ), f"sentinel malformed: {sentinel!r}"
    findings = [json.loads(ln) for ln in lines[:-1]]
    return exit_code, findings, sentinel


def _parse_sentinel(sentinel: str) -> dict[str, int]:
    """Extract specs=N symbols=M orphans=O coverage_gaps=C stubs=S."""
    inner = sentinel.removeprefix("<!-- sweep-redteam:v1:OK ").removesuffix(" -->")
    return {k: int(v) for k, v in (kv.split("=") for kv in inner.split())}


# --- Test cases (mapped to issue #1129 acceptance criteria) ---------------


def test_empty_specs_directory_emits_zero_sentinel(tmp_path, monkeypatch):
    """Case 1: no spec files → sentinel reports zeros across every axis;
    exit 0 because nothing was scanned.

    Confirms the tool emits the sentinel even when there's no work — the
    Sweep 5 protocol depends on the sentinel always being grep-able in
    the report.
    """
    # Build an empty workspace structure (no spec file written).
    (tmp_path / "workspaces" / "ws1" / "specs").mkdir(parents=True)
    monkeypatch.setattr(sweep_redteam, "ROOT", tmp_path)

    specs = list(sweep_redteam.iter_spec_files(None))
    assert specs == [], "empty specs dir should yield no spec files"

    buf = io.StringIO()
    exit_code = sweep_redteam.run(specs, buf)
    sentinel = buf.getvalue().strip()

    assert exit_code == 0
    parsed = _parse_sentinel(sentinel)
    assert parsed == {
        "specs": 0,
        "symbols": 0,
        "orphans": 0,
        "coverage_gaps": 0,
        "stubs": 0,
    }


def test_all_passing_spec_emits_no_findings(tmp_path, monkeypatch):
    """Case 2: spec promises symbol; source has it; Tier-2 test imports it.

    Expects: zero findings, sentinel reports symbols=1 with all gaps at 0,
    exit code 0.
    """
    spec_body = (
        "# Spec\n"
        "## API\n"
        "The runtime MUST use `myapp.api.Engine` for orchestration.\n"
    )
    source = (
        "class Engine:\n"
        '    """Real implementation."""\n'
        "    def run(self):\n"
        "        return 42\n"
    )
    integration_test = (
        "from myapp.api import Engine\n"
        "\n"
        "def test_engine_runs():\n"
        "    assert Engine().run() == 42\n"
    )
    _build_workspace_tree(
        tmp_path,
        spec_body=spec_body,
        source_files={"src/myapp/api.py": source},
        integration_tests={"test_engine.py": integration_test},
    )

    exit_code, findings, sentinel = _run_tool(monkeypatch, tmp_path)

    assert findings == [], f"unexpected findings: {findings}"
    parsed = _parse_sentinel(sentinel)
    assert parsed["specs"] == 1
    assert parsed["symbols"] == 1
    assert parsed["orphans"] == 0
    assert parsed["coverage_gaps"] == 0
    assert parsed["stubs"] == 0
    assert exit_code == 0


def test_orphan_when_source_missing(tmp_path, monkeypatch):
    """Case 3: spec promises symbol; source file missing entirely.

    Expects: one `orphan` finding citing the unresolved symbol; sentinel
    reports orphans=1; exit code 1.
    """
    spec_body = (
        "# Spec\n"
        "Implementations MUST provide `myapp.missing.Vanished` for the gateway.\n"
    )
    # NO source files written at all; tests/integration left empty.
    _build_workspace_tree(tmp_path, spec_body=spec_body)

    exit_code, findings, sentinel = _run_tool(monkeypatch, tmp_path)

    assert exit_code == 1
    assert len(findings) == 1, findings
    finding = findings[0]
    assert finding["category"] == "orphan"
    assert finding["symbol"] == "myapp.missing.Vanished"
    assert finding["source"] is None
    assert "no candidate source files" in finding["evidence"]
    parsed = _parse_sentinel(sentinel)
    assert parsed["orphans"] == 1
    assert parsed["coverage_gaps"] == 0
    assert parsed["stubs"] == 0


def test_coverage_gap_when_no_tier2_import(tmp_path, monkeypatch):
    """Case 4: spec promises symbol; source present; no Tier-2 import.

    Expects: one `coverage_gap` finding; sentinel reports coverage_gaps=1;
    exit code 1. The source-presence check passes (no orphan); the stub
    check passes (real body); only the Tier-2 grep returns empty.
    """
    spec_body = "# Spec\n" "Every request MUST route through `myapp.gateway.Router`.\n"
    source = (
        "class Router:\n"
        "    def dispatch(self, request):\n"
        "        return self._handlers[request.path](request)\n"
        "    def __init__(self):\n"
        "        self._handlers = {}\n"
    )
    _build_workspace_tree(
        tmp_path,
        spec_body=spec_body,
        source_files={"src/myapp/gateway.py": source},
        # No integration_tests — directory exists but contains no imports.
        integration_tests={},
    )

    exit_code, findings, sentinel = _run_tool(monkeypatch, tmp_path)

    assert exit_code == 1
    assert len(findings) == 1, findings
    finding = findings[0]
    assert finding["category"] == "coverage_gap"
    assert finding["symbol"] == "myapp.gateway.Router"
    assert finding["source"] is not None
    assert "src/myapp/gateway.py" in finding["source"]
    assert "tests/integration" in finding["evidence"]
    parsed = _parse_sentinel(sentinel)
    assert parsed["orphans"] == 0
    assert parsed["coverage_gaps"] == 1
    assert parsed["stubs"] == 0


def test_stub_when_body_raises_not_implemented(tmp_path, monkeypatch):
    """Case 5: spec promises symbol; source present; body is a stub.

    Body shape: `raise NotImplementedError(...)` as the sole statement.
    Expects: one `stub` finding (and one `coverage_gap` because the
    fixture also leaves Tier-2 empty — confirming the categories compose
    independently). Sentinel reports stubs=1 + coverage_gaps=1; exit 1.
    """
    spec_body = "# Spec\n" "The cache layer MUST implement `myapp.cache.LRU.evict`.\n"
    source = (
        "class LRU:\n"
        "    def evict(self, key):\n"
        '        raise NotImplementedError("TODO in next sprint")\n'
    )
    _build_workspace_tree(
        tmp_path,
        spec_body=spec_body,
        source_files={"src/myapp/cache.py": source},
    )

    exit_code, findings, sentinel = _run_tool(monkeypatch, tmp_path)

    assert exit_code == 1
    categories = sorted(f["category"] for f in findings)
    assert categories == ["coverage_gap", "stub"], findings

    stub_finding = next(f for f in findings if f["category"] == "stub")
    assert stub_finding["symbol"] == "myapp.cache.LRU.evict"
    assert "NotImplementedError" in stub_finding["evidence"]

    parsed = _parse_sentinel(sentinel)
    assert parsed["stubs"] == 1
    assert parsed["coverage_gaps"] == 1
    assert parsed["orphans"] == 0


# --- MUST-symbol extraction sanity checks (documented heuristic) ----------


def test_extract_symbols_requires_must_token(tmp_path):
    """Backticked symbols on non-MUST lines are NOT extracted.

    The heuristic deliberately requires the literal `MUST` token on the
    SAME line as the backticked identifier; this prevents incidental
    `Module.Name` mentions in prose from polluting the audit. Test the
    contract documented in the tool's module docstring.
    """
    spec = tmp_path / "doc.md"
    spec.write_text(
        "# Notes\n"
        "Reference: `myapp.unused.Symbol` is described elsewhere.\n"
        "Implementations MUST provide `myapp.real.Symbol` everywhere.\n",
        encoding="utf-8",
    )
    syms = sweep_redteam.extract_symbols(spec)
    names = [s.name for s in syms]
    assert names == ["myapp.real.Symbol"], names


def test_extract_symbols_deduplicates_repeats(tmp_path):
    """Same symbol mentioned twice yields one entry (first-seen wins)."""
    spec = tmp_path / "doc.md"
    spec.write_text(
        "## §1\nMUST use `myapp.api.Engine` on line 2.\n"
        "## §2\nMUST also use `myapp.api.Engine` on line 4.\n",
        encoding="utf-8",
    )
    syms = sweep_redteam.extract_symbols(spec)
    assert len(syms) == 1
    assert syms[0].spec_line == 2, "first-seen line wins for dedup"


def test_sentinel_field_shape_matches_spec(tmp_path, monkeypatch):
    """Sentinel verbatim matches the documented shape in commands/sweep.md.

    `<!-- sweep-redteam:v1:OK specs=N symbols=M orphans=O coverage_gaps=C stubs=S -->`
    """
    # Empty workspaces produces a stable sentinel — easy structural check.
    (tmp_path / "workspaces" / "ws1" / "specs").mkdir(parents=True)
    monkeypatch.setattr(sweep_redteam, "ROOT", tmp_path)
    buf = io.StringIO()
    sweep_redteam.run([], buf)
    sentinel = buf.getvalue().strip()
    expected = (
        "<!-- sweep-redteam:v1:OK specs=0 symbols=0 "
        "orphans=0 coverage_gaps=0 stubs=0 -->"
    )
    assert sentinel == expected
