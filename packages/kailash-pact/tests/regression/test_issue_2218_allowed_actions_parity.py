# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2218 -- ``allowed_actions`` enforcement-surface parity.

``operational.allowed_actions`` defaults to ``[]``, and the enforcement
surfaces disagreed about what that meant::

    action under test: 'delete_production_database'
    config                          gradient/agent    verify_action
    allowed_actions=[]  (default)   PERMIT            deny
    allowed_actions=['read']        deny              deny

Row 2 is the control -- with a non-empty allowlist the surfaces already agreed.
Row 1 was the defect: three of the four enforcement surfaces spelled the check
as ``if op.allowed_actions and action not in op.allowed_actions``, whose ``and``
short-circuits on the empty list and skips the check entirely. Removing every
entry from the allowlist therefore flipped a destructive action from denied to
permitted. The victim is the operator who tightened the allowlist to nothing.

The fix routes every surface through ONE shared restrictiveness model,
``kailash.trust.action_policy``, in which an empty (or unreadable) allowlist
ranks TIGHTEST and permits nothing -- ``security.md`` § Enforcement-Surface
Parity.

THE ASSERTION IS THE PARITY ITSELF. These tests do not merely check that each
surface is individually fail-closed; they feed the SAME ``allowed_actions``
input to EVERY surface and assert the verdicts are IDENTICAL. Without that,
the surfaces drift again.

Surfaces pinned here (each entered through its real public path, no mocking):
  1. ``GovernanceEngine.verify_action``       -- engine.py ``_evaluate_limit_proximity``
  2. ``GradientEngine.evaluate``              -- gradient.py ``_eval_operational``
  3. ``L3GovernedAgent.run``                  -- kaizen_agents governed_agent.py
  4. ``GovernanceEngine.create_bridge``       -- engine.py ``_validate_bridge_scope_locked``

Tightening validators reconciled onto the same reading:
  5. ``RoleEnvelope.validate_tightening``          -- pact/envelopes.py
  6. ``ConstraintEnvelope.is_tighter_than``        -- trust/envelope.py
  7. plane ``ConstraintEnvelope.is_tighter_than``  -- trust/plane/models.py
  8. ``ConstraintValidator``                       -- trust/constraint_validator.py

Acceptance criteria (issue #2218):
  1. An empty ``allowed_actions`` DENIES at every enforcement surface.
  2. A non-empty ``allowed_actions`` behaves identically at every surface
     (the control -- the fix must not change it).
  3. An absent operational dimension (``operational=None``) still means
     "not configured" and permits. Empty is NOT a synonym for absent. Note
     this state is only expressible on the trust-layer ``ConstraintEnvelope``:
     PACT's ``ConstraintEnvelopeConfig.operational`` is non-Optional, so it is
     asserted on the surface that can hold it, not across the parity table.
  4. Unrecognized / ``None`` action collections rank TIGHTEST, never widest --
     including the one-shot iterables and mappings that would otherwise turn
     into a silent permit.
  5. The tightening validators use the same reading: a parent whose allowlist
     permits nothing cannot have a child that permits something.
"""

from __future__ import annotations

from typing import Any

import pytest

from kailash.trust.action_policy import (
    action_permitted,
    allowed_actions_tightening_violation,
    evaluate_action,
    evaluate_scope,
    operational_view,
    permitted_action_set,
    scope_permitted,
)
from kailash.trust.constraint_validator import ConstraintValidator
from kailash.trust.envelope import ConstraintEnvelope, OperationalConstraint
from kailash.trust.pact.access import PactBridge
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import MonotonicTighteningError, RoleEnvelope
from kailash.trust.pact.exceptions import PactError
from kailash.trust.plane.models import ConstraintEnvelope as PlaneEnvelope
from kailash.trust.plane.models import OperationalConstraints as PlaneOperational

# Surface 3 of the parity this file asserts lives in kaizen_agents, which the
# "Test PACT" job deliberately does NOT install -- tests/unit/test_enforcement_modes.py
# in this same package asserts PactEngine's behaviour when kaizen-agents is
# ABSENT, so installing it there breaks five tests by construction. A bare
# module-scope import therefore errored the whole file at COLLECTION with
# `ModuleNotFoundError: No module named 'kaizen'`, which is how this gate came
# to be red rather than merely unrun.
#
# This skip is NOT the gate quietly opting out: the file is also run by
# test-kailash-kaizen.yml, in the environment that has all three surfaces
# installed, so the parity assertion genuinely executes on every PR. Without
# that second runner this would be a check that cannot fail, and the skip would
# be worse than the error it replaces.
pytest.importorskip(
    "kaizen_agents.governed_agent",
    reason=(
        "parity surface 3 needs kaizen-agents; this file is run for real by "
        "test-kailash-kaizen.yml, which installs it"
    ),
)

from kaizen.core.base_agent import BaseAgent  # noqa: E402
from kaizen.core.config import BaseAgentConfig  # noqa: E402
from kaizen_agents.governed_agent import (  # noqa: E402
    GovernanceRejectedError,
    L3GovernedAgent,
)
from pact.examples.university.org import create_university_org  # noqa: E402

# The university org's CS Chair, and the Dean who defines its envelope.
CS_CHAIR = "D1-R1-D1-R1-D1-R1-T1-R1"
DEAN = "D1-R1-D1-R1-D1-R1"
# A bridge peer in a different sub-tree, with no envelope of its own, and the
# lowest common ancestor that must approve the bridge.
BRIDGE_PEER = "D1-R1-D3-R1"
BRIDGE_LCA = "D1-R1"

DESTRUCTIVE = "delete_production_database"


class _StubAgent(BaseAgent):
    """Minimal real agent so ``L3GovernedAgent.run()`` can be exercised end-to-end."""

    def run(self, **inputs: Any) -> dict[str, Any]:
        return {"answer": "executed"}

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        return {"answer": "executed-async"}


def _stub_agent() -> _StubAgent:
    return _StubAgent(config=BaseAgentConfig(), mcp_servers=[])


# ---------------------------------------------------------------------------
# The four enforcement surfaces, each entered through its real public path.
# Every probe returns a plain bool so the verdicts are directly comparable.
# ---------------------------------------------------------------------------


def _surface_verify_action(allowed: list[str], action: str) -> bool:
    """Surface 1: ``GovernanceEngine.verify_action``."""
    compiled, _ = create_university_org()
    engine = GovernanceEngine(compiled)
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-2218",
            defining_role_address=DEAN,
            target_role_address=CS_CHAIR,
            envelope=_pact_envelope(allowed),
        )
    )
    verdict = engine.verify_action(
        role_address=CS_CHAIR, action=action, context={"cost": 1.0}
    )
    return bool(verdict.allowed)


def _surface_gradient(allowed: list[str], action: str) -> bool:
    """Surface 2: ``GradientEngine.evaluate``."""
    from kailash.trust.pact.gradient import GradientEngine

    result = GradientEngine(_pact_envelope(allowed)).evaluate(action, {})
    operational = [d for d in result.dimensions if d.dimension.value == "operational"]
    assert len(operational) == 1, "expected exactly one operational dimension result"
    return bool(operational[0].satisfied)


def _surface_governed_agent(allowed: list[str], action: str) -> bool:
    """Surface 3: ``L3GovernedAgent.run`` -- the agent's own execution path."""
    envelope = ConstraintEnvelope(
        operational=OperationalConstraint(allowed_actions=tuple(allowed))
    )
    governed = L3GovernedAgent(_stub_agent(), envelope=envelope, mcp_servers=[])
    try:
        governed.run(_action=action)
    except GovernanceRejectedError:
        return False
    return True


def _surface_bridge_scope(allowed: list[str], action: str) -> bool:
    """Surface 4: ``GovernanceEngine.create_bridge`` -> ``_validate_bridge_scope_locked``.

    A bridge whose ``operational_scope`` names ``action`` may only be created
    when its endpoint roles are themselves permitted to perform it.

    The probe DISCRIMINATES: ``create_bridge`` can raise ``PactError`` for
    several unrelated reasons (unparseable address, no LCA, missing approval).
    Only a scope rejection counts as a denial here; any other ``PactError``
    is re-raised so a broken fixture can never masquerade as a fail-closed
    verdict.
    """
    compiled, _ = create_university_org()
    engine = GovernanceEngine(compiled)
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-2218-bridge",
            defining_role_address=DEAN,
            target_role_address=CS_CHAIR,
            envelope=_pact_envelope(allowed),
        )
    )
    # BRIDGE_PEER holds no envelope, so only CS_CHAIR's allowlist is in play.
    engine.approve_bridge(CS_CHAIR, BRIDGE_PEER, BRIDGE_LCA)
    bridge = PactBridge(
        id="bridge-2218",
        role_a_address=CS_CHAIR,
        role_b_address=BRIDGE_PEER,
        bridge_type="scoped",
        max_classification=ConfidentialityLevel.PUBLIC,
        operational_scope=(action,),
    )
    try:
        engine.create_bridge(bridge)
    except PactError as exc:
        if "operational_scope rejected" not in str(exc):
            raise
        return False
    return True


def _pact_envelope(allowed: list[str]) -> ConstraintEnvelopeConfig:
    """Build the PACT-side envelope carrying ``allowed`` as its allowlist."""
    return ConstraintEnvelopeConfig(
        id="env-2218",
        description="issue 2218 parity envelope",
        financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        operational=OperationalConstraintConfig(allowed_actions=list(allowed)),
    )


ENFORCEMENT_SURFACES = {
    "verify_action": _surface_verify_action,
    "gradient": _surface_gradient,
    "governed_agent": _surface_governed_agent,
    "bridge_scope": _surface_bridge_scope,
}


def _all_surface_verdicts(allowed: list[str], action: str) -> dict[str, bool]:
    return {
        name: probe(allowed, action) for name, probe in ENFORCEMENT_SURFACES.items()
    }


# ---------------------------------------------------------------------------
# AC1 + AC2 + AC3: the parity table. The assertion IS the parity.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "allowed", "action", "expected"),
    [
        # AC1 -- the defect. The empty allowlist permits NOTHING, everywhere.
        ("empty allowlist, destructive action", [], DESTRUCTIVE, False),
        ("empty allowlist, benign action", [], "read", False),
        # AC2 -- the control. A non-empty allowlist is unchanged by the fix.
        ("named allowlist, listed action", ["read"], "read", True),
        ("named allowlist, unlisted action", ["read"], DESTRUCTIVE, False),
    ],
)
class TestEnforcementSurfaceParity:
    """The same input MUST produce the same verdict at every enforcement surface."""

    def test_all_surfaces_agree(
        self,
        case: str,
        allowed: list[str],
        action: str,
        expected: bool,
    ) -> None:
        verdicts = _all_surface_verdicts(allowed, action)
        distinct = set(verdicts.values())
        assert len(distinct) == 1, (
            f"{case}: enforcement surfaces DISAGREE on allowed_actions="
            f"{allowed!r} action={action!r} -- {verdicts}"
        )

    def test_all_surfaces_agree_on_the_fail_closed_verdict(
        self,
        case: str,
        allowed: list[str],
        action: str,
        expected: bool,
    ) -> None:
        verdicts = _all_surface_verdicts(allowed, action)
        assert verdicts == dict.fromkeys(ENFORCEMENT_SURFACES, expected), (
            f"{case}: expected every surface to return {expected} for "
            f"allowed_actions={allowed!r} action={action!r} -- got {verdicts}"
        )


class TestEmptyIsNotAbsent:
    """AC3: an empty allowlist and an ABSENT dimension are DIFFERENT states.

    Collapsing them is precisely how the fail-open surfaces got their answer:
    they read "empty" as "nobody configured this, so allow everything".

    Which surfaces can even express "absent" is itself pinned here. PACT's
    ``ConstraintEnvelopeConfig.operational`` is NOT optional -- it carries a
    ``default_factory``, so a PACT envelope ALWAYS has an operational
    dimension, and a default-constructed one permits nothing. Only the
    trust-layer ``ConstraintEnvelope`` (the type ``L3GovernedAgent`` consumes)
    can hold ``operational=None``.
    """

    def test_pact_envelope_cannot_express_an_absent_dimension(self) -> None:
        # The state is unconstructible, which is why the parity table above
        # does not contain it. If this ever starts passing None through, the
        # parity table MUST grow an absent-dimension row.
        with pytest.raises(Exception) as excinfo:
            ConstraintEnvelopeConfig(id="e", operational=None)  # type: ignore[arg-type]
        assert "operational" in str(excinfo.value)

    def test_default_pact_envelope_permits_nothing(self) -> None:
        # The field default IS the empty allowlist -- the issue's central point.
        assert ConstraintEnvelopeConfig(id="e").operational.allowed_actions == []
        assert (
            permitted_action_set(ConstraintEnvelopeConfig(id="e").operational)
            == frozenset()
        )

    def test_absent_dimension_permits_where_empty_denies(self) -> None:
        # Exercised on the one surface that can hold the absent state, through
        # its real run() path.
        absent = L3GovernedAgent(
            _stub_agent(),
            envelope=ConstraintEnvelope(operational=None),
            mcp_servers=[],
        )
        assert absent.run(_action=DESTRUCTIVE)["answer"] == "executed"
        assert _surface_governed_agent([], DESTRUCTIVE) is False

    def test_permitted_set_distinguishes_them(self) -> None:
        # None -> "not configured" (widest). Empty frozenset -> "permits nothing".
        assert permitted_action_set(None) is None
        assert permitted_action_set(OperationalConstraintConfig()) == frozenset()


# ---------------------------------------------------------------------------
# AC4: unrecognized / None collections rank TIGHTEST.
# ---------------------------------------------------------------------------


class TestUnrecognizedRanksTightest:
    def test_none_allowlist_on_a_present_dimension_permits_nothing(self) -> None:
        # The trust-layer dataclass accepts None; it must NOT read as "widest".
        op = OperationalConstraint(allowed_actions=None)  # type: ignore[arg-type]
        assert action_permitted(op, DESTRUCTIVE) is False
        assert permitted_action_set(op) == frozenset()

    def test_pydantic_config_rejects_a_none_allowlist_outright(self) -> None:
        # The PACT config type refuses to construct the ambiguous state at all,
        # which is the strongest form of fail-closed: it never reaches a surface.
        with pytest.raises(Exception) as excinfo:
            OperationalConstraintConfig(allowed_actions=None)  # type: ignore[arg-type]
        assert "allowed_actions" in str(excinfo.value)

    @pytest.mark.parametrize(
        "malformed",
        [
            "read",  # a bare string iterates into characters
            b"read",  # bytes iterate into ints
            bytearray(b"read"),
            123,  # not a collection at all
            ["read", 7],  # a non-string member
            {"read": True},  # a mapping iterates its KEYS
            {"transfer_funds": False},  # ... so a DISABLED entry would ALLOW
        ],
    )
    def test_malformed_allowlist_permits_nothing(self, malformed: Any) -> None:
        op = operational_view(allowed=malformed)
        verdict = evaluate_action(op, "read")
        assert verdict.permitted is False
        assert verdict.rule == "malformed"
        assert permitted_action_set(op) == frozenset()

    def test_a_disabled_mapping_entry_never_becomes_an_allow(self) -> None:
        # A mapping iterates its keys, so {"transfer_funds": False} would
        # normalize to an allowlist CONTAINING "transfer_funds" -- a disabled
        # entry silently becoming a grant. It must fail closed instead.
        op = operational_view(allowed={"transfer_funds": False})
        assert action_permitted(op, "transfer_funds") is False

    def test_one_shot_iterables_are_refused_rather_than_consumed(self) -> None:
        # A generator satisfies Iterable but is ONE-SHOT. The bridge validator
        # normalizes the SAME requested scope once per endpoint role, so a
        # generator would be exhausted by the first endpoint and read as EMPTY
        # by the second -- which evaluate_scope would treat as "no scope
        # requested" and PERMIT, silently skipping that endpoint's check.
        op = OperationalConstraintConfig(allowed_actions=["read"])
        gen = (a for a in ["read"])
        first = evaluate_scope(op, gen)
        second = evaluate_scope(op, gen)
        # Refused by type on BOTH reads -- never permitted, never divergent.
        assert first.permitted is False and first.rule == "malformed"
        assert second.permitted is False and second.rule == "malformed"

    def test_a_generator_allowlist_permits_nothing(self) -> None:
        op = operational_view(allowed=(a for a in ["read"]))
        assert action_permitted(op, "read") is False
        assert permitted_action_set(op) == frozenset()

    def test_none_dimension_still_means_unconfigured(self) -> None:
        assert action_permitted(None, DESTRUCTIVE) is True
        assert scope_permitted(None, [DESTRUCTIVE]) is True


class TestDenyWins:
    """The blocklist is unconditional and is consulted before the allowlist."""

    def test_blocked_beats_allowed(self) -> None:
        op = OperationalConstraintConfig(
            allowed_actions=["deploy"], blocked_actions=["deploy"]
        )
        verdict = evaluate_action(op, "deploy")
        assert verdict.permitted is False
        assert verdict.rule == "blocked-list"

    def test_blocked_scope_beats_allowed_scope(self) -> None:
        op = OperationalConstraintConfig(
            allowed_actions=["deploy", "read"], blocked_actions=["deploy"]
        )
        assert scope_permitted(op, ["read"]) is True
        assert scope_permitted(op, ["deploy"]) is False


# ---------------------------------------------------------------------------
# AC5: the tightening validators read allowed_actions the SAME way.
# ---------------------------------------------------------------------------


def _tightening_verdicts(
    parent_allowed: list[str], child_allowed: list[str]
) -> dict[str, bool]:
    """Return ``{surface: child_is_tighter_or_equal}`` for every tightening surface."""
    verdicts: dict[str, bool] = {}

    # 5. RoleEnvelope.validate_tightening (raises on a widening). The catch is
    # narrowed to the widening error: any other exception is a broken fixture
    # and must surface, not be scored as a fail-closed verdict.
    try:
        RoleEnvelope.validate_tightening(
            parent_envelope=_pact_envelope(parent_allowed),
            child_envelope=_pact_envelope(child_allowed),
        )
        verdicts["role_envelope"] = True
    except MonotonicTighteningError as exc:
        assert "allowed_actions" in str(
            exc
        ), f"validate_tightening rejected for an unrelated dimension: {exc}"
        verdicts["role_envelope"] = False

    # 6. ConstraintEnvelope.is_tighter_than (trust layer).
    parent_env = ConstraintEnvelope(
        operational=OperationalConstraint(allowed_actions=tuple(parent_allowed))
    )
    child_env = ConstraintEnvelope(
        operational=OperationalConstraint(allowed_actions=tuple(child_allowed))
    )
    verdicts["is_tighter_than"] = child_env.is_tighter_than(parent_env)

    # 7. plane models is_tighter_than.
    verdicts["plane_is_tighter_than"] = PlaneEnvelope(
        operational=PlaneOperational(allowed_actions=list(child_allowed))
    ).is_tighter_than(
        PlaneEnvelope(
            operational=PlaneOperational(allowed_actions=list(parent_allowed))
        )
    )

    # 8. EATP dict-based ConstraintValidator.
    verdicts["constraint_validator"] = (
        ConstraintValidator()
        .validate_tightening(
            {"allowed_actions": list(parent_allowed)},
            {"allowed_actions": list(child_allowed)},
        )
        .valid
    )

    # The shared predicate itself.
    verdicts["shared_predicate"] = (
        allowed_actions_tightening_violation(
            operational_view(allowed=parent_allowed),
            operational_view(allowed=child_allowed),
        )
        is None
    )
    return verdicts


@pytest.mark.parametrize(
    ("case", "parent", "child", "expected"),
    [
        # The defect's tightening twin: a parent permitting NOTHING cannot have
        # a child permitting SOMETHING. Previously several surfaces read the
        # empty parent as "widest" and waved the child through.
        ("empty parent, non-empty child WIDENS", [], ["read"], False),
        # An empty child permits nothing, so it always fits.
        ("empty child is the tightest child", ["read", "write"], [], True),
        # Neither side constrains actions -- the overwhelmingly common case.
        ("both empty", [], [], True),
        # Ordinary subset / superset.
        ("proper subset tightens", ["read", "write"], ["read"], True),
        ("added action widens", ["read"], ["read", "write"], False),
        ("identical is tighter-or-equal", ["read"], ["read"], True),
    ],
)
class TestTighteningSurfaceParity:
    def test_all_tightening_surfaces_agree(
        self, case: str, parent: list[str], child: list[str], expected: bool
    ) -> None:
        verdicts = _tightening_verdicts(parent, child)
        assert len(set(verdicts.values())) == 1, (
            f"{case}: tightening surfaces DISAGREE for parent={parent!r} "
            f"child={child!r} -- {verdicts}"
        )

    def test_all_tightening_surfaces_agree_on_the_fail_closed_verdict(
        self, case: str, parent: list[str], child: list[str], expected: bool
    ) -> None:
        verdicts = _tightening_verdicts(parent, child)
        assert verdicts == dict.fromkeys(verdicts, expected), (
            f"{case}: expected every tightening surface to return {expected} "
            f"for parent={parent!r} child={child!r} -- got {verdicts}"
        )


class TestTighteningMatchesEnforcement:
    """A configuration that REGISTERS must not then be evaluated more widely.

    This is the cross-layer invariant the split broke: registration and
    evaluation must read ``allowed_actions`` through the same model.
    """

    def test_a_child_that_registers_permits_only_what_the_parent_permits(
        self,
    ) -> None:
        parent, child = ["read", "write"], ["read"]
        assert _tightening_verdicts(parent, child)["shared_predicate"] is True
        # Everything the registered child permits, the parent also permits.
        child_permitted = permitted_action_set(
            OperationalConstraintConfig(allowed_actions=child)
        )
        parent_permitted = permitted_action_set(
            OperationalConstraintConfig(allowed_actions=parent)
        )
        assert child_permitted is not None and parent_permitted is not None
        assert child_permitted <= parent_permitted

    def test_a_parent_that_permits_nothing_admits_no_child_action(self) -> None:
        assert _all_surface_verdicts([], "read") == dict.fromkeys(
            ENFORCEMENT_SURFACES, False
        )
        assert _tightening_verdicts([], ["read"])["shared_predicate"] is False


class TestChildDroppingTheDimensionIsAWidening:
    def test_dropping_the_operational_dimension_widens(self) -> None:
        violation = allowed_actions_tightening_violation(
            OperationalConstraintConfig(allowed_actions=["read"]), None
        )
        assert violation is not None
        assert "drops the operational dimension" in violation

    def test_parent_without_the_dimension_constrains_nothing(self) -> None:
        assert (
            allowed_actions_tightening_violation(
                None, OperationalConstraintConfig(allowed_actions=["read"])
            )
            is None
        )

    # NOTE, deliberately untested: the org-load tightening validators in
    # `pact/config.py` call the shared predicate UNGUARDED, so its
    # drop-the-dimension branch stays reachable. That branch cannot be
    # exercised behaviourally today because
    # `ConstraintEnvelopeConfig.operational` is non-Optional (default_factory),
    # so no constructible org can drop the dimension. A source-scraping test
    # would assert on text rather than behaviour and would report `pass` for
    # inputs it cannot observe, so none is written here. The branch itself IS
    # covered above, through the predicate's own interface.
