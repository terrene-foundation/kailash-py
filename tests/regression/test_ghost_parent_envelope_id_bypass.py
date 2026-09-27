# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests -- a ghost ``parent_envelope_id`` disabled monotonic tightening.

Site 2 of issue #2238, the same bug class as the ``defining_role_address`` site
in ``test_ghost_defining_role_bypass.py``: the guard asked ``if parent is not
None``, and the lookup returns ``None`` both when NO parent was named (a
legitimate task envelope that narrows nothing) and when a parent WAS named and
does not exist (a caller asserting an authority that is not there).  Those two
cases must be treated oppositely, so the engine now separates them before the
lookup rather than after it.

Measured on the unfixed tree, control-and-subject on one engine with the same
wide task envelope (``max_spend_usd=1_000_000``, actions ``["read",
"wire_transfer"]``)::

    CONTROL  parent_envelope_id="re-lead"        -> MonotonicTighteningError
    SUBJECT  parent_envelope_id="does-not-exist" -> ACCEPTED, persisted

The control is what makes the subject readable: without it, "no exception" is
equally consistent with "the gate passed the ghost" and "the gate is
unreachable from this method at all".

SCOPE OF THE IMPACT, MEASURED NOT ASSUMED.  A task envelope is INTERSECTED with
every ancestor role envelope at compute time (``compute_effective_envelope``,
envelopes.py:782-787), so an unchecked WIDE task envelope does NOT widen the
effective envelope of a role that already has one --
``test_ghost_parent_does_not_widen_the_effective_envelope`` pins that.  What the
bypass does break is the recorded invariant and the EATP ``DelegationRecord``
emitted from the unvalidated envelope: the store accepts a task envelope that
claims more authority than its named parent ever held.  These tests assert the
refusal, not an enforcement escalation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
from kailash.trust.pact.envelopes import (
    MonotonicTighteningError,
    RoleEnvelope,
    TaskEnvelope,
)
from kailash.trust.pact.exceptions import PactError

pytestmark = [pytest.mark.regression]

_WIRE = "wire_transfer"
_TASK = "task-escalate"
_PARENT_ID = "re-lead"


def _org() -> OrgDefinition:
    return OrgDefinition(
        org_id="ghost-parent-org",
        name="Ghost Parent Org",
        departments=[DepartmentConfig(department_id="d-eng", name="Engineering")],
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
        ],
    )


def _config(env_id: str, spend: float, actions: list[str]) -> ConstraintEnvelopeConfig:
    return ConstraintEnvelopeConfig(
        id=env_id,
        financial=FinancialConstraintConfig(max_spend_usd=spend),
        operational=OperationalConstraintConfig(
            allowed_actions=actions, blocked_actions=[]
        ),
    )


@pytest.fixture
def governed() -> tuple[GovernanceEngine, str, str]:
    """Engine holding one $100 role envelope, id ``re-lead``, on the Lead.

    Returns ``(engine, vp_address, lead_address)``.
    """
    compiled = compile_org(_org())
    addresses = {node.name: addr for addr, node in compiled.nodes.items()}
    vp, lead = addresses["VP Engineering"], addresses["Lead Developer"]

    engine = GovernanceEngine(compiled)
    engine.set_role_envelope(
        RoleEnvelope(
            id=_PARENT_ID,
            defining_role_address=vp,
            target_role_address=lead,
            envelope=_config("env-lead", 100.0, ["read"]),
        )
    )
    return engine, vp, lead


def _wide_task(parent_id: str, env_id: str = "te-wide") -> TaskEnvelope:
    return TaskEnvelope(
        id=env_id,
        task_id=_TASK,
        parent_envelope_id=parent_id,
        envelope=_config("env-task-wide", 1_000_000.0, ["read", _WIRE]),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


# ===================================================================
# CONTROL -- the gate is reachable and does fire
# ===================================================================


def test_control_real_parent_id_still_refuses_a_wider_task_envelope(
    governed: tuple[GovernanceEngine, str, str],
) -> None:
    """Known-answer control for every assertion below.

    If this did not raise, a non-raising SUBJECT would prove nothing: the gate
    would simply be unreachable.
    """
    engine, *_ = governed
    with pytest.raises(MonotonicTighteningError) as excinfo:
        engine.set_task_envelope(_wide_task(_PARENT_ID))
    assert "max_spend_usd" in str(excinfo.value)


# ===================================================================
# POLE 1 -- a NAMED parent that does not resolve is refused
# ===================================================================


@pytest.mark.parametrize(
    "ghost",
    ["does-not-exist", "re-lead-v2", "RE-LEAD"],
    ids=["absent-id", "near-miss-id", "case-variant"],
)
def test_ghost_parent_envelope_id_is_refused(
    governed: tuple[GovernanceEngine, str, str], ghost: str
) -> None:
    """THE BYPASS PROOF: a named-but-unresolvable parent must fail closed.

    ``case-variant`` is included because envelope IDs are compared with ``==``
    (engine.py ``_find_role_envelope_by_id_locked``), so ``"RE-LEAD"`` names
    nothing while looking to a human like it names the parent.  Measured
    pre-fix, all three were ACCEPTED and persisted.
    """
    engine, *_ = governed
    with pytest.raises(PactError) as excinfo:
        engine.set_task_envelope(_wide_task(ghost))
    assert "parent envelope" in str(excinfo.value).lower()


def test_ghost_parent_refusal_persists_nothing(
    governed: tuple[GovernanceEngine, str, str],
) -> None:
    """Fail-closed means the refused task envelope was never stored."""
    engine, _, lead = governed
    with pytest.raises(PactError):
        engine.set_task_envelope(_wide_task("does-not-exist"))

    # No public read accessor for task envelopes on the engine; the store is
    # the authority the engine itself reads at compute time (engine.py:1870).
    assert engine._envelope_store.get_active_task_envelope(lead, _TASK) is None


def test_ghost_parent_does_not_widen_the_effective_envelope(
    governed: tuple[GovernanceEngine, str, str],
) -> None:
    """Scope honesty: ancestor intersection already neutralised the ENFORCEMENT
    half of this bypass, so this test states what the fix does and does not buy.

    The $100 role envelope still bounds the task, refusal or not.  The fix
    closes the unchecked WRITE (and the DelegationRecord emitted from it), not
    an effective-envelope escalation -- claiming otherwise would overstate it.
    """
    engine, _, lead = governed
    with pytest.raises(PactError):
        engine.set_task_envelope(_wide_task("does-not-exist"))

    effective = engine.compute_envelope(lead, task_id=_TASK)
    assert effective is not None
    assert effective.financial is not None
    assert effective.financial.max_spend_usd == 100.0


# ===================================================================
# POLE 2 -- every legitimate path still works
# ===================================================================


def test_task_envelope_with_no_parent_is_still_accepted(
    governed: tuple[GovernanceEngine, str, str],
) -> None:
    """The Site-2 equivalent of root-envelope creation.

    ``parent_envelope_id`` is a required ``str`` with no ``None`` form, so an
    EMPTY id is the only expressible "this envelope narrows no role envelope".
    That case has nothing to tighten against and must proceed -- a deny-on-None
    "fix" would fail here, which is exactly what makes this the negative pole.
    """
    engine, _, lead = governed
    engine.set_task_envelope(
        TaskEnvelope(
            id="te-parentless",
            task_id="task-parentless",
            parent_envelope_id="",
            envelope=_config("env-task-narrow", 25.0, ["read"]),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    stored = engine._envelope_store.get_active_task_envelope(lead, "task-parentless")
    assert stored is not None
    assert stored.id == "te-parentless"


def test_legitimate_narrowing_under_a_real_parent_still_succeeds(
    governed: tuple[GovernanceEngine, str, str],
) -> None:
    """A narrower task envelope naming the real parent is accepted and applied."""
    engine, _, lead = governed
    engine.set_task_envelope(
        TaskEnvelope(
            id="te-narrow",
            task_id=_TASK,
            parent_envelope_id=_PARENT_ID,
            envelope=_config("env-task-narrow", 50.0, ["read"]),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    effective = engine.compute_envelope(lead, task_id=_TASK)
    assert effective is not None
    assert effective.financial is not None
    assert effective.financial.max_spend_usd == 50.0
