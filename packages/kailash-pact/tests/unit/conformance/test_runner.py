# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 tests for the PACT N4/N5 conformance vector runner.

These tests pin the runner contract:

- ``ConformanceRunner.run`` returns a :class:`RunnerReport` with one
  :class:`VectorOutcome` per input vector, in input order.
- A vector whose ``canonical_json`` matches the SDK's emission lands as
  ``PASSED``.
- A vector whose ``canonical_json`` diverges by ONE BYTE lands as
  ``FAILED`` and carries both expected/actual JSON + their SHA-256
  fingerprints (cross-SDK forensic correlation key).
- N4 invariant violations (tier / durable / requires_signature /
  requires_replication) land as ``FAILED`` with a specific reason that
  does NOT shadow the canonical-JSON diff.
- An unknown ``contract`` lands as ``UNSUPPORTED`` (soft skip; counted
  separately).
- :meth:`RunnerReport.all_passed` is False when any FAILED or UNSUPPORTED
  outcome is present.
- :meth:`RunnerReport.render_failure_report` produces a structured
  human-readable diff.

Two known-bad strategies exercised:

1. **Single-byte canonical-JSON drift** -- the vector ``expected.canonical_json``
   has a corrupted UTF-8 byte (e.g. a swapped character). The runner builds the
   canonical event from inputs as usual; the actual canonical JSON does not
   equal the expected; mismatch surfaces.
2. **Tier invariant violation** -- the vector pins ``tier: zone4_delegated``
   but the input posture is ``PseudoAgent`` (Zone 1). The runner builds a Zone 1
   event; the invariant check fires before the canonical-JSON diff.

Shard D will add a Tier 2 test that runs the real cross-SDK vectors from
the kailash-rs tree against this runner; this Tier 1 file pins the runner
mechanics in isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pact.conformance import (
    ConformanceVector,
    ConformanceVectorError,
    ConformanceVectorExpected,
    ConformanceVectorInput,
    ConformanceVectorVerdict,
    DurabilityTier,
    GradientZone,
    PactPostureLevel,
)
from pact.conformance.runner import (
    ConformanceRunner,
    RunnerReport,
    VectorOutcome,
    VectorStatus,
    run_vectors,
)


# ---------------------------------------------------------------------------
# Vector stub builders
# ---------------------------------------------------------------------------


def _make_n4_vector(
    *,
    vector_id: str,
    posture: PactPostureLevel,
    expected_canonical_json: str,
    expected_tier: DurabilityTier | None = None,
    expected_durable: bool | None = None,
    expected_requires_signature: bool | None = None,
    expected_requires_replication: bool | None = None,
    fixed_event_id: str = "00000000-0000-4000-8000-000000000001",
    fixed_timestamp: str = "2026-01-01T00:00:00+00:00",
    role_address: str = "D1-R1",
    action: str = "ping",
    reason: str = "ok",
    zone: GradientZone = GradientZone.AUTO_APPROVED,
) -> ConformanceVector:
    return ConformanceVector(
        id=vector_id,
        contract="N4",
        description="stub N4 vector",
        input=ConformanceVectorInput(
            verdict=ConformanceVectorVerdict(
                zone=zone,
                reason=reason,
                action=action,
                role_address=role_address,
                details={},
            ),
            posture=posture,
            fixed_event_id=fixed_event_id,
            fixed_timestamp=fixed_timestamp,
        ),
        expected=ConformanceVectorExpected(
            canonical_json=expected_canonical_json,
            tier=expected_tier,
            durable=expected_durable,
            requires_signature=expected_requires_signature,
            requires_replication=expected_requires_replication,
        ),
        hash_algo="sha256",
    )


def _make_n5_vector(
    *,
    vector_id: str,
    expected_canonical_json: str,
    fixed_timestamp: str = "2026-01-01T00:00:00+00:00",
    role_address: str = "D1-R1-T1-R1",
    evidence_source: str | None = "D1-R1-T1-R1",
    evidence_schema: str | None = None,
    action: str = "wire_transfer",
    reason: str = "exceeded financial limit",
    zone: GradientZone = GradientZone.BLOCKED,
) -> ConformanceVector:
    return ConformanceVector(
        id=vector_id,
        contract="N5",
        description="stub N5 vector",
        input=ConformanceVectorInput(
            verdict=ConformanceVectorVerdict(
                zone=zone,
                reason=reason,
                action=action,
                role_address=role_address,
                details={},
            ),
            posture=None,
            fixed_timestamp=fixed_timestamp,
            evidence_source=evidence_source,
            evidence_schema=evidence_schema,
        ),
        expected=ConformanceVectorExpected(canonical_json=expected_canonical_json),
        hash_algo="sha256",
    )


# Hand-derived canonical strings (matching the synthetic vectors from
# ``test_vectors_loader.py``). These are the same byte strings the Rust
# runner emits for the same inputs.

_N4_ZONE1_CANONICAL = (
    '{"event_id":"00000000-0000-4000-8000-000000000001",'
    '"timestamp":"2026-01-01T00:00:00+00:00",'
    '"role_address":"D1-R1","posture":"pseudo_agent",'
    '"action":"ping","zone":"AutoApproved","reason":"ok",'
    '"tier":"zone1_pseudo","tenant_id":null,"signature":null}'
)

_N4_ZONE4_CANONICAL = (
    '{"event_id":"00000000-0000-4000-8000-000000000001",'
    '"timestamp":"2026-01-01T00:00:00+00:00",'
    '"role_address":"D1-R1","posture":"delegated",'
    '"action":"ping","zone":"AutoApproved","reason":"ok",'
    '"tier":"zone4_delegated","tenant_id":null,"signature":null}'
)

_N5_BLOCKED_CANONICAL = (
    '{"schema":"pact.governance.verdict.v1","source":"D1-R1-T1-R1",'
    '"timestamp":"2026-01-01T00:00:00+00:00","gradient":"Blocked",'
    '"action":"wire_transfer","payload":{"details":{},'
    '"reason":"exceeded financial limit",'
    '"role_address":"D1-R1-T1-R1"}}'
)


# ---------------------------------------------------------------------------
# PASSED outcomes
# ---------------------------------------------------------------------------


def test_runner_n4_zone1_passes():
    vector = _make_n4_vector(
        vector_id="stub_n4_zone1",
        posture=PactPostureLevel.PSEUDO_AGENT,
        expected_canonical_json=_N4_ZONE1_CANONICAL,
        expected_tier=DurabilityTier.ZONE1_PSEUDO,
        expected_durable=False,
        expected_requires_signature=False,
        expected_requires_replication=False,
    )
    report = ConformanceRunner().run([vector])
    assert isinstance(report, RunnerReport)
    assert report.total == 1
    assert report.passed == 1
    assert report.failed == 0
    assert report.unsupported == 0
    assert report.all_passed is True
    [outcome] = report.outcomes
    assert outcome.status is VectorStatus.PASSED
    assert outcome.contract == "N4"
    assert outcome.actual_canonical_json == _N4_ZONE1_CANONICAL
    assert outcome.actual_sha256 == outcome.expected_sha256
    assert outcome.reason == ""


def test_runner_n4_zone4_delegated_passes():
    vector = _make_n4_vector(
        vector_id="stub_n4_zone4",
        posture=PactPostureLevel.DELEGATED,
        expected_canonical_json=_N4_ZONE4_CANONICAL,
        expected_tier=DurabilityTier.ZONE4_DELEGATED,
        expected_durable=True,
        expected_requires_signature=True,
        expected_requires_replication=True,
    )
    report = run_vectors([vector])
    assert report.all_passed is True


def test_runner_n5_blocked_passes():
    vector = _make_n5_vector(
        vector_id="stub_n5_blocked",
        expected_canonical_json=_N5_BLOCKED_CANONICAL,
    )
    report = ConformanceRunner().run([vector])
    assert report.all_passed is True
    [outcome] = report.outcomes
    assert outcome.contract == "N5"
    assert outcome.actual_canonical_json == _N5_BLOCKED_CANONICAL


def test_runner_n5_uses_role_address_when_evidence_source_absent():
    """Mirrors Rust ``run_n5`` fallback: source = role_address when
    ``evidence_source`` is None."""
    expected = (
        '{"schema":"pact.governance.verdict.v1","source":"D1-R1-T1-R1",'
        '"timestamp":"2026-01-01T00:00:00+00:00","gradient":"Blocked",'
        '"action":"wire_transfer","payload":{"details":{},'
        '"reason":"exceeded financial limit",'
        '"role_address":"D1-R1-T1-R1"}}'
    )
    vector = _make_n5_vector(
        vector_id="stub_n5_no_source",
        expected_canonical_json=expected,
        evidence_source=None,
    )
    report = ConformanceRunner().run([vector])
    assert report.all_passed is True


def test_runner_n5_evidence_schema_override_passes():
    expected = (
        '{"schema":"pact.governance.custom.v1","source":"D1-R1-T1-R1",'
        '"timestamp":"2026-01-01T00:00:00+00:00","gradient":"Blocked",'
        '"action":"wire_transfer","payload":{"details":{},'
        '"reason":"exceeded financial limit",'
        '"role_address":"D1-R1-T1-R1"}}'
    )
    vector = _make_n5_vector(
        vector_id="stub_n5_schema_override",
        expected_canonical_json=expected,
        evidence_schema="pact.governance.custom.v1",
    )
    report = ConformanceRunner().run([vector])
    assert report.all_passed is True


# ---------------------------------------------------------------------------
# FAILED outcomes
# ---------------------------------------------------------------------------


def test_runner_n4_canonical_json_drift_fails_with_sha_diff():
    """Single-byte canonical-JSON drift surfaces as FAILED with both
    SHA-256 fingerprints populated."""
    drifted = _N4_ZONE1_CANONICAL.replace(
        '"tier":"zone1_pseudo"', '"tier":"zone1_PSEUDO"'
    )
    assert drifted != _N4_ZONE1_CANONICAL
    vector = _make_n4_vector(
        vector_id="stub_n4_drift",
        posture=PactPostureLevel.PSEUDO_AGENT,
        expected_canonical_json=drifted,
    )
    report = ConformanceRunner().run([vector])
    assert report.all_passed is False
    assert report.failed == 1
    [outcome] = report.outcomes
    assert outcome.status is VectorStatus.FAILED
    assert outcome.reason == "canonical_json mismatch"
    assert outcome.expected_canonical_json == drifted
    assert outcome.actual_canonical_json == _N4_ZONE1_CANONICAL
    # SHA-256 fingerprints differ (forensic correlation key)
    assert outcome.expected_sha256 != outcome.actual_sha256
    assert len(outcome.expected_sha256) == 64
    assert len(outcome.actual_sha256 or "") == 64


def test_runner_n4_tier_invariant_violation_fails_with_specific_reason():
    """Tier invariant mismatch fires before canonical-JSON diff."""
    # The vector pins tier=zone4_delegated but the input posture is
    # PseudoAgent which maps to Zone 1. The invariant check fires first.
    vector = _make_n4_vector(
        vector_id="stub_n4_tier_violation",
        posture=PactPostureLevel.PSEUDO_AGENT,
        # Even the canonical JSON we expect would NOT match here, but the
        # invariant check fires first and the reason should reflect tier.
        expected_canonical_json=_N4_ZONE1_CANONICAL,
        expected_tier=DurabilityTier.ZONE4_DELEGATED,
    )
    report = ConformanceRunner().run([vector])
    assert report.failed == 1
    [outcome] = report.outcomes
    assert outcome.status is VectorStatus.FAILED
    assert "tier mismatch" in outcome.reason
    # Canonical JSON is still recorded so the harness can render diagnostics.
    assert outcome.actual_canonical_json == _N4_ZONE1_CANONICAL


def test_runner_n4_durable_flag_violation_fails():
    vector = _make_n4_vector(
        vector_id="stub_n4_durable_violation",
        posture=PactPostureLevel.PSEUDO_AGENT,  # Zone 1 -> not durable
        expected_canonical_json=_N4_ZONE1_CANONICAL,
        expected_durable=True,  # Vector lies; runner catches.
    )
    report = ConformanceRunner().run([vector])
    [outcome] = report.outcomes
    assert outcome.status is VectorStatus.FAILED
    assert "durable flag mismatch" in outcome.reason


def test_runner_n4_requires_signature_violation_fails():
    vector = _make_n4_vector(
        vector_id="stub_n4_signature_violation",
        posture=PactPostureLevel.PSEUDO_AGENT,
        expected_canonical_json=_N4_ZONE1_CANONICAL,
        expected_requires_signature=True,  # Zone 1 doesn't sign.
    )
    report = ConformanceRunner().run([vector])
    [outcome] = report.outcomes
    assert outcome.status is VectorStatus.FAILED
    assert "requires_signature mismatch" in outcome.reason


def test_runner_n4_requires_replication_violation_fails():
    vector = _make_n4_vector(
        vector_id="stub_n4_replication_violation",
        posture=PactPostureLevel.PSEUDO_AGENT,
        expected_canonical_json=_N4_ZONE1_CANONICAL,
        expected_requires_replication=True,  # Zone 1 doesn't replicate.
    )
    report = ConformanceRunner().run([vector])
    [outcome] = report.outcomes
    assert outcome.status is VectorStatus.FAILED
    assert "requires_replication mismatch" in outcome.reason


def test_runner_n5_canonical_json_drift_fails():
    drifted = _N5_BLOCKED_CANONICAL.replace(
        '"gradient":"Blocked"', '"gradient":"BLOCKED"'
    )
    vector = _make_n5_vector(
        vector_id="stub_n5_drift",
        expected_canonical_json=drifted,
    )
    report = ConformanceRunner().run([vector])
    [outcome] = report.outcomes
    assert outcome.status is VectorStatus.FAILED
    assert outcome.expected_sha256 != outcome.actual_sha256


# ---------------------------------------------------------------------------
# UNSUPPORTED outcome
# ---------------------------------------------------------------------------


def test_runner_unsupported_contract_lands_as_soft_skip():
    # Build a vector with an unknown contract directly (parse_vector would
    # have rejected this, but a runner consumer may have a forward-compat
    # vector dir.)
    vector = ConformanceVector(
        id="stub_n7_future",
        contract="N7",
        description="hypothetical future contract",
        input=ConformanceVectorInput(
            verdict=ConformanceVectorVerdict(
                zone=GradientZone.AUTO_APPROVED,
                reason="ok",
                action="ping",
                role_address="D1-R1",
                details={},
            ),
            posture=None,
        ),
        expected=ConformanceVectorExpected(canonical_json="{}"),
        hash_algo="sha256",
    )
    report = ConformanceRunner().run([vector])
    assert report.passed == 0
    assert report.failed == 0
    assert report.unsupported == 1
    # all_passed is False even with zero FAILED -- unsupported signals the
    # runner is out of date with the spec.
    assert report.all_passed is False
    [outcome] = report.outcomes
    assert outcome.status is VectorStatus.UNSUPPORTED
    assert outcome.reason == "unsupported contract 'N7'"
    assert outcome.actual_canonical_json is None
    assert outcome.actual_sha256 is None


# ---------------------------------------------------------------------------
# Mixed batch
# ---------------------------------------------------------------------------


def test_runner_mixed_batch_preserves_input_order_and_aggregates():
    pass_n4 = _make_n4_vector(
        vector_id="b_pass",
        posture=PactPostureLevel.PSEUDO_AGENT,
        expected_canonical_json=_N4_ZONE1_CANONICAL,
    )
    fail_n5 = _make_n5_vector(
        vector_id="a_fail",
        expected_canonical_json='{"schema":"wrong"}',
    )
    pass_n5 = _make_n5_vector(
        vector_id="c_pass",
        expected_canonical_json=_N5_BLOCKED_CANONICAL,
    )
    report = ConformanceRunner().run([pass_n4, fail_n5, pass_n5])
    # Input order preserved (NOT sorted internally; the loader sorts).
    assert [o.vector_id for o in report.outcomes] == ["b_pass", "a_fail", "c_pass"]
    assert report.passed == 2
    assert report.failed == 1
    assert report.unsupported == 0
    assert report.all_passed is False
    failures = report.failures()
    assert len(failures) == 1
    assert failures[0].vector_id == "a_fail"


# ---------------------------------------------------------------------------
# Render failure report
# ---------------------------------------------------------------------------


def test_render_failure_report_contains_diff_and_sha_for_each_failure():
    drifted = _N4_ZONE1_CANONICAL.replace('"reason":"ok"', '"reason":"drift"')
    vector = _make_n4_vector(
        vector_id="stub_n4_render",
        posture=PactPostureLevel.PSEUDO_AGENT,
        expected_canonical_json=drifted,
    )
    report = ConformanceRunner().run([vector])
    rendered = report.render_failure_report()
    assert "[stub_n4_render]" in rendered
    assert "canonical_json mismatch" in rendered
    assert "expected:" in rendered
    assert "actual:" in rendered
    assert "expected_sha256:" in rendered
    assert "actual_sha256:" in rendered
    # Both fingerprints land
    assert rendered.count("sha256") >= 2


def test_render_failure_report_empty_on_all_pass():
    vector = _make_n4_vector(
        vector_id="stub_n4_pass",
        posture=PactPostureLevel.PSEUDO_AGENT,
        expected_canonical_json=_N4_ZONE1_CANONICAL,
    )
    report = ConformanceRunner().run([vector])
    assert report.render_failure_report() == ""


# ---------------------------------------------------------------------------
# Parse-time vs run-time error boundaries
# ---------------------------------------------------------------------------


def test_runner_raises_when_n4_vector_has_no_fixed_event_id():
    """The runner ALSO enforces N4 determinism (parse_vector enforces
    posture; the runner enforces fixed_event_id + fixed_timestamp)."""
    vector = ConformanceVector(
        id="stub_n4_no_event_id",
        contract="N4",
        description="bad",
        input=ConformanceVectorInput(
            verdict=ConformanceVectorVerdict(
                zone=GradientZone.AUTO_APPROVED,
                reason="ok",
                action="ping",
                role_address="D1-R1",
                details={},
            ),
            posture=PactPostureLevel.PSEUDO_AGENT,
            fixed_event_id=None,
            fixed_timestamp="2026-01-01T00:00:00+00:00",
        ),
        expected=ConformanceVectorExpected(canonical_json="{}"),
        hash_algo="sha256",
    )
    with pytest.raises(ConformanceVectorError, match="fixed_event_id"):
        ConformanceRunner().run([vector])


def test_runner_raises_when_n5_vector_has_no_fixed_timestamp():
    vector = ConformanceVector(
        id="stub_n5_no_ts",
        contract="N5",
        description="bad",
        input=ConformanceVectorInput(
            verdict=ConformanceVectorVerdict(
                zone=GradientZone.BLOCKED,
                reason="x",
                action="y",
                role_address="D1-R1",
                details={},
            ),
            posture=None,
            fixed_timestamp=None,
        ),
        expected=ConformanceVectorExpected(canonical_json="{}"),
        hash_algo="sha256",
    )
    with pytest.raises(ConformanceVectorError, match="fixed_timestamp"):
        ConformanceRunner().run([vector])


# ---------------------------------------------------------------------------
# Cross-SDK vector dir (Tier 1 sanity probe)
# ---------------------------------------------------------------------------

# When the kailash-rs sibling repo is checked out alongside kailash-py, the
# real cross-SDK vectors are at ../kailash-rs/crates/kailash-pact/tests/
# conformance/vectors/. This Tier 1 sanity probe loads them and runs the
# runner. If the path is absent (CI Python-only host), the test is skipped.
# Shard D will land a Tier 2 test with an explicit vector-fixture-copy that
# does NOT depend on the sibling checkout.


def _discover_sibling_vector_dir() -> Path | None:
    """Walk parent directories looking for a kailash-rs sibling checkout
    that contains the canonical N4/N5 conformance vectors.

    The kailash-py tree may be checked out as the parent's worktree (e.g.
    ``loom/kailash-py/.claude/worktrees/...``) OR side-by-side with
    kailash-rs (``loom/kailash-rs/``, ``loom/kailash-py/``). We probe up to
    10 ancestors to cover both layouts; the first match wins.

    Returns ``None`` when no sibling checkout is found, in which case the
    probe test below is skipped.
    """
    suffix = (
        "kailash-rs",
        "crates",
        "kailash-pact",
        "tests",
        "conformance",
        "vectors",
    )
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor.joinpath(*suffix)
        if candidate.is_dir():
            return candidate
    return None


_SIBLING_VECTOR_DIR = _discover_sibling_vector_dir()


@pytest.mark.skipif(
    _SIBLING_VECTOR_DIR is None,
    reason=(
        "kailash-rs sibling checkout not found in any parent directory; "
        "the cross-SDK vector dir is expected at "
        "<ancestor>/kailash-rs/crates/kailash-pact/tests/conformance/vectors. "
        "Shard D will add a Tier 2 fixture-based test that does not depend "
        "on the sibling repo."
    ),
)
def test_runner_passes_against_real_cross_sdk_vectors():
    """Sanity probe -- run the real kailash-rs conformance vectors.

    Skipped if the sibling repo is not checked out alongside kailash-py
    (the typical CI configuration). When present, every loaded vector MUST
    pass; any failure points to a cross-SDK byte drift between Rust and
    Python canonicalisation.
    """
    from pact.conformance import load_vectors_from_dir

    vectors = load_vectors_from_dir(_SIBLING_VECTOR_DIR)
    assert len(vectors) >= 1, "expected at least one cross-SDK vector"
    report = ConformanceRunner().run(vectors)
    assert report.all_passed, (
        f"cross-SDK vector mismatch -- {report.failed} failed, "
        f"{report.unsupported} unsupported. "
        f"Diff:\n{report.render_failure_report()}"
    )


# ---------------------------------------------------------------------------
# VectorOutcome immutability
# ---------------------------------------------------------------------------


def test_vector_outcome_is_frozen():
    """VectorOutcome MUST be frozen so callers cannot mutate result records."""
    outcome = VectorOutcome(
        vector_id="x",
        contract="N4",
        status=VectorStatus.PASSED,
        reason="",
        expected_canonical_json="{}",
        actual_canonical_json="{}",
        expected_sha256="0" * 64,
        actual_sha256="0" * 64,
    )
    with pytest.raises(
        Exception
    ):  # noqa: B017 - frozen dataclass raises FrozenInstanceError
        outcome.status = VectorStatus.FAILED  # type: ignore[misc]
