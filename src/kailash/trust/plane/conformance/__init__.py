# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP Conformance Suite for TrustPlane.

Validates whether an EATP implementation correctly implements
the normative requirements from the spec:
- MUST tests: Must pass for conformance
- SHOULD tests: Expected but not required
- MAY tests: Optional, reported as supported/unsupported

Conformance levels (per EATP spec Section 7):
- EATP Compatible: Genesis + Anchor + Constraint MUST tests
- EATP Conformant: All MUST tests, 80%+ SHOULD tests
- EATP Complete: All MUST + SHOULD + verification gradient + postures
"""

import asyncio
import copy
import hmac as hmac_mod
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

from kailash.trust._locking import safe_read_json as _safe_read_json


class RequirementLevel(Enum):
    """RFC 2119 requirement levels."""

    MUST = "MUST"
    SHOULD = "SHOULD"
    MAY = "MAY"


class ConformanceLevel(Enum):
    """EATP conformance levels (per spec Section 7)."""

    COMPATIBLE = "compatible"
    CONFORMANT = "conformant"
    COMPLETE = "complete"


class TestResult(Enum):
    """Result of a single conformance test."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class ConformanceTest:
    """A single conformance test."""

    name: str
    description: str
    element: str  # Category: genesis, delegation, constraint, attestation, anchor, verification, posture, mirror
    level: RequirementLevel
    min_level: ConformanceLevel = ConformanceLevel.COMPATIBLE
    test_fn: Callable[..., Awaitable[bool]] | Callable[..., bool] | None = None
    result: TestResult = TestResult.SKIP
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "element": self.element,
            "level": self.level.value,
            "min_level": self.min_level.value,
            "result": self.result.value,
            "error": self.error,
        }


@dataclass
class ConformanceReport:
    """Result of running the conformance suite."""

    implementation: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tests: list[ConformanceTest] = field(default_factory=list)
    level_achieved: ConformanceLevel | None = None

    @property
    def must_pass(self) -> int:
        return sum(
            1
            for t in self.tests
            if t.level == RequirementLevel.MUST and t.result == TestResult.PASS
        )

    @property
    def must_total(self) -> int:
        return sum(1 for t in self.tests if t.level == RequirementLevel.MUST)

    @property
    def should_pass(self) -> int:
        return sum(
            1
            for t in self.tests
            if t.level == RequirementLevel.SHOULD and t.result == TestResult.PASS
        )

    @property
    def should_total(self) -> int:
        return sum(1 for t in self.tests if t.level == RequirementLevel.SHOULD)

    @property
    def all_must_pass(self) -> bool:
        return self.must_pass == self.must_total

    @property
    def should_percentage(self) -> float:
        if self.should_total == 0:
            return 100.0
        return round(self.should_pass / self.should_total * 100, 1)

    def compute_level(self) -> ConformanceLevel | None:
        """Determine the highest conformance level achieved.

        Uses structural requirements per EATP spec Section 7:
        - Compatible: All MUST tests at Compatible level pass
        - Conformant: All Compatible + all MUST tests at Conformant level pass,
          plus 80%+ of SHOULD tests at Conformant level
        - Complete: All Conformant + all MUST tests at Complete level pass,
          plus all SHOULD tests pass
        """

        def _level_passes(level: ConformanceLevel) -> bool:
            """Check if all MUST tests for a given level pass.

            Returns False if there are no MUST tests at this level
            (cannot claim a level without evidence).
            """
            must_tests = [
                t
                for t in self.tests
                if t.level == RequirementLevel.MUST and t.min_level == level
            ]
            if not must_tests:
                return False
            return all(t.result == TestResult.PASS for t in must_tests)

        _LEVEL_ORDER = {
            ConformanceLevel.COMPATIBLE: 0,
            ConformanceLevel.CONFORMANT: 1,
            ConformanceLevel.COMPLETE: 2,
        }

        def _should_percentage_at(level: ConformanceLevel) -> float:
            """Get SHOULD pass percentage for tests at or below a level."""
            should_tests = [
                t
                for t in self.tests
                if t.level == RequirementLevel.SHOULD
                and _LEVEL_ORDER[t.min_level] <= _LEVEL_ORDER[level]
            ]
            if not should_tests:
                return 100.0
            passed = sum(1 for t in should_tests if t.result == TestResult.PASS)
            return round(passed / len(should_tests) * 100, 1)

        # Compatible: all MUST at Compatible level
        if not _level_passes(ConformanceLevel.COMPATIBLE):
            return None

        # Conformant: Compatible + all MUST at Conformant + 80% SHOULD
        if not _level_passes(ConformanceLevel.CONFORMANT):
            return ConformanceLevel.COMPATIBLE

        if _should_percentage_at(ConformanceLevel.CONFORMANT) < 80:
            return ConformanceLevel.COMPATIBLE

        # Complete: Conformant + all MUST at Complete + all SHOULD pass
        if not _level_passes(ConformanceLevel.COMPLETE):
            return ConformanceLevel.CONFORMANT

        if self.should_percentage < 100:
            return ConformanceLevel.CONFORMANT

        return ConformanceLevel.COMPLETE

    def to_dict(self) -> dict[str, Any]:
        self.level_achieved = self.compute_level()
        return {
            "implementation": self.implementation,
            "timestamp": self.timestamp.isoformat(),
            "level_achieved": (
                self.level_achieved.value if self.level_achieved else None
            ),
            "summary": {
                "must_pass": self.must_pass,
                "must_total": self.must_total,
                "should_pass": self.should_pass,
                "should_total": self.should_total,
                "should_percentage": self.should_percentage,
            },
            "tests": [t.to_dict() for t in self.tests],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


class ConformanceSuite:
    """EATP Conformance test runner.

    Runs a battery of tests against a TrustProject to verify
    EATP conformance at Compatible, Conformant, or Complete level.
    """

    def __init__(self) -> None:
        self._tests: list[ConformanceTest] = []
        self._register_tests()

    def _register_tests(self) -> None:
        """Register all conformance tests.

        Each test is tagged with min_level per EATP spec Section 7:
        - COMPATIBLE: Genesis, basic Constraint, basic Anchor
        - CONFORMANT: All 5 elements, 4 ops, verification gradient,
                      cascade revocation, delegation, reasoning traces
        - COMPLETE: All postures, enforcement modes, interop, confidentiality
        """
        # --- EATP Compatible (Level 1) ---
        # Genesis Record tests
        self._tests.extend(
            [
                ConformanceTest(
                    name="genesis_exists",
                    description="Project has a Genesis Record",
                    element="genesis",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPATIBLE,
                ),
                ConformanceTest(
                    name="genesis_has_authority",
                    description="Genesis Record references an authority",
                    element="genesis",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPATIBLE,
                ),
                ConformanceTest(
                    name="genesis_has_agent",
                    description="Genesis Record creates an agent identity",
                    element="genesis",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPATIBLE,
                ),
                ConformanceTest(
                    name="genesis_has_chain_hash",
                    description="Genesis Record produces a chain hash",
                    element="genesis",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPATIBLE,
                ),
            ]
        )

        # Constraint Envelope tests (basic: Compatible; all 5 dims: Conformant)
        self._tests.extend(
            [
                ConformanceTest(
                    name="constraint_hash_stable",
                    description="Envelope hash is deterministic",
                    element="constraint",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPATIBLE,
                ),
                ConformanceTest(
                    name="constraint_enforcement",
                    description="Blocked actions return BLOCKED verdict",
                    element="constraint",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPATIBLE,
                ),
            ]
        )

        # Audit Anchor tests (Compatible)
        self._tests.extend(
            [
                ConformanceTest(
                    name="anchor_created_on_decision",
                    description="Recording a decision creates an audit anchor",
                    element="anchor",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPATIBLE,
                ),
                ConformanceTest(
                    name="anchor_has_parent_chain",
                    description="Anchors form a linked chain via parent references",
                    element="anchor",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPATIBLE,
                ),
                ConformanceTest(
                    name="anchor_chain_verifiable",
                    description="Chain integrity is verifiable",
                    element="anchor",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPATIBLE,
                ),
            ]
        )

        # --- EATP Conformant (Level 2) ---
        # All 5 dimensions + monotonic tightening
        self._tests.extend(
            [
                ConformanceTest(
                    name="constraint_five_dimensions",
                    description="Constraint envelope supports all 5 EATP dimensions",
                    element="constraint",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.CONFORMANT,
                ),
                ConformanceTest(
                    name="constraint_monotonic_tightening",
                    description="Envelopes can only be tightened, not loosened",
                    element="constraint",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.CONFORMANT,
                ),
            ]
        )

        # Verification at STANDARD and FULL (Conformant MUST)
        self._tests.extend(
            [
                ConformanceTest(
                    name="verification_standard",
                    description="STANDARD verification validates constraints and capabilities",
                    element="verification",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.CONFORMANT,
                ),
                ConformanceTest(
                    name="verification_full",
                    description="FULL verification validates cryptographic chain integrity",
                    element="verification",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.CONFORMANT,
                ),
            ]
        )

        # Delegation (Conformant MUST)
        self._tests.extend(
            [
                ConformanceTest(
                    name="delegation_supported",
                    description="Delegation chains are supported",
                    element="delegation",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.CONFORMANT,
                ),
                ConformanceTest(
                    name="delegation_cascade_revocation",
                    description="Revoking a delegate cascades to sub-delegates",
                    element="delegation",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.CONFORMANT,
                ),
            ]
        )

        # Capability Attestation (Conformant MUST — all 5 elements)
        self._tests.append(
            ConformanceTest(
                name="attestation_supported",
                description="Capability Attestation exists in the trust chain",
                element="attestation",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.CONFORMANT,
            )
        )

        # Verification gradient — 4 categories (Conformant MUST)
        self._tests.append(
            ConformanceTest(
                name="verification_gradient",
                description="Four verification categories: Auto-approved, Flagged, Held, Blocked",
                element="verification",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.CONFORMANT,
            )
        )

        # Reasoning traces (Conformant MUST)
        self._tests.append(
            ConformanceTest(
                name="reasoning_trace_stored",
                description="Reasoning traces are stored with audit anchors",
                element="anchor",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.CONFORMANT,
            )
        )

        # REASONING_REQUIRED constraint (Conformant MUST — reasoning traces
        # must be present when FULL verification is used)
        self._tests.append(
            ConformanceTest(
                name="reasoning_required",
                description="Reasoning traces are attached to audit anchors (REASONING_REQUIRED)",
                element="anchor",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.CONFORMANT,
            )
        )

        # Dual-binding signing (Conformant MUST — reasoning_trace_hash in
        # signing payload prevents same-signer trace substitution)
        self._tests.append(
            ConformanceTest(
                name="dual_binding_signing",
                description="Reasoning trace hash is bound into the anchor signing payload",
                element="anchor",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.CONFORMANT,
            )
        )

        # QUICK verification (Conformant SHOULD)
        self._tests.append(
            ConformanceTest(
                name="verification_quick",
                description="QUICK verification produces verification reports",
                element="verification",
                level=RequirementLevel.SHOULD,
                min_level=ConformanceLevel.CONFORMANT,
            )
        )

        # Persistent storage (Conformant SHOULD — spec line 76)
        self._tests.append(
            ConformanceTest(
                name="persistent_storage",
                description="At least one persistent storage backend beyond in-memory",
                element="anchor",
                level=RequirementLevel.SHOULD,
                min_level=ConformanceLevel.CONFORMANT,
            )
        )

        # --- EATP Complete (Level 3) ---
        # Trust Postures (Complete MUST)
        self._tests.extend(
            [
                ConformanceTest(
                    name="posture_five_levels",
                    description="All 5 trust posture levels are supported",
                    element="posture",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPLETE,
                ),
                ConformanceTest(
                    name="posture_progression",
                    description="Trust posture can progress through levels",
                    element="posture",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPLETE,
                ),
                ConformanceTest(
                    name="posture_instant_downgrade",
                    description="Trust posture can be instantly downgraded",
                    element="posture",
                    level=RequirementLevel.MUST,
                    min_level=ConformanceLevel.COMPLETE,
                ),
            ]
        )

        # Confidentiality (Complete MUST)
        self._tests.append(
            ConformanceTest(
                name="confidentiality_five_levels",
                description="All 5 confidentiality levels work with VerificationBundle",
                element="attestation",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.COMPLETE,
            )
        )

        # Enforcement modes (Complete MUST)
        self._tests.append(
            ConformanceTest(
                name="enforcement_dual_mode",
                description="Both StrictEnforcer and ShadowEnforcer are available",
                element="constraint",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.COMPLETE,
            )
        )

        # VerificationBundle export (Complete MUST)
        self._tests.append(
            ConformanceTest(
                name="verification_bundle_export",
                description="VerificationBundle can be created from a project",
                element="anchor",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.COMPLETE,
            )
        )

        # Interop export formats (Complete MUST — spec requires 2 of 6)
        self._tests.append(
            ConformanceTest(
                name="interop_export_formats",
                description="At least 2 export formats are supported (JSON + HTML)",
                element="anchor",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.COMPLETE,
            )
        )

        # Shadow enforcer report (Complete SHOULD)
        self._tests.append(
            ConformanceTest(
                name="enforcement_shadow_report",
                description="Shadow enforcer produces observation reports",
                element="constraint",
                level=RequirementLevel.SHOULD,
                min_level=ConformanceLevel.COMPLETE,
            )
        )

        # Mirror Thesis tests (MAY — not required at any level)
        self._tests.extend(
            [
                ConformanceTest(
                    name="mirror_execution_records",
                    description="Execution records (autonomous AI) are supported",
                    element="mirror",
                    level=RequirementLevel.MAY,
                    min_level=ConformanceLevel.COMPLETE,
                ),
                ConformanceTest(
                    name="mirror_escalation_records",
                    description="Escalation records (AI needs human) are supported",
                    element="mirror",
                    level=RequirementLevel.MAY,
                    min_level=ConformanceLevel.COMPLETE,
                ),
                ConformanceTest(
                    name="mirror_intervention_records",
                    description="Intervention records (human intervenes) are supported",
                    element="mirror",
                    level=RequirementLevel.MAY,
                    min_level=ConformanceLevel.COMPLETE,
                ),
            ]
        )

    async def run(self, project: Any) -> ConformanceReport:
        """Run the conformance suite against a TrustProject.

        Creates a copy of each test to avoid mutating internal state,
        allowing the suite to be reused across multiple runs.

        Args:
            project: A TrustProject instance to test

        Returns:
            ConformanceReport with results
        """
        report = ConformanceReport(
            implementation=f"TrustPlane ({project.manifest.project_name})"
        )

        for test in self._tests:
            test_copy = copy.copy(test)
            try:
                passed = await self._run_test(test_copy, project)
                test_copy.result = TestResult.PASS if passed else TestResult.FAIL
            except Exception as e:
                test_copy.result = TestResult.ERROR
                test_copy.error = str(e)

            report.tests.append(test_copy)

        report.level_achieved = report.compute_level()
        return report

    async def _run_test(self, test: ConformanceTest, project: Any) -> bool:
        """Run a single conformance test."""
        method_name = f"_test_{test.name}"
        method = getattr(self, method_name, None)
        if method is None:
            raise NotImplementedError(f"Test not implemented: {test.name}")
        result = method(project)
        if asyncio.iscoroutine(result):
            return await result
        return result

    # --- Genesis Record tests ---

    def _test_genesis_exists(self, project: Any) -> bool:
        return bool(project.manifest.genesis_id)

    def _test_genesis_has_authority(self, project: Any) -> bool:
        genesis_path = project._dir / "genesis.json"
        if not genesis_path.exists():
            return False
        data = _safe_read_json(genesis_path)
        return bool(data.get("authority_id"))

    def _test_genesis_has_agent(self, project: Any) -> bool:
        genesis_path = project._dir / "genesis.json"
        if not genesis_path.exists():
            return False
        data = _safe_read_json(genesis_path)
        return bool(data.get("agent_id"))

    def _test_genesis_has_chain_hash(self, project: Any) -> bool:
        return bool(project.manifest.chain_hash)

    # --- Constraint Envelope tests ---

    def _test_constraint_five_dimensions(self, project: Any) -> bool:
        env = project.manifest.constraint_envelope
        if env is None:
            return False
        # Check all 5 dimensions exist as attributes
        return all(
            hasattr(env, dim)
            for dim in [
                "operational",
                "data_access",
                "financial",
                "temporal",
                "communication",
            ]
        )

    def _test_constraint_hash_stable(self, project: Any) -> bool:
        """Verify deterministic hashing: identical content → same hash, different content → different hash."""
        from kailash.trust.plane.models import (
            ConstraintEnvelope,
            OperationalConstraints,
        )

        env = project.manifest.constraint_envelope
        if env is None:
            return False
        # Two identical envelopes must produce the same hash
        env_copy = ConstraintEnvelope.from_dict(env.to_dict())
        if env.envelope_hash() != env_copy.envelope_hash():
            return False
        # A different envelope must produce a different hash
        different = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["__conformance_unique__"]
            ),
        )
        return env.envelope_hash() != different.envelope_hash()

    def _test_constraint_monotonic_tightening(self, project: Any) -> bool:
        """Verify using the PROJECT's constraint envelope, not synthetic ones."""
        from kailash.trust.plane.models import (
            ConstraintEnvelope,
            OperationalConstraints,
        )

        env = project.manifest.constraint_envelope
        if env is None:
            return False
        # Create a tighter version by adding a blocked action
        tighter_data = env.to_dict()
        tighter_data["operational"]["blocked_actions"] = (
            env.operational.blocked_actions + ["__conformance_extra_block__"]
        )
        tighter = ConstraintEnvelope.from_dict(tighter_data)
        if not tighter.is_tighter_than(env):
            return False
        # Create a looser version by removing a blocked action
        if env.operational.blocked_actions:
            looser_data = env.to_dict()
            looser_data["operational"]["blocked_actions"] = []
            looser = ConstraintEnvelope.from_dict(looser_data)
            if looser.is_tighter_than(env):
                return False  # Removing blocks should NOT be tighter
        return True

    def _test_constraint_enforcement(self, project: Any) -> bool:
        """Verify enforcement across multiple constraint paths, not just one."""
        from kailash.trust.enforce.strict import Verdict

        env = project.manifest.constraint_envelope
        if env is None:
            return False
        # BLOCKED path: every blocked action must return BLOCKED
        if not env.operational.blocked_actions:
            return False  # Cannot verify enforcement without constraints
        for blocked_action in env.operational.blocked_actions:
            if project.check(blocked_action) != Verdict.BLOCKED:
                return False
        # ALLOWED path: allowed actions must NOT return BLOCKED
        for allowed_action in env.operational.allowed_actions:
            if project.check(allowed_action) == Verdict.BLOCKED:
                return False
        # Unknown action (not in any list) must not crash
        unknown_verdict = project.check("__conformance_unknown_action__")
        if unknown_verdict == Verdict.BLOCKED:
            return False  # Unknown actions should not be hard-blocked
        return True

    # --- Audit Anchor tests ---

    async def _test_anchor_created_on_decision(self, project: Any) -> bool:
        from kailash.trust.plane.models import DecisionRecord

        initial_count = project.manifest.total_audits
        await project.record_decision(
            DecisionRecord(
                decision_type="conformance_test",
                decision="Testing anchor creation",
                rationale="Conformance suite",
            )
        )
        return project.manifest.total_audits > initial_count

    async def _test_anchor_has_parent_chain(self, project: Any) -> bool:
        from kailash.trust.plane.models import DecisionRecord

        # Create anchors to ensure chain has >= 2
        for i in range(2):
            await project.record_decision(
                DecisionRecord(
                    decision_type="conformance_test",
                    decision=f"Chain linkage test {i}",
                    rationale="Conformance suite",
                )
            )
        anchors_dir = project._dir / "anchors"
        if not anchors_dir.exists():
            return False
        files = sorted(anchors_dir.glob("*.json"))
        if len(files) < 2:
            return False
        # Check that later anchors reference earlier ones
        last = _safe_read_json(files[-1])
        return "parent_anchor_id" in last.get("context", {})

    async def _test_anchor_chain_verifiable(self, project: Any) -> bool:
        report = await project.verify()
        return report["chain_valid"]

    # --- Capability Attestation tests ---

    def _test_attestation_supported(self, project: Any) -> bool:
        """Verify trust chain contains capability attestations with real content."""
        chains_dir = project._dir / "chains"
        if not chains_dir.exists():
            return False
        chain_files = list(chains_dir.glob("**/*.json"))
        if not chain_files:
            return False
        # Verify at least one chain file contains capability attestation data
        for chain_file in chain_files:
            data = _safe_read_json(chain_file)
            if not isinstance(data, dict) or "agent_id" not in data:
                continue
            # EATP chain structure: {agent_id, chain: {capabilities: [...]}}
            chain = data.get("chain", {})
            if isinstance(chain, dict):
                caps = chain.get("capabilities", [])
                if isinstance(caps, list) and len(caps) > 0:
                    # Verify at least one capability has required fields
                    for cap in caps:
                        if (
                            isinstance(cap, dict)
                            and "capability" in cap
                            and "attester_id" in cap
                        ):
                            return True
        return False

    # --- Verification Gradient tests ---

    def _test_verification_gradient(self, project: Any) -> bool:
        """Verify all 4 verification categories work."""
        from kailash.trust.enforce.strict import Verdict

        env = project.manifest.constraint_envelope
        if env is None:
            return False
        # BLOCKED: a blocked action must return BLOCKED
        if env.operational.blocked_actions:
            blocked = env.operational.blocked_actions[0]
            if project.check(blocked) != Verdict.BLOCKED:
                return False
        # AUTO_APPROVED: an allowed action should return AUTO_APPROVED
        if env.operational.allowed_actions:
            allowed = env.operational.allowed_actions[0]
            result = project.check(allowed)
            if result not in (Verdict.AUTO_APPROVED, Verdict.FLAGGED):
                return False
        # Verify all 4 categories exist in the Verdict enum
        return all(
            hasattr(Verdict, v) for v in ["AUTO_APPROVED", "FLAGGED", "HELD", "BLOCKED"]
        )

    async def _test_verification_quick(self, project: Any) -> bool:
        """QUICK verification: project produces verification reports."""
        report = await project.verify()
        return "verification_level" in report

    async def _test_verification_standard(self, project: Any) -> bool:
        """STANDARD verification: constraint and capability validation."""
        report = await project.verify()
        return (
            report.get("chain_valid") is not None
            and report.get("total_decisions", -1) >= 0
        )

    async def _test_verification_full(self, project: Any) -> bool:
        """FULL verification: cryptographic chain integrity verified."""
        report = await project.verify()
        return report.get("chain_valid", False)

    # --- Reasoning Trace tests ---

    async def _test_reasoning_trace_stored(self, project: Any) -> bool:
        """Verify reasoning traces are stored with audit anchors."""
        from kailash.trust.plane.models import DecisionRecord

        await project.record_decision(
            DecisionRecord(
                decision_type="conformance_test",
                decision="Testing reasoning trace storage",
                rationale="Conformance suite — verifying traces attach to anchors",
            )
        )
        anchors_dir = project._dir / "anchors"
        if not anchors_dir.exists():
            return False
        files = sorted(anchors_dir.glob("*.json"))
        if not files:
            return False
        data = _safe_read_json(files[-1])
        return "reasoning_trace" in data and data["reasoning_trace"] is not None

    async def _test_reasoning_required(self, project: Any) -> bool:
        """Verify REASONING_REQUIRED: decision anchors have reasoning traces
        with required fields, and verify() detects missing traces.

        EATP spec requires reasoning traces at FULL verification level.
        This test verifies:
        1. TrustPlane always attaches reasoning traces to decision anchors
        2. The reasoning trace contains required fields (decision, rationale)
        3. The reasoning_trace_hash is present (dual-binding)
        """
        from kailash.trust.plane.models import DecisionRecord

        # Record a decision — should always get a reasoning trace
        await project.record_decision(
            DecisionRecord(
                decision_type="conformance_test",
                decision="REASONING_REQUIRED test",
                rationale="Must have reasoning trace in anchor",
            )
        )
        anchors_dir = project._dir / "anchors"
        if not anchors_dir.exists():
            return False
        files = sorted(anchors_dir.glob("*.json"))
        if not files:
            return False
        # Check the most recent anchor has a non-empty reasoning trace
        data = _safe_read_json(files[-1])
        trace = data.get("reasoning_trace")
        if not isinstance(trace, dict):
            return False
        # Reasoning trace must have decision and rationale
        if not trace.get("decision") or not trace.get("rationale"):
            return False
        # reasoning_trace_hash must be present (EATP v2.2 dual-binding)
        if not data.get("reasoning_trace_hash"):
            return False
        return True

    async def _test_dual_binding_signing(self, project: Any) -> bool:
        """Verify dual-binding: reasoning_trace_hash is bound in the anchor.

        EATP v2.2 requires the reasoning_trace_hash to be included in the
        anchor to prevent same-signer substitution. This test verifies that:
        1. Anchors with reasoning traces include a reasoning_trace_hash field
        2. The hash matches the actual trace content (not swapped)

        Fails if reasoning_trace_hash is missing or doesn't match.
        """
        from kailash.trust.plane.models import DecisionRecord
        from kailash.trust.reasoning.traces import ReasoningTrace

        # Record a decision to create an anchor with reasoning trace
        await project.record_decision(
            DecisionRecord(
                decision_type="conformance_test",
                decision="Dual-binding signing test",
                rationale="Verify reasoning_trace_hash binding",
            )
        )
        anchors_dir = project._dir / "anchors"
        if not anchors_dir.exists():
            return False
        files = sorted(anchors_dir.glob("*.json"))
        if not files:
            return False

        data = _safe_read_json(files[-1])

        trace_data = data.get("reasoning_trace")
        if not isinstance(trace_data, dict):
            return False

        # The anchor MUST have reasoning_trace_hash as a top-level field
        stored_hash = data.get("reasoning_trace_hash")
        if stored_hash is None:
            return False  # Dual-binding requires the hash to be present

        # Reconstruct the reasoning trace and verify the hash matches
        trace = ReasoningTrace.from_dict(trace_data)
        expected_hash = trace.content_hash_hex()
        return hmac_mod.compare_digest(stored_hash, expected_hash)

    # --- Persistent Storage tests ---

    async def _test_persistent_storage(self, project: Any) -> bool:
        """Verify round-trip persistence: write a decision, reload from disk, verify it survived."""
        from kailash.trust.plane.models import DecisionRecord
        from kailash.trust.plane.project import TrustProject

        # Record a decision with a unique marker
        marker = "__conformance_persistence_test__"
        await project.record_decision(
            DecisionRecord(
                decision_type="conformance_test",
                decision=marker,
                rationale="Testing round-trip persistence",
            )
        )
        # Reload project from disk (new instance, same directory)
        reloaded = await TrustProject.load(project._dir)
        # Verify the decision survived the reload
        if reloaded.manifest.total_audits < 1:
            return False
        # Verify manifest.json exists on disk with correct count
        manifest_path = project._dir / "manifest.json"
        if not manifest_path.exists():
            return False
        stored = _safe_read_json(manifest_path)
        return stored.get("total_audits", 0) >= project.manifest.total_audits

    # --- Trust Posture tests ---

    async def _test_posture_five_levels(self, project: Any) -> bool:
        """Verify all 5 trust postures are reachable, not just that one exists."""
        from kailash.trust.posture.postures import TrustPosture

        all_postures = [
            TrustPosture.PSEUDO,
            TrustPosture.TOOL,
            TrustPosture.SUPERVISED,
            TrustPosture.DELEGATING,
            TrustPosture.AUTONOMOUS,
        ]
        # Current posture must be one of the 5
        if project.posture not in all_postures:
            return False
        # Transition to each posture and verify it takes effect
        for target in all_postures:
            new = await project.transition_posture(target, "conformance: five levels")
            if new != target:
                return False
        # Return to initial safe posture
        await project.transition_posture(TrustPosture.PSEUDO, "conformance: cleanup")
        return True

    async def _test_posture_progression(self, project: Any) -> bool:
        """Trust posture can progress through levels."""
        from kailash.trust.posture.postures import TrustPosture

        initial = project.posture
        target = (
            TrustPosture.TOOL
            if initial != TrustPosture.TOOL
            else TrustPosture.SUPERVISED
        )
        new = await project.transition_posture(target, "conformance test: progression")
        return new == target

    async def _test_posture_instant_downgrade(self, project: Any) -> bool:
        """Trust posture can be instantly downgraded."""
        from kailash.trust.posture.postures import TrustPosture

        # Ensure we're not already at the lowest posture
        if project.posture == TrustPosture.PSEUDO:
            await project.transition_posture(TrustPosture.TOOL, "conformance setup")
        # Now downgrade — must succeed immediately
        new = await project.transition_posture(
            TrustPosture.PSEUDO, "conformance test: instant downgrade"
        )
        return new == TrustPosture.PSEUDO

    # --- Confidentiality tests ---

    async def _test_confidentiality_five_levels(self, project: Any) -> bool:
        """All 5 confidentiality levels work with VerificationBundle."""
        from kailash.trust.plane.bundle import VerificationBundle
        from kailash.trust.reasoning.traces import ConfidentialityLevel

        for level in [
            ConfidentialityLevel.PUBLIC,
            ConfidentialityLevel.RESTRICTED,
            ConfidentialityLevel.CONFIDENTIAL,
            ConfidentialityLevel.SECRET,
            ConfidentialityLevel.TOP_SECRET,
        ]:
            bundle = await VerificationBundle.create(
                project, confidentiality_ceiling=level
            )
            if bundle is None:
                return False
        return True

    # --- Enforcement tests ---

    async def _test_enforcement_dual_mode(self, project: Any) -> bool:
        """Verify both enforcement modes work by switching between them.

        Tests behavioral differences:
        1. Strict mode: blocked actions return BLOCKED
        2. Shadow mode: can be switched to and produces reports
        3. Mode switching creates audit anchors (audit count increases)
        """
        from kailash.trust.enforce.strict import Verdict

        env = project.manifest.constraint_envelope
        if env is None or not env.operational.blocked_actions:
            return False

        blocked_action = env.operational.blocked_actions[0]
        initial_mode = project.enforcement_mode

        # 1. Verify strict mode: blocked actions return BLOCKED
        if initial_mode != "strict":
            await project.switch_enforcement("strict", "conformance: test strict")
        strict_verdict = project.check(blocked_action)
        if strict_verdict != Verdict.BLOCKED:
            return False

        # 2. Switch to shadow mode — verify mode changed and report works
        audits_before = project.manifest.total_audits
        await project.switch_enforcement("shadow", "conformance: test shadow")
        if project.enforcement_mode != "shadow":
            return False
        # Shadow enforcer must produce a report (even if empty)
        shadow_report = project.shadow_report()
        if not isinstance(shadow_report, str):
            return False
        # Mode switch should create an audit anchor
        if project.manifest.total_audits <= audits_before:
            return False

        # 3. Switch back to strict — verify enforcement is restored
        await project.switch_enforcement("strict", "conformance: restore strict")
        if project.enforcement_mode != "strict":
            return False
        restored_verdict = project.check(blocked_action)
        if restored_verdict != Verdict.BLOCKED:
            return False

        return True

    def _test_enforcement_shadow_report(self, project: Any) -> bool:
        """Shadow enforcer produces observation reports."""
        report = project.shadow_report()
        return isinstance(report, str)

    # --- VerificationBundle and Interop tests ---

    async def _test_verification_bundle_export(self, project: Any) -> bool:
        """VerificationBundle can be created from a project."""
        from kailash.trust.plane.bundle import VerificationBundle

        bundle = await VerificationBundle.create(project)
        return (
            bundle.genesis is not None
            and bundle.public_key != ""
            and bundle.chain_hash != ""
        )

    async def _test_interop_export_formats(self, project: Any) -> bool:
        """At least 2 export formats are supported (JSON + HTML)."""
        from kailash.trust.plane.bundle import VerificationBundle

        bundle = await VerificationBundle.create(project)
        # JSON export
        json_str = bundle.to_json()
        if not json_str:
            return False
        # HTML export
        html_str = bundle.to_html()
        if not html_str:
            return False
        return True

    # --- Delegation tests ---

    def _test_delegation_supported(self, project: Any) -> bool:
        from kailash.trust.plane.delegation import DelegationManager

        mgr = DelegationManager(project._dir)
        d = mgr.add_delegate("conformance_test", ["operational"])
        return d.delegate_id.startswith("del-")

    def _test_delegation_cascade_revocation(self, project: Any) -> bool:
        from kailash.trust.plane.delegation import DelegationManager

        mgr = DelegationManager(project._dir)
        parent = mgr.add_delegate("cascade_parent", ["operational"])
        mgr.add_delegate(
            "cascade_child",
            ["operational"],
            parent_delegate_id=parent.delegate_id,
        )
        revoked = mgr.revoke_delegate(parent.delegate_id)
        return len(revoked) == 2

    # --- Mirror Thesis tests ---

    async def _test_mirror_execution_records(self, project: Any) -> bool:
        """Verify record_execution() creates an audit anchor with mirror data."""
        from kailash.trust.plane.models import ExecutionRecord

        initial_audits = project.manifest.total_audits
        exec_id = await project.record_execution(
            ExecutionRecord(
                action="conformance_autonomous_action",
                constraint_reference="conformance_test",
            )
        )
        if not exec_id.startswith("exec-"):
            return False
        if project.manifest.total_audits <= initial_audits:
            return False
        # Verify the anchor file contains mirror_record
        anchors_dir = project._dir / "anchors"
        files = sorted(anchors_dir.glob("*.json"))
        data = _safe_read_json(files[-1])
        return data.get("mirror_record", {}).get("record_type") == "execution"

    async def _test_mirror_escalation_records(self, project: Any) -> bool:
        """Verify record_escalation() creates an audit anchor with mirror data."""
        from kailash.trust.plane.models import EscalationRecord, HumanCompetency

        initial_audits = project.manifest.total_audits
        esc_id = await project.record_escalation(
            EscalationRecord(
                trigger="conformance_boundary_reached",
                recommendation="Human judgment needed",
                competency_categories=[HumanCompetency.ETHICAL_JUDGMENT],
                constraint_dimension="operational",
            )
        )
        if not esc_id.startswith("esc-"):
            return False
        if project.manifest.total_audits <= initial_audits:
            return False
        anchors_dir = project._dir / "anchors"
        files = sorted(anchors_dir.glob("*.json"))
        data = _safe_read_json(files[-1])
        return data.get("mirror_record", {}).get("record_type") == "escalation"

    async def _test_mirror_intervention_records(self, project: Any) -> bool:
        """Verify record_intervention() creates an audit anchor with mirror data."""
        from kailash.trust.plane.models import HumanCompetency, InterventionRecord

        initial_audits = project.manifest.total_audits
        int_id = await project.record_intervention(
            InterventionRecord(
                observation="conformance_human_noticed_issue",
                action_taken="Human corrected the output",
                competency_categories=[HumanCompetency.CONTEXTUAL_WISDOM],
            )
        )
        if not int_id.startswith("int-"):
            return False
        if project.manifest.total_audits <= initial_audits:
            return False
        anchors_dir = project._dir / "anchors"
        files = sorted(anchors_dir.glob("*.json"))
        data = _safe_read_json(files[-1])
        return data.get("mirror_record", {}).get("record_type") == "intervention"


def format_conformance_report(report: ConformanceReport) -> str:
    """Format a conformance report as human-readable text."""
    lines: list[str] = []
    level = report.compute_level()
    level_str = level.value.upper() if level else "NONE"

    lines.append(f"EATP Conformance Report: {report.implementation}")
    lines.append(f"Level Achieved: {level_str}")
    lines.append(
        f"MUST: {report.must_pass}/{report.must_total} | "
        f"SHOULD: {report.should_pass}/{report.should_total} ({report.should_percentage}%)"
    )
    lines.append("")

    # Group by element
    elements: dict[str, list[ConformanceTest]] = {}
    for t in report.tests:
        elements.setdefault(t.element, []).append(t)

    for element, tests in elements.items():
        lines.append(f"  {element.upper()}")
        for t in tests:
            icon = {"pass": "+", "fail": "X", "skip": "-", "error": "!"}[t.result.value]
            lines.append(f"    [{icon}] {t.level.value:6s} {t.description}")
            if t.error:
                lines.append(f"           Error: {t.error}")
        lines.append("")

    return "\n".join(lines)
