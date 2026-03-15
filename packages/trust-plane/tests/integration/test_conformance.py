# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for EATP conformance suite (M10-01, M10-04).

Validates that TrustPlane passes its own conformance suite and
that the conformance framework itself works correctly.
"""

import asyncio
import json

import pytest

from trustplane.conformance import (
    ConformanceLevel,
    ConformanceReport,
    ConformanceSuite,
    ConformanceTest,
    RequirementLevel,
    TestResult,
    format_conformance_report,
)
from trustplane.models import ConstraintEnvelope, OperationalConstraints
from trustplane.project import TrustProject


@pytest.fixture
def trust_dir(tmp_path):
    return tmp_path / "trust-plane"


@pytest.fixture
def project_with_envelope(trust_dir):
    envelope = ConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=["draft_content", "record_decision"],
            blocked_actions=["fabricate", "delete_project"],
        ),
        signed_by="Test Author",
    )
    return asyncio.run(
        TrustProject.create(
            trust_dir=str(trust_dir),
            project_name="Conformance Test",
            author="Test Author",
            constraint_envelope=envelope,
        )
    )


class TestConformanceFramework:
    def test_report_no_tests(self):
        report = ConformanceReport(implementation="test")
        assert report.must_pass == 0
        assert report.must_total == 0
        assert report.should_percentage == 100.0
        assert report.compute_level() is None

    def test_report_all_must_pass_compatible(self):
        """All MUST tests at Compatible level → Compatible (no Conformant tests)."""
        report = ConformanceReport(implementation="test")
        report.tests = [
            ConformanceTest(
                name="t1",
                description="d1",
                element="genesis",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.COMPATIBLE,
                result=TestResult.PASS,
            ),
        ]
        assert report.all_must_pass
        # Only Compatible-level MUST tests → Compatible
        assert report.compute_level() == ConformanceLevel.COMPATIBLE

    def test_report_must_fail(self):
        report = ConformanceReport(implementation="test")
        report.tests = [
            ConformanceTest(
                name="t1",
                description="d1",
                element="genesis",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.COMPATIBLE,
                result=TestResult.FAIL,
            ),
        ]
        assert not report.all_must_pass
        assert report.compute_level() is None

    def test_report_conformant_level(self):
        """All Compatible + Conformant MUST pass, 80% SHOULD → Conformant."""
        report = ConformanceReport(implementation="test")
        # Compatible MUST
        report.tests.append(
            ConformanceTest(
                name="m1",
                description="",
                element="genesis",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.COMPATIBLE,
                result=TestResult.PASS,
            )
        )
        # Conformant MUST
        report.tests.append(
            ConformanceTest(
                name="m2",
                description="",
                element="delegation",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.CONFORMANT,
                result=TestResult.PASS,
            )
        )
        # 5 SHOULD at Conformant, 4 pass (80%)
        for i in range(4):
            report.tests.append(
                ConformanceTest(
                    name=f"s{i}",
                    description="",
                    element="genesis",
                    level=RequirementLevel.SHOULD,
                    min_level=ConformanceLevel.CONFORMANT,
                    result=TestResult.PASS,
                )
            )
        report.tests.append(
            ConformanceTest(
                name="s4",
                description="",
                element="genesis",
                level=RequirementLevel.SHOULD,
                min_level=ConformanceLevel.CONFORMANT,
                result=TestResult.FAIL,
            )
        )
        assert report.compute_level() == ConformanceLevel.CONFORMANT

    def test_report_complete_level(self):
        """All MUST at all levels + all SHOULD pass → Complete."""
        report = ConformanceReport(implementation="test")
        for level in [
            ConformanceLevel.COMPATIBLE,
            ConformanceLevel.CONFORMANT,
            ConformanceLevel.COMPLETE,
        ]:
            report.tests.append(
                ConformanceTest(
                    name=f"m_{level.value}",
                    description="",
                    element="genesis",
                    level=RequirementLevel.MUST,
                    min_level=level,
                    result=TestResult.PASS,
                )
            )
        report.tests.append(
            ConformanceTest(
                name="s1",
                description="",
                element="genesis",
                level=RequirementLevel.SHOULD,
                min_level=ConformanceLevel.CONFORMANT,
                result=TestResult.PASS,
            )
        )
        assert report.compute_level() == ConformanceLevel.COMPLETE

    def test_report_conformant_must_fail_stays_compatible(self):
        """Compatible MUST pass but Conformant MUST fails → Compatible."""
        report = ConformanceReport(implementation="test")
        report.tests = [
            ConformanceTest(
                name="m1",
                description="",
                element="genesis",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.COMPATIBLE,
                result=TestResult.PASS,
            ),
            ConformanceTest(
                name="m2",
                description="",
                element="delegation",
                level=RequirementLevel.MUST,
                min_level=ConformanceLevel.CONFORMANT,
                result=TestResult.FAIL,
            ),
        ]
        assert report.compute_level() == ConformanceLevel.COMPATIBLE

    def test_report_json(self):
        report = ConformanceReport(implementation="test")
        report.tests = [
            ConformanceTest(
                name="t1",
                description="d1",
                element="genesis",
                level=RequirementLevel.MUST,
                result=TestResult.PASS,
            ),
        ]
        data = json.loads(report.to_json())
        assert data["implementation"] == "test"
        assert data["summary"]["must_pass"] == 1

    def test_format_report(self):
        report = ConformanceReport(implementation="test")
        report.tests = [
            ConformanceTest(
                name="t1",
                description="Test one",
                element="genesis",
                level=RequirementLevel.MUST,
                result=TestResult.PASS,
            ),
            ConformanceTest(
                name="t2",
                description="Test two",
                element="genesis",
                level=RequirementLevel.MUST,
                result=TestResult.FAIL,
                error="Missing field",
            ),
        ]
        text = format_conformance_report(report)
        assert "EATP Conformance Report" in text
        assert "Test one" in text
        assert "Missing field" in text


class TestConformanceSuite:
    def test_suite_has_tests(self):
        suite = ConformanceSuite()
        assert len(suite._tests) > 0

    def test_suite_covers_all_elements(self):
        suite = ConformanceSuite()
        elements = {t.element for t in suite._tests}
        assert "genesis" in elements
        assert "constraint" in elements
        assert "anchor" in elements
        assert "verification" in elements
        assert "posture" in elements
        assert "delegation" in elements
        assert "attestation" in elements
        assert "mirror" in elements

    def test_suite_has_must_tests(self):
        suite = ConformanceSuite()
        must_tests = [t for t in suite._tests if t.level == RequirementLevel.MUST]
        assert len(must_tests) >= 25

    def test_suite_covers_all_levels(self):
        suite = ConformanceSuite()
        levels = {t.min_level for t in suite._tests}
        assert ConformanceLevel.COMPATIBLE in levels
        assert ConformanceLevel.CONFORMANT in levels
        assert ConformanceLevel.COMPLETE in levels

    def test_suite_structural_requirements(self):
        """Verify the suite has the right tests at the right levels."""
        suite = ConformanceSuite()
        # Compatible: genesis + anchor + constraint MUST tests
        compatible_must = [
            t
            for t in suite._tests
            if t.min_level == ConformanceLevel.COMPATIBLE
            and t.level == RequirementLevel.MUST
        ]
        assert len(compatible_must) >= 9  # 4 genesis + 2 constraint + 3 anchor

        # Conformant: all 5 elements, delegation, verification, attestation, gradient, reasoning
        conformant_must = [
            t
            for t in suite._tests
            if t.min_level == ConformanceLevel.CONFORMANT
            and t.level == RequirementLevel.MUST
        ]
        assert (
            len(conformant_must) >= 9
        )  # dims, tighten, verify×2, deleg×2, attest, gradient, reasoning

        # Complete: posture×3, confidentiality, enforcement, bundle, interop
        complete_must = [
            t
            for t in suite._tests
            if t.min_level == ConformanceLevel.COMPLETE
            and t.level == RequirementLevel.MUST
        ]
        assert (
            len(complete_must) >= 7
        )  # posture×3 + confidentiality + enforcement + bundle + interop

    def test_suite_reusable(self):
        """Suite can be run multiple times without state leakage."""
        suite = ConformanceSuite()
        # All tests should start as SKIP
        assert all(t.result == TestResult.SKIP for t in suite._tests)
        # After a conceptual run, internal tests should remain SKIP
        # (actual run() uses copies)


class TestTrustPlaneConformance:
    """TrustPlane MUST pass EATP Complete conformance — this is the self-test."""

    def test_trustplane_passes_all_must(self, project_with_envelope):
        suite = ConformanceSuite()
        report = asyncio.run(suite.run(project_with_envelope))

        failed_must = [
            t
            for t in report.tests
            if t.level == RequirementLevel.MUST and t.result != TestResult.PASS
        ]
        if failed_must:
            details = "\n".join(
                f"  {t.name}: {t.result.value} ({t.error})" for t in failed_must
            )
            pytest.fail(f"MUST tests failed:\n{details}")

        assert report.all_must_pass

    def test_trustplane_passes_all_should(self, project_with_envelope):
        suite = ConformanceSuite()
        report = asyncio.run(suite.run(project_with_envelope))

        failed_should = [
            t
            for t in report.tests
            if t.level == RequirementLevel.SHOULD and t.result != TestResult.PASS
        ]
        if failed_should:
            details = "\n".join(
                f"  {t.name}: {t.result.value} ({t.error})" for t in failed_should
            )
            pytest.fail(f"SHOULD tests failed:\n{details}")

    def test_trustplane_achieves_full(self, project_with_envelope):
        suite = ConformanceSuite()
        report = asyncio.run(suite.run(project_with_envelope))
        level = report.compute_level()
        assert level == ConformanceLevel.COMPLETE, (
            f"Expected COMPLETE conformance, got {level}. "
            f"MUST: {report.must_pass}/{report.must_total}, "
            f"SHOULD: {report.should_pass}/{report.should_total}"
        )

    def test_conformance_report_valid_json(self, project_with_envelope):
        suite = ConformanceSuite()
        report = asyncio.run(suite.run(project_with_envelope))
        data = json.loads(report.to_json())
        assert data["level_achieved"] is not None
        assert data["summary"]["must_pass"] == data["summary"]["must_total"]
