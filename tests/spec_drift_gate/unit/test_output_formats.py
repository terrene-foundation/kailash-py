"""Tier 1 unit tests for SDG-302: --format human / json / github + ADR-6.

Covers:

- fix_hint_for() returns (a)/(b)/(c) triad for every FR catalog entry
- _emit_json shape + meta block + severity field
- _emit_github GitHub-Actions-annotation regex match
- exit code semantics (FAIL=1, WARN/PASS=0)
- escape rules for GitHub format (`,` and newlines)
"""

from __future__ import annotations

import io
import json
import re
import contextlib

import pytest

from spec_drift_gate import (
    BaselineEntry,
    Finding,
    fix_hint_for,
    _emit_human,
    _emit_json,
    _emit_github,
    FIX_HINT_CATALOG,
)
from datetime import date


def _f(
    fr_code: str = "FR-1",
    symbol: str = "Foo",
    kind: str = "class",
    level: str = "FAIL",
    spec: str = "specs/x.md",
    line: int = 10,
    message: str = "missing",
) -> Finding:
    return Finding(spec, line, fr_code, symbol, kind, message, level=level)


class TestFixHintCatalog:
    @pytest.mark.parametrize("fr_code", list(FIX_HINT_CATALOG.keys()))
    def test_every_fr_has_triad(self, fr_code: str) -> None:
        f = _f(fr_code=fr_code, symbol="Bar")
        hint = fix_hint_for(f)
        assert hint.startswith("→ fix:")
        # ADR-6: exactly 3 options, separated by " OR "
        assert ", OR (b) " in hint
        assert ", OR (c) " in hint

    def test_unknown_fr_falls_back(self) -> None:
        f = _f(fr_code="FR-99", symbol="Bar")
        hint = fix_hint_for(f)
        assert "(a)" in hint and "(b)" in hint and "(c)" in hint
        assert "Bar" in hint

    def test_fr4_hint_cites_orphan_detection_rule(self) -> None:
        f = _f(fr_code="FR-4", symbol="MyError", kind="error_class")
        hint = fix_hint_for(f)
        assert "errors module" in hint
        assert "orphan-detection.md" in hint

    def test_fr7_hint_cites_facade_manager_rule(self) -> None:
        f = _f(fr_code="FR-7", symbol="tests/integration/test_x.py")
        hint = fix_hint_for(f)
        assert "facade-manager-detection.md" in hint


class TestJsonEmitter:
    def test_shape_includes_meta_findings_expired(self) -> None:
        f = _f()
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = _emit_json([f], suppressed_count=3, expired_warns=[])
        payload = json.loads(buf.getvalue())
        assert set(payload.keys()) == {"meta", "findings", "expired_baseline"}
        assert payload["meta"]["suppressed_baseline_count"] == 3
        assert payload["meta"]["expired_baseline_count"] == 0
        assert code == 1  # FAIL findings → exit 1

    def test_finding_object_has_required_fields(self) -> None:
        f = _f(fr_code="FR-4", symbol="MyError", kind="error_class")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            _emit_json([f], suppressed_count=0, expired_warns=[])
        payload = json.loads(buf.getvalue())
        entry = payload["findings"][0]
        assert set(entry.keys()) >= {
            "spec",
            "line",
            "finding",
            "symbol",
            "kind",
            "severity",
            "message",
            "fix_hint",
        }
        assert entry["severity"] == "FAIL"
        assert entry["fix_hint"].startswith("→ fix:")

    def test_warn_finding_has_null_fix_hint(self) -> None:
        f = _f(level="WARN")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            _emit_json([f], suppressed_count=0, expired_warns=[])
        payload = json.loads(buf.getvalue())
        assert payload["findings"][0]["fix_hint"] is None

    def test_expired_baseline_block(self) -> None:
        b = BaselineEntry(
            "specs/x.md",
            5,
            "FR-1",
            "Foo",
            "class",
            "F-E2-01",
            date(2026, 1, 1),
            date(2026, 4, 1),
        )
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = _emit_json([], suppressed_count=0, expired_warns=[b])
        payload = json.loads(buf.getvalue())
        assert payload["meta"]["expired_baseline_count"] == 1
        assert payload["expired_baseline"][0]["origin"] == "F-E2-01"
        assert code == 0  # WARN-only → exit 0

    def test_warn_only_returns_zero(self) -> None:
        f = _f(level="WARN")
        with contextlib.redirect_stdout(io.StringIO()):
            code = _emit_json([f], suppressed_count=0, expired_warns=[])
        assert code == 0


class TestGitHubEmitter:
    GH_LINE_RE = re.compile(r"^::(error|warning) file=([^,]+),line=(\d+)::(.+)$")

    def test_fail_emits_error_annotation(self) -> None:
        f = _f(level="FAIL")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = _emit_github([f])
        line = buf.getvalue().strip()
        m = self.GH_LINE_RE.match(line)
        assert m, f"line did not match GH annotation regex: {line!r}"
        assert m.group(1) == "error"
        assert m.group(2) == "specs/x.md"
        assert m.group(3) == "10"
        assert code == 1

    def test_warn_emits_warning_annotation(self) -> None:
        f = _f(level="WARN")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = _emit_github([f])
        line = buf.getvalue().strip()
        m = self.GH_LINE_RE.match(line)
        assert m and m.group(1) == "warning"
        assert code == 0

    def test_fail_message_includes_fix_hint(self) -> None:
        f = _f(level="FAIL", fr_code="FR-4", symbol="MyError")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            _emit_github([f])
        out = buf.getvalue()
        # GH annotations cannot have raw newlines — `→ fix:` must be inline
        assert "→ fix:" in out
        assert out.count("\n") == 1  # exactly one annotation, one newline

    def test_commas_in_message_are_escaped(self) -> None:
        # Commas in the message would terminate the annotation prematurely;
        # the emitter MUST escape them as %2C.
        f = _f(level="FAIL", message="missing, comma in message")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            _emit_github([f])
        line = buf.getvalue().strip()
        # Header has line=10 (with comma), but rest of message commas escaped
        m = self.GH_LINE_RE.match(line)
        assert m
        assert "%2C" in m.group(4)

    def test_expired_baseline_warning(self) -> None:
        b = BaselineEntry(
            "specs/x.md",
            5,
            "FR-1",
            "Foo",
            "class",
            "F-E2-01",
            date(2026, 1, 1),
            date(2026, 4, 1),
        )
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = _emit_github([], expired_warns=[b])
        out = buf.getvalue()
        assert out.startswith("::warning ")
        assert "baseline-expired" in out
        assert code == 0


class TestHumanEmitter:
    def test_fail_finding_indents_fix_hint(self) -> None:
        from pathlib import Path

        f = _f()
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            _emit_human(
                [f],
                spec_paths=[Path("specs/x.md")],
                sections_by_spec={"specs/x.md": []},
            )
        out = buf.getvalue()
        # Fix-hint line is indented with 2 spaces
        assert "  → fix:" in out

    def test_suppressed_count_line(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            _emit_human(
                [],
                spec_paths=[],
                sections_by_spec={},
                suppressed_count=5,
            )
        assert "INFO baseline grace: 5 pre-existing" in buf.getvalue()

    def test_expired_warns_emit_warn_lines(self) -> None:
        b = BaselineEntry(
            "specs/x.md",
            5,
            "FR-1",
            "Foo",
            "class",
            "F-E2-01",
            date(2026, 1, 1),
            date(2026, 4, 1),
        )
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = _emit_human(
                [],
                spec_paths=[],
                sections_by_spec={},
                expired_warns=[b],
            )
        out = buf.getvalue()
        assert "WARN baseline expired" in out
        assert "F-E2-01" in out
        assert code == 0
