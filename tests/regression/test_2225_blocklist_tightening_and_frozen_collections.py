# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the two #2225 residuals.

RESIDUAL A -- ``RoleEnvelope.validate_tightening`` had no blocklist-superset
check, so a child envelope could STRIP an action its parent blocks and still
register. Monotonic tightening requires BOTH directions: child allowed must be
a SUBSET of the parent's, and child blocked must be a SUPERSET.

RESIDUAL B -- the ``frozen=True`` dataclasses in ``trust/plane/models.py`` held
plain ``list`` fields. ``frozen=True`` blocks REBINDING an attribute and does
nothing about in-place mutation of a list it holds, and ``from_dict`` ALIASED
the caller's list, so an allowlist could be widened after a tightening check
had already passed.
"""

import pytest

import kailash
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.plane.models import (
    CommunicationConstraints,
    DataAccessConstraints,
    OperationalConstraints,
)


def test_module_resolves_from_this_worktree():
    """A green whose module came from another checkout is not evidence."""
    assert "/.kailash-py-wt/governance/" in kailash.__file__, kailash.__file__


def _envelope(eid, allowed, blocked):
    return ConstraintEnvelopeConfig(
        id=eid,
        operational=OperationalConstraintConfig(
            allowed_actions=tuple(allowed), blocked_actions=tuple(blocked)
        ),
    )


# ---------------------------------------------------------------------------
# RESIDUAL A -- both poles
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_child_stripping_parent_blocked_action_is_refused():
    """NEGATIVE pole: unblocking what the parent blocked is a WIDENING."""
    parent = _envelope("p", ["read", "transfer_funds"], ["transfer_funds"])
    child = _envelope("c", ["read", "transfer_funds"], [])  # stripped

    with pytest.raises(Exception) as exc:
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)
    assert "transfer_funds" in str(exc.value)
    assert "blocked_actions" in str(exc.value)


@pytest.mark.regression
def test_child_partially_stripping_parent_blocklist_is_refused():
    """Dropping ONE parent-blocked action AND allowing it is a widening."""
    parent = _envelope("p", ["read", "delete_all"], ["transfer_funds", "delete_all"])
    # keeps transfer_funds blocked, drops delete_all -- and allows it
    child = _envelope("c", ["read", "delete_all"], ["transfer_funds"])

    with pytest.raises(Exception) as exc:
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)
    assert "delete_all" in str(exc.value)


@pytest.mark.regression
def test_child_omitting_blocklist_it_never_allows_still_registers():
    """POSITIVE pole: a task envelope is an intersected OVERLAY.

    It declares only what it narrows and legitimately omits blocked_actions.
    Dropping a blocked action the child never allows escalates nothing -- the
    allowlist still denies it -- so a strict "child blocklist must be a
    superset" rule would break this working pattern for no safety gain.
    """
    parent = _envelope("p", ["read", "grade"], ["delete"])
    child = _envelope("c", ["read", "grade"], [])  # omits the blocklist

    RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)


@pytest.mark.regression
def test_legitimately_tightening_child_still_registers():
    """POSITIVE pole: a deny-everything fix would pass the negative test alone.

    The child preserves the parent's blocklist, ADDS to it, and narrows the
    allowlist -- tightening on every axis. It must still register.
    """
    parent = _envelope("p", ["read", "write", "transfer_funds"], ["transfer_funds"])
    child = _envelope("c", ["read"], ["transfer_funds", "delete_all"])

    RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)


@pytest.mark.regression
def test_child_restating_parent_blocklist_exactly_still_registers():
    """POSITIVE pole: an equal blocklist is tighter-or-equal, not a widening."""
    parent = _envelope("p", ["read", "transfer_funds"], ["transfer_funds"])
    child = _envelope("c", ["read", "transfer_funds"], ["transfer_funds"])

    RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)


@pytest.mark.regression
def test_parent_with_empty_blocklist_accepts_any_child_blocklist():
    """POSITIVE pole: nothing to preserve means nothing can be stripped."""
    parent = _envelope("p", ["read", "write"], [])
    child = _envelope("c", ["read"], ["write"])

    RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)


# ---------------------------------------------------------------------------
# RESIDUAL B -- frozen dataclasses hold immutable collections
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_from_dict_does_not_alias_the_callers_list():
    """The caller must not retain a live handle into a validated envelope."""
    caller = {"allowed_actions": ["read"], "blocked_actions": ["transfer_funds"]}
    oc = OperationalConstraints.from_dict(caller)

    assert oc.allowed_actions is not caller["allowed_actions"]
    caller["allowed_actions"].append("transfer_funds")
    assert "transfer_funds" not in oc.allowed_actions


@pytest.mark.regression
@pytest.mark.parametrize(
    "factory,fieldname",
    [
        (lambda: OperationalConstraints(allowed_actions=["read"]), "allowed_actions"),
        (
            lambda: OperationalConstraints(blocked_actions=["transfer_funds"]),
            "blocked_actions",
        ),
        (lambda: DataAccessConstraints(read_paths=["/a"]), "read_paths"),
        (lambda: DataAccessConstraints(write_paths=["/a"]), "write_paths"),
        (lambda: DataAccessConstraints(blocked_paths=["/a"]), "blocked_paths"),
        (lambda: DataAccessConstraints(blocked_patterns=["*.pem"]), "blocked_patterns"),
        (
            lambda: CommunicationConstraints(allowed_channels=["email"]),
            "allowed_channels",
        ),
        (
            lambda: CommunicationConstraints(blocked_channels=["sms"]),
            "blocked_channels",
        ),
        (lambda: CommunicationConstraints(requires_review=["x"]), "requires_review"),
    ],
)
def test_collection_fields_reject_in_place_mutation(factory, fieldname):
    """frozen=True blocks rebinding; the field itself must refuse mutation."""
    obj = factory()
    value = getattr(obj, fieldname)
    assert not isinstance(value, list), f"{fieldname} is a mutable list"
    with pytest.raises(AttributeError):
        value.append("escalated")


@pytest.mark.regression
def test_constraints_still_round_trip_through_to_dict_and_from_dict():
    """POSITIVE pole: immutability must not break serialization."""
    oc = OperationalConstraints.from_dict(
        {"allowed_actions": ["read"], "blocked_actions": ["transfer_funds"]}
    )
    again = OperationalConstraints.from_dict(oc.to_dict())
    assert list(again.allowed_actions) == ["read"]
    assert list(again.blocked_actions) == ["transfer_funds"]
