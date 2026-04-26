"""Tier-1 unit tests for FR-8 workspace-artifact leak sweep (SDG-202).

The sweep operates DOCUMENT-WIDE (not per-section) because a leaked
workspace ID is wrong everywhere. Suppressed contexts:
- ``## Cross-References`` and other excluded section headings
- Fenced code blocks
- Lines starting with ``Origin:`` / ``Citation:`` / ``Status:`` / etc.
- Lines inside negated subsections (``### Drift To Clean Up`` etc.)
- Lines whose paragraph carries a NOT / "Until then" / etc. negation

``W31 31b`` shorthand IDs are unconditional leaks.
``workspaces/<dir>`` paths are leaks UNLESS the line carries a citation
prefix or marker.
"""

from __future__ import annotations

from pathlib import Path

from spec_drift_gate import (
    SymbolIndex,
    parse_overrides,
    run_sweeps,
    scan_sections,
)


def _findings(spec_text: str) -> list:
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    return run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=SymbolIndex(),
    )


def test_w_shorthand_in_prose_emits_finding() -> None:
    spec_text = (
        "# Foo\n\n"
        "## 9. Discussion\n\n"
        "The bug surfaced via W31 31b investigation.\n"
    )
    findings = [f for f in _findings(spec_text) if f.fr_code == "FR-8"]
    assert len(findings) == 1
    assert findings[0].symbol == "W31 31b"
    assert findings[0].kind == "workspace_leak"


def test_workspace_path_in_status_header_silent() -> None:
    spec_text = (
        "# Foo\n\n"
        "Status: DRAFT at `workspaces/audit/draft-v1.md` until merge.\n\n"
        "## 1. Overview\n\nBody.\n"
    )
    assert [f for f in _findings(spec_text) if f.fr_code == "FR-8"] == []


def test_workspace_path_with_origin_prefix_silent() -> None:
    spec_text = (
        "# Foo\n\n"
        "## 1. Overview\n\n"
        "Origin: workspaces/audit/round-1-findings.md is the source.\n"
    )
    assert [f for f in _findings(spec_text) if f.fr_code == "FR-8"] == []


def test_workspace_path_unprefixed_emits_finding() -> None:
    spec_text = (
        "# Foo\n\n"
        "## 1. Overview\n\n"
        "Tracked in workspaces/audit/draft.md without explicit citation.\n"
    )
    findings = [f for f in _findings(spec_text) if f.fr_code == "FR-8"]
    assert len(findings) == 1
    assert findings[0].kind == "workspace_path"


def test_excluded_cross_references_section_silent() -> None:
    spec_text = (
        "# Foo\n\n"
        "## 1. Overview\n\nBody text.\n\n"
        "## Cross-References\n\n"
        "- workspaces/audit/round-1.md\n"
        "- workspaces/portfolio/W5-E2-findings.md\n"
    )
    assert [f for f in _findings(spec_text) if f.fr_code == "FR-8"] == []


def test_negated_subsection_silences_fr8() -> None:
    """A subsection heading like ``### 7.3 Source-Comment Drift To Clean Up``
    or ``### 9.3 No Cross-Process X (Yet)`` silences FR-8 inside its body."""

    spec_text = (
        "# Foo\n\n"
        "## 7. Discussion\n\n"
        "### 7.3 Drift To Clean Up In Wave 6\n\n"
        "The error message references W31 31b — a workspace artifact.\n"
    )
    assert [f for f in _findings(spec_text) if f.fr_code == "FR-8"] == []


def test_yet_parenthetical_silences_fr8() -> None:
    spec_text = (
        "# Foo\n\n"
        "## 9. Discussion\n\n"
        "### 9.3 No Cross-Process Cost Tracker (Yet)\n\n"
        "W32 32a is the planned future implementation.\n"
    )
    assert [f for f in _findings(spec_text) if f.fr_code == "FR-8"] == []


def test_inline_negation_silences_fr8() -> None:
    """Paragraph-level NOT / Until-then markers also silence FR-8."""

    spec_text = (
        "# Foo\n\n"
        "## 9. Discussion\n\n"
        "Wave 6 follow-up: rename the W31 31b reference. Do NOT edit in this round.\n"
    )
    assert [f for f in _findings(spec_text) if f.fr_code == "FR-8"] == []


def test_fenced_code_block_silences_fr8() -> None:
    spec_text = (
        "# Foo\n\n"
        "## 1. Overview\n\n"
        "```\n# Example: workspaces/test/fixture.md\nW31 31b\n```\n"
    )
    assert [f for f in _findings(spec_text) if f.fr_code == "FR-8"] == []
