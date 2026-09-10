# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
A2A authorization regression tests.

Authentication established WHO is calling; nothing established WHAT they could
do. An adversarial review measured `caller.agent_id` and `caller.claims` at zero
occurrences in any authorization check, so `audit.query` and `agent.invoke` took
their target from `params`, and `trust.delegate` delegated the SERVING agent's
authority to a caller-chosen delegatee.

The load-bearing property here is that every refusal path FAILS CLOSED against
three separately-measured fail-OPEN behaviours in the surrounding code:

1. PACT treats a `None` envelope as "no constraints — permitted".
2. `AgentRoleMapping.resolve()` passes unknown ids through as role addresses.
3. An A2A service with no governance org would otherwise authorize nothing and
   allow everything.

Each is exercised below with BOTH poles, because a test suite that only ever
refuses cannot distinguish "fails closed" from "broken shut".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pytest

from kailash.trust.a2a.auth import CallerIdentity
from kailash.trust.a2a.authorization import A2AAuthorizer
from kailash.trust.a2a.exceptions import AuthorizationError
from kailash.trust.a2a.models import A2AToken

CALLER = "agent-caller"
CALLER_ROLE = "D1.T2.R3"
SUBJECT = "agent-subject"
SUBJECT_ROLE = "D1.T2.R9"


def _caller(agent_id: str = CALLER) -> CallerIdentity:
    now = datetime.now(timezone.utc)
    claims = A2AToken(
        sub=agent_id,
        iss=agent_id,
        aud="agent-under-test",
        exp=now + timedelta(hours=1),
        iat=now,
        jti="jti-1",
        authority_id="org-001",
        trust_chain_hash="chainhash",
        capabilities=["analyze"],
    )
    return CallerIdentity(agent_id=agent_id, claims=claims, token="tok")


class Verdict:
    """Stands in for PACT's GovernanceVerdict (the fields the adapter reads)."""

    def __init__(
        self, level: str, envelope: Optional[Dict[str, Any]], reason: str = ""
    ):
        self.level = level
        self.effective_envelope_snapshot = envelope
        self.reason = reason


class Decision:
    """Stands in for PACT's AccessDecision."""

    def __init__(self, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason


class FakeEngine:
    """Deterministic governance engine.

    Not a mock of PACT — a Protocol-satisfying adapter with fixed rules, per
    `testing.md` § Protocol Adapters. The real engine is exercised by the PACT
    suite; what is under test HERE is how this adapter reacts to each verdict
    shape, including the permissive one.
    """

    def __init__(self, verdict: Verdict, decision: Decision):
        self._verdict = verdict
        self._decision = decision
        self.verify_calls: list = []
        self.access_calls: list = []

    def verify_action(self, role_address, action, context=None):
        self.verify_calls.append((role_address, action, context))
        return self._verdict

    def check_access(self, role_address, knowledge_item, posture):
        self.access_calls.append((role_address, knowledge_item, posture))
        return self._decision


class FakeRoles:
    """Agent→role mapping. Exposes get_address ONLY — no resolve()."""

    def __init__(self, mapping: Dict[str, str]):
        self._m = dict(mapping)

    def get_address(self, agent_id: str) -> Optional[str]:
        return self._m.get(agent_id)


GOVERNED = {"allowed_actions": ["trust.delegate", "agent.invoke"]}


def _authorizer(
    *,
    level: str = "auto_approved",
    envelope: Optional[Dict[str, Any]] = None,
    allowed: bool = True,
    roles: Optional[Dict[str, str]] = None,
) -> A2AAuthorizer:
    return A2AAuthorizer(
        governance_engine=FakeEngine(
            Verdict(level, GOVERNED if envelope is None else envelope),
            Decision(allowed),
        ),
        role_mapping=FakeRoles(
            roles if roles is not None else {CALLER: CALLER_ROLE, SUBJECT: SUBJECT_ROLE}
        ),
        posture=object(),
    )


# --------------------------------------------------------------------------
# The permissive-envelope fail-open (measured in PACT)
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_absent_envelope_is_refused_not_treated_as_approval():
    """A `None` envelope means PACT evaluated no constraints.

    PACT returns `auto_approved` with no envelope configured — measured, with a
    control showing the same engine returns `blocked` once an envelope exists.
    So this verdict is a NON-ANSWER and must not authorize anything.
    """
    authz = A2AAuthorizer(
        governance_engine=FakeEngine(Verdict("auto_approved", None), Decision(True)),
        role_mapping=FakeRoles({CALLER: CALLER_ROLE}),
        posture=object(),
    )
    with pytest.raises(AuthorizationError) as exc:
        authz.require_action(_caller(), "trust.delegate")
    assert "no governance envelope" in str(exc.value)


def test_governed_envelope_with_approval_is_permitted():
    """Negative control: with an envelope in effect, the same call proceeds.

    Without this the test above would pass against an adapter that refuses
    unconditionally.
    """
    authz = _authorizer()
    assert authz.require_action(_caller(), "trust.delegate") == CALLER_ROLE


# --------------------------------------------------------------------------
# Verdict levels — positive allowlist
# --------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["blocked", "flagged", "held", "", "APPROVED", "ok"])
def test_only_auto_approved_permits(level):
    """Anything outside the allowlist is refused, including unknown levels.

    A deny-list would admit any level PACT gains later.
    """
    authz = _authorizer(level=level)
    with pytest.raises(AuthorizationError):
        authz.require_action(_caller(), "trust.delegate")


# --------------------------------------------------------------------------
# Unmapped agents (the resolve() passthrough this adapter refuses to use)
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_unmapped_caller_is_refused():
    authz = _authorizer(roles={})
    with pytest.raises(AuthorizationError) as exc:
        authz.require_action(_caller(), "trust.delegate")
    assert "not mapped" in str(exc.value)


@pytest.mark.regression
def test_role_address_shaped_agent_id_is_not_passed_through():
    """`resolve()` would pass this through; `get_address()` returns None.

    Measured on the real mapping: `resolve('agent-002-Rogue')` returns the
    string unchanged, because the passthrough branch tests only whether the id
    contains a D, T or R.
    """
    authz = _authorizer(roles={CALLER: CALLER_ROLE})
    with pytest.raises(AuthorizationError):
        authz.require_action(_caller("agent-002-Rogue"), "trust.delegate")


def test_unmapped_audit_subject_is_refused():
    authz = _authorizer(roles={CALLER: CALLER_ROLE})
    with pytest.raises(AuthorizationError):
        authz.require_audit_access(_caller(), "nobody-knows-this-agent")


# --------------------------------------------------------------------------
# audit.query — routed to PACT containment, not hardcoded equality
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_audit_access_denial_is_refused():
    authz = _authorizer(allowed=False)
    with pytest.raises(AuthorizationError) as exc:
        authz.require_audit_access(_caller(), SUBJECT)
    assert "audit access denied" in str(exc.value)


def test_audit_access_grant_is_permitted():
    """Negative control for the denial test."""
    authz = _authorizer(allowed=True)
    authz.require_audit_access(_caller(), SUBJECT)


@pytest.mark.regression
def test_audit_item_is_owned_by_the_SUBJECT_not_the_caller():
    """The knowledge item's owning unit must be the subject's role address.

    This is what makes PACT's containment steps do the work: same-unit allows
    the subject, a prefix allows a supervisor, and an unrelated peer falls
    through to KSP/bridge which default to deny. Setting the caller's own
    address here would make every check trivially same-unit — an authorization
    layer that authorizes everything.
    """
    engine = FakeEngine(Verdict("auto_approved", GOVERNED), Decision(True))
    authz = A2AAuthorizer(
        governance_engine=engine,
        role_mapping=FakeRoles({CALLER: CALLER_ROLE, SUBJECT: SUBJECT_ROLE}),
        posture=object(),
    )
    authz.require_audit_access(_caller(), SUBJECT)

    role_address, item, _posture = engine.access_calls[0]
    assert role_address == CALLER_ROLE, "the CALLER's role drives the check"
    assert item.owning_unit_address == SUBJECT_ROLE, (
        "the item must be owned by the SUBJECT; owning it by the caller would "
        "make every access trivially same-unit"
    )
    assert SUBJECT in item.item_id


def test_cross_agent_audit_is_a_configuration_decision_not_a_hardcoded_deny():
    """A different-agent subject is NOT refused on identity grounds alone.

    A same-agent equality check would refuse here unconditionally, permanently
    foreclosing compliance-officer and incident-responder access. The decision
    belongs to PACT's containment algorithm.
    """
    authz = _authorizer(allowed=True)
    authz.require_audit_access(_caller(), SUBJECT)  # must not raise


# --------------------------------------------------------------------------
# The action and context actually reach PACT
# --------------------------------------------------------------------------


def test_requested_capabilities_are_forwarded_for_envelope_bounding():
    """The capability list must reach PACT, not be intersected locally.

    `intersect_envelopes` already implements intersection with monotonic
    tightening; re-implementing it here would be a parallel authz surface.
    """
    engine = FakeEngine(Verdict("auto_approved", GOVERNED), Decision(True))
    authz = A2AAuthorizer(
        governance_engine=engine,
        role_mapping=FakeRoles({CALLER: CALLER_ROLE}),
        posture=object(),
    )
    authz.require_action(
        _caller(), "trust.delegate", {"requested_capabilities": ["admin.everything"]}
    )

    role_address, action, context = engine.verify_calls[0]
    assert role_address == CALLER_ROLE
    assert action == "trust.delegate"
    assert context["requested_capabilities"] == ["admin.everything"]


def test_token_capabilities_are_not_consulted_as_a_grant():
    """The adapter must not read `caller.claims.capabilities` as authority.

    The token is self-issued (`sub == iss`, capabilities supplied by the caller
    at mint time), so it proves only what the caller asserts about itself.
    """
    import inspect

    from kailash.trust.a2a import authorization

    src = inspect.getsource(authorization)
    assert (
        "claims.capabilities" not in src
    ), "token capabilities are self-asserted and must not be used as a grant"
