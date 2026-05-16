"""
SaaS Starter Template - Auth Workflows + Multi-Tenant Isolation (Tier-2)

Tier-2 rewrite of ``tests/unit/templates/test_saas_starter_auth.py`` per
issue #996 Workstream-B shard B-2e. The original Tier-1 file was parked
behind ``pytestmark = pytest.mark.skip(...)`` because it violated
``specs/testing-tiers.md`` § Tier-1 Rule 1 — bare top-imports of
``LocalRuntime`` + ``WorkflowBuilder`` plus ``runtime.execute(workflow)``
against in-process aiosqlite hung the GH-runner py3.11 worker (brief
failure-layer #3: fork + asyncio incompatibility).

This rewrite moves all 20 tests to Tier-2 where:

* Real ``LocalRuntime`` + ``WorkflowBuilder`` + ``runtime.execute`` are
  contractually permitted (``rules/testing.md`` § 3-Tier Testing).
* NO MOCKING — exercises the production
  ``templates.saas_starter.workflows.auth`` + ``middleware.tenant``
  helpers end-to-end against a file-backed SQLite database.
* File-backed SQLite (via tempdir) per the carve-out documented in
  ``packages/kailash-dataflow/tests/CLAUDE.md:109-122`` — the
  saas_starter helpers exercise only schema-only models with no
  PostgreSQL-specific dialect features, so SQLite faithfully
  reproduces production semantics while keeping the suite collectable
  with a clean ``[dev]``-only install (no Docker / port 5434 required).

Probe verdict: 20 of 20 tests map to existing production code
(``workspaces/issue-979-workstream-b-parallel/journal/0010-PROBE-b-2e-auth-orphan-map.md``).
Zero orphans. The sibling test_jwt.py file already establishes the
file-backed SQLite + tempdir-teardown pattern for the saas_starter
integration tier.

The conftest (``tests/integration/templates/saas_starter/conftest.py``)
sets ``SAAS_STARTER_JWT_SECRET`` BEFORE collection so the saas_starter
auth modules can be imported at the top of this file without tripping
the import-time RuntimeError they raise on missing secret.

Closes the B-2e shard of #996 (Workstream-B parallel wave).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta

import jwt
import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from templates.saas_starter.middleware.tenant import (
    build_org_switching_workflow,
    build_tenant_scoped_bulk_update_workflow,
    build_tenant_scoped_delete_workflow,
    build_tenant_scoped_list_workflow,
    build_tenant_scoped_read_workflow,
    build_tenant_scoped_update_workflow,
    inject_tenant_context,
)
from templates.saas_starter.models import register_models
from templates.saas_starter.workflows.auth import (
    build_login_workflow,
    build_oauth_github_workflow,
    build_oauth_google_workflow,
    build_password_reset_complete_workflow,
    build_password_reset_request_workflow,
    build_registration_workflow,
    build_token_validation_workflow,
)

# ----------------------------------------------------------------------
# Fixture — real DataFlow against a temp-file SQLite database with the
# full saas_starter model set registered.
#
# Pattern mirrors api_gateway_starter/test_example_app.py::db and the
# sibling test_jwt.py: file-backed (NOT :memory:) so DataFlow's migration
# + write pools see a consistent schema across short-lived connections.
# Uses register_models() (the production registration entry point) so
# Organization, User, Subscription, APIKey, WebhookEvent are all
# available — the auth + tenant workflows reference Organization, User,
# Subscription by name via NodeType strings.
# ----------------------------------------------------------------------


@pytest.fixture(scope="function")
def db():
    """Real DataFlow with the full saas_starter model registration."""
    tmpdir = tempfile.mkdtemp(prefix="saas_auth_test_")
    default_url = f"sqlite:///{tmpdir}/test.db"
    database_url = os.getenv("TEST_DATABASE_URL", default_url)
    db_instance = DataFlow(database_url)

    # Register all saas_starter models (Organization, User, Subscription,
    # APIKey, WebhookEvent) via the production entry point. The auth
    # workflows reference these by NodeType string ("OrganizationCreateNode",
    # "UserCreateNode", etc.) so the full set must be registered.
    register_models(db_instance)

    # Explicitly create tables for SQLite per the original test fixture's
    # discipline — DataFlow's auto_migrate path requires this for SQLite
    # file backends where each short-lived connection sees a fresh schema.
    db_instance.create_tables(database_type="sqlite")

    yield db_instance

    # Cleanup: close the DataFlow instance (release the aiosqlite worker
    # thread per issue #1010) and remove the temp directory. Errors
    # during teardown are expected when the event loop has already
    # closed; mirrors test_jwt.py teardown discipline.
    try:
        asyncio.run(db_instance.close_async())
    except Exception:
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="function")
def runtime():
    """LocalRuntime instance per test, scoped via the documented context-manager
    pattern. Per the v0.12.0 deprecation, ``runtime.execute()`` without
    ``with`` raises ``DeprecationWarning`` (will become an error); the
    yield+context-manager form releases the runtime's event-loop +
    thread-pool resources at test teardown, eliminating the warning AND
    the post-test "I/O operation on closed file" logging cascade that
    appears when the runtime outlives the captured stderr stream.
    """
    with LocalRuntime() as r:
        yield r


# ----------------------------------------------------------------------
# Section 1: Data Models (5 tests)
#
# Exercises register_models() through the DataFlow facade. Tests assert
# the model registration produced the expected nodes and field shapes,
# AND that real workflow execution against the file-backed SQLite
# database persists + retrieves the expected rows.
# ----------------------------------------------------------------------


@pytest.mark.integration
class TestSaaSDataModels:
    """SaaS data model structure + validation exercised against real infra."""

    def test_organization_model_structure(self, db):
        """Organization model registers correct fields + generates CRUD nodes."""
        assert "Organization" in db._models, "Organization model not registered"

        assert "OrganizationCreateNode" in db._nodes
        assert "OrganizationReadNode" in db._nodes
        assert "OrganizationUpdateNode" in db._nodes
        assert "OrganizationListNode" in db._nodes

        org_fields = db.get_model_fields("Organization")
        field_names = list(org_fields.keys())

        for required in ("id", "name", "slug", "plan_id", "status", "settings"):
            assert required in field_names, f"Organization missing field: {required}"

        assert org_fields["id"]["type"] is str
        assert org_fields["name"]["type"] is str
        assert org_fields["slug"]["type"] is str

    def test_user_model_with_organization_fk(self, db):
        """User model carries organization_id FK + generates CRUD nodes."""
        assert "User" in db._models, "User model not registered"

        assert "UserCreateNode" in db._nodes
        assert "UserReadNode" in db._nodes
        assert "UserUpdateNode" in db._nodes
        assert "UserListNode" in db._nodes

        user_fields = db.get_model_fields("User")
        field_names = list(user_fields.keys())

        for required in (
            "id",
            "organization_id",
            "email",
            "password_hash",
            "role",
            "status",
        ):
            assert required in field_names, f"User missing field: {required}"

        assert user_fields["id"]["type"] is str
        assert user_fields["organization_id"]["type"] is str
        assert user_fields["email"]["type"] is str

    def test_subscription_model_stripe_fields(self, db):
        """Subscription model has Stripe-integration fields + CRUD nodes."""
        assert "Subscription" in db._models, "Subscription model not registered"

        assert "SubscriptionCreateNode" in db._nodes
        assert "SubscriptionReadNode" in db._nodes
        assert "SubscriptionUpdateNode" in db._nodes

        sub_fields = db.get_model_fields("Subscription")
        field_names = list(sub_fields.keys())

        for required in (
            "id",
            "organization_id",
            "plan_id",
            "stripe_customer_id",
            "stripe_subscription_id",
            "status",
            "current_period_start",
            "current_period_end",
        ):
            assert required in field_names, f"Subscription missing field: {required}"

        assert sub_fields["stripe_customer_id"]["type"] is str
        assert sub_fields["stripe_subscription_id"]["type"] is str

    def test_model_relationships(self, db, runtime):
        """Cross-model FK relationships persist through real workflow execution."""
        workflow = WorkflowBuilder()

        # Deterministic IDs scoped per test — file-backed DB + per-test
        # tempdir teardown removes the timestamp-suffix collision-avoidance
        # the original Tier-1 file relied on.
        unique_suffix = f"{int(time.time() * 1_000_000)}"
        org_id = f"org_{unique_suffix}"
        user_id = f"user_{unique_suffix}"
        sub_id = f"sub_{unique_suffix}"
        email = f"rel_{unique_suffix}@example.com"

        workflow.add_node(
            "OrganizationCreateNode",
            "create_org",
            {
                "id": org_id,
                "name": f"Test Org {unique_suffix}",
                "slug": f"test-org-{unique_suffix}",
                "plan_id": "free",
                "status": "active",
                "settings": {},
            },
        )
        workflow.add_node(
            "UserCreateNode",
            "create_user",
            {
                "id": user_id,
                "organization_id": org_id,
                "email": email,
                "password_hash": "hashed_password",
                "role": "owner",
                "status": "active",
            },
        )
        workflow.add_node(
            "SubscriptionCreateNode",
            "create_subscription",
            {
                "id": sub_id,
                "organization_id": org_id,
                "plan_id": "price_123",
                "stripe_customer_id": "cus_123",
                "stripe_subscription_id": "sub_123",
                "status": "active",
                "current_period_start": datetime.now(),
                "current_period_end": datetime.now() + timedelta(days=30),
                "cancel_at_period_end": False,
            },
        )
        workflow.add_node("UserListNode", "list_users", {"limit": 100})
        workflow.add_node("SubscriptionListNode", "list_subscriptions", {"limit": 100})

        results, _ = runtime.execute(workflow.build())

        assert results["create_org"]["id"] == org_id
        assert results["create_user"]["organization_id"] == org_id
        assert results["create_subscription"]["organization_id"] == org_id

        # ListNode returns dict with 'records' key — match the production
        # contract exercised in test_jwt.py and the original Tier-1 file.
        user_result = results["list_users"]
        user_list = (
            user_result.get("records", user_result)
            if isinstance(user_result, dict)
            else user_result
        )
        assert isinstance(user_list, list)
        assert len(user_list) >= 1
        assert user_id in [u["id"] for u in user_list]

        sub_result = results["list_subscriptions"]
        sub_list = (
            sub_result.get("records", sub_result)
            if isinstance(sub_result, dict)
            else sub_result
        )
        assert isinstance(sub_list, list)
        assert len(sub_list) >= 1
        assert sub_id in [s["id"] for s in sub_list]

    def test_model_field_validation(self, db, runtime):
        """Uniqueness constraints enforced through real DB inserts (raise on dup)."""
        workflow = WorkflowBuilder()

        unique_suffix = f"{int(time.time() * 1_000_000)}"
        org_id = f"org_{unique_suffix}"
        user_id = f"user_{unique_suffix}"
        slug = f"unique-slug-{unique_suffix}"
        email = f"unique_{unique_suffix}@example.com"

        workflow.add_node(
            "OrganizationCreateNode",
            "create_org",
            {
                "id": org_id,
                "name": "Validation Test",
                "slug": slug,
                "plan_id": "free",
                "status": "active",
                "settings": {},
            },
        )
        workflow.add_node(
            "UserCreateNode",
            "create_user",
            {
                "id": user_id,
                "organization_id": org_id,
                "email": email,
                "password_hash": "hashed_password",
                "role": "owner",
                "status": "active",
            },
        )
        results, _ = runtime.execute(workflow.build())

        assert results["create_org"]["slug"] == slug
        assert results["create_user"]["email"] == email

        # Duplicate-email insert MUST raise — real uniqueness index, not
        # a mocked validator.
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "UserCreateNode",
            "create_duplicate_user",
            {
                "id": f"user_dup_{unique_suffix}",
                "organization_id": org_id,
                "email": email,  # duplicate
                "password_hash": "hashed_password",
                "role": "member",
                "status": "active",
            },
        )
        with pytest.raises(Exception) as exc_info:
            runtime.execute(workflow2.build())

        err_msg = str(exc_info.value).lower()
        assert (
            "unique" in err_msg or "duplicate" in err_msg
        ), f"Should raise uniqueness constraint error, got: {err_msg}"


# ----------------------------------------------------------------------
# Section 2: Authentication Workflows (8 tests)
#
# Exercises the workflows.auth.build_* helpers end-to-end. Every test
# runs a real registration through the production workflow path and then
# asserts the downstream workflow (login, token-validate, password-reset,
# oauth) operates on the persisted state. Real PyJWT + bcrypt + DataFlow
# nodes — no mocks.
# ----------------------------------------------------------------------


@pytest.mark.integration
class TestAuthenticationWorkflows:
    """Auth workflow builders exercised end-to-end against real DataFlow."""

    def test_user_registration_workflow(self, db, runtime):
        """Registration workflow persists org + user + issues real JWT."""
        unique_email = f"newuser_{int(time.time() * 1000)}@example.com"
        workflow = build_registration_workflow(
            email=unique_email, password="securepassword123", org_name="New Startup"
        )

        results, _ = runtime.execute(workflow)

        # Organization persisted via real OrganizationCreateNode
        assert "organization" in results
        assert results["organization"]["name"] == "New Startup"
        assert results["organization"]["slug"] == "new-startup"
        assert results["organization"]["status"] == "active"

        # User persisted with owner role + bcrypt-hashed password
        assert "user" in results
        assert results["user"]["email"] == unique_email
        assert results["user"]["role"] == "owner"
        assert results["user"]["status"] == "active"
        assert results["user"]["organization_id"] == results["organization"]["id"]
        assert results["user"]["password_hash"] != "securepassword123"
        assert results["user"]["password_hash"].startswith("$2b$")

        # PythonCodeNode-emitted JWT — unwrap {"result": "..."} shape
        token_result = results["token"]
        token_str = (
            token_result["result"] if isinstance(token_result, dict) else token_result
        )
        assert isinstance(token_str, str)
        assert len(token_str) > 50

        decoded = jwt.decode(token_str, options={"verify_signature": False})
        assert decoded["user_id"] == results["user"]["id"]
        assert decoded["org_id"] == results["organization"]["id"]

    def test_user_login_workflow(self, db, runtime):
        """Login workflow finds the user persisted by the registration workflow."""
        email = f"login_test_{int(time.time() * 1000)}@example.com"
        password = "testpassword123"

        reg_workflow = build_registration_workflow(
            email=email, password=password, org_name="Login Test Org"
        )
        reg_results, _ = runtime.execute(reg_workflow)

        login_workflow = build_login_workflow(email=email, password=password)
        results, _ = runtime.execute(login_workflow)

        assert "find_user" in results
        find_user_result = results["find_user"]
        assert "records" in find_user_result
        assert len(find_user_result["records"]) == 1

        user = find_user_result["records"][0]
        assert user["email"] == email
        assert user["id"] == reg_results["user"]["id"]

    def test_token_validation_workflow(self, db, runtime):
        """build_token_validation_workflow round-trips a freshly-issued token."""
        email = f"token_test_{int(time.time() * 1000)}@example.com"
        reg_workflow = build_registration_workflow(
            email=email, password="password123", org_name="Token Test"
        )
        reg_results, _ = runtime.execute(reg_workflow)

        token_result = reg_results["token"]
        token = (
            token_result["result"] if isinstance(token_result, dict) else token_result
        )

        validation_workflow = build_token_validation_workflow(token=token)
        results, _ = runtime.execute(validation_workflow)

        validate_result = results.get("validate", {})
        validation_data = validate_result.get("result", validate_result)

        assert validation_data["valid"] is True
        assert validation_data["user_id"] == reg_results["user"]["id"]
        assert validation_data["org_id"] == reg_results["organization"]["id"]
        assert "exp" in validation_data

    def test_token_expiration_workflow(self, db, runtime):
        """Expired tokens raise through real PyJWT validation at build time.

        ``build_token_validation_workflow`` performs ``jwt.decode`` at build
        time (PythonCodeNode's sandbox doesn't expose ``jwt``), so an
        expired token raises ``jwt.ExpiredSignatureError`` — which the
        builder re-raises as ``Exception("Token expired")`` — BEFORE the
        workflow even executes. The test asserts that path.

        Note: ``exp`` is set via timezone-aware ``datetime.now(UTC)`` so the
        token is unambiguously expired regardless of the test runner's
        local timezone. A naive ``datetime.now() - timedelta(hours=1)``
        is interpreted as UTC by PyJWT and resolves to a FUTURE
        timestamp in any local timezone east of UTC, masking the
        expiration. Original Tier-1 test had this bug; behind
        ``pytestmark.skip`` it never surfaced. Fixed in the rewrite per
        zero-tolerance Rule 1.
        """
        from datetime import UTC

        payload = {
            "user_id": "test_user",
            "org_id": "test_org",
            "exp": datetime.now(UTC) - timedelta(hours=2),  # unambiguously expired
        }
        # Dedicated secret — distinct from SAAS_STARTER_JWT_SECRET so the
        # builder's build-time decode uses the same secret we encode with.
        expired_token = jwt.encode(payload, "test_secret", algorithm="HS256")

        with pytest.raises(Exception) as exc_info:
            build_token_validation_workflow(token=expired_token, secret="test_secret")

        err = str(exc_info.value).lower()
        assert (
            "expired" in err or "invalid" in err
        ), f"Expired token must raise expiration error, got: {exc_info.value}"

    def test_password_reset_request_workflow(self, db, runtime):
        """Password reset request issues a JWT with <=15-minute expiry."""
        email = f"reset_test_{int(time.time() * 1000)}@example.com"
        reg_workflow = build_registration_workflow(
            email=email, password="oldpassword", org_name="Reset Test"
        )
        runtime.execute(reg_workflow)

        reset_request_workflow = build_password_reset_request_workflow(email=email)
        results, _ = runtime.execute(reset_request_workflow)

        assert "reset_token" in results
        reset_token_result = results["reset_token"]
        reset_token = (
            reset_token_result["result"]
            if isinstance(reset_token_result, dict)
            else reset_token_result
        )
        assert isinstance(reset_token, str)

        decoded = jwt.decode(reset_token, options={"verify_signature": False})
        assert "exp" in decoded
        exp_time = datetime.fromtimestamp(decoded["exp"])
        time_until_expiry = (exp_time - datetime.now()).total_seconds()
        assert (
            time_until_expiry <= 15 * 60
        ), "Reset token should expire within 15 minutes"

        assert "email_sent" in results

    def test_password_reset_complete_workflow(self, db, runtime):
        """Reset-complete decodes the reset token + bcrypt-hashes the new password."""
        email = f"reset_complete_{int(time.time() * 1000)}@example.com"
        reg_workflow = build_registration_workflow(
            email=email, password="oldpassword", org_name="Reset Complete Test"
        )
        runtime.execute(reg_workflow)

        reset_request_workflow = build_password_reset_request_workflow(email=email)
        reset_results, _ = runtime.execute(reset_request_workflow)

        reset_token_result = reset_results["reset_token"]
        reset_token = (
            reset_token_result["result"]
            if isinstance(reset_token_result, dict)
            else reset_token_result
        )

        reset_complete_workflow = build_password_reset_complete_workflow(
            reset_token=reset_token, new_password="newpassword123"
        )
        results, _ = runtime.execute(reset_complete_workflow)

        assert "decode_reset" in results
        decode_result = results["decode_reset"]
        result_data = (
            decode_result.get("result", decode_result)
            if isinstance(decode_result, dict)
            else decode_result
        )

        assert result_data["email"] == email
        assert result_data["new_hash"].startswith("$2b$")

    def test_oauth_google_integration_workflow(self, db, runtime):
        """OAuth-Google workflow persists org + user from a Google profile dict."""
        google_token = {
            "email": f"google_user_{int(time.time() * 1000)}@gmail.com",
            "name": "Google User",
            "picture": "https://example.com/photo.jpg",
            "sub": "google_user_id_123",
        }

        oauth_workflow = build_oauth_google_workflow(google_token=google_token)
        results, _ = runtime.execute(oauth_workflow)

        assert "user" in results
        assert results["user"]["email"] == google_token["email"]
        assert "organization" in results

        assert "token" in results
        token_result = results["token"]
        token_str = (
            token_result["result"] if isinstance(token_result, dict) else token_result
        )
        assert isinstance(token_str, str)

        assert "is_new_user" in results
        is_new_result = results["is_new_user"]
        is_new_user = (
            is_new_result["result"]
            if isinstance(is_new_result, dict)
            else is_new_result
        )
        assert is_new_user is True

    def test_oauth_github_integration_workflow(self, db, runtime):
        """OAuth-GitHub workflow persists org + user from a GitHub profile dict."""
        github_token = {
            "email": f"github_user_{int(time.time() * 1000)}@github.com",
            "name": "GitHub User",
            "avatar_url": "https://github.com/avatar.jpg",
            "login": "githubuser123",
        }

        oauth_workflow = build_oauth_github_workflow(github_token=github_token)
        results, _ = runtime.execute(oauth_workflow)

        assert "user" in results
        assert results["user"]["email"] == github_token["email"]
        assert "organization" in results

        assert "token" in results
        token_result = results["token"]
        token_str = (
            token_result["result"] if isinstance(token_result, dict) else token_result
        )
        assert isinstance(token_str, str)

        assert "is_new_user" in results
        is_new_result = results["is_new_user"]
        is_new_user = (
            is_new_result["result"]
            if isinstance(is_new_result, dict)
            else is_new_result
        )
        assert is_new_user is True


# ----------------------------------------------------------------------
# Section 3: Multi-Tenant Data Isolation (7 tests)
#
# Exercises middleware.tenant.* helpers against two real tenants
# populated via the production registration workflow. Verifies cross-
# tenant reads/updates/deletes are prevented by the tenant_id filter
# decoded from the JWT — real PyJWT decode + real DataFlow filter, no
# mocks. Tenant-isolation discipline per rules/tenant-isolation.md.
# ----------------------------------------------------------------------


@pytest.mark.integration
class TestMultiTenantIsolation:
    """Tenant isolation contract exercised end-to-end against real DataFlow."""

    @pytest.fixture
    def two_tenants(self, db, runtime):
        """Two real tenants populated via build_registration_workflow."""
        # Tenant A
        tenant_a_workflow = build_registration_workflow(
            email=f"tenant_a_{int(time.time() * 1000)}@example.com",
            password="password",
            org_name="Tenant A",
        )
        tenant_a_results, _ = runtime.execute(tenant_a_workflow)

        # Tenant B — micro-sleep ensures the timestamp-derived slug differs
        # (build_registration_workflow uses slugify(org_name); both
        # tenants use distinct org names here so this is belt-and-suspenders).
        time.sleep(0.001)
        tenant_b_workflow = build_registration_workflow(
            email=f"tenant_b_{int(time.time() * 1000)}@example.com",
            password="password",
            org_name="Tenant B",
        )
        tenant_b_results, _ = runtime.execute(tenant_b_workflow)

        token_a_result = tenant_a_results["token"]
        token_a = (
            token_a_result["result"]
            if isinstance(token_a_result, dict)
            else token_a_result
        )
        token_b_result = tenant_b_results["token"]
        token_b = (
            token_b_result["result"]
            if isinstance(token_b_result, dict)
            else token_b_result
        )

        return {
            "tenant_a": {
                "org_id": tenant_a_results["organization"]["id"],
                "user_id": tenant_a_results["user"]["id"],
                "token": token_a,
            },
            "tenant_b": {
                "org_id": tenant_b_results["organization"]["id"],
                "user_id": tenant_b_results["user"]["id"],
                "token": token_b,
            },
        }

    def test_tenant_context_injection(self, db, runtime, two_tenants):
        """inject_tenant_context extracts org_id from a real JWT."""
        # inject_tenant_context is a plain function — no workflow execution.
        # The fact that this assertion holds proves the JWT signed by
        # workflows.auth (using SAAS_STARTER_JWT_SECRET) verifies cleanly
        # under middleware.tenant (which reads the same env var).
        context = inject_tenant_context(two_tenants["tenant_a"]["token"])
        assert "tenant_id" in context
        assert context["tenant_id"] == two_tenants["tenant_a"]["org_id"]

    def test_cross_tenant_read_prevention(self, db, runtime, two_tenants):
        """build_tenant_scoped_read_workflow blocks reads across tenant boundaries."""
        workflow = build_tenant_scoped_read_workflow(
            model_name="User",
            record_id=two_tenants["tenant_b"]["user_id"],
            tenant_token=two_tenants["tenant_a"]["token"],
        )

        results, _ = runtime.execute(workflow)

        # The workflow filters by both id AND organization_id, so tenant B's
        # user (different org_id) cannot surface in tenant A's scoped query.
        user_result = results.get("user", {})
        records = (
            user_result.get("records", []) if isinstance(user_result, dict) else []
        )

        returned_user_ids = [r.get("id") for r in records]
        assert (
            two_tenants["tenant_b"]["user_id"] not in returned_user_ids
        ), "Cross-tenant read must be prevented — tenant B's user MUST NOT appear"

        for record in records:
            assert (
                record.get("organization_id") == two_tenants["tenant_a"]["org_id"]
            ), "Every returned record must belong to the token's tenant"

    def test_cross_tenant_update_prevention(self, db, runtime, two_tenants):
        """build_tenant_scoped_update_workflow blocks cross-tenant updates."""
        workflow = build_tenant_scoped_update_workflow(
            model_name="User",
            record_id=two_tenants["tenant_b"]["user_id"],
            updates={"role": "admin"},
            tenant_token=two_tenants["tenant_a"]["token"],
        )

        # The workflow either raises (ownership check fails the PythonCodeNode
        # `verify_ownership` step) or surfaces an empty `check_ownership`
        # result. Both outcomes satisfy the tenant-isolation contract.
        try:
            results, _ = runtime.execute(workflow)
            check_result = results.get("check_ownership", {})
            records = (
                check_result.get("records", [])
                if isinstance(check_result, dict)
                else []
            )
            found_ids = [r.get("id") for r in records]
            assert (
                two_tenants["tenant_b"]["user_id"] not in found_ids
            ), "Ownership check must not surface tenant B's user under tenant A's token"
        except Exception as e:
            err = str(e).lower()
            assert any(
                x in err for x in ("permission", "access", "forbidden", "denied")
            ), f"Cross-tenant update must raise permission error, got: {e}"

    def test_cross_tenant_delete_prevention(self, db, runtime, two_tenants):
        """build_tenant_scoped_delete_workflow blocks cross-tenant deletes."""
        workflow = build_tenant_scoped_delete_workflow(
            model_name="User",
            record_id=two_tenants["tenant_b"]["user_id"],
            tenant_token=two_tenants["tenant_a"]["token"],
        )

        try:
            results, _ = runtime.execute(workflow)
            check_result = results.get("check_ownership", {})
            records = (
                check_result.get("records", [])
                if isinstance(check_result, dict)
                else []
            )
            found_ids = [r.get("id") for r in records]
            assert (
                two_tenants["tenant_b"]["user_id"] not in found_ids
            ), "Ownership check must not surface tenant B's user under tenant A's token"
        except Exception as e:
            err = str(e).lower()
            assert any(
                x in err for x in ("permission", "access", "forbidden", "denied")
            ), f"Cross-tenant delete must raise permission error, got: {e}"

    def test_tenant_scoped_list_queries(self, db, runtime, two_tenants):
        """build_tenant_scoped_list_workflow filters every record by the token's org_id."""
        workflow = build_tenant_scoped_list_workflow(
            model_name="User", tenant_token=two_tenants["tenant_a"]["token"]
        )

        results, _ = runtime.execute(workflow)

        users_result = results["users"]
        users = (
            users_result.get("records", [])
            if isinstance(users_result, dict)
            else users_result
        )
        assert isinstance(users, list)
        assert len(users) >= 1, "At least tenant A's own user must be in the list"

        tenant_a_org_id = two_tenants["tenant_a"]["org_id"]
        for user in users:
            assert (
                user["organization_id"] == tenant_a_org_id
            ), f"List leaked user from wrong tenant: {user['organization_id']}"

    def test_organization_switching(self, db, runtime, two_tenants):
        """build_org_switching_workflow scopes list queries to the target org."""
        # Plant a user in tenant A directly via UserCreateNode (the
        # switching workflow then filters by organization_id).
        workflow = WorkflowBuilder()
        multi_org_user_id = f"multi_user_{int(time.time() * 1000)}"
        multi_org_email = f"multi_{int(time.time() * 1000)}@example.com"

        workflow.add_node(
            "UserCreateNode",
            "create_multi_user_a",
            {
                "id": multi_org_user_id,
                "organization_id": two_tenants["tenant_a"]["org_id"],
                "email": multi_org_email,
                "password_hash": "hashed",
                "role": "member",
                "status": "active",
            },
        )
        runtime.execute(workflow.build())

        workflow_a = build_org_switching_workflow(
            user_id=multi_org_user_id,
            target_org_id=two_tenants["tenant_a"]["org_id"],
            operation="list_users",
        )
        results_a, _ = runtime.execute(workflow_a)

        users_result = results_a["users"]
        users = (
            users_result.get("records", [])
            if isinstance(users_result, dict)
            else users_result
        )
        assert all(
            u["organization_id"] == two_tenants["tenant_a"]["org_id"] for u in users
        ), "Org-switched list MUST be scoped to the target org"

    def test_tenant_isolation_in_bulk_operations(self, db, runtime, two_tenants):
        """Bulk update via build_tenant_scoped_bulk_update_workflow respects org_id."""
        workflow = build_tenant_scoped_bulk_update_workflow(
            model_name="User",
            updates={"status": "verified"},
            tenant_token=two_tenants["tenant_a"]["token"],
        )

        runtime.execute(workflow)

        # Verify tenant B's user was NOT affected — read it back via the
        # raw UserReadNode (bypasses tenant scoping deliberately to inspect
        # the row's current state).
        workflow_check = WorkflowBuilder()
        workflow_check.add_node(
            "UserReadNode",
            "check_tenant_b_user",
            {"id": two_tenants["tenant_b"]["user_id"]},
        )
        check_results, _ = runtime.execute(workflow_check.build())

        tenant_b_user = check_results["check_tenant_b_user"]
        assert (
            tenant_b_user["status"] != "verified"
        ), "Bulk update MUST NOT cross tenant boundaries"
