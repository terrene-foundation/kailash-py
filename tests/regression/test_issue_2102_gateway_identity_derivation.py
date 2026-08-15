"""Regression: the gateway took a principal from a request field (#2102).

``POST /api/sessions`` read its session owner from the POST body's ``user_id``.
``GET /events`` and ``WS /ws`` read their subscription identity from a
``user_id`` QUERY parameter -- and that value is not a label, it is handed to
``EventFilter``, so it decides whose events the stream receives.

Measured on the pre-fix source, with a VALID bearer token for ``alice``
presented on a default ``APIGateway()``::

    POST /api/sessions  {"user_id": "attacker-chosen"}   Authorization: Bearer <alice>
    -> 200 {"user_id": "attacker-chosen", ...}

Two defects stacked to produce that. The dependency ran
``await self.auth_manager.verify_token(token)``, but ``JWTAuthManager``'s
``verify_token`` is SYNC while ``MiddlewareAuthManager``'s is ASYNC, so with
the manager this class constructs BY DEFAULT every verification raised
``TypeError: object dict can't be used in 'await' expression`` and resolved to
"no principal". And the claim it then read was ``payload.get("user_id")``,
while every token this SDK mints carries the subject as ``sub`` -- so even with
the await fixed the derived identity would have been empty.

The tests below pin BOTH polarities per route, through the HTTP and WebSocket
surfaces rather than by calling the dependency directly, because the defect
lived in how the route WIRED the dependency, which a direct call cannot see.
"""

import pytest

pytest.importorskip("fastapi", reason="gateway tests require the `server` extra")
pytest.importorskip("jwt", reason="PyJWT is required to mint the test credentials")

from fastapi.testclient import TestClient  # noqa: E402

from kailash.middleware.communication.api_gateway import APIGateway  # noqa: E402

#: 48 bytes, over the 32-byte floor `APIGateway` enforces on this variable.
GATEWAY_SECRET = "test-gateway-secret-" + "x" * 28


@pytest.fixture(autouse=True)
def gateway_secret(monkeypatch):
    """Every auth-enabled gateway below needs a signing secret to construct."""
    monkeypatch.setenv("KAILASH_API_GATEWAY_SECRET", GATEWAY_SECRET)


def _client(gateway: APIGateway) -> TestClient:
    return TestClient(gateway.app)


def _bearer(gateway: APIGateway, user_id: str) -> dict:
    """A credential this gateway itself minted, for ``user_id``."""
    token = gateway.auth_manager.create_access_token(user_id=user_id)
    return {"Authorization": f"Bearer {token}"}


class TestSessionRouteIdentityIsServerDerived:
    """``POST /api/sessions`` -- the site the issue named."""

    def test_verified_principal_beats_the_body_field(self):
        """The headline case: alice's token, attacker's body, alice's session."""
        gateway = APIGateway(title="test")
        response = _client(gateway).post(
            "/api/sessions",
            json={"user_id": "attacker-chosen"},
            headers=_bearer(gateway, "alice"),
        )

        assert response.status_code == 200, response.text
        assert response.json()["user_id"] == "alice", (
            "the session owner came from the request body, not the credential: "
            f"{response.text}"
        )

    def test_no_credential_is_refused_rather_than_trusted(self):
        """The other polarity: with auth required, absence is a 401, not a fallback."""
        gateway = APIGateway(title="test")
        response = _client(gateway).post(
            "/api/sessions", json={"user_id": "attacker-chosen"}
        )

        assert response.status_code == 401, response.text

    def test_route_refuses_even_when_the_gate_is_delegated_outside(self):
        """``external_auth_reason`` installs NO gate here, so the ROUTE must refuse.

        This is the case that proves the refusal lives at the identity site and
        not only in the middleware: nothing rejects the request before the
        handler runs, and the handler still must not read the body.
        """
        gateway = APIGateway(title="test", external_auth_reason="fronted by istio")
        response = _client(gateway).post(
            "/api/sessions", json={"user_id": "attacker-chosen"}
        )

        assert response.status_code == 401, response.text
        assert "verified credential" in response.json()["detail"]

    def test_delegated_gate_still_derives_the_identity_from_the_token(self):
        gateway = APIGateway(title="test", external_auth_reason="fronted by istio")
        response = _client(gateway).post(
            "/api/sessions",
            json={"user_id": "attacker-chosen"},
            headers=_bearer(gateway, "alice"),
        )

        assert response.status_code == 200, response.text
        assert response.json()["user_id"] == "alice"


class TestOpenDeploymentContractIsUnchanged:
    """``enable_auth=False`` and ``require_auth=False`` are EXPLICIT opt-outs.

    They are the documented way to run this gateway open, and
    ``resolve_server_auth`` already announces that exposure loudly at
    construction. Refusing here would break an operator who said what they
    wanted in the words available to them -- the same reasoning that makes
    ``require_auth`` tri-state (issue #636's contract, #2072's resolution).
    """

    def test_enable_auth_false_keeps_the_body_value_as_the_identity(self):
        gateway = APIGateway(title="test", enable_auth=False)
        response = _client(gateway).post("/api/sessions", json={"user_id": "whoever"})

        assert response.status_code == 200, response.text
        assert response.json()["user_id"] == "whoever"

    def test_require_auth_false_keeps_the_body_value_as_the_identity(self):
        gateway = APIGateway(title="test", require_auth=False)
        response = _client(gateway).post("/api/sessions", json={"user_id": "whoever"})

        assert response.status_code == 200, response.text
        assert response.json()["user_id"] == "whoever"

    def test_a_presented_credential_still_wins_on_an_open_deployment(self):
        """Open does not mean "ignore credentials": a verified one is still the truth."""
        gateway = APIGateway(title="test", require_auth=False)
        response = _client(gateway).post(
            "/api/sessions",
            json={"user_id": "attacker-chosen"},
            headers=_bearer(gateway, "alice"),
        )

        assert response.status_code == 200, response.text
        assert response.json()["user_id"] == "alice"


class TestSiblingSweepRealtimeRoutes:
    """``/ws`` and ``/events``: the same field, reached through the query string.

    ``user_id`` there is a SUBSCRIPTION FILTER. An authenticated caller passing
    ``?user_id=<somebody else>`` subscribed to that user's event stream, which
    is the same identity-derivation defect with a confidentiality consequence.
    """

    def test_websocket_ignores_the_query_user_id_in_favour_of_the_principal(self):
        gateway = APIGateway(title="test")
        client = _client(gateway)

        with client.websocket_connect(
            "/ws?user_id=victim", headers=_bearer(gateway, "alice")
        ):
            registry = gateway.realtime.connection_manager.user_connections
            assert (
                "alice" in registry
            ), f"the socket was not registered under the principal: {registry!r}"
            assert "victim" not in registry, (
                "the socket subscribed to another user's events from a query "
                f"parameter: {registry!r}"
            )

    def test_websocket_without_a_credential_is_refused(self):
        """The gate refuses the handshake; the route never runs."""
        from starlette.websockets import WebSocketDisconnect

        gateway = APIGateway(title="test")
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with _client(gateway).websocket_connect("/ws?user_id=victim"):
                pass

        assert excinfo.value.code == 1008, "expected a POLICY VIOLATION close"

    def test_websocket_query_user_id_survives_on_an_open_deployment(self):
        gateway = APIGateway(title="test", require_auth=False)
        client = _client(gateway)

        with client.websocket_connect("/ws?user_id=anonymous-picked"):
            registry = gateway.realtime.connection_manager.user_connections
            assert "anonymous-picked" in registry

    @pytest.mark.asyncio
    async def test_sse_stream_is_filtered_by_the_principal_not_the_query(self):
        """Driven against the raw ASGI app, and cancelled by this test.

        Neither HTTP client works here, and the reason is in the route rather
        than in the test: the SSE generator loops forever on a 30-second
        heartbeat and never completes, so both ``TestClient`` and
        ``httpx.ASGITransport`` block waiting for an app task that has no end.
        Calling ``gateway.app`` directly lets this test take the first body
        chunk -- which is emitted AFTER the stream registers itself, so it is
        proof of registration -- and then cancel, which is what a real client
        disconnecting does.
        """
        import asyncio

        gateway = APIGateway(title="test")
        headers = _bearer(gateway, "alice")
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/events",
            "raw_path": b"/events",
            "root_path": "",
            "query_string": b"user_id=victim",
            "headers": [
                (b"host", b"testserver"),
                (b"authorization", headers["Authorization"].encode()),
            ],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }

        first_body_chunk = asyncio.Event()
        status: list[int] = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                status.append(message["status"])
            elif message["type"] == "http.response.body":
                first_body_chunk.set()

        task = asyncio.create_task(gateway.app(scope, receive, send))
        try:
            await asyncio.wait_for(first_body_chunk.wait(), timeout=10)
            registered = [
                stream["user_id"]
                for stream in gateway.realtime.sse_manager.streams.values()
            ]
        finally:
            task.cancel()

        assert status == [200], f"the stream never started: {status!r}"
        assert registered == [
            "alice"
        ], f"the SSE stream was filtered by a query parameter: {registered!r}"

    def test_sse_without_a_credential_is_refused(self):
        gateway = APIGateway(title="test")
        response = _client(gateway).get("/events?user_id=victim")

        assert response.status_code == 401, response.text


class TestSubjectClaimPrecedenceIsShared:
    """The identity comes from ``sub``, through ONE helper.

    The gateway's own first attempt read ``payload.get("user_id")`` alone,
    which is ``None`` for every token this SDK mints. Both callers now share
    ``kailash.trust.auth.jwt.subject_from_claims``.
    """

    def test_sub_is_preferred_and_alternatives_are_accepted(self):
        from kailash.trust.auth.jwt import subject_from_claims

        assert subject_from_claims({"sub": "alice", "user_id": "bob"}) == "alice"
        assert subject_from_claims({"user_id": "bob"}) == "bob"
        assert subject_from_claims({"uid": "carol"}) == "carol"

    def test_a_numeric_subject_is_rendered_not_rejected(self):
        from kailash.trust.auth.jwt import subject_from_claims

        assert subject_from_claims({"sub": 12345}) == "12345"

    def test_structural_and_empty_claims_yield_no_principal(self):
        from kailash.trust.auth.jwt import subject_from_claims

        assert subject_from_claims({}) is None
        assert subject_from_claims({"sub": ""}) is None
        assert subject_from_claims({"sub": {"nested": "object"}}) is None
        assert subject_from_claims({"sub": ["alice"]}) is None
        assert (
            subject_from_claims({"sub": True}) is None
        ), "`True` is an int subclass but it is not an identity"

    def test_the_gateway_derives_the_subject_the_validator_would(self):
        """One precedence, two callers -- pinned against drift.

        The gate's normalizer and the gateway's direct-verification path must
        agree on the same token, which is exactly what a second copy of the
        precedence would silently stop doing.
        """
        from kailash.trust.auth.jwt import JWTConfig as TrustJWTConfig
        from kailash.trust.auth.jwt import JWTValidator

        gateway = APIGateway(title="test")
        token = gateway.auth_manager.create_access_token(user_id="alice")
        claims = gateway.auth_manager.verify_token(token)

        validator = JWTValidator(
            TrustJWTConfig(
                secret=GATEWAY_SECRET,
                algorithm="HS256",
                issuer="kailash-gateway",
                audience="kailash-api",
            )
        )
        assert validator.create_user_from_payload(claims).user_id == "alice"

        response = _client(gateway).post(
            "/api/sessions", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["user_id"] == "alice"


class TestVerifyTokenIsAwaitedOnlyWhenAwaitable:
    """The sync/async split between the two managers in this SDK.

    ``JWTAuthManager.verify_token`` is sync, ``MiddlewareAuthManager``'s is
    async. Awaiting unconditionally is what made the DEFAULT manager's every
    verification raise ``TypeError`` and silently resolve to "no principal".
    """

    @pytest.mark.asyncio
    async def test_a_sync_manager_resolves_a_principal(self):
        gateway = APIGateway(title="test")
        token = gateway.auth_manager.create_access_token(user_id="alice")

        class _Connection:
            state = None
            headers = {"Authorization": f"Bearer {token}"}

        assert await gateway._authenticated_user_id(_Connection()) == "alice"

    @pytest.mark.asyncio
    async def test_an_async_manager_resolves_a_principal(self):
        """`MiddlewareAuthManager` is the async shape, and is a real one."""
        from kailash.middleware.auth.auth_manager import MiddlewareAuthManager

        manager = MiddlewareAuthManager(
            secret_key=GATEWAY_SECRET, enable_audit=False, database_url=None
        )
        gateway = APIGateway(title="test", auth_manager=manager, require_auth=False)
        token = await manager.create_access_token("alice")

        class _Connection:
            state = None
            headers = {"Authorization": f"Bearer {token}"}

        assert await gateway._authenticated_user_id(_Connection()) == "alice"
