"""Tier 1 unit tests for SDG-303: --refresh-baseline + ageout state machine.

Covers:

- ageout_state(): fresh / expired (>=90d) / expired_2x (>=180d)
- archive_resolved(): appends, never overwrites; carries resolved_sha + resolved_at
- parse_filter / apply_filter: origin / spec / finding / symbol scoping
- malformed --filter raises typed error
"""

from __future__ import annotations

import json
import pytest
from datetime import date
from pathlib import Path

from spec_drift_gate import (
    BaselineEntry,
    SpecDriftGateError,
    DEFAULT_AGEOUT_DAYS,
    ageout_state,
    apply_filter,
    archive_resolved,
    parse_filter,
)


def _entry(
    spec: str = "specs/x.md",
    origin: str = "F-E2-01",
    finding: str = "FR-1",
    symbol: str = "Foo",
    added: date | None = None,
) -> BaselineEntry:
    d_added = added or date(2026, 4, 26)
    return BaselineEntry(
        spec=spec,
        line=1,
        finding=finding,
        symbol=symbol,
        kind="class",
        origin=origin,
        added=d_added,
        ageout=date(2026, 7, 25),
    )


class TestAgeoutState:
    @pytest.mark.parametrize(
        "added,today,expected",
        [
            (date(2026, 4, 20), date(2026, 4, 26), "fresh"),  # 6 days
            (date(2026, 1, 26), date(2026, 4, 26), "expired"),  # 90 days
            (date(2026, 1, 1), date(2026, 4, 26), "expired"),  # >90 < 180
            (date(2025, 10, 28), date(2026, 4, 26), "expired_2x"),  # 180 days
            (date(2025, 1, 1), date(2026, 4, 26), "expired_2x"),  # well past
        ],
    )
    def test_state_transitions(self, added: date, today: date, expected: str) -> None:
        e = _entry(added=added)
        assert ageout_state(e, today=today) == expected

    def test_default_ageout_days_used(self) -> None:
        # Verify the default constant is 90
        assert DEFAULT_AGEOUT_DAYS == 90

    def test_custom_ageout_days(self) -> None:
        # 30-day ageout: 31 days past = expired
        e = _entry(added=date(2026, 3, 25))
        assert ageout_state(e, today=date(2026, 4, 26), ageout_days=30) == "expired"


class TestParseFilter:
    def test_empty_filter_returns_empty_dict(self) -> None:
        assert parse_filter(None) == {}
        assert parse_filter("") == {}

    def test_single_predicate(self) -> None:
        assert parse_filter("origin:F-E2-12") == {"origin": "F-E2-12"}

    def test_multi_predicate_comma_separated(self) -> None:
        assert parse_filter("origin:F-E2-12,finding:FR-4") == {
            "origin": "F-E2-12",
            "finding": "FR-4",
        }

    def test_malformed_predicate_raises(self) -> None:
        with pytest.raises(SpecDriftGateError, match="malformed predicate"):
            parse_filter("no-colon")

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(SpecDriftGateError, match="unknown key"):
            parse_filter("notakey:foo")


class TestApplyFilter:
    def test_no_predicates_passes_through(self) -> None:
        e = _entry()
        assert apply_filter([e], {}) == [e]

    def test_origin_scope(self) -> None:
        e1 = _entry(origin="F-E2-01")
        e2 = _entry(origin="F-E2-02")
        assert apply_filter([e1, e2], {"origin": "F-E2-01"}) == [e1]

    def test_spec_scope(self) -> None:
        e1 = _entry(spec="specs/a.md")
        e2 = _entry(spec="specs/b.md")
        assert apply_filter([e1, e2], {"spec": "specs/a.md"}) == [e1]

    def test_finding_scope(self) -> None:
        e1 = _entry(finding="FR-1")
        e2 = _entry(finding="FR-4")
        assert apply_filter([e1, e2], {"finding": "FR-4"}) == [e2]

    def test_compound_predicates_are_AND(self) -> None:
        e1 = _entry(origin="F-E2-01", finding="FR-1")
        e2 = _entry(origin="F-E2-01", finding="FR-4")
        e3 = _entry(origin="F-E2-99", finding="FR-1")
        result = apply_filter([e1, e2, e3], {"origin": "F-E2-01", "finding": "FR-1"})
        assert result == [e1]


class TestArchiveResolved:
    def test_appends_resolved_sha_and_resolved_at(self, tmp_path: Path) -> None:
        archive = tmp_path / "resolved.jsonl"
        e = _entry(origin="F-E2-12")
        n = archive_resolved(
            [e],
            archive,
            resolved_sha="abc1234",
            resolved_at=date(2026, 4, 26),
        )
        assert n == 1
        payload = json.loads(archive.read_text().strip())
        assert payload["resolved_sha"] == "abc1234"
        assert payload["resolved_at"] == "2026-04-26"
        assert payload["origin"] == "F-E2-12"

    def test_append_only_preserves_prior_entries(self, tmp_path: Path) -> None:
        archive = tmp_path / "resolved.jsonl"
        archive_resolved(
            [_entry(symbol="First")],
            archive,
            resolved_sha="old",
            resolved_at=date(2026, 1, 1),
        )
        archive_resolved(
            [_entry(symbol="Second")],
            archive,
            resolved_sha="new",
            resolved_at=date(2026, 4, 26),
        )
        lines = [json.loads(line) for line in archive.read_text().splitlines()]
        assert len(lines) == 2
        assert {p["symbol"] for p in lines} == {"First", "Second"}
        # Each entry retains its OWN resolved_sha — never overwritten
        sha_by_symbol = {p["symbol"]: p["resolved_sha"] for p in lines}
        assert sha_by_symbol == {"First": "old", "Second": "new"}

    def test_empty_input_is_no_op(self, tmp_path: Path) -> None:
        archive = tmp_path / "resolved.jsonl"
        n = archive_resolved([], archive, resolved_sha="x")
        assert n == 0
        assert not archive.exists()
