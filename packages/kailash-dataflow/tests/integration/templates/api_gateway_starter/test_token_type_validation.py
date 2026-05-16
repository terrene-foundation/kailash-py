"""
Tier-2 regression for issue #996 Shard C — api_gateway_starter JWT
middleware rejects signed-but-wrong-type tokens.

Failure mode pre-fix:

    saas_starter issues three JWT shapes, ALL signed with the same
    SAAS_STARTER_JWT_SECRET:

        - type=access          (1h expiry, intended for API access)
        - type=refresh         (7d expiry, only valid at refresh endpoint)
        - type=password_reset  (15m expiry, only valid at reset endpoint)

    The api_gateway middleware at
    ``templates/api_gateway_starter/middleware/jwt_auth.py`` validated
    the signature + expiry only. A signed ``refresh`` or
    ``password_reset`` token therefore passed verification and got
    ``request.state.user_claims`` attached, granting the caller full
    API access for the token's lifetime.

    The fix (commit landing alongside this test) adds an explicit
    ``verification.get("type") != "access"`` check after
    ``verify_token`` succeeds. This test exercises all three shapes
    against the real middleware via a real FastAPI app + DataFlow
    instance — NO MOCKING per ``rules/testing.md`` Tier 2/3 policy.

Cross-references:
    - sibling refresh-only check: ``templates/saas_starter/auth/jwt_auth.py:486``
    - issue: #996 (Round 3 /redteam security-reviewer finding)
    - Tier-2 carve-out for templates: ``tests/CLAUDE.md`` § "Carve-out
      tests/integration/templates/* (file-backed SQLite)"

Why this test file is self-contained (does NOT reuse sibling fixtures):
    The ``db``/``app``/``client``/``test_user``/``test_organization``
    fixtures in ``test_example_app.py`` are private to that module
    (pytest does not share fixtures across test files unless they are
    in a conftest). Promoting them to conftest would be a sibling-file
    refactor outside this shard's scope. The fixtures below mirror the
    sibling setup at module scope, paying ~one extra app spin-up per
    file for clean shard isolation.
"""

import os
import shutil
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

import jwt
import pytest
from fastapi.testclient import TestClient
from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from templates.saas_starter.auth.jwt_auth import (
    JWT_ALGORITHM,
    JWT_SECRET,
    hash_password,
)


@pytest.fixture(scope="module")
def db():
    """File-backed SQLite DataFlow instance.

    Mirrors the sibling ``test_example_app.py`` fixture: registers only
    ``APIKey`` here; ``User`` and ``Organization`` are registered later
    by ``create_app(db)``. Uses file-backed SQLite (NOT ``:memory:``)
    so DataFlow's migration pool — which opens multiple short-lived
    connections — sees a consistent schema.
    """
    tmpdir = tempfile.mkdtemp(prefix="api_gateway_token_type_test_")
    default_url = f"sqlite:///{tmpdir}/test.db"
    database_url = os.getenv("TEST_DATABASE_URL", default_url)
    db_instance = DataFlow(database_url)

    @db_instance.model
    class APIKey:
        id: str
        organization_id: str
        name: str
        key_hash: str
        scopes: list
        status: str
        rate_limit: Optional[int] = None
        expires_at: Optional[datetime] = None

        __dataflow__ = {
            "indexes": [
                {"name": "idx_apikey_org", "fields": ["organization_id"]},
                {"name": "idx_apikey_hash", "fields": ["key_hash"]},
                {"name": "idx_apikey_status", "fields": ["status"]},
            ]
        }

    yield db_instance

    try:
        import asyncio

        asyncio.run(db_instance.close_async())
    except Exception:
        # Fixture-teardown cleanup errors are expected (event loop may
        # already be closed); the OS reclaims the temp dir next.
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def app(db):
    """FastAPI app with the full middleware stack — same construction
    as ``test_example_app.py``."""
    from templates.api_gateway_starter.example_app.main import create_app

    return create_app(db)


@pytest.fixture(scope="module")
def client(app):
    """TestClient wrapping the FastAPI app — exercises real middleware."""
    return TestClient(app)


@pytest.fixture(scope="module")
def test_organization(db):
    """Create a real organization row for the token claims."""
    org_id = f"org-{uuid.uuid4()}"

    workflow = WorkflowBuilder()
    workflow.add_node(
        "OrganizationCreateNode",
        "create_org",
        {"id": org_id, "name": "Token Type Test Org", "status": "active"},
    )

    # Context-manager form per LocalRuntime DeprecationWarning (v0.12.0
    # makes the bare form an error). Matches the discipline in
    # `templates/saas_starter/*` after PR #1029 (commit ca670e543).
    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow.build())
    return results["create_org"]


@pytest.fixture(scope="module")
def test_user(db, test_organization):
    """Create a real user row referenced by the token claims."""
    user_id = f"user-{uuid.uuid4()}"
    email = f"token-type-{uuid.uuid4()}@example.com"

    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserCreateNode",
        "create_user",
        {
            "id": user_id,
            "organization_id": test_organization["id"],
            "email": email,
            "name": "Token Type Test User",
            "password_hash": hash_password("TestPassword123!"),
            "role": "admin",
            "status": "active",
        },
    )

    # Context-manager form per LocalRuntime DeprecationWarning.
    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow.build())
    return results["create_user"]


@pytest.fixture(scope="module")
def jwt_access_token(test_user, test_organization):
    """A type=access token — should be accepted by the gateway."""
    payload = {
        "user_id": test_user["id"],
        "org_id": test_organization["id"],
        "email": test_user["email"],
        "role": test_user["role"],
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture(scope="module")
def jwt_refresh_token(test_user):
    """A type=refresh token signed with the SAME secret. Pre-fix this
    was silently accepted by the api_gateway middleware. saas_starter
    only intends this shape for the refresh endpoint."""
    payload = {
        "user_id": test_user["id"],
        "exp": int(
            (datetime.now(UTC) + timedelta(days=7)).timestamp()
        ),  # 7-day refresh expiry
        "iat": int(time.time()),
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture(scope="module")
def jwt_password_reset_token(test_user):
    """A type=password_reset token signed with the SAME secret. Pre-fix
    this 15-minute token granted full API access despite being intended
    only for the password-reset endpoint."""
    payload = {
        "user_id": test_user["id"],
        "email": test_user["email"],
        "exp": int(
            (datetime.now(UTC) + timedelta(minutes=15)).timestamp()
        ),  # 15-min reset expiry
        "iat": int(time.time()),
        "type": "password_reset",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture(scope="module")
def jwt_no_type_token(test_user, test_organization):
    """A token with NO ``type`` claim — should also be rejected.
    Defends against ambiguity from older saas_starter versions or
    third-party token issuers that omit the type discriminator."""
    payload = {
        "user_id": test_user["id"],
        "org_id": test_organization["id"],
        "email": test_user["email"],
        "role": test_user["role"],
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        # NO "type" claim
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


class TestTokenTypeValidation:
    """Issue #996 Shard C regression — token-type discrimination at the
    api_gateway JWT middleware boundary."""

    def test_access_token_accepted(self, client, jwt_access_token):
        """A type=access token MUST pass the middleware and reach the
        downstream route (200 from /users)."""
        response = client.get(
            "/users", headers={"Authorization": f"Bearer {jwt_access_token}"}
        )
        # 200 means the middleware accepted the access token AND the
        # downstream RBAC + handler both succeeded. Anything other than
        # 200 here means we broke the happy path with the new check.
        assert response.status_code == 200, (
            f"access token rejected with {response.status_code}: " f"{response.text}"
        )

    def test_refresh_token_rejected_at_api_gateway(self, client, jwt_refresh_token):
        """A type=refresh token signed with the gateway's secret MUST
        be rejected with 401 + ``Invalid token type`` in detail.

        Pre-fix this returned 200 (or 403 if RBAC was the first wall
        because the refresh payload omits ``role``). Either way the
        middleware silently attached ``user_claims`` for a token never
        meant to reach the gateway."""
        response = client.get(
            "/users", headers={"Authorization": f"Bearer {jwt_refresh_token}"}
        )
        assert response.status_code == 401, (
            f"refresh token NOT rejected — got {response.status_code}: "
            f"{response.text}"
        )
        detail = response.json().get("detail", "")
        assert (
            "Invalid token type" in detail
        ), f"401 returned but detail does not cite token-type: {detail!r}"

    def test_password_reset_token_rejected_at_api_gateway(
        self, client, jwt_password_reset_token
    ):
        """A type=password_reset token MUST be rejected at the
        gateway. The 15-min expiry window is dangerously short to
        notice an abuse, and the token's intended scope is one
        endpoint, not the whole API."""
        response = client.get(
            "/users",
            headers={"Authorization": f"Bearer {jwt_password_reset_token}"},
        )
        assert response.status_code == 401, (
            f"password_reset token NOT rejected — got {response.status_code}: "
            f"{response.text}"
        )
        detail = response.json().get("detail", "")
        assert (
            "Invalid token type" in detail
        ), f"401 returned but detail does not cite token-type: {detail!r}"

    def test_token_with_no_type_claim_rejected(self, client, jwt_no_type_token):
        """A token with NO ``type`` claim MUST be rejected. Defends
        against ambiguity from older/external issuers — fail-closed
        is the only safe default at an auth boundary."""
        response = client.get(
            "/users", headers={"Authorization": f"Bearer {jwt_no_type_token}"}
        )
        assert response.status_code == 401, (
            f"no-type token NOT rejected — got {response.status_code}: "
            f"{response.text}"
        )
        detail = response.json().get("detail", "")
        assert (
            "Invalid token type" in detail
        ), f"401 returned but detail does not cite token-type: {detail!r}"
