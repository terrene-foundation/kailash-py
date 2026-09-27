# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests -- a ghost ``defining_role_address`` disabled monotonic tightening.

``GovernanceEngine.set_role_envelope`` validated the new envelope against the
DEFINING role's effective envelope, but only ``if defining_envelope is not
None``.  ``_compute_envelope_locked`` returns ``None`` for any address whose
accountability chain holds no envelope -- INCLUDING an address that does not
exist in the compiled organization at all.  Naming a non-existent role therefore
skipped the check entirely, and ``POST /envelopes`` passed the body field
straight through (the request schema validates D/T/R SHAPE only).

Measured on the unfixed tree (same engine, same wide envelope, overwriting an
already-governed role)::

    BASELINE verify_action(wire_transfer, $500k)          -> blocked
    CONTROL  overwrite, defining=<real role, $100 envelope>
             -> MonotonicTighteningError: child max_spend_usd (1000000.0)
                exceeds parent (100.0)
    ATTACK   overwrite, defining="D9-R9"                  -> ACCEPTED
    ATTACK   verify_action(wire_transfer, $500k)          -> auto_approved

Widening a LEAF is neutralised at compute time, because the effective envelope
intersects every ancestor envelope.  Overwriting the TOPMOST envelope in a
chain is not: nothing above it narrows the result.

THE DISCRIMINATOR IS EXISTENCE, NOT PRESENCE OF A PARENT ENVELOPE.  ``None`` is
also the legitimate state when a genuine ROOT envelope is created under a real
role that holds no envelope of its own, so failing closed on ``None`` would
break root-envelope creation.  The engine therefore resolves the defining
address through the SAME ``_resolve_role_address`` helper every other state
mutation uses, and refuses only when it names no node.

BOTH POLES ARE ASSERTED.  A deny-everything "fix" -- refusing whenever the
parent envelope is ``None`` -- fails
``test_root_envelope_creation_under_a_real_definer_still_succeeds`` and
``test_legitimate_tightening_under_a_real_definer_still_succeeds``.
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.compilation import RoleDefinition, compile_org
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    DepartmentConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    OrgDefinition,
    TeamConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import MonotonicTighteningError, RoleEnvelope
from kailash.trust.pact.exceptions import PactError

pytestmark = [pytest.mark.regression]

_WIRE = "wire_transfer"
_BIG = {"cost": 500_000.0}


def _org() -> OrgDefinition:
    return OrgDefinition(
        org_id="ghost-definer-org",
        name="Ghost Definer Org",
        departments=[
            DepartmentConfig(department_id="d-eng", name="Engineering"),
            DepartmentConfig(department_id="d-fin", name="Finance"),
        ],
        teams=[TeamConfig(id="t-backend", name="Backend", workspace="ws-backend")],
        roles=[
            RoleDefinition(
                role_id="r-vp",
                name="VP Engineering",
                reports_to_role_id=None,
                is_primary_for_unit="d-eng",
            ),
            RoleDefinition(
                role_id="r-lead",
                name="Lead Developer",
                reports_to_role_id="r-vp",
                is_primary_for_unit="t-backend",
            ),
            RoleDefinition(
                role_id="r-cfo",
                name="CFO",
                reports_to_role_id=None,
                is_primary_for_unit="d-fin",
            ),
        ],
    )


def _envelope(
    env_id: str, spend: float, actions: list[str]
) -> ConstraintEnvelopeConfig:
    return ConstraintEnvelopeConfig(
        id=env_id,
        financial=FinancialConstraintConfig(max_spend_usd=spend),
        operational=OperationalConstraintConfig(
            allowed_actions=actions, blocked_actions=[]
        ),
    )


@pytest.fixture
def governed() -> tuple[GovernanceEngine, str, str, str]:
    """Engine with a $100 CFO envelope and a $100 Lead envelope it defines.

    Returns ``(engine, vp_address, cfo_address, lead_address)``.  The Lead
    envelope is the TOPMOST envelope in the Lead's own chain (the VP holds
    none), so widening it is NOT neutralised by ancestor intersection -- which
    is what makes this the escalation shape rather than a no-op.
    """
    org = _org()
    compiled = compile_org(org)
    addresses = {node.name: addr for addr, node in compiled.nodes.items()}
    vp, cfo, lead = (
        addresses["VP Engineering"],
        addresses["CFO"],
        addresses["Lead Developer"],
    )

    engine = GovernanceEngine(compiled)
    # Root envelope for the CFO, defined by a REAL role that holds no envelope.
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-cfo",
            defining_role_address=vp,
            target_role_address=cfo,
            envelope=_envelope("env-cfo", 100.0, ["read"]),
        )
    )
    # The CFO (cross-branch definer) defines the Lead's envelope.
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-lead",
            defining_role_address=cfo,
            target_role_address=lead,
            envelope=_envelope("env-lead", 100.0, ["read"]),
        )
    )
    return engine, vp, cfo, lead


def _wide_overwrite(definer: str, target: str) -> RoleEnvelope:
    return RoleEnvelope(
        id="re-lead",
        defining_role_address=definer,
        target_role_address=target,
        envelope=_envelope("env-lead", 1_000_000.0, ["read", _WIRE]),
    )


# ===================================================================
# POLE 1 -- the attack is refused
# ===================================================================


def test_baseline_wide_action_is_blocked_before_any_overwrite(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """Known-answer control: the escalation target starts out blocked.

    Without this the attack assertions cannot discriminate -- a permanently
    blocked action would satisfy them for the wrong reason.
    """
    engine, _vp, _cfo, lead = governed
    assert engine.verify_action(lead, _WIRE, _BIG).level == "blocked"


@pytest.mark.parametrize(
    "ghost",
    ["D9-R9", "D9-R9-D4-R7"],
    ids=["flat-ghost", "nested-ghost"],
)
def test_ghost_defining_role_is_refused(
    governed: tuple[GovernanceEngine, str, str, str], ghost: str
) -> None:
    """THE BYPASS PROOF: a WELL-FORMED address naming no node must fail closed.

    Well-formed is what makes these discriminating.  ``Address.parse`` accepts
    them, the envelope store's prefix scan returns ``{}`` without raising, and
    the pre-fix engine therefore saw ``defining_envelope is None`` and skipped
    monotonic tightening outright.  Measured on the unfixed tree both raised
    nothing at all -- ``Failed: DID NOT RAISE PactError`` -- and the $1M
    envelope was persisted.
    """
    engine, _vp, _cfo, lead = governed
    with pytest.raises(PactError) as excinfo:
        engine.set_role_envelope(_wide_overwrite(ghost, lead))
    assert "defining role address" in str(excinfo.value).lower()


def test_case_variant_of_a_real_address_is_refused(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """A case variant of a REAL address is a ghost -- and a third bypass vector.

    ``AddressSegment.parse`` upper-cases the type char (addressing.py:101), so
    ``"d1-r2"`` parses to ``D1-R2``; the compiled-org node lookup is a plain
    case-sensitive dict key, so it resolves to nothing.  Measured pre-fix:
    ``Failed: DID NOT RAISE PactError``.
    """
    engine, _vp, cfo, lead = governed
    with pytest.raises(PactError) as excinfo:
        engine.set_role_envelope(_wide_overwrite(cfo.lower(), lead))
    assert "defining role address" in str(excinfo.value).lower()


@pytest.mark.parametrize(
    "malformed",
    ["HACKED", "org/dept/supervisor", "", "   "],
    ids=["non-address", "path-shaped", "empty", "whitespace"],
)
def test_malformed_defining_role_address_is_rejected_and_writes_nothing(
    governed: tuple[GovernanceEngine, str, str, str], malformed: str
) -> None:
    """CONTRACT test, NOT the bypass proof -- stated so it is not miscited.

    These four were ALREADY refused before the fix, but by ``Address.parse``
    deep inside ``_compute_envelope_locked``, as ``AddressError`` (a
    ``PactError`` subclass) carrying parser text such as ``Invalid node type
    'H' in segment 'HACKED'`` and ``Address string is empty``.  A bare
    ``pytest.raises(PactError)`` here is therefore GREEN on the unfixed tree
    and proves nothing about the escalation.

    What it does pin, and why it is worth keeping: malformed input must never
    write state, and after the fix the refusal comes from the resolver at the
    TOP of the method naming the offending FIELD, rather than incidentally from
    a parser several frames down that a future refactor could move.
    """
    engine, _vp, _cfo, lead = governed
    with pytest.raises(PactError) as excinfo:
        engine.set_role_envelope(_wide_overwrite(malformed, lead))
    assert "defining role address" in str(excinfo.value).lower()

    # The substantive assertion: the prior $100 envelope is still in force.
    assert engine.verify_action(lead, _WIRE, _BIG).level == "blocked"
    effective = engine.compute_envelope(lead)
    assert effective is not None
    assert effective.financial is not None
    assert effective.financial.max_spend_usd == 100.0


def test_ghost_defining_role_does_not_mutate_the_stored_envelope(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """Fail-closed means the refusal leaves the prior envelope in force."""
    engine, _vp, _cfo, lead = governed
    with pytest.raises(PactError):
        engine.set_role_envelope(_wide_overwrite("D9-R9", lead))

    assert engine.verify_action(lead, _WIRE, _BIG).level == "blocked"
    effective = engine.compute_envelope(lead)
    assert effective is not None
    assert effective.financial is not None
    assert effective.financial.max_spend_usd == 100.0


# ===================================================================
# POLE 2 -- every legitimate path still works
# ===================================================================


def test_root_envelope_creation_under_a_real_definer_still_succeeds(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """``defining_envelope is None`` is legitimate for a genuine root envelope.

    The ``governed`` fixture already exercises this (the CFO envelope is
    defined by a VP who holds none); this asserts it explicitly so a
    deny-on-None "fix" cannot pass.
    """
    engine, vp, _cfo, _lead = governed
    effective = engine.compute_envelope(_cfo_of(engine))
    assert effective is not None
    assert effective.financial is not None
    assert effective.financial.max_spend_usd == 100.0
    assert vp  # the definer is a real role that holds no envelope of its own


def _cfo_of(engine: GovernanceEngine) -> str:
    return {node.name: addr for addr, node in engine.get_org().nodes.items()}["CFO"]


def test_honest_definer_still_raises_monotonic_tightening(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """The pre-existing check must still fire -- and with its own error type.

    If the existence guard swallowed this case the attack test would pass for
    the wrong reason.
    """
    engine, _vp, cfo, lead = governed
    with pytest.raises(MonotonicTighteningError) as excinfo:
        engine.set_role_envelope(_wide_overwrite(cfo, lead))
    assert "max_spend_usd" in str(excinfo.value)


def test_legitimate_tightening_under_a_real_definer_still_succeeds(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """A narrower envelope from the real definer is still accepted."""
    engine, _vp, cfo, lead = governed
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-lead",
            defining_role_address=cfo,
            target_role_address=lead,
            envelope=_envelope("env-lead", 50.0, ["read"]),
        )
    )
    effective = engine.compute_envelope(lead)
    assert effective is not None
    assert effective.financial is not None
    assert effective.financial.max_spend_usd == 50.0


def test_config_role_id_definer_is_accepted_and_still_tightening_checked(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """A config role ID resolves to a real node -- accepted, and CHECKED.

    ``grant_clearance``/``revoke_clearance``/``transition_clearance`` all accept
    a config role ID, so ``set_role_envelope`` must too.  Pre-fix the raw ID was
    handed straight to ``_compute_envelope_locked``, where it died in
    ``Address.parse`` (``AddressError: Invalid segment: 'r'``) before any
    governance guard ran -- so this raised the WRONG exception type, not
    ``MonotonicTighteningError``.  Post-fix the resolver runs first, maps
    ``r-cfo`` to the CFO's positional address, and the widening is refused by
    the tightening gate it was always meant to hit.
    """
    engine, _vp, _cfo, lead = governed
    with pytest.raises(MonotonicTighteningError):
        engine.set_role_envelope(_wide_overwrite("r-cfo", lead))
