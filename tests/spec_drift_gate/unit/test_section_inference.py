"""Tier-1 unit tests for section-context inference (SDG-101).

Verifies the ADR-2 section heading allowlist:
- Headings matching the allowlist trigger sweeps.
- Headings outside the allowlist (Scope, Out of Scope, Industry Parity,
  Deferred to M2, Cross-References, Conformance Checklist) are silent.
- Numbered/prefixed headings ("## 2. Construction") are matched.
- Fenced code blocks must NOT be parsed as headings.
"""

from __future__ import annotations

import textwrap

from spec_drift_gate import ALLOWLIST, Section, scan_sections


def test_scan_sections_matches_canonical_construction_heading() -> None:
    text = textwrap.dedent(
        """\
        # Spec Title

        ## 2. Construction

        Symbol body.
        """
    )
    sections = scan_sections(text)

    matched = [s for s in sections if s.matched_frs]
    assert len(matched) == 1
    assert matched[0].heading.startswith("## 2. Construction")
    assert "FR-1" in matched[0].matched_frs
    assert "FR-2" in matched[0].matched_frs


def test_scan_sections_matches_errors_heading() -> None:
    text = "## 6. Errors\n\nSome content"
    sections = scan_sections(text)
    matched = [s for s in sections if "FR-4" in s.matched_frs]
    assert len(matched) == 1


def test_scan_sections_matches_test_contract_heading() -> None:
    text = "## 11. Test Contract\n\nlist of tests"
    sections = scan_sections(text)
    matched = [s for s in sections if "FR-7" in s.matched_frs]
    assert len(matched) == 1


def test_scan_sections_matches_surface_heading() -> None:
    text = "## Surface\n\nbody"
    sections = scan_sections(text)
    matched = [s for s in sections if "FR-1" in s.matched_frs]
    assert len(matched) == 1


def test_scan_sections_matches_public_api_heading() -> None:
    text = "## Public API\n\nbody"
    sections = scan_sections(text)
    matched = [s for s in sections if "FR-1" in s.matched_frs]
    assert len(matched) == 1


def test_scan_sections_skips_excluded_headings() -> None:
    """## Scope, ## Out of Scope, ## Industry Parity, ## Deferred to M2,
    ## Cross-References, ## Conformance Checklist MUST NOT match."""
    text = textwrap.dedent(
        """\
        ## 1. Scope

        body

        ## Out of Scope

        body

        ## Industry Parity

        body

        ## Deferred to M2

        body

        ## Cross-References

        body

        ## Conformance Checklist

        body

        ## Maintenance Notes

        body
        """
    )
    sections = scan_sections(text)
    matched = [s for s in sections if s.matched_frs]
    assert matched == [], f"Excluded sections wrongly matched: {matched}"


def test_scan_sections_skips_unrelated_headings() -> None:
    text = textwrap.dedent(
        """\
        ## 12. Maintenance Notes

        body

        ## 9. Persistence

        body
        """
    )
    sections = scan_sections(text)
    matched = [s for s in sections if s.matched_frs]
    assert matched == []


def test_scan_sections_excludes_headings_inside_fenced_code_blocks() -> None:
    """Lines inside a ``` ... ``` fence MUST NOT be parsed as headings,
    even if they start with `## `."""
    text = textwrap.dedent(
        """\
        ## 1. Scope

        ```python
        ## Construction      # this is INSIDE a fence — must be ignored
        x = 1
        ```

        ## 2. Construction

        body
        """
    )
    sections = scan_sections(text)
    construction = [s for s in sections if s.heading.startswith("## 2.")]
    assert len(construction) == 1
    # The "## Construction" inside a fence MUST NOT have triggered another match
    assert (
        sum(1 for s in sections if s.heading.startswith("## Construction")) == 0
    ), "fenced code block heading wrongly parsed"


def test_scan_sections_returns_section_objects_with_line_ranges() -> None:
    text = textwrap.dedent(
        """\
        ## 2. Construction

        body line a
        body line b

        ## 3. Errors
        """
    )
    sections = scan_sections(text)
    construction = next(s for s in sections if "Construction" in s.heading)
    assert isinstance(construction, Section)
    assert construction.heading_line >= 1
    assert construction.body_end > construction.heading_line


def test_allowlist_keys_match_spec() -> None:
    """ADR-2 § 3.1: 4 sweep families addressed in S1."""
    assert "FR-1" in ALLOWLIST
    assert "FR-2" in ALLOWLIST
    assert "FR-4" in ALLOWLIST
    assert "FR-7" in ALLOWLIST


def test_scan_sections_emits_zero_warn_when_specs_have_allowlisted_sections() -> None:
    """A v2-compliant spec lists scanned sections without WARN."""
    text = textwrap.dedent(
        """\
        ## 1. Scope
        ## 2. Construction
        ## 6. Errors
        ## 11. Test Contract
        """
    )
    sections = scan_sections(text)
    matched = [s for s in sections if s.matched_frs]
    assert (
        len(matched) >= 3
    )  # Construction (FR-1+FR-2), Errors (FR-4), Test Contract (FR-7)
