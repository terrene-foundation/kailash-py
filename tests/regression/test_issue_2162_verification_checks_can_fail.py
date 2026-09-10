# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2162 -- conformance MUSTs that could not fail.

``_test_verification_standard`` and ``_test_verification_quick`` were
structurally incapable of returning ``False``:

* ``_test_verification_quick``    -- ``return "verification_level" in report``
* ``_test_verification_standard`` -- ``report.get("chain_valid") is not None
  and report.get("total_decisions", -1) >= 0``

``_verify_locked`` has exactly one ``return`` and it is an unconditional dict
literal that always carries both keys, so neither check could go red for any
input. ``is not None`` is True *when ``chain_valid`` is ``False``* -- so the
CONFORMANT-level MUST passed a project whose chain the same report marked
broken.

A check that cannot return False is not a weak test, it is a NON-INSTRUMENT:
its output carries no information and every conformance report citing it cites
nothing.

Discrimination (``rules/instrument-discipline.md`` MUST-1): each test here is
BIPOLAR -- the broken-input case is paired with an intact-input case asserting
the SAME check returns True. A check that had been "fixed" by hard-wiring
``return False`` would pass the failure pole and fail the success pole, so
these tests distinguish "now correct" from "now always False". Both poles must
hold for the pair to mean anything.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from kailash.trust.plane.conformance import (
    ConformanceLevel,
    ConformanceSuite,
    RequirementLevel,
    TestResult,
)
from kailash.trust.plane.models import (
    ConstraintEnvelope,
    DecisionRecord,
    OperationalConstraints,
)
from kailash.trust.plane.project import TrustProject


def _make_project(trust_dir) -> TrustProject:
    envelope = ConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=["draft_content", "record_decision"],
            blocked_actions=["fabricate", "delete_project"],
        ),
        signed_by="Regression 2162",
    )
    project = asyncio.run(
        TrustProject.create(
            trust_dir=str(trust_dir),
            project_name="Issue 2162",
            author="Regression 2162",
            constraint_envelope=envelope,
        )
    )
    # One decision -> one anchor file, so there is a chain to break.
    asyncio.run(
        project.record_decision(
            DecisionRecord(
                decision_type="record_decision",
                decision="Seed the anchor chain",
                rationale="A chain needs at least one anchor to be breakable",
            )
        )
    )
    return project


def _break_anchor_chain(project: TrustProject) -> None:
    """Point the newest anchor at a parent that is not its predecessor.

    This is exactly the corruption ``_verify_locked``'s linkage walk exists to
    detect; it sets ``chain_valid`` to False without touching any other field.
    """
    anchor_files = sorted((project._dir / "anchors").glob("*.json"))
    assert anchor_files, "fixture must produce at least one anchor file"
    newest = anchor_files[-1]
    data = json.loads(newest.read_text())
    data["parent_anchor_id"] = "aud-00000000-dead-beef-0000-000000000000"
    newest.write_text(json.dumps(data))


@pytest.fixture
def project(tmp_path):
    return _make_project(tmp_path / "trust-plane")


class TestVerificationStandardFailsClosed:
    """The MUST at CONFORMANT level must go red on a broken chain."""

    def test_intact_chain_passes(self, project):
        """Success pole -- without this the failure pole proves nothing."""
        report = asyncio.run(project.verify())
        assert report["chain_valid"] is True, "fixture chain must start intact"

        suite = ConformanceSuite()
        assert asyncio.run(suite._test_verification_standard(project)) is True

    def test_broken_chain_fails(self, project):
        """Failure pole -- the exact input the old body passed."""
        _break_anchor_chain(project)

        report = asyncio.run(project.verify())
        assert report["chain_valid"] is False, "corruption must break the chain"
        # The old body's predicate, asserted explicitly: it is True on this
        # very input, which is why the MUST could not catch it.
        assert (report.get("chain_valid") is not None) is True

        suite = ConformanceSuite()
        assert asyncio.run(suite._test_verification_standard(project)) is False

    def test_broken_chain_fails_the_must_in_a_full_suite_run(self, project):
        """The failure must surface as a FAILED MUST, not just a False return."""
        _break_anchor_chain(project)

        suite = ConformanceSuite()
        report = asyncio.run(suite.run(project))
        by_name = {t.name: t for t in report.tests}

        standard = by_name["verification_standard"]
        assert standard.level is RequirementLevel.MUST
        assert standard.min_level is ConformanceLevel.CONFORMANT
        assert standard.result is TestResult.FAIL, (
            "verification_standard must FAIL (not ERROR/PASS) on a broken chain; "
            f"got {standard.result.value} ({standard.error})"
        )
        assert report.all_must_pass is False

    def test_intact_chain_passes_the_must_in_a_full_suite_run(self, project):
        """Success pole for the suite-level assertion above."""
        suite = ConformanceSuite()
        report = asyncio.run(suite.run(project))
        by_name = {t.name: t for t in report.tests}
        assert by_name["verification_standard"].result is TestResult.PASS
        assert report.all_must_pass is True

    def test_missing_envelope_fails(self, tmp_path):
        """Constraint half of the description: no envelope -> no pass."""
        project = asyncio.run(
            TrustProject.create(
                trust_dir=str(tmp_path / "trust-plane"),
                project_name="Issue 2162 no envelope",
                author="Regression 2162",
            )
        )
        assert project.constraint_envelope is None
        suite = ConformanceSuite()
        assert asyncio.run(suite._test_verification_standard(project)) is False

    def test_unenforced_blocked_action_fails(self, project, monkeypatch):
        """Capability half: a gate that stops refusing blocked actions fails."""
        from kailash.trust.enforce.strict import Verdict

        suite = ConformanceSuite()
        # Control: the unpatched gate passes (success pole).
        assert asyncio.run(suite._test_verification_standard(project)) is True

        # Prove the mutation reaches the code under test before reading the
        # result (``instrument-discipline`` MUST-2(b)): check() must actually
        # stop returning BLOCKED for a blocked action.
        monkeypatch.setattr(
            type(project),
            "check",
            lambda self, action, context=None: Verdict.AUTO_APPROVED,
        )
        blocked = project.constraint_envelope.operational.blocked_actions[0]
        assert project.check(blocked) is Verdict.AUTO_APPROVED, (
            "mutation did not reach check(); a non-red result below would be "
            "an inert mutation, not a vacuous test"
        )

        assert asyncio.run(suite._test_verification_standard(project)) is False


class TestVerificationQuickAssertsValues:
    """The SHOULD must assert report *values*, not key presence."""

    def test_wellformed_report_passes(self, project):
        """Success pole."""
        suite = ConformanceSuite()
        assert asyncio.run(suite._test_verification_quick(project)) is True

    @pytest.mark.parametrize(
        "mutation, why",
        [
            ({"verification_level": "NOT_A_LEVEL"}, "level outside the gradient"),
            ({"verification_level": None}, "level absent"),
            ({"project_id": "proj-someone-elses"}, "report bound to another project"),
            ({"verified_at": "not-a-timestamp"}, "unparseable verification time"),
            ({"verified_at": None}, "verification time absent"),
        ],
    )
    def test_malformed_report_fails(self, project, monkeypatch, mutation, why):
        """Failure poles -- each one the old key-presence body accepted."""
        real_verify = project.verify

        async def mutated_verify(*args, **kwargs):
            report = await real_verify(*args, **kwargs)
            for key, value in mutation.items():
                if value is None:
                    report.pop(key, None)
                else:
                    report[key] = value
            return report

        monkeypatch.setattr(project, "verify", mutated_verify)

        # The mutation reaches the code under test: the report really is
        # malformed (MUST-2(b) -- distinguishes a vacuous check from an
        # inert mutation).
        produced = asyncio.run(project.verify())
        for key, value in mutation.items():
            if value is None:
                assert key not in produced, f"mutation did not remove {key}"
            else:
                assert produced[key] == value, f"mutation did not set {key}"
        # The old body's predicate on this same input, asserted explicitly.
        if "verification_level" not in mutation or mutation["verification_level"]:
            assert ("verification_level" in produced) is True

        suite = ConformanceSuite()
        assert asyncio.run(suite._test_verification_quick(project)) is False, why
