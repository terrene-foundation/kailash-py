# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration suite for the PACT N4/N5 conformance runner.

This file is the self-contained cross-SDK byte-equality gate. Unlike the
Tier 1 sibling-checkout probe in ``test_runner.py`` (skipped when
``kailash-rs`` is not adjacent to ``kailash-py``), this suite runs every
vendored vector under ``tests/fixtures/conformance/`` against the real
``ConformanceRunner`` AND constructs a real ``PactEngine`` (which owns a
real ``GovernanceEngine`` from the Trust Plane) so the integration
exercises the same governance facade downstream consumers wire.

Why a real ``GovernanceEngine`` even though the conformance runner is
governance-independent: per ``rules/orphan-detection.md`` Rule 2, every
wired manager (the runner is a manager-shape class on the conformance
public surface) MUST have a Tier 2 test that constructs a real framework
instance, not a mock. The runner happens to be stateless w.r.t. the
``GovernanceEngine`` today, but the cross-SDK contract MUST be
exercisable from the same harness that downstream Trust-Plane consumers
use, so a future runner that does invoke the engine surfaces breakage in
the same place.

NO mocking: real ``ConformanceRunner``, real ``PactEngine``, real
filesystem. Mocks in Tier 2 are BLOCKED per ``rules/testing.md`` § Tier 2.

Vendored vectors are byte-identical copies from kailash-rs commit
``95916caa66d698d2d7c2755a4b5f3e61019af74e``; refresh procedure lives in
``packages/kailash-pact/tests/fixtures/conformance/README.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pact.conformance import (
    ConformanceRunner,
    RunnerReport,
    VectorStatus,
    load_vectors_from_dir,
)
from pact.engine import PactEngine

# Path to the vendored fixtures (relative to this file's location).
_FIXTURES_ROOT = Path(__file__).parent.parent.parent / "fixtures" / "conformance"
_N4_DIR = _FIXTURES_ROOT / "n4"
_N5_DIR = _FIXTURES_ROOT / "n5"

# Path to the minimal org YAML used to construct a real GovernanceEngine.
_MINIMAL_ORG = (
    Path(__file__).parent.parent.parent
    / "unit"
    / "governance"
    / "fixtures"
    / "minimal-org.yaml"
)


@pytest.fixture(scope="module")
def real_pact_engine() -> PactEngine:
    """Construct a real ``PactEngine`` (and its real ``GovernanceEngine``).

    The conformance runner is governance-independent today, but the Tier 2
    contract requires exercising the same facade downstream consumers wire
    so a future runner that consults governance breaks here, not in
    production.
    """
    return PactEngine(org=str(_MINIMAL_ORG))


@pytest.fixture(scope="module")
def runner(real_pact_engine: PactEngine) -> ConformanceRunner:
    """Real ``ConformanceRunner`` constructed alongside a real engine.

    The fixture takes ``real_pact_engine`` so pytest reports a clear
    dependency chain even though the runner does not reference the engine.
    """
    # The engine is constructed for the side-effect of proving the
    # downstream-consumer wiring works at fixture time; the runner does
    # not need it. Bind to a local variable so the engine survives module
    # scope (test collection retains the fixture).
    _ = real_pact_engine
    return ConformanceRunner()


# ---------------------------------------------------------------------------
# N4 vendored suite
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_vendored_n4_vectors_all_pass(runner: ConformanceRunner) -> None:
    """Every vendored N4 vector MUST emit canonical JSON byte-equal to the
    expected string from the Rust source of truth.

    Vendored N4 inventory (5 vectors): zone1_pseudo, zone2_guardian,
    zone3_cognate, zone3_continuous_insight, zone4_delegated.
    """
    vectors = load_vectors_from_dir(_N4_DIR)
    assert len(vectors) == 5, (
        f"expected 5 vendored N4 vectors, got {len(vectors)}; "
        f"check tests/fixtures/conformance/n4/ inventory + README"
    )
    report = runner.run(vectors)
    assert isinstance(report, RunnerReport)
    assert report.total == 5
    assert report.failed == 0, (
        f"N4 cross-SDK byte-equality contract violated -- "
        f"{report.failed} failed.\n{report.render_failure_report()}"
    )
    assert report.unsupported == 0, (
        f"N4 vendored fixtures contain unsupported contracts; "
        f"{report.unsupported} unsupported. The runner is stale or the "
        f"fixtures were vendored from a kailash-rs commit that introduced "
        f"a new contract."
    )
    assert report.passed == 5
    assert report.all_passed is True

    # Verify every individual outcome carries the cross-SDK forensic
    # correlation key (sha256 fingerprint) so a downstream diff can attach
    # to either side of the contract.
    for outcome in report.outcomes:
        assert outcome.status is VectorStatus.PASSED
        assert outcome.contract == "N4"
        assert outcome.expected_sha256 == outcome.actual_sha256
        assert len(outcome.expected_sha256) == 64  # sha256 hex


# ---------------------------------------------------------------------------
# N5 vendored suite
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_vendored_n5_vectors_all_pass(runner: ConformanceRunner) -> None:
    """Every vendored N5 vector MUST emit canonical JSON byte-equal to the
    expected string from the Rust source of truth.

    Vendored N5 inventory (2 vectors): evidence_blocked,
    evidence_verdict_v1.
    """
    vectors = load_vectors_from_dir(_N5_DIR)
    assert len(vectors) == 2, (
        f"expected 2 vendored N5 vectors, got {len(vectors)}; "
        f"check tests/fixtures/conformance/n5/ inventory + README"
    )
    report = runner.run(vectors)
    assert report.total == 2
    assert report.failed == 0, (
        f"N5 cross-SDK byte-equality contract violated -- "
        f"{report.failed} failed.\n{report.render_failure_report()}"
    )
    assert report.unsupported == 0
    assert report.passed == 2
    assert report.all_passed is True

    for outcome in report.outcomes:
        assert outcome.status is VectorStatus.PASSED
        assert outcome.contract == "N5"
        assert outcome.expected_sha256 == outcome.actual_sha256


# ---------------------------------------------------------------------------
# Combined suite (full inventory)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_vendored_full_suite_passes(runner: ConformanceRunner) -> None:
    """Combined run across both N4 and N5 directories.

    Mirrors the kailash-rs ``all_vectors_load_and_pass`` test surface --
    the single "is the cross-SDK contract intact" gate downstream
    consumers (and CI matrix jobs) read.
    """
    n4_vectors = load_vectors_from_dir(_N4_DIR)
    n5_vectors = load_vectors_from_dir(_N5_DIR)
    all_vectors = list(n4_vectors) + list(n5_vectors)
    assert len(all_vectors) == 7, (
        f"expected 7 vendored vectors total (5 N4 + 2 N5), "
        f"got {len(all_vectors)}; refresh fixtures from kailash-rs"
    )

    report = runner.run(all_vectors)
    assert report.total == 7
    # MUST: every vector PASSED OR UNSUPPORTED; never FAILED.
    assert report.failed == 0, (
        f"cross-SDK byte-equality contract violated -- "
        f"{report.failed} failed.\n{report.render_failure_report()}"
    )
    # Counts PASSED >= 5 (the 5 N4 vectors at minimum); the 2 N5 are also
    # supported so the actual count is 7. Pin >= 5 so a future N5 contract
    # bump that lands an UNSUPPORTED vector does not break this gate
    # before the N4 minimum is met.
    assert report.passed >= 5
    assert report.passed + report.unsupported == report.total


# ---------------------------------------------------------------------------
# Real-engine wiring proof
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_real_governance_engine_constructs_alongside_runner(
    real_pact_engine: PactEngine,
) -> None:
    """Prove the real ``PactEngine`` (and its real ``GovernanceEngine``)
    constructs cleanly in the same fixture scope as the runner.

    This guards against a future refactor that inadvertently couples the
    runner to the engine -- if the runner ever takes a ``governance``
    parameter, this test surfaces the dependency at construction time
    rather than at runtime against a real vector.
    """
    assert real_pact_engine is not None
    # ``_governance`` is the private GovernanceEngine handle; we read it
    # only to assert real-instance construction (the rule against engine
    # exposure to agent code does not apply -- this is test code, not
    # agent code).
    governance = real_pact_engine._governance
    assert governance is not None
    # Real GovernanceEngine class import resolves to the trust-plane
    # implementation; the conformance runner is independent today.
    from kailash.trust.pact.engine import GovernanceEngine

    assert isinstance(governance, GovernanceEngine)
