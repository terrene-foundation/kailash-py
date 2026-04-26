"""Tier 2 integration tests — W6.5 reproduction.

Replays the exact Wave 6.5 round-1 FeatureStore draft fabrications to
prove the gate WOULD have caught CRIT-1 (5 fabricated `*Error` classes)
and CRIT-2 (1 fabricated wiring-test path) at PR time.

These are the brief's load-bearing demo: "deliberately-broken spec edit
fails CI; the realignment passes". Failure of any of these tests means
the W6.5-class drift would silently slip through the gate.

Tier 2 contract per `rules/testing.md`: real source tree, no mocks. The
gate is invoked as the production CLI would call it (manifest-driven
SymbolIndex against the real Kailash source roots) — not as a Tier 1
unit-test of an isolated function.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from spec_drift_gate import (
    Manifest,
    SymbolIndex,
    ErrorsModule,
    parse_overrides,
    run_sweeps,
    scan_sections,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "spec_drift_gate"


@pytest.fixture(scope="module")
def cache():
    """Real SymbolIndex against the manifest-declared source roots.

    Module-scoped: building the index over the full Kailash tree takes
    seconds; sharing it across the W6.5 replay tests keeps the file's
    runtime under the NFR-1 30s budget envelope.
    """
    m = Manifest.load()
    return SymbolIndex.build(
        [sr.path for sr in m.source_roots],
        errors_modules=[ErrorsModule(m.errors_default)]
        + [ErrorsModule(o.path) for o in m.errors_overrides],
    )


def _run_gate(spec_path: Path, cache):
    text = spec_path.read_text()
    sections = scan_sections(text)
    overrides = parse_overrides(text)
    return run_sweeps(spec_path, text, sections, overrides, cache)


@pytest.mark.integration
class TestCrit1Replay:
    """W6.5 CRIT-1: 5 fabricated `*Error` classes in `## Errors`."""

    def test_exactly_five_fr4_findings(self, cache) -> None:
        spec = FIXTURES / "w65_crit1_fabricated_errors.md"
        findings = _run_gate(spec, cache)
        fail_findings = [f for f in findings if f.level == "FAIL"]
        assert len(fail_findings) == 5, (
            f"W6.5 CRIT-1 replay must surface exactly 5 findings; got "
            f"{len(fail_findings)}: {[(f.fr_code, f.symbol) for f in fail_findings]}"
        )
        assert all(f.fr_code == "FR-4" for f in fail_findings)

    def test_exact_class_names_match_w65_review(self, cache) -> None:
        """The 5 class names MUST be bit-faithful to the W6.5 round-1 draft.

        If the fixture drifts from the original, the test FAILS — the
        contract is that we replay the round-1 fabrications verbatim.
        """
        spec = FIXTURES / "w65_crit1_fabricated_errors.md"
        findings = _run_gate(spec, cache)
        symbols = {f.symbol for f in findings if f.level == "FAIL"}
        expected = {
            "FeatureGroupNotFoundError",
            "FeatureVersionNotFoundError",
            "FeatureEvolutionError",
            "OnlineStoreUnavailableError",
            "CrossTenantReadError",
        }
        assert (
            symbols == expected
        ), f"W6.5 CRIT-1 fixture drift: expected {expected}, got {symbols}"


@pytest.mark.integration
class TestCrit2Replay:
    """W6.5 CRIT-2: 1 fabricated wiring-test path in `## Test Contract`."""

    def test_exactly_one_fr7_finding(self, cache) -> None:
        spec = FIXTURES / "w65_crit2_fabricated_test_path.md"
        findings = _run_gate(spec, cache)
        fail_findings = [f for f in findings if f.level == "FAIL"]
        assert len(fail_findings) == 1
        assert fail_findings[0].fr_code == "FR-7"

    def test_exact_path_matches_w65_review(self, cache) -> None:
        spec = FIXTURES / "w65_crit2_fabricated_test_path.md"
        findings = _run_gate(spec, cache)
        symbols = {f.symbol for f in findings if f.level == "FAIL"}
        assert symbols == {
            "packages/kailash-ml/tests/integration/test_feature_store_wiring.py"
        }


@pytest.mark.integration
class TestCombinedDemo:
    """Brief acceptance criterion: 6 findings (5 FR-4 + 1 FR-7)."""

    def test_exactly_six_findings(self, cache) -> None:
        spec = FIXTURES / "w65_combined_demo.md"
        findings = _run_gate(spec, cache)
        fail_findings = [f for f in findings if f.level == "FAIL"]
        assert len(fail_findings) == 6, (
            f"Combined demo must produce exactly 6 findings (5 FR-4 + 1 FR-7); "
            f"got {len(fail_findings)}"
        )

    def test_breakdown_is_5_fr4_plus_1_fr7(self, cache) -> None:
        spec = FIXTURES / "w65_combined_demo.md"
        findings = _run_gate(spec, cache)
        fr_counts: dict[str, int] = {}
        for f in findings:
            if f.level != "FAIL":
                continue
            fr_counts[f.fr_code] = fr_counts.get(f.fr_code, 0) + 1
        assert fr_counts == {"FR-4": 5, "FR-7": 1}
