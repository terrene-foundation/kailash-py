# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the #2225 frozen-collections residual.

The ``frozen=True`` dataclasses in ``trust/plane/models.py`` held plain ``list``
fields. ``frozen=True`` blocks REBINDING an attribute and does nothing about
in-place mutation of a list it holds, so ``.allowed_actions.append("admin")``
was a permanent self-granted permission -- and ``from_dict`` ALIASED the
caller's list, so the widening could also land from OUTSIDE the envelope after
a tightening check had already passed.

SCOPE. This file covers the frozen-collections half of #2225 ONLY. The sibling
"blocklist tightening at RoleEnvelope registration" residual is deliberately
NOT covered here: the fix it needs is a design decision that is still open (see
the salvage notes on branch fix/2225-frozen-collections-salvage), and a test
asserting behaviour the tree does not implement is a red test, not a guard.
"""

from pathlib import Path

import pytest

import kailash
from kailash.trust.plane.models import (
    CommunicationConstraints,
    DataAccessConstraints,
    OperationalConstraints,
)

pytestmark = [pytest.mark.regression]


def test_module_resolves_from_this_checkout():
    """A green whose module came from ANOTHER checkout is not evidence.

    This repo has a real trap: pytest run inside a git worktree can silently
    import ``kailash`` from the main checkout (or from site-packages), so the
    suite passes while testing code that is not the code under review.

    The assertion is deliberately computed from THIS file's own location
    instead of a hardcoded path, so it travels: it pins "the kailash package
    under test is the one that lives in the same tree as this test", which is
    the property that matters, in every checkout and in CI.
    """
    repo_root = Path(__file__).resolve().parents[2]
    kailash_path = Path(kailash.__file__).resolve()
    assert kailash_path.is_relative_to(repo_root), (
        f"kailash imported from {kailash_path}, which is outside the tree "
        f"containing this test ({repo_root}) -- the suite is testing a "
        f"different checkout."
    )


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
    assert again.allowed_actions == ("read",)
    assert again.blocked_actions == ("transfer_funds",)


@pytest.mark.regression
def test_to_dict_emits_lists_so_signing_bytes_are_unchanged():
    """to_dict() is the serialization boundary feeding envelope_hash.

    The retype is an INTERNAL representation change. If to_dict() started
    emitting tuples, json.dumps would still succeed (a tuple encodes as a JSON
    array), so nothing would fail loudly -- but any consumer doing an equality
    or isinstance check on the decoded structure, and any code path comparing
    a stored dict to a freshly built one, would diverge silently. Pin the list.
    """
    oc = OperationalConstraints(allowed_actions=["read"], blocked_actions=["wire"])
    d = oc.to_dict()
    assert isinstance(d["allowed_actions"], list)
    assert isinstance(d["blocked_actions"], list)

    dac = DataAccessConstraints(read_paths=["/a"], write_paths=["/b"])
    dd = dac.to_dict()
    assert isinstance(dd["read_paths"], list)
    assert isinstance(dd["write_paths"], list)

    cc = CommunicationConstraints(allowed_channels=["email"])
    cd = cc.to_dict()
    assert isinstance(cd["allowed_channels"], list)
