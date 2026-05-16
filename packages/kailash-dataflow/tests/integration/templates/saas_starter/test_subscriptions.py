"""SaaS Starter — Subscription Management Tier-2 integration tests.

Closes part of GH issue #996 (B-2c sub-shard). Brief AC#5 from
``workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:48-50``:

    "Any remaining tier-1 test that imports motor, psycopg, or other DB drivers
    is either gated behind importorskip OR moved to tests/integration/."

The legacy tests/unit/templates/test_saas_subscriptions.py top-imported
``LocalRuntime`` + ``WorkflowBuilder`` (banned at tier-1 per
specs/testing-tiers.md § Tier-1 Rule 1), so the entire module was
``pytestmark.skip``-gated. This file is the Tier-2 rewrite: real DataFlow,
real ``saas_starter.billing.subscriptions`` functions, zero mocking
(unittest.mock primitives are AST-banned by
tests/integration/conftest.py).

The 10 original test scenarios are preserved as 10 functions (1:1 mapping):

1. test_get_organization_subscription
2. test_check_feature_access_allowed
3. test_check_feature_access_denied
4. test_upgrade_subscription_success
5. test_downgrade_subscription_success
6. test_cancel_subscription
7. test_feature_limits_enforcement
8. test_subscription_tier_transitions
9. test_trial_period_expiration
10. test_payment_failure_handling

Fixture pattern mirrors
``tests/integration/templates/api_gateway_starter/test_example_app.py`` —
tempfile + sqlite:/// + only-the-needed-models registration. SQLite is the
Tier-2 backend here because (a) the subscription functions do not exercise
PostgreSQL-specific dialect and (b) the SDK Docker shared PG (port 5434)
is not required by any function in this surface. This matches the
api_gateway_starter sibling and keeps the suite collectable with the
``[dev]``-only install.
"""

import os
import tempfile
from datetime import datetime, timedelta

import pytest

from dataflow import DataFlow

# ``templates.saas_starter.*`` resolves because the kailash-dataflow tests
# conftest (packages/kailash-dataflow/tests/conftest.py) adds
# ``packages/kailash-dataflow`` to sys.path; the sibling
# ``api_gateway_starter`` integration test uses the same spelling.
from templates.saas_starter.billing.subscriptions import (
    cancel_subscription,
    check_feature_access,
    downgrade_subscription,
    get_organization_subscription,
    upgrade_subscription,
)

# ---------------------------------------------------------------------------
# Fixtures — file-backed SQLite DataFlow with only the models this surface
# touches (Organization + Subscription). The api_gateway_starter sibling
# uses the same pattern; both keep the registration list minimal to avoid
# schema collisions with other templates' Organization/User definitions.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def db():
    """File-backed SQLite DataFlow with Subscription + Organization registered.

    Per-function scope so each test gets an isolated database. The file
    lives in a tempdir to keep DataFlow's migration pool (which opens
    multiple short-lived connections) consistent across writes —
    ``sqlite:///:memory:`` gives each connection an isolated database and
    breaks the migration handshake.
    """
    tmpdir = tempfile.mkdtemp(prefix="saas_subs_test_")
    default_url = f"sqlite:///{tmpdir}/test.db"
    database_url = os.getenv("TEST_DATABASE_URL", default_url)
    db_instance = DataFlow(database_url)

    @db_instance.model
    class Organization:
        id: str
        name: str
        slug: str
        plan_id: str
        status: str
        settings: dict

        __dataflow__ = {
            "indexes": [
                {"name": "idx_org_slug", "fields": ["slug"], "unique": True},
                {"name": "idx_org_status", "fields": ["status"]},
            ]
        }

    @db_instance.model
    class Subscription:
        id: str
        organization_id: str
        plan_id: str
        stripe_customer_id: str
        stripe_subscription_id: str
        status: str
        current_period_start: datetime
        current_period_end: datetime
        cancel_at_period_end: bool

        __dataflow__ = {
            "indexes": [
                {"name": "idx_sub_org", "fields": ["organization_id"]},
                {"name": "idx_sub_customer", "fields": ["stripe_customer_id"]},
                {"name": "idx_sub_subscription", "fields": ["stripe_subscription_id"]},
                {"name": "idx_sub_status", "fields": ["status"]},
            ]
        }

    yield db_instance

    # Cleanup — explicit close_async per rules/patterns.md § Async Resource
    # Cleanup, then drop the tempdir.
    import shutil

    try:
        await db_instance.close_async()
    except Exception:
        # Teardown errors are expected (event loop may already be closed);
        # the OS reclaims the temp dir next.
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


def _make_subscription(
    *,
    id: str,
    organization_id: str,
    plan_id: str = "price_pro_monthly",
    status: str = "active",
    cancel_at_period_end: bool = False,
    current_period_start: datetime | None = None,
    current_period_end: datetime | None = None,
) -> dict:
    """Helper producing a Subscription row dict for express.create.

    Centralizes the field shape so the 10 tests below don't each restate
    every column. The defaults mirror the legacy tier-1 file's mock dicts
    (price_pro_monthly + active + January 2025 period) so each translated
    test still asserts the same end-state.
    """
    return {
        "id": id,
        "organization_id": organization_id,
        "plan_id": plan_id,
        "stripe_customer_id": f"cus_{organization_id}",
        "stripe_subscription_id": f"sub_stripe_{id}",
        "status": status,
        "current_period_start": current_period_start or datetime(2025, 1, 1),
        "current_period_end": current_period_end or datetime(2025, 2, 1),
        "cancel_at_period_end": cancel_at_period_end,
    }


# ---------------------------------------------------------------------------
# Tier-2 tests — real DataFlow, real subscription functions, zero mocking.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_organization_subscription(db):
    """Get an organization's current subscription through the real list path."""
    org_id = "org_456"
    await db.express.create(
        "Subscription",
        _make_subscription(id="sub_123", organization_id=org_id),
    )

    result = get_organization_subscription(db, org_id)

    assert result is not None, "Should return subscription"
    assert result["id"] == "sub_123", "Should return correct subscription"
    assert result["organization_id"] == org_id, "Should belong to org"
    assert result["status"] == "active", "Should be active"


@pytest.mark.integration
def test_check_feature_access_allowed():
    """Pure-function tier check — Pro/Enterprise/Free features advertised as allowed."""
    # Pro tier should have advanced features
    assert (
        check_feature_access("pro", "advanced_analytics") is True
    ), "Pro tier should have advanced analytics"
    assert (
        check_feature_access("pro", "api_access") is True
    ), "Pro tier should have API access"

    # Free tier should have basic features
    assert (
        check_feature_access("free", "basic_features") is True
    ), "Free tier should have basic features"


@pytest.mark.integration
def test_check_feature_access_denied():
    """Pure-function tier check — features advertised as denied stay denied."""
    # Free tier should NOT have pro features
    assert (
        check_feature_access("free", "advanced_analytics") is False
    ), "Free tier should not have advanced analytics"
    assert (
        check_feature_access("free", "api_access") is False
    ), "Free tier should not have API access"

    # Basic tier should NOT have enterprise features
    assert (
        check_feature_access("basic", "sso") is False
    ), "Basic tier should not have SSO"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upgrade_subscription_success(db):
    """Upgrade an existing subscription's plan_id via the real update path."""
    org_id = "org_456"
    await db.express.create(
        "Subscription",
        _make_subscription(
            id="sub_upg", organization_id=org_id, plan_id="price_basic_monthly"
        ),
    )

    upgrade_subscription(db, org_id, "price_pro_monthly")

    # Read-back verifies the write per rules/testing.md § State Persistence
    # Verification — UpdateNode may return None on the SQLite dialect, so the
    # contract is the read, not the return value.
    after = get_organization_subscription(db, org_id)
    assert after is not None, "Subscription should still exist after upgrade"
    assert after["plan_id"] == "price_pro_monthly", "Should have new plan ID"
    assert after["status"] == "active", "Should still be active"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_downgrade_subscription_success(db):
    """Downgrade an existing subscription's plan_id via the real update path."""
    org_id = "org_456"
    await db.express.create(
        "Subscription",
        _make_subscription(
            id="sub_dwn", organization_id=org_id, plan_id="price_pro_monthly"
        ),
    )

    downgrade_subscription(db, org_id, "price_basic_monthly")

    after = get_organization_subscription(db, org_id)
    assert after is not None, "Subscription should still exist after downgrade"
    assert after["plan_id"] == "price_basic_monthly", "Should have new plan ID"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_subscription(db):
    """Cancellation flips cancel_at_period_end while leaving status active."""
    org_id = "org_456"
    await db.express.create(
        "Subscription",
        _make_subscription(id="sub_cancel", organization_id=org_id),
    )

    cancel_subscription(db, org_id)

    after = get_organization_subscription(db, org_id)
    assert after is not None, "Subscription should still exist after cancel"
    assert after["cancel_at_period_end"] is True, "Should be marked for cancellation"
    assert after["status"] == "active", "Should still be active until period end"


@pytest.mark.integration
def test_feature_limits_enforcement():
    """Pure-function tier hierarchy check — feature sets increase by tier."""
    # Free tier features (limited)
    free_features = ["basic_features", "single_user"]
    for feature in free_features:
        assert (
            check_feature_access("free", feature) is True
        ), f"Free tier should have {feature}"

    # Pro tier features (more)
    pro_features = [
        "basic_features",
        "advanced_analytics",
        "api_access",
        "team_collaboration",
    ]
    for feature in pro_features:
        assert (
            check_feature_access("pro", feature) is True
        ), f"Pro tier should have {feature}"

    # Enterprise features (most)
    enterprise_features = [
        "basic_features",
        "advanced_analytics",
        "api_access",
        "team_collaboration",
        "sso",
        "custom_integrations",
    ]
    for feature in enterprise_features:
        assert (
            check_feature_access("enterprise", feature) is True
        ), f"Enterprise tier should have {feature}"


@pytest.mark.integration
def test_subscription_tier_transitions():
    """Pure-function tier hierarchy — feature access increases up the tier ladder."""
    test_feature = "advanced_analytics"

    # Free and basic should not have advanced analytics
    assert check_feature_access("free", test_feature) is False
    assert check_feature_access("basic", test_feature) is False

    # Pro and enterprise should have advanced analytics
    assert check_feature_access("pro", test_feature) is True
    assert check_feature_access("enterprise", test_feature) is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trial_period_expiration(db):
    """Trial subscription persisted with trialing status and expired period_end."""
    org_id = "org_trial"
    expired_start = datetime.now() - timedelta(days=15)
    expired_end = datetime.now() - timedelta(days=1)  # Expired yesterday

    await db.express.create(
        "Subscription",
        _make_subscription(
            id="sub_trial",
            organization_id=org_id,
            plan_id="price_pro_trial",
            status="trialing",
            current_period_start=expired_start,
            current_period_end=expired_end,
        ),
    )

    result = get_organization_subscription(db, org_id)

    assert result is not None, "Should return trial subscription"
    assert result["status"] == "trialing", "Should have trialing status"
    # Compare to a fresh `datetime.now()` snapshot; the stored value is
    # strictly in the past so the assertion does not race the test clock.
    assert result["current_period_end"] < datetime.now(), "Should be expired"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_payment_failure_handling(db):
    """past_due status persists through the real read path."""
    org_id = "org_payment_failed"
    await db.express.create(
        "Subscription",
        _make_subscription(
            id="sub_failed",
            organization_id=org_id,
            status="past_due",
        ),
    )

    result = get_organization_subscription(db, org_id)

    assert result is not None, "Should return subscription"
    assert result["status"] == "past_due", "Should have past_due status"
    assert result["organization_id"] == org_id, "Should belong to org"
