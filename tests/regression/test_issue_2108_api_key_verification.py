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
    """The store holds digests, so a dump leaks nothing presentable."""
    api_key = await manager.create_api_key(user_id="u-5", key_name="k")

    store = manager._api_key_store
    assert api_key not in repr(store.__dict__)
    assert store.count() == 1

    from kailash.middleware.auth.api_keys import hash_api_key

    # The one entry is keyed by the digest, and the digest is not reversible.
    assert store.lookup(key_hash=hash_api_key(api_key)) is not None


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
        def store(self, *, key_hash, record):
            raise RuntimeError("backend down")

        def lookup(self, *, key_hash):
            raise RuntimeError("backend down")

        def revoke(self, *, key_hash):
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
