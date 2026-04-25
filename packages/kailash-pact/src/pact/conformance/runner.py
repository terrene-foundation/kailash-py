# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT N4/N5 conformance vector runner.

Drives a sequence of :class:`~pact.conformance.vectors.ConformanceVector`
through the SDK's canonical-JSON path and asserts byte-for-byte equality
against ``expected.canonical_json``.

The runner is the Python-side analog of the Rust
``conformance_vectors.rs::all_vectors_load_and_pass`` test. It is
deliberately framework-agnostic: it does NOT touch ``GovernanceEngine`` or
any production governance hot path. Its sole responsibility is the
cross-SDK byte-equality contract.

Two contracts in scope:

- **N4** -- ``TieredAuditEvent`` canonicalisation. The runner reconstructs
  the event from ``input.verdict`` + ``input.posture``, applies the vector's
  ``fixed_event_id`` / ``fixed_timestamp`` (these are mandatory for N4), and
  asserts ``event.canonical_json() == expected.canonical_json``. It also
  asserts the four optional N4 invariants (``tier``, ``durable``,
  ``requires_signature``, ``requires_replication``) when present.

- **N5** -- ``Evidence`` canonicalisation. The runner reconstructs the
  evidence record from ``input.verdict``, ``input.evidence_source`` (or
  ``role_address`` fallback per the Rust ``run_n5`` flow), the mandatory
  ``input.fixed_timestamp``, and the optional ``input.evidence_schema``,
  then asserts ``evidence.canonical_json() == expected.canonical_json``.

# Result aggregation

:class:`RunnerReport` carries one :class:`VectorOutcome` per vector with
status ``PASSED`` / ``FAILED`` / ``UNSUPPORTED``. ``FAILED`` outcomes carry
the expected and actual canonical JSON plus their SHA-256 fingerprints so a
cross-SDK diff can be emitted (mirroring the Rust runner's panic message
shape).

# Failure mode

The runner is fail-LOUD by default for the per-vector path -- a malformed
vector raises :class:`~pact.conformance.vectors.ConformanceVectorError`
during loading. A vector whose ``contract`` field is otherwise unsupported
(e.g. a future N7) is recorded as ``UNSUPPORTED`` rather than raised, so a
single mixed-contract vector dir does not block the supported subset.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
from collections.abc import Iterable, Sequence
from enum import Enum

from pact.conformance.vectors import (
    ConformanceVector,
    ConformanceVectorError,
    Evidence,
    TieredAuditEvent,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ConformanceRunner",
    "RunnerReport",
    "VectorOutcome",
    "VectorStatus",
]


# ---------------------------------------------------------------------------
# Outcome types
# ---------------------------------------------------------------------------


class VectorStatus(str, Enum):
    """Per-vector run status.

    - ``PASSED``: byte-for-byte canonical JSON equal to ``expected``.
    - ``FAILED``: canonical JSON mismatch (expected vs actual diverge), OR
      one of the N4 invariants (tier / durable / requires_signature /
      requires_replication) failed.
    - ``UNSUPPORTED``: vector ``contract`` is not in {``"N4"``, ``"N5"``}.
      Treated as a soft skip; counted separately in :class:`RunnerReport`.
    """

    PASSED = "passed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


@dataclasses.dataclass(frozen=True)
class VectorOutcome:
    """The result of running one vector through the runner.

    Attributes:
        vector_id: Vector ``id`` from the JSON file.
        contract: ``"N4"`` or ``"N5"`` (other values land as
            :attr:`VectorStatus.UNSUPPORTED`).
        status: Pass/fail/unsupported.
        reason: Short human-readable reason -- ``""`` on pass, populated on
            fail/unsupported.
        expected_canonical_json: Expected canonical JSON. Populated for every
            outcome (so the harness can dump a successful match too).
        actual_canonical_json: Actual canonical JSON. ``None`` for
            unsupported vectors.
        expected_sha256: Lowercase-hex SHA-256 of the expected canonical
            JSON UTF-8 bytes. Cross-SDK forensic correlation key.
        actual_sha256: Lowercase-hex SHA-256 of the actual canonical JSON
            UTF-8 bytes. ``None`` for unsupported vectors.
    """

    vector_id: str
    contract: str
    status: VectorStatus
    reason: str
    expected_canonical_json: str
    actual_canonical_json: str | None
    expected_sha256: str
    actual_sha256: str | None


@dataclasses.dataclass(frozen=True)
class RunnerReport:
    """Aggregate report from running a batch of vectors.

    Attributes:
        outcomes: One :class:`VectorOutcome` per input vector, in the order
            the runner saw them (typically alphabetical by ``id`` after
            :func:`~pact.conformance.vectors.load_vectors_from_dir`).
        passed: Count of outcomes with status ``PASSED``.
        failed: Count of outcomes with status ``FAILED``.
        unsupported: Count of outcomes with status ``UNSUPPORTED``.
    """

    outcomes: tuple[VectorOutcome, ...]
    passed: int
    failed: int
    unsupported: int

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.unsupported

    @property
    def all_passed(self) -> bool:
        """True iff zero ``FAILED`` outcomes AND zero ``UNSUPPORTED``.

        ``UNSUPPORTED`` does NOT count toward ``all_passed`` -- a vector dir
        that contains an unsupported contract is signalling that the runner
        is out of date with the spec, which is a release-gate failure even
        though no N4/N5 vector failed individually.
        """
        return self.failed == 0 and self.unsupported == 0

    def failures(self) -> tuple[VectorOutcome, ...]:
        """Convenience -- iterate only the FAILED outcomes."""
        return tuple(o for o in self.outcomes if o.status is VectorStatus.FAILED)

    def render_failure_report(self) -> str:
        """Produce a human-readable multi-line report of every FAILED
        outcome's expected-vs-actual diff and SHA-256 fingerprints.

        The message shape mirrors the Rust ``run_n4`` panic body:

        .. code-block:: text

           [<vector_id>] canonical_json mismatch
             expected: <...>
             expected_sha256: <hex>
             actual:   <...>
             actual_sha256:   <hex>
        """
        if not self.failures():
            return ""
        lines: list[str] = []
        for outcome in self.failures():
            lines.append(f"[{outcome.vector_id}] {outcome.reason}")
            lines.append(f"  expected: {outcome.expected_canonical_json}")
            lines.append(f"  expected_sha256: {outcome.expected_sha256}")
            lines.append(f"  actual:   {outcome.actual_canonical_json}")
            lines.append(f"  actual_sha256:   {outcome.actual_sha256}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class ConformanceRunner:
    """Drive vectors through the canonical-JSON contract.

    Construct once, call :meth:`run` per vector list. Stateless across
    runs -- the runner holds no per-instance configuration today, but is a
    class (rather than a free function) so future contract evolution
    (config flags, alternative encoders, structured-diff plugins) lands
    without breaking the call site.

    Example::

        from pact.conformance import load_vectors_from_dir
        from pact.conformance.runner import ConformanceRunner

        vectors = load_vectors_from_dir("path/to/vectors")
        report = ConformanceRunner().run(vectors)
        if not report.all_passed:
            raise SystemExit(report.render_failure_report())
    """

    def run(self, vectors: Iterable[ConformanceVector]) -> RunnerReport:
        """Drive every vector through the appropriate contract path.

        Returns a :class:`RunnerReport` aggregating per-vector outcomes.
        Never raises for per-vector failures (those land as ``FAILED``
        outcomes); raises :class:`ConformanceVectorError` only for
        contract-violating inputs that cannot be reconstructed at all
        (missing ``fixed_event_id`` on an N4 vector, missing
        ``fixed_timestamp`` on an N5 vector).
        """
        outcomes: list[VectorOutcome] = []
        passed = failed = unsupported = 0
        for vector in vectors:
            outcome = self._run_one(vector)
            outcomes.append(outcome)
            if outcome.status is VectorStatus.PASSED:
                passed += 1
            elif outcome.status is VectorStatus.FAILED:
                failed += 1
            else:
                unsupported += 1
        report = RunnerReport(
            outcomes=tuple(outcomes),
            passed=passed,
            failed=failed,
            unsupported=unsupported,
        )
        logger.info(
            "conformance.runner.complete",
            extra={
                "total": report.total,
                "passed": passed,
                "failed": failed,
                "unsupported": unsupported,
            },
        )
        return report

    # ---- private dispatch ----

    def _run_one(self, vector: ConformanceVector) -> VectorOutcome:
        if vector.contract == "N4":
            return self._run_n4(vector)
        if vector.contract == "N5":
            return self._run_n5(vector)
        # Unsupported contract -- soft skip. The empty actual_canonical_json
        # signals that the runner did not attempt construction.
        expected_sha = _sha256_hex(vector.expected.canonical_json)
        return VectorOutcome(
            vector_id=vector.id,
            contract=vector.contract,
            status=VectorStatus.UNSUPPORTED,
            reason=f"unsupported contract {vector.contract!r}",
            expected_canonical_json=vector.expected.canonical_json,
            actual_canonical_json=None,
            expected_sha256=expected_sha,
            actual_sha256=None,
        )

    # ---- N4: TieredAuditEvent ----

    def _run_n4(self, vector: ConformanceVector) -> VectorOutcome:
        if vector.input.posture is None:
            # parse_vector already enforces this, but re-assert at the
            # runner boundary so a hand-constructed vector cannot bypass.
            raise ConformanceVectorError(
                f"vector {vector.id!r}: N4 contract requires input.posture"
            )
        # The Rust runner sets event_id + timestamp from the vector's fixed
        # fields when present and falls back to runtime values otherwise.
        # The conformance contract pins both: our N4 path requires both.
        if not vector.input.fixed_event_id:
            raise ConformanceVectorError(
                f"vector {vector.id!r}: N4 contract requires "
                f"input.fixed_event_id for deterministic canonicalisation"
            )
        if not vector.input.fixed_timestamp:
            raise ConformanceVectorError(
                f"vector {vector.id!r}: N4 contract requires "
                f"input.fixed_timestamp for deterministic canonicalisation"
            )

        event = TieredAuditEvent.from_verdict(
            vector.input.verdict,
            vector.input.posture,
            event_id=vector.input.fixed_event_id,
            timestamp=vector.input.fixed_timestamp,
        )
        actual = event.canonical_json()
        expected = vector.expected.canonical_json

        # First check the four optional N4 invariants. If any fails, fail
        # FAST with a focused reason rather than a canonical-JSON diff (the
        # diff would be misleading because the tier inside the JSON
        # already disagrees by construction).
        invariant_failure = self._check_n4_invariants(vector, event)
        if invariant_failure is not None:
            return VectorOutcome(
                vector_id=vector.id,
                contract="N4",
                status=VectorStatus.FAILED,
                reason=invariant_failure,
                expected_canonical_json=expected,
                actual_canonical_json=actual,
                expected_sha256=_sha256_hex(expected),
                actual_sha256=_sha256_hex(actual),
            )

        return _outcome_from_canonical_diff(
            vector_id=vector.id,
            contract="N4",
            expected=expected,
            actual=actual,
        )

    @staticmethod
    def _check_n4_invariants(
        vector: ConformanceVector, event: TieredAuditEvent
    ) -> str | None:
        """Return ``None`` on pass, a short reason string on fail."""
        expected = vector.expected
        if expected.tier is not None and event.tier is not expected.tier:
            return (
                f"tier mismatch: expected {expected.tier.value!r}, "
                f"got {event.tier.value!r}"
            )
        if expected.durable is not None and event.tier.is_durable() != expected.durable:
            return (
                f"durable flag mismatch: expected {expected.durable}, "
                f"got {event.tier.is_durable()}"
            )
        if (
            expected.requires_signature is not None
            and event.tier.requires_signature() != expected.requires_signature
        ):
            return (
                f"requires_signature mismatch: expected "
                f"{expected.requires_signature}, "
                f"got {event.tier.requires_signature()}"
            )
        if (
            expected.requires_replication is not None
            and event.tier.requires_replication() != expected.requires_replication
        ):
            return (
                f"requires_replication mismatch: expected "
                f"{expected.requires_replication}, "
                f"got {event.tier.requires_replication()}"
            )
        return None

    # ---- N5: Evidence ----

    def _run_n5(self, vector: ConformanceVector) -> VectorOutcome:
        if not vector.input.fixed_timestamp:
            raise ConformanceVectorError(
                f"vector {vector.id!r}: N5 contract requires "
                f"input.fixed_timestamp for deterministic canonicalisation"
            )
        # Mirror the Rust ``run_n5``: source = evidence_source if present,
        # else verdict.role_address.
        source = (
            vector.input.evidence_source
            if vector.input.evidence_source is not None
            else vector.input.verdict.role_address
        )
        evidence = Evidence.from_verdict(
            vector.input.verdict,
            source=source,
            timestamp=vector.input.fixed_timestamp,
        )
        if vector.input.evidence_schema is not None:
            evidence = evidence.with_schema(vector.input.evidence_schema)
        actual = evidence.canonical_json()
        expected = vector.expected.canonical_json
        return _outcome_from_canonical_diff(
            vector_id=vector.id,
            contract="N5",
            expected=expected,
            actual=actual,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outcome_from_canonical_diff(
    *,
    vector_id: str,
    contract: str,
    expected: str,
    actual: str,
) -> VectorOutcome:
    """Compare canonical JSON byte strings; build the corresponding outcome."""
    expected_sha = _sha256_hex(expected)
    actual_sha = _sha256_hex(actual)
    if actual == expected:
        return VectorOutcome(
            vector_id=vector_id,
            contract=contract,
            status=VectorStatus.PASSED,
            reason="",
            expected_canonical_json=expected,
            actual_canonical_json=actual,
            expected_sha256=expected_sha,
            actual_sha256=actual_sha,
        )
    return VectorOutcome(
        vector_id=vector_id,
        contract=contract,
        status=VectorStatus.FAILED,
        reason="canonical_json mismatch",
        expected_canonical_json=expected,
        actual_canonical_json=actual,
        expected_sha256=expected_sha,
        actual_sha256=actual_sha,
    )


def _sha256_hex(value: str) -> str:
    """Lowercase-hex SHA-256 of ``value`` UTF-8 bytes.

    Matches the Rust ``sha256_hex`` helper used in the runner panic message
    so cross-SDK fingerprints align byte-for-byte.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def run_vectors(vectors: Sequence[ConformanceVector]) -> RunnerReport:
    """Convenience wrapper around :meth:`ConformanceRunner.run`."""
    return ConformanceRunner().run(vectors)
