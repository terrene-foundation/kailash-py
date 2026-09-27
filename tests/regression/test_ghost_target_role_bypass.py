# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests -- an unresolvable ``target_role_address`` was never resolved.

Site 3 of issue #2238, the sibling field of the already-fixed
``defining_role_address``.  ``set_role_envelope`` resolved the DEFINING role
through ``_resolve_role_address`` but wrote ``target_role_address`` straight
through to the store, the ``is_new`` probe, and ``_cascade_invalidate``.

The envelope store is keyed on the RAW ``target_role_address``
(``store.py::save_role_envelope``), and every consumer keys on the positional
address -- ``get_ancestor_envelopes`` is reached from
``compute_effective_envelope`` only for addresses in the target's
``accountability_chain``.  A target that names no node, or names a real role by
an alias, is therefore an ABSENCE RENDERED AS A SUCCESS: the write is accepted
and persisted under a key no lookup ever reads, while the caller believes the
role is now constrained.

MEASURED on the unfixed tree, control-and-subject on one engine (real
``GovernanceEngine``, real store, ``max_spend_usd`` assertions):

    CONTROL  definer=CFO target=LEAD      env=$1M  -> MonotonicTighteningError
    SUBJECT  definer=CFO target="D9-R9"   env=$50  -> ACCEPTED, keyed "D9-R9"
    SUBJECT  definer=CFO target="r-lead"  env=$50  -> ACCEPTED, keyed "r-lead"
    SUBJECT  definer=CFO target=<lower>   env=$50  -> ACCEPTED, keyed lower-case

    CONTROL  narrow LEAD to $25 via target=LEAD  -> compute_envelope = 25.0
    SUBJECT  narrow LEAD to $25 via target="r-lead"
             -> ACCEPTED, and compute_envelope = 100.0 -- the narrowing was
                SILENTLY NOT APPLIED

The last pair is the load-bearing one: the caller asked for a TIGHTENING and
was told it succeeded, while the role kept its wider ``$100`` authority.  This
is fail-open, not merely untidy data.

THE DISCRIMINATOR IS EXISTENCE, NOT THE FIELD'S SHAPE.  ``Address.parse``
already rejects malformed input; well-formed-but-non-existent is the hole.
The YAML surface has always resolved BOTH envelope addresses
(``yaml_resolvers.resolve_envelope`` resolves ``spec.target`` and
``spec.defined_by`` fail-closed), so resolving the target here only restores
parity between the two authoring surfaces.

BOTH POLES ARE ASSERTED: a deny-everything "fix" fails the real-target and
config-role-id-target cases below, which must be ACCEPTED and APPLIED.
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


def _org() -> OrgDefinition:
    return OrgDefinition(
        org_id="ghost-target-org",
        name="Ghost Target Org",
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
    """Engine with a $1000 CFO envelope and the $100 Lead envelope it defines.

    Returns ``(engine, vp_address, cfo_address, lead_address)``.  The CFO can
    legitimately tighten the Lead to anything at or under $1000, which is what
    makes the narrow-to-$25 subject below a REAL tightening rather than a
    tightening the definer had no authority to grant.
    """
    compiled = compile_org(_org())
    addresses = {node.name: addr for addr, node in compiled.nodes.items()}
    vp, cfo, lead = (
        addresses["VP Engineering"],
        addresses["CFO"],
        addresses["Lead Developer"],
    )
    engine = GovernanceEngine(compiled)
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-cfo",
            defining_role_address=vp,
            target_role_address=cfo,
            envelope=_envelope("env-cfo", 1000.0, ["read"]),
        )
    )
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-lead",
            defining_role_address=cfo,
            target_role_address=lead,
            envelope=_envelope("env-lead", 100.0, ["read"]),
        )
    )
    return engine, vp, cfo, lead


def _set(
    definer: str, target: str, spend: float, env_id: str = "re-subject"
) -> RoleEnvelope:
    return RoleEnvelope(
        id=env_id,
        defining_role_address=definer,
        target_role_address=target,
        envelope=_envelope("env-subject", spend, ["read"]),
    )


# ===================================================================
# CONTROL -- the instrument can return the OTHER verdict
# ===================================================================


def test_control_wide_envelope_under_a_real_target_is_refused(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """Known-answer control for every refusal assertion below.

    Without this, a SUBJECT that raised would prove nothing: the tightening
    gate might simply be unreachable from this method.
    """
    engine, _vp, cfo, lead = governed
    with pytest.raises(MonotonicTighteningError) as excinfo:
        engine.set_role_envelope(_set(cfo, lead, 1_000_000.0, env_id="re-too-wide"))
    assert "max_spend_usd" in str(excinfo.value)


# ===================================================================
# POLE 1 -- a target that resolves to no node is refused
# ===================================================================


@pytest.mark.parametrize(
    "ghost",
    ["D9-R9", "D9-R9-D4-R7"],
    ids=["flat-ghost", "nested-ghost"],
)
def test_ghost_target_role_address_is_refused(
    governed: tuple[GovernanceEngine, str, str, str], ghost: str
) -> None:
    """THE BYPASS PROOF: a WELL-FORMED target naming no node must fail closed.

    Measured pre-fix: both were ACCEPTED and the envelope was persisted under
    the ghost key (``store.py`` keys on the raw target).
    """
    engine, _vp, cfo, _lead = governed
    with pytest.raises(PactError) as excinfo:
        engine.set_role_envelope(_set(cfo, ghost, 50.0))
    assert "target role address" in str(excinfo.value).lower()


def test_case_variant_target_is_refused(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """A case variant of a REAL address resolves to nothing.

    ``AddressSegment.parse`` upper-cases the type char, so ``"d1-r1-t1-r1"``
    parses cleanly; the compiled-org node lookup is a plain case-sensitive dict
    key, so it names no node.  Measured pre-fix: ACCEPTED, persisted under the
    lower-case key.
    """
    engine, _vp, cfo, lead = governed
    with pytest.raises(PactError) as excinfo:
        engine.set_role_envelope(_set(cfo, lead.lower(), 50.0))
    assert "target role address" in str(excinfo.value).lower()


def test_ghost_target_refusal_persists_nothing(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """Fail-closed means the refused envelope never reached the store."""
    engine, _vp, cfo, lead = governed
    with pytest.raises(PactError):
        engine.set_role_envelope(_set(cfo, "D9-R9", 50.0))

    assert engine._envelope_store.get_role_envelope("D9-R9") is None
    effective = engine.compute_envelope(lead)
    assert effective is not None
    assert effective.financial is not None
    assert effective.financial.max_spend_usd == 100.0


# ===================================================================
# THE IMPACT -- an alias target silently failed to apply a tightening
# ===================================================================


def test_config_role_id_target_is_resolved_and_the_tightening_APPLIES(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """A config role ID names a REAL role -- accepted, resolved, and APPLIED.

    This is the measured escalation.  Pre-fix, ``target="r-lead"`` with a $25
    envelope was ACCEPTED (the tightening gate passed, since the definer's
    $1000 envelope permits $25) and stored under the literal key ``"r-lead"``.
    ``compute_effective_envelope`` walks the target's ``accountability_chain``
    and therefore never saw it: ``compute_envelope(lead)`` still reported
    ``100.0``.  The caller was told a tightening succeeded; the role kept its
    wider authority.

    Post-fix the address is resolved through the same helper every other state
    mutation uses, so the envelope lands on the role it names.
    """
    engine, _vp, cfo, lead = governed
    engine.set_role_envelope(_set(cfo, "r-lead", 25.0, env_id="re-narrow-alias"))

    # Stored under the POSITIONAL address, not the alias the caller typed.
    assert engine._envelope_store.get_role_envelope("r-lead") is None
    assert engine._envelope_store.get_role_envelope(lead) is not None

    effective = engine.compute_envelope(lead)
    assert effective is not None
    assert effective.financial is not None
    assert effective.financial.max_spend_usd == 25.0


def test_alias_and_positional_targets_address_the_same_role(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """The alias form is an UPSERT of the positional envelope, not a second one.

    ``is_new`` is computed from the resolved address, so an alias write must be
    reported as a MODIFICATION of the existing envelope rather than creating a
    parallel record that no lookup reaches.
    """
    engine, _vp, cfo, lead = governed
    before = engine._envelope_store.get_role_envelope(lead)
    assert before is not None and before.id == "re-lead"

    engine.set_role_envelope(
        RoleEnvelope(
            id="re-lead",
            defining_role_address=cfo,
            target_role_address="r-lead",
            envelope=_envelope("env-lead", 75.0, ["read"]),
        )
    )

    stored = engine._envelope_store.get_role_envelope(lead)
    assert stored is not None
    assert stored.target_role_address == lead
    assert stored.envelope.financial is not None
    assert stored.envelope.financial.max_spend_usd == 75.0
    assert len(engine._envelope_store._role_envelopes) == 2


# ===================================================================
# POLE 2 -- every legitimate path still works
# ===================================================================


def test_positional_target_still_accepted_and_applied(
    governed: tuple[GovernanceEngine, str, str, str],
) -> None:
    """The ordinary path -- a positional target -- is untouched."""
    engine, _vp, cfo, lead = governed
    engine.set_role_envelope(_set(cfo, lead, 25.0, env_id="re-narrow-real"))
    effective = engine.compute_envelope(lead)
    assert effective is not None
    assert effective.financial is not None
    assert effective.financial.max_spend_usd == 25.0


def test_root_envelope_creation_still_succeeds() -> None:
    """A genuine root envelope under a real definer that holds none.

    ``defining_envelope is None`` is the LEGITIMATE state for a root envelope;
    resolving the target must not turn that into a refusal.
    """
    compiled = compile_org(_org())
    addresses = {node.name: addr for addr, node in compiled.nodes.items()}
    vp, cfo = addresses["VP Engineering"], addresses["CFO"]

    engine = GovernanceEngine(compiled)
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-cfo-root",
            defining_role_address=vp,
            target_role_address=cfo,
            envelope=_envelope("env-cfo-root", 500.0, ["read", _WIRE]),
        )
    )
    effective = engine.compute_envelope(cfo)
    assert effective is not None
    assert effective.financial is not None
    assert effective.financial.max_spend_usd == 500.0
