"""Structural invariant: Nexus API-key auth is header-only (#1056).

cross-sdk-inspection.md §3a item 2 -- pin the signature/shape that prevents
the kailash-rs#998 bug class (hand-rolled query-string API-key percent-decode)
from existing in Python Nexus. If a future PR ports a `?api_key=` decoder from
the Rust side, BOTH assertions below fail and the failure message points the
next agent back to #1056 / kailash-rs#998 for a cross-SDK re-audit.

This is a verify-and-pin disposition (severity NOT-AFFECTED): there is no
production-code fix because there is no vulnerable surface. The value is
regression-prevention only -- mirrors the issue #525 / PR #528 precedent.

@pytest.mark.regression -- behavioral/structural, never deleted.
"""

import dataclasses

import pytest
from fastapi import APIRouter, Depends
from starlette.testclient import TestClient

from nexus import Nexus
from nexus.auth.dependencies import get_current_user
from nexus.auth.jwt import JWTConfig, JWTMiddleware

_APIKEY_SECRET = "issue-1056-apikey-invariant-secret-at-least-32-chars"
_VALID_KEY = "valid-api-key-1056"

# The ONLY API-key-related fields the contract permits. `specs/security-auth.md
# §2.2`: "Client sends X-API-Key header." A query-string API-key field
# (e.g. `api_key_query_param`) appearing here is the bug class returning.
_ALLOWED_APIKEY_FIELDS = {"api_key_header", "api_key_enabled", "api_key_validator"}


@pytest.mark.regression
def test_jwtconfig_has_no_query_string_apikey_field():
    """JWTConfig exposes no `api_key_query_param`-style field.

    Enumerates dataclass fields structurally (not grep). Any field whose name
    contains 'api_key' must be one of the three header-path fields. A new
    api-key field -> a new (likely query-string) decode surface -> the Rust
    bug class becomes reachable -> cross-SDK re-audit required.
    """
    field_names = {f.name for f in dataclasses.fields(JWTConfig)}
    apikey_fields = {n for n in field_names if "api_key" in n}
    extra = apikey_fields - _ALLOWED_APIKEY_FIELDS
    assert not extra, (
        f"JWTConfig grew API-key field(s) {sorted(extra)} beyond the "
        f"header-only contract {sorted(_ALLOWED_APIKEY_FIELDS)}. If this is a "
        f"query-string API-key path, the kailash-rs#998 percent-decode bug "
        f"class is now reachable in Python Nexus -- re-audit per "
        f"cross-sdk-inspection.md §3a and kailash-py#1056 before shipping."
    )


@pytest.fixture
def apikey_client():
    """Nexus app with API-key auth enabled and a real validator."""
    app = Nexus(enable_durability=False)
    app.add_middleware(
        JWTMiddleware,
        config=JWTConfig(
            secret=_APIKEY_SECRET,
            api_key_enabled=True,
            api_key_validator=lambda k: k == _VALID_KEY,
        ),
    )
    router = APIRouter()

    @router.get("/whoami")
    def whoami(user=Depends(get_current_user)):
        return {"uid": user.user_id}

    app.include_router(router, prefix="/api")
    assert app.fastapi_app is not None  # always set post-init; narrows type
    return TestClient(app.fastapi_app)


@pytest.mark.regression
def test_apikey_in_header_authenticates(apikey_client):
    """Baseline: a valid API key in the X-API-Key header authenticates.

    Proves the test exercises the real api-key auth path (not a vacuous
    always-401 assertion in the query-string test below).
    """
    resp = apikey_client.get("/api/whoami", headers={"X-API-Key": _VALID_KEY})
    assert resp.status_code == 200


@pytest.mark.regression
def test_apikey_in_query_string_does_not_authenticate(apikey_client):
    """Behavioral invariant: a valid API key in the QUERY STRING is NOT honored.

    cross-sdk-inspection.md §3a item 2 -- pins the bug-class absence
    behaviorally (refactor-resilient; testing.md "behavioral over
    source-grep"). The same key that authenticates via header MUST fail via
    `?X-API-Key=` and `?api_key=`. If a future PR ports the kailash-rs#998
    query-string API-key decoder, one of these flips to 200 and this test
    fails -- forcing a cross-SDK re-audit per #1056.
    """
    for param in ("X-API-Key", "api_key", "apikey"):
        resp = apikey_client.get(f"/api/whoami?{param}={_VALID_KEY}")
        assert resp.status_code == 401, (
            f"API key supplied via query param '?{param}=' authenticated "
            f"(status {resp.status_code}). Python Nexus API-key auth MUST be "
            f"header-only (specs/security-auth.md §2.2). This is the "
            f"kailash-rs#998 query-string credential-decode bug class "
            f"appearing in Python Nexus -- re-audit per "
            f"cross-sdk-inspection.md §3a + kailash-py#1056 before shipping."
        )
