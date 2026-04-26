"""Tier 2 integration test — full-corpus sweep + NFR-1 perf budget.

The gate runs against the FULL `specs/` corpus on a real checkout and
the wall-clock MUST stay under NFR-1's 30-second budget. The test does
NOT assert zero findings (the corpus has a 116-FAIL pre-existing
backlog as of S3 — those freeze into the baseline at S5). It asserts:

1. The sweep completes within budget.
2. Every WARN-level finding is a B1 ``__getattr__`` divergence (the
   only WARN class in v1.0).
3. The pristine v2 corpus (`specs/ml-automl.md` +
   `specs/ml-feature-store.md`) produces zero FAIL findings.
"""

from __future__ import annotations

import time
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
NFR_1_BUDGET_SECONDS = 30.0


@pytest.fixture(scope="module")
def manifest():
    return Manifest.load()


@pytest.fixture(scope="module")
def cache(manifest):
    return SymbolIndex.build(
        [sr.path for sr in manifest.source_roots],
        errors_modules=[ErrorsModule(manifest.errors_default)]
        + [ErrorsModule(o.path) for o in manifest.errors_overrides],
    )


@pytest.mark.integration
def test_full_corpus_under_nfr1_budget(manifest, cache) -> None:
    """NFR-1: full ~70-spec corpus completes in <30s."""
    spec_paths = sorted(Path().glob(manifest.spec_glob))
    assert (
        len(spec_paths) >= 50
    ), f"corpus shrank unexpectedly — {len(spec_paths)} specs; expected ≥50"

    start = time.perf_counter()
    total_findings = 0
    for spec_path in spec_paths:
        text = spec_path.read_text()
        sections = scan_sections(text)
        overrides = parse_overrides(text)
        findings = run_sweeps(spec_path, text, sections, overrides, cache)
        total_findings += len(findings)
    elapsed = time.perf_counter() - start

    assert elapsed < NFR_1_BUDGET_SECONDS, (
        f"NFR-1 violation: full-corpus sweep took {elapsed:.2f}s, "
        f"budget is {NFR_1_BUDGET_SECONDS}s"
    )
    # Sanity: the corpus produces SOME findings (the 116-FAIL backlog as
    # of S3). Zero findings would mean the dispatch layer regressed and
    # all sweeps are silently no-op.
    assert total_findings > 0


@pytest.mark.integration
def test_pristine_v2_corpus_zero_fail(cache) -> None:
    """The Wave 6.5 v2 specs (post-realignment) MUST produce 0 FAIL."""
    pristine = [
        REPO_ROOT / "specs" / "ml-automl.md",
        REPO_ROOT / "specs" / "ml-feature-store.md",
    ]
    fail_findings = []
    for spec_path in pristine:
        text = spec_path.read_text()
        sections = scan_sections(text)
        overrides = parse_overrides(text)
        findings = run_sweeps(spec_path, text, sections, overrides, cache)
        fail_findings.extend(f for f in findings if f.level == "FAIL")
    assert fail_findings == [], (
        f"pristine v2 corpus regressed — {len(fail_findings)} FAIL findings: "
        f"{[(f.spec_path, f.fr_code, f.symbol) for f in fail_findings[:5]]}"
    )


@pytest.mark.integration
def test_warn_findings_are_only_b1_class(manifest, cache) -> None:
    """v1.0 WARN-level findings are EXCLUSIVELY B1 ``__getattr__`` ones.

    If a future sweep adds a new WARN class without journaling the
    disposition (per Q9.3 / journal 0005), this test fails loudly.
    """
    spec_paths = sorted(Path().glob(manifest.spec_glob))
    warn_codes: set[str] = set()
    for spec_path in spec_paths:
        text = spec_path.read_text()
        sections = scan_sections(text)
        overrides = parse_overrides(text)
        findings = run_sweeps(spec_path, text, sections, overrides, cache)
        for f in findings:
            if f.level == "WARN":
                warn_codes.add(f.fr_code)
    assert warn_codes <= {
        "B1"
    }, f"new WARN class introduced without disposition: {warn_codes - {'B1'}}"
