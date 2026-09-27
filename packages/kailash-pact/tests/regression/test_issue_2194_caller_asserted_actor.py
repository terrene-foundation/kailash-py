# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2194 -- caller-asserted governance actor fields.

Every write endpoint in ``pact.governance.api.endpoints`` binds an
authenticated ``identity`` and none of them read it.  The actor recorded on
the durable record and on the governance audit event was taken verbatim from
the request body::

    granted_by_role_address=req.granted_by_role_address   # endpoints.py:321
    source_role_address=req.granted_by_role_address       # endpoints.py:337

``GovernanceAuth.verify_token`` returns one of two CONSTANTS -- ``"authenticated"``
or ``"anonymous"`` -- so there is no per-principal identity to derive the actor
from.  A server-derived actor (``security.md`` § Identity-derivation parity)
therefore CANNOT be written today, and fabricating a comparison against a
constant identity would ship a wrong authorization check in place of an honest
gap.

What these tests pin is the HONESTY property, not an authorization property:

1. the caller's assertion is recorded in a grammar that MARKS it unverified,
   so an auditor cannot mistake it for an authenticated fact;
2. the server-derived identity is recorded ALONGSIDE it, which is the only
   fact about the caller the system actually holds;
3. the caller's assertion is never labelled ``verified``;
4. the existing population path still works -- the body field remains
   required and remains validated as a well-formed D/T/R address.

These assertions are deliberately INDEPENDENT of which authorization model
(#2194 options 1/2/3) is eventually chosen.  When per-principal tokens land,
``ACTOR_VERIFIED`` flips to True and the claim prefix disappears; these tests
are what will force that flip to be explicit rather than silent.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from kailash.trust.pact.compilation import RoleDefinition, compile_org
from kailash.trust.pact.config import DepartmentConfig, OrgDefinition, TeamConfig
from kailash.trust.pact.engine import GovernanceEngine
from pact.governance.api.auth import GovernanceAuth
from pact.governance.api.events import event_bus
from pact.governance.api.router import create_governance_app

pytestmark = [pytest.mark.regression, pytest.mark.security]

_TOKEN = "test-governance-token-2194"


def _build_engine() -> tuple[GovernanceEngine, dict[str, str]]:
    """Build a two-role org and return (engine, {role name: D/T/R address})."""
    org = OrgDefinition(
        org_id="issue-2194-org",
        name="Issue 2194 Org",
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
    compiled = compile_org(org)
    addresses = {node.name: addr for addr, node in compiled.nodes.items()}
    return GovernanceEngine(org), addresses


@pytest.fixture
def engine_and_addresses() -> tuple[GovernanceEngine, dict[str, str]]:
    return _build_engine()


@pytest.fixture
async def client(
    engine_and_addresses: tuple[GovernanceEngine, dict[str, str]],
) -> Any:
    engine, _ = engine_and_addresses
    app = create_governance_app(engine, GovernanceAuth(api_token=_TOKEN))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TOKEN}"}


async def _capture_events(coro: Any) -> tuple[Any, list[dict[str, Any]]]:
    """Run ``coro`` with an EventBus subscriber attached.

    Returns ``(response, events)``. The response is returned deliberately:
    an empty event list is otherwise ambiguous between "the endpoint emitted
    nothing" and "the request was rejected before it could emit", and the
    caller must be able to tell those apart.
    """
    queue = await event_bus.subscribe()
    try:
        response = await coro
        await asyncio.sleep(0)  # let the fire-and-forget publish drain
        events: list[dict[str, Any]] = []
        while not queue.empty():
            events.append(queue.get_nowait().to_dict())
        return response, events
    finally:
        await event_bus.unsubscribe(queue)


# ===================================================================
# POST /clearances -- granted_by
# ===================================================================


@pytest.mark.asyncio
async def test_stored_clearance_marks_granted_by_as_unverified_claim(
    client: AsyncClient,
    auth_headers: dict[str, str],
    engine_and_addresses: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """The DURABLE record must not carry a caller assertion as a bare address.

    Before the fix the stored ``granted_by_role_address`` was byte-identical to
    the body field, so a reader of the clearance record (or of a backup, or of
    the sqlite ``granted_by`` column) could not tell an authenticated grant
    from an unauthenticated assertion.
    """
    from pact.governance.api.auth import UNVERIFIED_CLAIM_PREFIX

    engine, addrs = engine_and_addresses
    vp, lead = addrs["VP Engineering"], addrs["Lead Developer"]

    resp = await client.post(
        "/api/v1/governance/clearances",
        json={
            "role_address": lead,
            "max_clearance": "confidential",
            "compartments": [],
            "granted_by_role_address": vp,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    stored = engine._clearance_store.get_clearance(lead)
    assert stored is not None
    assert stored.granted_by_role_address != vp, (
        "stored granted_by is byte-identical to the caller's assertion -- "
        "an unverified claim recorded in the grammar of a server-derived fact"
    )
    assert stored.granted_by_role_address.startswith(UNVERIFIED_CLAIM_PREFIX)
    # The claim itself must survive: this is an honesty fix, not a data loss.
    assert stored.granted_by_role_address.endswith(vp)


@pytest.mark.asyncio
async def test_clearance_event_separates_claim_from_server_derived_identity(
    client: AsyncClient,
    auth_headers: dict[str, str],
    engine_and_addresses: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """The AUDIT EVENT must label the claim and carry the server-derived identity."""
    _, addrs = engine_and_addresses
    vp, lead = addrs["VP Engineering"], addrs["Lead Developer"]

    resp, events = await _capture_events(
        client.post(
            "/api/v1/governance/clearances",
            json={
                "role_address": lead,
                "max_clearance": "confidential",
                "compartments": [],
                "granted_by_role_address": vp,
            },
            headers=auth_headers,
        )
    )
    assert resp.status_code == 201, resp.text
    assert len(events) == 1, f"expected one governance event, got {len(events)}"
    data = events[0]["data"]

    assert "granted_by" not in data, (
        "'granted_by' reads as a statement of fact; an unverified assertion "
        "must not be published under that key"
    )
    assert data["granted_by_claimed"] == vp
    assert data["actor_verified"] is False
    # The identity the server actually derived -- previously bound and never read.
    assert data["authenticated_identity"] == "authenticated"


# ===================================================================
# POST /ksps -- created_by
# ===================================================================


@pytest.mark.asyncio
async def test_stored_ksp_marks_created_by_as_unverified_claim(
    client: AsyncClient,
    auth_headers: dict[str, str],
    engine_and_addresses: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """Sibling surface: ``POST /ksps`` has the same shape and the same defect."""
    from pact.governance.api.auth import UNVERIFIED_CLAIM_PREFIX

    engine, addrs = engine_and_addresses
    vp = addrs["VP Engineering"]
    dept = addrs["Engineering"]
    team = addrs["Backend"]

    resp = await client.post(
        "/api/v1/governance/ksps",
        json={
            "source_unit_address": dept,
            "target_unit_address": team,
            "max_classification": "restricted",
            "created_by_role_address": vp,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    ksps = engine._access_policy_store.list_ksps()
    assert len(ksps) == 1
    assert ksps[0].created_by_role_address != vp
    assert ksps[0].created_by_role_address.startswith(UNVERIFIED_CLAIM_PREFIX)
    assert ksps[0].created_by_role_address.endswith(vp)


@pytest.mark.asyncio
async def test_ksp_event_separates_claim_from_server_derived_identity(
    client: AsyncClient,
    auth_headers: dict[str, str],
    engine_and_addresses: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    _, addrs = engine_and_addresses
    vp, dept, team = addrs["VP Engineering"], addrs["Engineering"], addrs["Backend"]

    resp, events = await _capture_events(
        client.post(
            "/api/v1/governance/ksps",
            json={
                "source_unit_address": dept,
                "target_unit_address": team,
                "max_classification": "restricted",
                "created_by_role_address": vp,
            },
            headers=auth_headers,
        )
    )
    assert resp.status_code == 201, resp.text
    assert len(events) == 1
    data = events[0]["data"]
    assert data["created_by_claimed"] == vp
    assert data["actor_verified"] is False
    assert data["authenticated_identity"] == "authenticated"


# ===================================================================
# The remaining endpoints -- identity bound and never read (uniform gap)
# ===================================================================


@pytest.mark.asyncio
async def test_every_governance_event_carries_the_server_derived_identity(
    client: AsyncClient,
    auth_headers: dict[str, str],
    engine_and_addresses: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """``identity`` was bound at all nine endpoints and read at none.

    Each emitting endpoint must publish the one fact the server actually
    derived about its caller, so an event stream is never a record composed
    entirely of caller assertions.
    """
    engine, addrs = engine_and_addresses
    vp, lead = addrs["VP Engineering"], addrs["Lead Developer"]
    team = addrs["Backend"]

    # Bridge creation is gated on LCA approval, which is a real governance
    # precondition and not what this test is about.
    from kailash.trust.pact.addressing import Address

    lca = Address.lowest_common_ancestor(Address.parse(vp), Address.parse(lead))
    assert lca is not None
    engine.approve_bridge(vp, lead, str(lca))

    calls = [
        (
            "/api/v1/governance/check-access",
            {
                "role_address": lead,
                "item_id": "item-1",
                "item_classification": "public",
                "item_owning_unit": team,
                "item_compartments": [],
                "posture": "shared_planning",
            },
        ),
        (
            "/api/v1/governance/verify-action",
            {"role_address": lead, "action": "read_docs"},
        ),
        (
            "/api/v1/governance/bridges",
            {
                "role_a_address": vp,
                "role_b_address": lead,
                "bridge_type": "scoped",
                "max_classification": "restricted",
            },
        ),
        (
            "/api/v1/governance/envelopes",
            {
                "envelope_id": "env-2194",
                "defining_role_address": vp,
                "target_role_address": lead,
                "constraints": {"financial": {"max_transaction": 100.0}},
            },
        ),
    ]

    for path, body in calls:
        resp, events = await _capture_events(
            client.post(path, json=body, headers=auth_headers)
        )
        assert resp.status_code in (200, 201), f"{path}: {resp.status_code} {resp.text}"
        assert len(events) == 1, f"{path}: expected one event, got {len(events)}"
        data = events[0]["data"]
        assert data.get("authenticated_identity") == "authenticated", (
            f"{path}: governance event carries no server-derived identity; "
            f"every field in it is a caller assertion"
        )


# ===================================================================
# Non-regression: the population path the fix must NOT break
# ===================================================================


@pytest.mark.asyncio
async def test_body_actor_field_is_still_required_and_still_validated(
    client: AsyncClient,
    auth_headers: dict[str, str],
    engine_and_addresses: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """Rejecting the body field outright would break the only population path.

    The honest fix LABELS the assertion; it does not remove the caller's
    ability to make it, and it does not weaken the existing D/T/R validation.
    """
    _, addrs = engine_and_addresses
    lead = addrs["Lead Developer"]

    missing = await client.post(
        "/api/v1/governance/clearances",
        json={
            "role_address": lead,
            "max_clearance": "confidential",
            "compartments": [],
        },
        headers=auth_headers,
    )
    assert missing.status_code == 422

    malformed = await client.post(
        "/api/v1/governance/clearances",
        json={
            "role_address": lead,
            "max_clearance": "confidential",
            "compartments": [],
            "granted_by_role_address": "not-a-dtr-address",
        },
        headers=auth_headers,
    )
    assert malformed.status_code == 422


@pytest.mark.asyncio
async def test_identity_is_not_a_principal_and_is_not_compared_to_the_claim(
    engine_and_addresses: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """The gap is structural: there is no principal to derive an actor from.

    This pins the PREMISE of the deferral. If token issuance ever grows a
    per-principal identity, ``identity_names_a_principal`` starts returning
    True and this test fails -- which is exactly the moment the #2194
    authorization-model decision must be revisited.
    """
    from pact.governance.api.auth import identity_names_a_principal

    auth = GovernanceAuth(api_token=_TOKEN)
    assert auth.verify_token(_TOKEN) == "authenticated"
    assert GovernanceAuth(api_token=None).verify_token(None) == "anonymous"

    assert identity_names_a_principal("authenticated") is False
    assert identity_names_a_principal("anonymous") is False
    assert identity_names_a_principal("D1-R1") is True
