# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2108 -- API-key authentication could never succeed.

``MiddlewareAuthManager`` issued and verified API keys through
``CredentialManagerNode``, which cannot store anything. Measured on the loaded
methods before the fix, not inferred::

    create_api_key -> NodeExecutionError: Node 'CredentialManagerNode' execution
                      failed: ValueError: Credential 'api_credentials' not found
                      in any configured source
    verify_api_key -> HTTPException 401 Invalid API key

Two independent defects produced that:

* ``CredentialManagerNode.run()`` took ``**inputs`` and read NONE of it -- and
  could not have, because ``get_parameters()`` returned ``{}`` and
  ``Node.execute`` drops every keyword it does not find there. Measured::

      [NODE] Unknown parameter(s) for CredentialManagerNode:
      ['credential_name', ..., 'operation']. Valid parameters: [].

  So ``operation=`` and ``credential_name=`` were both discarded
  (``zero-tolerance.md`` Rule 3c).

* The node's return dict is ``{credentials, source, validated, masked_display,
  metadata}`` -- there is **no** ``success`` key on any path, so
  ``result.get("success", False)`` was unconditionally False and
  ``verify_api_key`` always raised 401.

Why it went unnoticed: no test in the tree exercised either method
(``grep -rn 'verify_api_key\\|create_api_key' tests/`` returned nothing), and the
FastAPI dependency tries its bearer branch first, which satisfied every existing
test.

Both polarities are asserted throughout -- an ISSUED key authenticates AND an
unissued/revoked/expired one is refused. A suite with only the negative half is
exactly what let a path that can only reject look healthy for this long.

No ``Mock`` appears in this file: a mocked store would accept every call and
pass identically against the broken implementation.
"""

from datetime import datetime, timedelta, timezone

import pytest
from starlette.exceptions import HTTPException

from kailash.middleware.auth.auth_manager import MiddlewareAuthManager
from kailash.nodes.security import CredentialManagerNode

pytestmark = pytest.mark.regression

_SECRET = "issue-2108-regression-secret-key-at-least-32-bytes"


@pytest.fixture
def manager():
    """An auth manager with API keys on and audit off.

    Audit is off so a failure here is attributable to the API-key path rather
    than to ``AuditLogNode``'s own backend requirements.
    """
    return MiddlewareAuthManager(
        secret_key=_SECRET, enable_api_keys=True, enable_audit=False
    )


# ---------------------------------------------------------------------------
# The load-bearing pair: an issued key works, an unissued one does not.
# ---------------------------------------------------------------------------


async def test_issued_api_key_authenticates(manager):
    """LOAD-BEARING. The positive polarity the old suite could not express.

    Pre-fix ``create_api_key`` raised ``NodeExecutionError`` before returning a
    key at all.
    """
    api_key = await manager.create_api_key(
        user_id="u-1", key_name="ci-runner", permissions=["workflow:execute"]
    )

    assert api_key.startswith("sk_")

    metadata = await manager.verify_api_key(api_key)

    assert metadata["user_id"] == "u-1"
    assert metadata["key_name"] == "ci-runner"
    assert metadata["permissions"] == ["workflow:execute"]


async def test_unissued_api_key_is_rejected(manager):
    """CONTROL for the test above: a key that was never issued gets 401.

    Without this, ``verify_api_key`` returning metadata could equally mean it
    accepts anything.
    """
    with pytest.raises(HTTPException) as excinfo:
        await manager.verify_api_key("sk_never-issued-by-anyone")

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid API key"


async def test_revoked_api_key_is_rejected(manager):
    """A revoked key stops authenticating -- and revocation reports what it did."""
    api_key = await manager.create_api_key(user_id="u-2", key_name="temp")
    assert (await manager.verify_api_key(api_key))["user_id"] == "u-2"

    assert await manager.revoke_api_key(api_key) is True

    with pytest.raises(HTTPException) as excinfo:
        await manager.verify_api_key(api_key)
    assert excinfo.value.status_code == 401

    # Revoking again is not an error: the end state is the same, and raising
    # would tell a caller whether a key had ever existed.
    assert await manager.revoke_api_key(api_key) is False


async def test_expired_api_key_is_rejected(manager):
    """An expired key fails closed without needing a sweeper to have run."""
    api_key = await manager.create_api_key(
        user_id="u-3",
        key_name="short-lived",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    with pytest.raises(HTTPException) as excinfo:
        await manager.verify_api_key(api_key)
    assert excinfo.value.status_code == 401


async def test_unexpired_key_with_future_expiry_still_works(manager):
    """CONTROL for the expiry test: the expiry check must not reject everything."""
    api_key = await manager.create_api_key(
        user_id="u-4",
        key_name="long-lived",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert (await manager.verify_api_key(api_key))["user_id"] == "u-4"


async def test_two_keys_do_not_authenticate_as_each_other(manager):
    """Each key resolves to its OWN principal.

    A store that returned the first (or any) record would pass every test above
    while granting one user's key another user's identity.
    """
    key_a = await manager.create_api_key(user_id="alice", key_name="a")
    key_b = await manager.create_api_key(user_id="bob", key_name="b")

    assert (await manager.verify_api_key(key_a))["user_id"] == "alice"
    assert (await manager.verify_api_key(key_b))["user_id"] == "bob"


# ---------------------------------------------------------------------------
# Storage invariants
# ---------------------------------------------------------------------------


async def test_plaintext_key_is_never_stored(manager):
    """The store holds a salted digest, so a dump leaks nothing presentable."""
    api_key = await manager.create_api_key(user_id="u-5", key_name="k")

    store = manager._api_key_store
    dump = repr(store.__dict__)
    assert api_key not in dump
    assert store.count() == 1

    from kailash.middleware.auth.api_keys import split_api_key

    key_id, secret = split_api_key(api_key)

    # The SECRET half is absent from the store in every form; only the public
    # id and the salted digest are present.
    assert secret not in dump
    record = store.lookup(key_id=key_id)
    assert record is not None
    assert record.secret_digest and record.secret_digest != secret

    # And the record the caller receives on a successful verification carries
    # no verification material at all.
    returned = await manager.verify_api_key(api_key)
    assert "secret_digest" not in returned
    assert "salt" not in returned


async def test_api_keys_disabled_refuses_every_operation():
    """``enable_api_keys=False`` refuses all three, and holds no store."""
    manager = MiddlewareAuthManager(
        secret_key=_SECRET, enable_api_keys=False, enable_audit=False
    )
    assert manager._api_key_store is None

    for coro in (
        manager.create_api_key(user_id="u", key_name="k"),
        manager.verify_api_key("sk_anything"),
        manager.revoke_api_key("sk_anything"),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await coro
        assert excinfo.value.status_code == 400


async def test_injected_store_is_used(manager):
    """A shared backend is the documented multi-worker answer -- so it must work.

    Two managers sharing one store: a key issued through the first authenticates
    through the second, which is the whole point of the injection point.
    """
    from kailash.middleware.auth.api_keys import InMemoryAPIKeyStore

    shared = InMemoryAPIKeyStore()
    worker_a = MiddlewareAuthManager(
        secret_key=_SECRET, enable_audit=False, api_key_store=shared
    )
    worker_b = MiddlewareAuthManager(
        secret_key=_SECRET, enable_audit=False, api_key_store=shared
    )

    api_key = await worker_a.create_api_key(user_id="u-6", key_name="shared")
    assert (await worker_b.verify_api_key(api_key))["user_id"] == "u-6"

    # And the DEFAULT store is process-local, which is the fail-CLOSED direction:
    # a manager that does not share the store refuses the key.
    with pytest.raises(HTTPException):
        await manager.verify_api_key(api_key)


async def test_store_failure_fails_closed(manager):
    """A store outage must refuse, never admit."""
    from kailash.middleware.auth.api_keys import APIKeyStore

    class BrokenStore(APIKeyStore):
        def store(self, *, key_id, record):
            raise RuntimeError("backend down")

        def lookup(self, *, key_id):
            raise RuntimeError("backend down")

        def revoke(self, *, key_id):
            raise RuntimeError("backend down")

    broken = MiddlewareAuthManager(
        secret_key=_SECRET, enable_audit=False, api_key_store=BrokenStore()
    )

    with pytest.raises(HTTPException) as verify_exc:
        await broken.verify_api_key("sk_whatever")
    assert verify_exc.value.status_code == 401

    # Creation reports failure rather than handing back a key that can never
    # authenticate -- which is the #2108 shape pointed the other way.
    with pytest.raises(HTTPException) as create_exc:
        await broken.create_api_key(user_id="u", key_name="k")
    assert create_exc.value.status_code == 500


# ---------------------------------------------------------------------------
# The FastAPI dependency -- the reachable surface.
# ---------------------------------------------------------------------------


async def test_x_api_key_header_authenticates_through_the_dependency(manager):
    """End-to-end on the real dependency, via a real request scope.

    ``get_current_user_dependency`` reads ``user_id`` and ``permissions`` off
    the verification result, so this pins the RETURN SHAPE as well as the
    outcome: a store that verified correctly but returned a differently-shaped
    dict would still produce an unusable principal.
    """
    from starlette.requests import Request

    api_key = await manager.create_api_key(
        user_id="u-7", key_name="dep", permissions=["read"]
    )
    verify_user = manager.get_current_user_dependency()

    def _request(header_value):
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"x-api-key", header_value.encode("latin-1"))],
                "query_string": b"",
            }
        )

    user = await verify_user(_request(api_key), credentials=None)
    assert user["user_id"] == "u-7"
    assert user["permissions"] == ["read"]

    # CONTROL: a wrong key on the same path is refused.
    with pytest.raises(HTTPException) as excinfo:
        await verify_user(_request("sk_wrong"), credentials=None)
    assert excinfo.value.status_code == 401


async def test_public_key_id_alone_does_not_authenticate(manager):
    """The key_id half is PUBLIC -- it must authorize nothing on its own.

    Splitting a key into a public id and a secret is what lets the store be
    addressed by a non-credential and lets an audit log name a key. That is only
    safe if presenting a real key_id with a wrong secret is refused, so this is
    the test that makes the design sound rather than merely convenient.
    """
    from kailash.middleware.auth.api_keys import split_api_key

    api_key = await manager.create_api_key(user_id="u-8", key_name="split")
    key_id, secret = split_api_key(api_key)

    for forged in (
        f"sk_{key_id}.wrong-secret",
        f"sk_{key_id}.",
        f"sk_{key_id}",
        f"sk_{key_id}.{secret[:-1]}",
    ):
        with pytest.raises(HTTPException) as excinfo:
            await manager.verify_api_key(forged)
        assert excinfo.value.status_code == 401, forged

    # CONTROL: the intact key still works, so the refusals above are the secret
    # check and not a broken parser.
    assert (await manager.verify_api_key(api_key))["user_id"] == "u-8"


async def test_malformed_keys_are_refused_without_raising(manager):
    """A malformed key is a failed authentication, not a server fault."""
    for malformed in ("", "not-a-key", "sk_", "sk_.", ".", "sk_no-separator"):
        with pytest.raises(HTTPException) as excinfo:
            await manager.verify_api_key(malformed)
        assert excinfo.value.status_code == 401, malformed


async def test_revocation_requires_the_secret_not_just_the_id(manager):
    """Revoking on a public id alone would be credential-free denial of service.

    The key_id may appear in an audit log by design. If revocation accepted it
    without the secret, anyone who read that log could disable another
    principal's key.
    """
    from kailash.middleware.auth.api_keys import split_api_key

    api_key = await manager.create_api_key(user_id="u-9", key_name="revoke")
    key_id, _ = split_api_key(api_key)

    assert await manager.revoke_api_key(f"sk_{key_id}.wrong-secret") is False
    # Still live: the forged revocation changed nothing.
    assert (await manager.verify_api_key(api_key))["user_id"] == "u-9"

    # CONTROL: with the real secret it revokes.
    assert await manager.revoke_api_key(api_key) is True
    with pytest.raises(HTTPException):
        await manager.verify_api_key(api_key)


def test_secret_digest_is_salted_per_record():
    """Two records with the same secret must not share a digest."""
    from kailash.middleware.auth.api_keys import derive_secret_digest, generate_salt

    secret = "the-same-secret-value"
    first = derive_secret_digest(secret, generate_salt())
    second = derive_secret_digest(secret, generate_salt())

    assert first != second
    # Deterministic for a fixed salt, or verification could never succeed.
    salt = generate_salt()
    assert derive_secret_digest(secret, salt) == derive_secret_digest(secret, salt)


def test_generated_keys_are_ascii_and_unique():
    """ASCII keeps keys presentable through the header path that rejects
    non-ASCII (#2114), and uniqueness is what makes key_id a usable address."""
    from kailash.middleware.auth.api_keys import generate_api_key

    seen = set()
    for _ in range(50):
        presented, key_id, secret = generate_api_key()
        assert presented.isascii()
        assert presented == f"sk_{key_id}.{secret}"
        assert key_id not in seen
        seen.add(key_id)


# ---------------------------------------------------------------------------
# The APIGateway session route -- the caller #2103 removed (AC 5).
# ---------------------------------------------------------------------------


@pytest.fixture
def gateway_with_api_keys(manager):
    """A gateway whose injected manager can actually verify API keys.

    ``require_auth=False`` keeps the request-level gate out of the way so the
    measurement is the SESSION ROUTE's principal resolution and nothing else;
    the route is deliberately optional-auth either way.
    """
    from kailash.middleware.communication.api_gateway import APIGateway

    return APIGateway(
        title="issue-2108-gateway",
        enable_auth=True,
        auth_manager=manager,
        require_auth=False,
    )


async def test_session_route_accepts_an_issued_api_key(manager, gateway_with_api_keys):
    """LOAD-BEARING for AC 5: the restored X-API-Key branch resolves a principal.

    The server-derived principal must WIN over the caller-supplied body field --
    which is the whole point of resolving one (#2047 / #2103 bug class).
    """
    from fastapi.testclient import TestClient

    api_key = await manager.create_api_key(user_id="key-owner", key_name="gw")
    client = TestClient(gateway_with_api_keys.app)

    response = client.post(
        "/api/sessions",
        json={"user_id": "attacker-supplied", "metadata": {}},
        headers={"X-API-Key": api_key},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == "key-owner"


async def test_session_route_ignores_a_rejected_api_key(gateway_with_api_keys):
    """CONTROL: a bad key resolves NO principal rather than a wrong one.

    The route is optional-auth, so the request still succeeds -- but on the
    body-supplied identity, exactly as it did before a credential was offered.
    """
    from fastapi.testclient import TestClient

    client = TestClient(gateway_with_api_keys.app)
    response = client.post(
        "/api/sessions",
        json={"user_id": "body-identity", "metadata": {}},
        headers={"X-API-Key": "sk_not-a-real-key"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == "body-identity"


def test_session_route_survives_a_manager_without_api_key_support(caplog):
    """A manager that cannot verify API keys warns ONCE, not once per request.

    ``JWTAuthManager`` -- what ``APIGateway(enable_auth=True)`` builds by
    default -- has no ``verify_api_key``. That is a wiring fact, identical for
    every request, so repeating it per anonymous request would reintroduce the
    #2114 amplification shape on a different route.
    """
    import logging

    from fastapi.testclient import TestClient

    from kailash.middleware.auth.jwt_auth import JWTAuthManager
    from kailash.middleware.communication.api_gateway import APIGateway

    gateway = APIGateway(
        title="issue-2108-default-manager",
        enable_auth=True,
        auth_manager=JWTAuthManager(secret_key=_SECRET),
        require_auth=False,
    )
    client = TestClient(gateway.app)

    with caplog.at_level(logging.DEBUG):
        for _ in range(4):
            response = client.post(
                "/api/sessions",
                json={"user_id": "body-identity", "metadata": {}},
                headers={"X-API-Key": "sk_anything"},
            )
            assert response.status_code == 200, response.text

    unsupported = [
        r
        for r in caplog.records
        if r.getMessage() == "api_gateway.api_key_auth_unsupported"
    ]
    assert (
        len(unsupported) == 1
    ), f"expected exactly one warning, got {len(unsupported)}"


def test_session_route_resolves_a_sync_managers_bearer_token(caplog):
    """A SYNC verifier must work: `JWTAuthManager.verify_token` is not async.

    Measured before the fix::

        JWTAuthManager.verify_token is coroutine fn: False
        await {'a': 1} -> TypeError: object dict can't be used in
                          'await' expression

    The unconditional ``await`` raised, the branch's own ``except Exception``
    swallowed it, and every valid token on the DEFAULT gateway resolved to no
    principal -- so the caller-supplied body identity won. This asserts the
    server-derived subject wins instead, reading the RFC 7519 ``sub`` claim
    that manager actually stamps.
    """
    from fastapi.testclient import TestClient

    from kailash.middleware.auth.jwt_auth import JWTAuthManager
    from kailash.middleware.communication.api_gateway import APIGateway

    auth = JWTAuthManager(secret_key=_SECRET)
    gateway = APIGateway(
        title="issue-2108-sync-manager",
        enable_auth=True,
        auth_manager=auth,
        require_auth=False,
    )
    token = auth.create_access_token(user_id="token-owner")
    if not isinstance(token, str):  # some managers return a token pair
        token = getattr(token, "access_token", token)

    client = TestClient(gateway.app)
    response = client.post(
        "/api/sessions",
        json={"user_id": "attacker-supplied", "metadata": {}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == "token-owner"


# ---------------------------------------------------------------------------
# The sibling call site the AC-4 sweep found: MiddlewareAuthenticationMiddleware.
# ---------------------------------------------------------------------------


def _authentication_middleware(**kwargs):
    from kailash.middleware.auth.access_control import (
        MiddlewareAccessControlManager,
        MiddlewareAuthenticationMiddleware,
    )

    return MiddlewareAuthenticationMiddleware(
        MiddlewareAccessControlManager(enable_audit=False), **kwargs
    )


async def test_authentication_middleware_accepts_a_valid_token(manager):
    """LOAD-BEARING. This path refused EVERY request before the fix.

    It asked ``credential_manager.execute(action=..., token=...)`` for a
    ``"valid"`` key that node returns on no path, through kwargs
    ``Node.execute`` strips -- the #2108 defect at a third call site.
    """
    middleware = _authentication_middleware(token_verifier=manager)
    token = await manager.create_access_token(
        user_id="ctx-user", permissions=["read"], metadata={"team": "platform"}
    )

    authenticated, context = await middleware.authenticate_request(
        {"Authorization": f"Bearer {token}"}, session_id="s-1"
    )

    assert authenticated is True
    assert context is not None
    assert context.user_id == "ctx-user"
    assert context.session_id == "s-1"


async def test_authentication_middleware_rejects_a_bad_token(manager):
    """CONTROL: acceptance above is not "accepts anything"."""
    middleware = _authentication_middleware(token_verifier=manager)

    authenticated, context = await middleware.authenticate_request(
        {"Authorization": "Bearer not-a-real-token"}
    )

    assert authenticated is False
    assert context is None


async def test_authentication_middleware_rejects_a_missing_header(manager):
    """No credential is refused without consulting the verifier at all."""
    middleware = _authentication_middleware(token_verifier=manager)

    assert await middleware.authenticate_request({}) == (False, None)
    assert await middleware.authenticate_request({"Authorization": "Basic x"}) == (
        False,
        None,
    )


async def test_authentication_middleware_without_key_material_fails_closed(caplog):
    """No verifier and no secret: refuse, and say so ONCE with the wiring."""
    import logging

    middleware = _authentication_middleware()

    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            assert await middleware.authenticate_request(
                {"Authorization": "Bearer anything"}
            ) == (False, None)

    warnings = [
        r
        for r in caplog.records
        if r.getMessage() == "middleware_auth.no_token_verifier"
    ]
    assert len(warnings) == 1
    assert "token_verifier" in getattr(warnings[0], "wiring", "")


async def test_authentication_middleware_accepts_a_sync_verifier():
    """A SYNC verifier must work -- `JWTValidator.verify_token` is not async."""
    from kailash.trust.auth.jwt import JWTConfig, JWTValidator

    config = JWTConfig(secret=_SECRET)
    validator = JWTValidator(config)
    middleware = _authentication_middleware(token_verifier=validator)

    # `user_id` becomes the RFC 7519 `sub` claim -- the spelling this manager
    # uses and `MiddlewareAuthManager` does not, which is why the middleware
    # reads both.
    token = validator.create_access_token(user_id="sync-user", roles=["ops"])

    authenticated, context = await middleware.authenticate_request(
        {"Authorization": f"Bearer {token}"}
    )

    assert authenticated is True
    assert context.user_id == "sync-user"


# ---------------------------------------------------------------------------
# CredentialManagerNode's parameter contract (AC 1 -- Rule 3c).
# ---------------------------------------------------------------------------


def test_credential_manager_declares_its_parameters():
    """``get_parameters()`` returning ``{}`` is what silently dropped kwargs."""
    node = CredentialManagerNode(credential_name="probe", name="probe")
    params = node.get_parameters()

    assert set(params) >= {
        "credential_name",
        "credential_type",
        "credential_sources",
        "validate_on_fetch",
    }
    # All optional: `execute()` with no arguments must keep working.
    assert all(not p.required for p in params.values())


def test_credential_manager_honours_credential_name_input(monkeypatch):
    """LOAD-BEARING for AC 1: the passed name decides what is fetched.

    Pre-fix this fetched ``constructed_name`` regardless, because ``execute``
    stripped the keyword and ``run`` read ``self.credential_name``.
    """
    monkeypatch.setenv("CONSTRUCTED_NAME_API_KEY", "constructed-key-value-0123456789")
    monkeypatch.setenv("REQUESTED_NAME_API_KEY", "requested-key-value-0123456789")

    node = CredentialManagerNode(
        credential_name="constructed_name",
        credential_type="api_key",
        credential_sources=["env"],
        name="probe",
        cache_duration_seconds=None,
    )

    result = node.execute(credential_name="requested_name")
    assert result["credentials"]["api_key"] == "requested-key-value-0123456789"

    # CONTROL: with no override the construction-time name still wins, so the
    # change is an override and not a silent redirection.
    assert (
        node.execute()["credentials"]["api_key"] == "constructed-key-value-0123456789"
    )


def test_credential_manager_cache_is_keyed_on_the_effective_name(monkeypatch):
    """Caching must not serve the credential another call asked for.

    With the cache keyed on the construction-time name, the first fetch would
    answer every later call whatever name it passed.
    """
    monkeypatch.setenv("FIRST_NAME_API_KEY", "first-key-value-01234567890123")
    monkeypatch.setenv("SECOND_NAME_API_KEY", "second-key-value-0123456789012")

    node = CredentialManagerNode(
        credential_name="first_name",
        credential_type="api_key",
        credential_sources=["env"],
        name="probe",
        cache_duration_seconds=300,
    )

    assert node.execute()["credentials"]["api_key"] == "first-key-value-01234567890123"
    assert (
        node.execute(credential_name="second_name")["credentials"]["api_key"]
        == "second-key-value-0123456789012"
    )


def test_credential_manager_honours_validate_on_fetch_input(monkeypatch):
    """``validate_on_fetch`` reaches the validation branch it names."""
    # Too short for the api_key pattern (^[A-Za-z0-9\\-_]{20,}$), so validation
    # is the only thing that can distinguish the two calls below.
    monkeypatch.setenv("SHORT_NAME_API_KEY", "short")

    node = CredentialManagerNode(
        credential_name="short_name",
        credential_type="api_key",
        credential_sources=["env"],
        name="probe",
        cache_duration_seconds=None,
        validate_on_fetch=True,
    )

    assert node.execute()["validated"] is False
    assert node.execute(validate_on_fetch=False)["validated"] is True


# ---------------------------------------------------------------------------
# RotatingCredentialNode refuses rather than silently never rotating (#2138).
# ---------------------------------------------------------------------------


def test_rotation_refuses_instead_of_reporting_false_success():
    """LOAD-BEARING. `start_rotation` returned success and rotated nothing.

    It answered ``{"success": True, "message": "Rotation started..."}`` and
    spawned a worker whose every tick could only conclude "no rotation needed",
    because CredentialManagerNode implements none of get_credential /
    store_credential / delete_credential. A caller reading that success has
    every reason to believe its credentials are rotating, so a credential
    advertised as rotating stayed valid forever with nothing saying otherwise.

    The full rotation feature is #2138; this asserts the interim behaviour is
    LOUD refusal rather than silent staleness.
    """
    from kailash.nodes.security.rotating_credentials import RotatingCredentialNode
    from kailash.sdk_exceptions import NodeExecutionError

    node = RotatingCredentialNode(name="rot")

    for operation in ("start_rotation", "rotate_now"):
        with pytest.raises(NodeExecutionError) as excinfo:
            node.run(operation=operation, credential_name="api_token")
        message = str(excinfo.value)
        # The operator needs to know WHAT is missing and WHERE to look.
        assert "#2138" in message, message
        assert "store_credential" in message, message

    # No worker was started: a refused rotation must not leave a thread behind
    # that logs failures forever.
    assert node._rotation_threads == {}


def test_rotation_bookkeeping_operations_still_work():
    """CONTROL: the refusal is scoped to the operations that cannot function.

    stop_rotation / check_status / get_audit_log touch none of the missing
    store operations, so refusing them too would be an over-broad break.
    """
    from kailash.nodes.security.rotating_credentials import RotatingCredentialNode

    node = RotatingCredentialNode(name="rot")

    # Asserted against each operation's ACTUAL return shape -- only
    # stop_rotation reports `success`; the two readers return their payload.
    assert node.run(operation="stop_rotation", credential_name="x")["success"] is True
    assert node.run(operation="check_status")["active_threads"] == []
    assert node.run(operation="get_audit_log")["total_entries"] == 0
