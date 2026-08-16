"""Regression: session-scoped routes had no ownership check (#2145).

#2102 answered "who is calling". This is the adjacent question it did not
answer: **what may that caller act on**. Every session-scoped route on
``APIGateway`` took a caller-supplied ``session_id`` and acted on it without
ever comparing the session's owner against the caller -- even though
``WorkflowSession.user_id`` has always carried that owner.

Measured before the fix, both parties holding valid tokens the gateway itself
minted, on a default (gated) ``APIGateway()``::

    alice session: 3815fbd4-...  owner=alice
    --- bob, authenticated as bob, acting on ALICE's session ---
    POST /api/workflows?session_id=alice_sid  -> 200
    POST /api/executions?session_id=alice_sid -> 200
    DELETE /api/sessions/alice_sid            -> 200

The middle line is the severe one: the workflow body is caller-authored
``PythonCodeNode`` source, so that is authenticated arbitrary code execution
inside another user's session. ``GET /api/sessions`` supplied the target
directory, enumerating every session with its owner.

**Every test here carries the owner-succeeds row as a discrimination
control.** A suite that only shows ``bob`` refused cannot tell this fix from
one that refuses everybody -- which is the failure mode a fail-closed change
is most likely to ship.
"""

import pytest

pytest.importorskip("fastapi", reason="gateway tests require the `server` extra")
pytest.importorskip("jwt", reason="PyJWT is required to mint the test credentials")

from fastapi.testclient import TestClient  # noqa: E402

from kailash.middleware.communication.api_gateway import APIGateway  # noqa: E402

GATEWAY_SECRET = "test-gateway-secret-" + "x" * 28

#: A workflow whose body is caller-authored source. It is what makes
#: `POST /api/executions` on someone else's session code execution rather than
#: a data leak.
WORKFLOW = {
    "name": "probe",
    "nodes": [
        {
            "id": "n",
            "type": "PythonCodeNode",
            "config": {"name": "n", "code": "result = {'ok': True}"},
        }
    ],
    "connections": [],
}


@pytest.fixture(autouse=True)
def gateway_secret(monkeypatch):
    monkeypatch.setenv("KAILASH_API_GATEWAY_SECRET", GATEWAY_SECRET)


def _bearer(gateway: APIGateway, user_id: str) -> dict:
    return {
        "Authorization": f"Bearer {gateway.auth_manager.create_access_token(user_id=user_id)}"
    }


@pytest.fixture
def gated():
    """A default gateway plus alice's session, her workflow and her execution.

    Returns ``(gateway, client, alice_headers, bob_headers, ids)``. The state
    is built THROUGH the API as alice, so every id below is one she legitimately
    owns -- which is what makes the owner rows meaningful.
    """
    gateway = APIGateway(title="ownership-test")
    client = TestClient(gateway.app)
    alice = _bearer(gateway, "alice")
    bob = _bearer(gateway, "bob")

    session_id = client.post("/api/sessions", json={}, headers=alice).json()[
        "session_id"
    ]
    workflow_id = client.post(
        f"/api/workflows?session_id={session_id}", json=WORKFLOW, headers=alice
    ).json()["workflow_id"]
    execution_id = client.post(
        f"/api/executions?session_id={session_id}",
        json={"workflow_id": workflow_id, "inputs": {}},
        headers=alice,
    ).json()["execution_id"]

    ids = {"sid": session_id, "wid": workflow_id, "eid": execution_id}
    return gateway, client, alice, bob, ids


#: Every session-scoped route, as (method, url template). Enumerated from the
#: source with an AST sweep rather than by hand -- the hand-written list in the
#: issue missed `GET /api/executions` and `GET /api/schemas/workflows/...`,
#: which is exactly the sibling-left-unguarded failure the sweep exists to
#: catch. Destructive routes are last so they do not invalidate the ids above.
SESSION_SCOPED_ROUTES = [
    ("GET", "/api/sessions/{sid}"),
    ("GET", "/api/workflows/{wid}?session_id={sid}"),
    ("GET", "/api/workflows?session_id={sid}"),
    ("GET", "/api/executions/{eid}?session_id={sid}"),
    ("GET", "/api/executions?session_id={sid}"),
    ("GET", "/api/schemas/workflows/{wid}?session_id={sid}"),
    ("GET", "/api/events/recent?session_id={sid}"),
    ("DELETE", "/api/executions/{eid}?session_id={sid}"),
    ("DELETE", "/api/sessions/{sid}"),
]


class TestEverySessionScopedRouteChecksOwnership:
    """Both polarities, every route. The owner row is the discrimination control."""

    @pytest.mark.parametrize("method,template", SESSION_SCOPED_ROUTES)
    def test_non_owner_is_refused(self, gated, method, template):
        _, client, _, bob, ids = gated
        response = client.request(method, template.format(**ids), headers=bob)

        assert response.status_code == 404, (
            f"{method} {template} let a non-owner through: "
            f"{response.status_code} {response.text[:200]}"
        )

    @pytest.mark.parametrize("method,template", SESSION_SCOPED_ROUTES)
    def test_owner_still_succeeds(self, gated, method, template):
        """THE CONTROL. Without this row, refusing everybody would look green."""
        _, client, alice, _, ids = gated
        response = client.request(method, template.format(**ids), headers=alice)

        assert response.status_code == 200, (
            f"{method} {template} refused the session's own owner: "
            f"{response.status_code} {response.text[:200]}"
        )

    def test_mutating_routes_both_polarities(self, gated):
        """The two POSTs, which the parametrized table cannot express."""
        _, client, alice, bob, ids = gated
        sid = ids["sid"]

        assert (
            client.post(
                f"/api/workflows?session_id={sid}", json=WORKFLOW, headers=bob
            ).status_code
            == 404
        )
        owner = client.post(
            f"/api/workflows?session_id={sid}", json=WORKFLOW, headers=alice
        )
        assert owner.status_code == 200, owner.text

        wid = owner.json()["workflow_id"]
        assert (
            client.post(
                f"/api/executions?session_id={sid}",
                json={"workflow_id": wid, "inputs": {}},
                headers=bob,
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/executions?session_id={sid}",
                json={"workflow_id": wid, "inputs": {}},
                headers=alice,
            ).status_code
            == 200
        )

    def test_refusal_does_not_confirm_the_session_exists(self, gated):
        """404, not 403 -- otherwise every route is a session-id oracle.

        A non-owner must not be able to tell a real session id from one that
        was never issued, so both answers must be byte-identical.
        """
        _, client, _, bob, ids = gated

        real = client.get(f"/api/sessions/{ids['sid']}", headers=bob)
        fake = client.get(
            "/api/sessions/00000000-0000-0000-0000-000000000000", headers=bob
        )

        assert real.status_code == fake.status_code == 404
        assert real.json() == fake.json(), (
            "the two answers differ, so the route is a membership oracle: "
            f"{real.json()} vs {fake.json()}"
        )


class TestTheIssueAttackTrace:
    """The exact sequence from #2145, end to end."""

    def test_bob_can_no_longer_execute_code_in_alices_session(self, gated):
        _, client, alice, bob, ids = gated
        sid = ids["sid"]

        injected = client.post(
            f"/api/workflows?session_id={sid}",
            json={
                "name": "bobs_workflow",
                "nodes": [
                    {
                        "id": "n",
                        "type": "PythonCodeNode",
                        "config": {"name": "n", "code": "result = {'pwned': True}"},
                    }
                ],
                "connections": [],
            },
            headers=bob,
        )
        assert injected.status_code == 404, injected.text

        assert client.delete(f"/api/sessions/{sid}", headers=bob).status_code == 404
        # And alice's session survived bob's attempt to close it.
        assert client.get(f"/api/sessions/{sid}", headers=alice).status_code == 200


class TestSessionListIsScopedToTheCaller:
    """`GET /api/sessions` was the attacker's target directory."""

    def test_each_caller_sees_only_their_own(self, gated):
        gateway, client, alice, bob, ids = gated
        bob_session = client.post("/api/sessions", json={}, headers=bob).json()[
            "session_id"
        ]

        alice_view = client.get("/api/sessions", headers=alice).json()
        bob_view = client.get("/api/sessions", headers=bob).json()

        alice_ids = {s["session_id"] for s in alice_view["sessions"]}
        bob_ids = {s["session_id"] for s in bob_view["sessions"]}

        assert ids["sid"] in alice_ids
        assert (
            bob_session not in alice_ids
        ), f"alice enumerated bob's session: {alice_ids}"
        assert bob_session in bob_ids, "the control failed: bob cannot see his own"
        assert ids["sid"] not in bob_ids

    def test_owners_are_not_disclosed_to_other_users(self, gated):
        _, client, _, bob, ids = gated
        listing = client.get("/api/sessions", headers=bob).json()

        assert all(
            s["user_id"] == "bob" for s in listing["sessions"]
        ), f"another user's owner leaked through the listing: {listing}"


class TestUnclaimedSessionsAreRefused:
    """An ownerless session is legacy state, not a wildcard."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("owner", ["", None])
    async def test_ownerless_session_is_refused_with_a_named_condition(self, owner):
        gateway = APIGateway(title="ownerless-test")
        client = TestClient(gateway.app)
        alice = _bearer(gateway, "alice")

        # Created directly on the middleware: since #2102 the HTTP surface
        # cannot produce one of these, which is precisely why it is legacy.
        session_id = await gateway.agent_ui.create_session(user_id=owner)

        response = client.get(f"/api/sessions/{session_id}", headers=alice)

        assert response.status_code == 403, (
            "an empty owner was treated as a wildcard matching every caller: "
            f"{response.status_code} {response.text[:200]}"
        )
        assert "no recorded owner" in response.json()["detail"]


class TestOpenDeploymentContractUnchanged:
    """`enable_auth=False` / `require_auth=False` have no identities to own by."""

    def test_ownership_is_not_enforced_and_says_so_once(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            gateway = APIGateway(title="open-test", enable_auth=False)

        assert any(
            "session_ownership_unenforced" in r.getMessage() for r in caplog.records
        ), (
            "an open deployment must announce that ownership is unenforced: "
            f"{[r.getMessage() for r in caplog.records]}"
        )

        client = TestClient(gateway.app)
        session_id = client.post("/api/sessions", json={"user_id": "alice"}).json()[
            "session_id"
        ]
        # Anyone may drive it, which is this configuration's documented contract.
        assert client.get(f"/api/sessions/{session_id}").status_code == 200
        assert client.get("/api/sessions").json()["total"] == 1

    def test_require_auth_false_behaves_the_same(self):
        gateway = APIGateway(title="open-test-2", require_auth=False)
        client = TestClient(gateway.app)
        session_id = client.post("/api/sessions", json={"user_id": "alice"}).json()[
            "session_id"
        ]
        assert client.get(f"/api/sessions/{session_id}").status_code == 200


class TestRealtimeRoutesAreSessionScoped:
    """`/ws` and `/events` take `session_id` too, and #2139's pin did not cover it.

    ``ConnectionManager.send_to_session`` walks ``session_connections[session_id]``
    and calls ``send_to_connection`` DIRECTLY, never evaluating the
    ``EventFilter`` -- so pinning ``user_id`` to the principal (the #2151 fix)
    left this path open. Measured before this fix, alice on
    ``?session_id=<bob's session>``::

        send_to_session(bob) delivered to 1 connection(s)
        ALICE'S SOCKET RECEIVED: {"body": "bob-session-only payload"}
    """

    def test_websocket_both_polarities(self, gated):
        from starlette.websockets import WebSocketDisconnect

        _, client, alice, bob, ids = gated
        sid = ids["sid"]

        # THE CONTROL: the owner's handshake still completes.
        with client.websocket_connect(f"/ws?session_id={sid}", headers=alice):
            pass

        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"/ws?session_id={sid}", headers=bob):
                pass
        assert excinfo.value.code == 1008, "expected a POLICY VIOLATION close"

    def test_sse_non_owner_is_refused(self, gated):
        _, client, _, bob, ids = gated
        response = client.get(f"/events?session_id={ids['sid']}", headers=bob)

        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_sse_owner_still_streams(self, gated):
        """THE CONTROL for `/events`, driven against the raw ASGI app.

        The SSE generator loops forever on a heartbeat, so neither HTTP client
        can close a successful stream; this takes the first body chunk and
        cancels, which is what a real client disconnecting does.
        """
        import asyncio

        gateway, _, alice, _, ids = gated
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/events",
            "raw_path": b"/events",
            "root_path": "",
            "query_string": f"session_id={ids['sid']}".encode(),
            "headers": [
                (b"host", b"testserver"),
                (b"authorization", alice["Authorization"].encode()),
            ],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        started = asyncio.Event()
        status: list[int] = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                status.append(message["status"])
            elif message["type"] == "http.response.body":
                started.set()

        task = asyncio.create_task(gateway.app(scope, receive, send))
        try:
            await asyncio.wait_for(started.wait(), timeout=10)
        finally:
            task.cancel()

        assert status == [200], f"the owner's own stream was refused: {status!r}"


class TestWebhookSubscriptionIsScopedToTheCaller:
    """`POST /api/webhooks` — the THIRD subscription surface.

    `/ws` and `/events` were scoped to the principal by #2151 and this issue,
    but a webhook consults no connection registry: it is registered once and
    delivered to forever after, so neither fix reaches it. Registered with an
    all-unset ``EventFilter`` it matched every event from every user, because
    ``EventFilter.matches`` SKIPS each unset criterion
    (``events.py``: ``if self.user_id and event.user_id != self.user_id``).

    Measured before the fix::

        EventFilter().matches(<an event owned by bob>) = True
    """

    def test_registration_scopes_the_filter_to_the_principal(self, gated):
        gateway, client, alice, _, _ = gated

        response = client.post(
            "/api/webhooks",
            json={"url": "https://alice.example/hook", "event_types": []},
            headers=alice,
        )
        assert response.status_code == 200, response.text

        webhook_id = response.json()["webhook_id"]
        registered = gateway.realtime.webhook_manager.webhooks[webhook_id]
        event_filter = registered["event_filter"]

        assert event_filter.user_id == "alice", (
            "the webhook filter was left unscoped, so it matches every user's "
            f"events: user_id={event_filter.user_id!r}"
        )

    def test_the_scoped_filter_actually_rejects_another_users_event(self, gated):
        """The filter is only worth anything if it REJECTS — assert on matches()."""
        gateway, client, alice, _, _ = gated

        webhook_id = client.post(
            "/api/webhooks",
            json={"url": "https://alice.example/hook", "event_types": []},
            headers=alice,
        ).json()["webhook_id"]
        event_filter = gateway.realtime.webhook_manager.webhooks[webhook_id][
            "event_filter"
        ]

        class _Event:
            type = None
            priority = None
            source = None
            target = None
            session_id = "bob-session"
            user_id = "bob"

        class _OwnEvent(_Event):
            session_id = "alice-session"
            user_id = "alice"

        assert (
            event_filter.matches(_Event()) is False
        ), "the webhook still matches another user's event"
        # THE CONTROL: it must still match the subscriber's OWN events, or a
        # filter that rejects everything would look identical to a correct one.
        assert event_filter.matches(_OwnEvent()) is True

    def test_open_deployment_keeps_the_unscoped_filter(self):
        gateway = APIGateway(title="open-webhook", enable_auth=False)
        client = TestClient(gateway.app)

        webhook_id = client.post(
            "/api/webhooks", json={"url": "https://x.example/h", "event_types": []}
        ).json()["webhook_id"]
        event_filter = gateway.realtime.webhook_manager.webhooks[webhook_id][
            "event_filter"
        ]

        assert event_filter.user_id is None


class TestRecentEventsAreScopedToTheCaller:
    """`/api/events/recent` without a `session_id` returned everyone's events."""

    def test_events_are_filtered_to_the_principal(self, gated):
        gateway, client, alice, bob, ids = gated

        alice_events = client.get("/api/events/recent", headers=alice).json()
        bob_events = client.get("/api/events/recent", headers=bob).json()

        foreign = [
            e for e in alice_events["events"] if e.get("user_id") not in (None, "alice")
        ]
        assert not foreign, f"alice received another user's events: {foreign[:2]}"
        assert all(
            e.get("user_id") in (None, "bob") for e in bob_events["events"]
        ), "the control failed: bob's own listing is not scoped to bob"
