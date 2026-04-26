"""Tier 1 unit tests for SDG-301: baseline JSONL + diff logic.

Covers:

- BaselineEntry round-trip (write → read → equality)
- Sort determinism (stable JSONL order across runs)
- BaselineParseError on every malformed-input class:
  * invalid JSON
  * missing required fields
  * non-int line, bad ISO date, free-form origin
- diff_findings classification matrix:
  * new / pre_existing / resolved / expired (>= 90d) / expired_2x (>= 180d)
- identity match excludes line (line shifts don't invalidate entries)
"""

from __future__ import annotations

import pytest
from datetime import date
from pathlib import Path

from spec_drift_gate import (
    BaselineEntry,
    BaselineParseError,
    Finding,
    diff_findings,
    read_baseline,
    write_baseline,
)


@pytest.fixture
def baseline_path(tmp_path: Path) -> Path:
    return tmp_path / "baseline.jsonl"


def _entry(
    spec: str = "specs/x.md",
    line: int = 1,
    finding: str = "FR-1",
    symbol: str = "Foo",
    kind: str = "class",
    origin: str = "F-E2-01",
    added: date | None = None,
    ageout: date | None = None,
) -> BaselineEntry:
    return BaselineEntry(
        spec=spec,
        line=line,
        finding=finding,
        symbol=symbol,
        kind=kind,
        origin=origin,
        added=added or date(2026, 4, 26),
        ageout=ageout or date(2026, 7, 25),
    )


class TestRoundTrip:
    def test_empty_file_returns_empty_list(self, baseline_path: Path) -> None:
        baseline_path.write_text("")
        assert read_baseline(baseline_path) == []

    def test_missing_file_returns_empty_list(self, baseline_path: Path) -> None:
        # File deliberately not created
        assert read_baseline(baseline_path) == []

    def test_round_trip_preserves_entries(self, baseline_path: Path) -> None:
        entries = [
            _entry(spec="specs/a.md", line=10, symbol="Bar"),
            _entry(spec="specs/x.md", line=5, symbol="Foo"),
        ]
        write_baseline(entries, baseline_path)
        parsed = read_baseline(baseline_path)
        assert parsed == sorted(entries, key=BaselineEntry.sort_key)

    def test_write_is_deterministic_across_runs(self, baseline_path: Path) -> None:
        # Order of input entries should NOT affect on-disk byte order.
        e1 = _entry(spec="specs/a.md", line=10)
        e2 = _entry(spec="specs/x.md", line=5)
        write_baseline([e1, e2], baseline_path)
        bytes_a = baseline_path.read_bytes()
        write_baseline([e2, e1], baseline_path)
        bytes_b = baseline_path.read_bytes()
        assert bytes_a == bytes_b

    def test_blank_lines_are_skipped(self, baseline_path: Path) -> None:
        e = _entry()
        write_baseline([e], baseline_path)
        # Inject a blank line — read should succeed
        with baseline_path.open("a") as fh:
            fh.write("\n\n")
        assert read_baseline(baseline_path) == [e]


class TestParseErrors:
    def test_invalid_json_raises(self, baseline_path: Path) -> None:
        baseline_path.write_text("not-json\n")
        with pytest.raises(BaselineParseError, match="invalid JSON"):
            read_baseline(baseline_path)

    def test_missing_required_fields_raises(self, baseline_path: Path) -> None:
        baseline_path.write_text('{"spec": "x"}\n')
        with pytest.raises(BaselineParseError, match="missing required fields"):
            read_baseline(baseline_path)

    def test_non_int_line_raises(self, baseline_path: Path) -> None:
        baseline_path.write_text(
            '{"spec":"x","line":"abc","finding":"FR-1","symbol":"S","kind":"c",'
            '"origin":"gh-1","added":"2026-04-26","ageout":"2026-07-25"}\n'
        )
        with pytest.raises(BaselineParseError, match="not int"):
            read_baseline(baseline_path)

    def test_bad_iso_date_raises(self, baseline_path: Path) -> None:
        baseline_path.write_text(
            '{"spec":"x","line":1,"finding":"FR-1","symbol":"S","kind":"c",'
            '"origin":"gh-1","added":"not-a-date","ageout":"2026-07-25"}\n'
        )
        with pytest.raises(BaselineParseError, match="ISO YYYY-MM-DD"):
            read_baseline(baseline_path)

    def test_freeform_origin_rejected(self, baseline_path: Path) -> None:
        baseline_path.write_text(
            '{"spec":"x","line":1,"finding":"FR-1","symbol":"S","kind":"c",'
            '"origin":"some prose","added":"2026-04-26","ageout":"2026-07-25"}\n'
        )
        with pytest.raises(BaselineParseError, match="origin must match"):
            read_baseline(baseline_path)

    @pytest.mark.parametrize(
        "valid_origin",
        ["F-E2-01", "F-E10-99", "#642", "#642-discovery", "gh-123", "PR-456"],
    )
    def test_valid_origins_accepted(
        self, baseline_path: Path, valid_origin: str
    ) -> None:
        e = _entry(origin=valid_origin)
        write_baseline([e], baseline_path)
        assert read_baseline(baseline_path) == [e]


class TestDiffClassification:
    def test_today_only_finding_is_new(self) -> None:
        f = Finding("specs/a.md", 1, "FR-1", "Foo", "class", "msg")
        diff = diff_findings([f], [], today_date=date(2026, 4, 26))
        assert diff.new == [f]
        assert diff.pre_existing == []
        assert diff.resolved == []

    def test_baseline_only_entry_is_resolved(self) -> None:
        b = _entry()
        diff = diff_findings([], [b], today_date=date(2026, 4, 26))
        assert diff.resolved == [b]
        assert diff.new == []

    def test_match_on_identity_excludes_line(self) -> None:
        # Same (spec, finding, symbol, kind) but different line — pre-existing.
        f = Finding("specs/a.md", 99, "FR-1", "Foo", "class", "msg")
        b = _entry(spec="specs/a.md", line=1, finding="FR-1", symbol="Foo")
        diff = diff_findings([f], [b], today_date=date(2026, 4, 26))
        assert diff.pre_existing == [f]
        assert diff.new == []
        assert diff.resolved == []

    def test_expired_at_90_days(self) -> None:
        # added 2026-01-26, today 2026-04-26 → exactly 90 days → expired
        b = _entry(added=date(2026, 1, 26), ageout=date(2026, 4, 26))
        f = Finding("specs/x.md", 1, "FR-1", "Foo", "class", "msg")
        diff = diff_findings([f], [b], today_date=date(2026, 4, 26))
        assert diff.expired == [b]
        assert diff.expired_2x == []

    def test_expired_2x_at_180_days(self) -> None:
        # added 2025-10-28, today 2026-04-26 → 180 days → expired_2x
        b = _entry(added=date(2025, 10, 28), ageout=date(2026, 1, 26))
        f = Finding("specs/x.md", 1, "FR-1", "Foo", "class", "msg")
        diff = diff_findings([f], [b], today_date=date(2026, 4, 26))
        assert diff.expired_2x == [b]
        assert diff.expired == []

    def test_fresh_entry_no_warn(self) -> None:
        b = _entry(added=date(2026, 4, 20))
        f = Finding("specs/x.md", 1, "FR-1", "Foo", "class", "msg")
        diff = diff_findings([f], [b], today_date=date(2026, 4, 26))
        assert diff.expired == []
        assert diff.expired_2x == []
        assert diff.pre_existing == [f]

    def test_classification_is_total(self) -> None:
        # Every today-finding lands in exactly one of new / pre_existing.
        f1 = Finding("specs/a.md", 1, "FR-1", "Foo", "class", "msg")
        f2 = Finding("specs/b.md", 1, "FR-1", "Bar", "class", "msg")
        b = _entry(spec="specs/a.md", finding="FR-1", symbol="Foo")
        diff = diff_findings([f1, f2], [b], today_date=date(2026, 4, 26))
        assert sorted([f.symbol for f in diff.new + diff.pre_existing]) == [
            "Bar",
            "Foo",
        ]
