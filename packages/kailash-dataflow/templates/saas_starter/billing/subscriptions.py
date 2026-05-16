"""
SaaS Starter Template - Subscription Management

Simplified subscription management with direct Python functions.

Functions:
- get_organization_subscription(db, organization_id) - Get current subscription
- check_feature_access(subscription_tier, feature_name) - Check feature availability
- upgrade_subscription(db, organization_id, new_tier) - Upgrade subscription
- downgrade_subscription(db, organization_id, new_tier) - Downgrade subscription
- cancel_subscription(db, organization_id) - Cancel subscription

Architecture:
- Direct Python functions for subscription logic
- DataFlow workflows ONLY for database operations
- Feature gates defined as simple dicts
- Simple, testable, fast functions
"""

from typing import Dict, Optional

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Feature access matrix by subscription tier
FEATURE_TIERS = {
    "free": {"basic_features", "single_user"},
    "basic": {"basic_features", "single_user", "team_collaboration"},
    "pro": {
        "basic_features",
        "single_user",
        "team_collaboration",
        "advanced_analytics",
        "api_access",
    },
    "enterprise": {
        "basic_features",
        "single_user",
        "team_collaboration",
        "advanced_analytics",
        "api_access",
        "sso",
        "custom_integrations",
    },
}


def get_organization_subscription(db, organization_id: str) -> Optional[Dict]:
    """
    Get organization's current subscription.

    Args:
        db: DataFlow instance
        organization_id: Organization ID

    Returns:
        Subscription dict if found, None otherwise

    Example:
        >>> sub = get_organization_subscription(db, "org_123")
        >>> if sub:
        ...     print(sub["plan_id"])
        price_pro_monthly
    """
    # DataFlow ListNode reads ``filter`` (singular) — ``filters`` (plural)
    # is silently dropped, so the list returned every org's subscription.
    workflow = WorkflowBuilder()
    workflow.add_node(
        "SubscriptionListNode",
        "list_subscriptions",
        {"filter": {"organization_id": organization_id}, "limit": 1},
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    # DataFlow 2.0 ``*ListNode`` returns ``{"records": [...], "count": n, ...}``
    # rather than a raw list — mirrors the verify_api_key (commit 8385851a0)
    # unwrap idiom. Bare ``subscriptions[0]`` raised ``KeyError: 0`` on every
    # caller of every subscription helper (upgrade/downgrade/cancel/trial/etc.).
    list_result = results.get("list_subscriptions") or {}
    subscriptions = (
        list_result.get("records", []) if isinstance(list_result, dict) else []
    )
    return subscriptions[0] if subscriptions else None


def check_feature_access(subscription_tier: str, feature_name: str) -> bool:
    """
    Check if feature is available on subscription tier.

    Args:
        subscription_tier: Subscription tier (free, basic, pro, enterprise)
        feature_name: Feature name to check

    Returns:
        True if feature is available, False otherwise

    Example:
        >>> has_access = check_feature_access("pro", "api_access")
        >>> if has_access:
        ...     print("Feature available")
        Feature available
    """
    tier_features = FEATURE_TIERS.get(subscription_tier, set())
    return feature_name in tier_features


def _update_subscription_fields(
    db, organization_id: str, fields: Dict
) -> Optional[Dict]:
    """Internal helper: look up subscription by org, then update by ``id``.

    DataFlow's ``*UpdateNode`` requires ``id`` / ``record_id`` in the filter
    (see UPDATE_NODE_MISSING_FILTER_ID error code). Subscriptions are
    1:1 with organizations in this template but the row is keyed by ``id``,
    so we resolve the id via ``get_organization_subscription`` first.
    """
    existing = get_organization_subscription(db, organization_id)
    if existing is None:
        return None

    workflow = WorkflowBuilder()
    workflow.add_node(
        "SubscriptionUpdateNode",
        "update_subscription",
        {"filter": {"id": existing["id"]}, "fields": fields},
    )

    runtime = LocalRuntime()
    runtime.execute(workflow.build())

    # Return the post-update row read-back (state-persistence verification
    # per rules/testing.md § State Persistence Verification).
    return get_organization_subscription(db, organization_id)


def upgrade_subscription(db, organization_id: str, new_tier: str) -> Optional[Dict]:
    """
    Upgrade subscription to higher tier.

    Args:
        db: DataFlow instance
        organization_id: Organization ID
        new_tier: New subscription tier/plan ID

    Returns:
        Updated subscription dict if successful, None otherwise

    Example:
        >>> sub = upgrade_subscription(db, "org_123", "price_pro_monthly")
        >>> if sub:
        ...     print(sub["plan_id"])
        price_pro_monthly
    """
    return _update_subscription_fields(
        db, organization_id, {"plan_id": new_tier, "status": "active"}
    )


def downgrade_subscription(db, organization_id: str, new_tier: str) -> Optional[Dict]:
    """
    Downgrade subscription to lower tier.

    Args:
        db: DataFlow instance
        organization_id: Organization ID
        new_tier: New subscription tier/plan ID

    Returns:
        Updated subscription dict if successful, None otherwise

    Example:
        >>> sub = downgrade_subscription(db, "org_123", "price_basic_monthly")
        >>> if sub:
        ...     print(sub["plan_id"])
        price_basic_monthly
    """
    return _update_subscription_fields(db, organization_id, {"plan_id": new_tier})


def cancel_subscription(db, organization_id: str) -> Optional[Dict]:
    """
    Cancel subscription at end of period.

    Args:
        db: DataFlow instance
        organization_id: Organization ID

    Returns:
        Updated subscription dict with cancel_at_period_end=True

    Example:
        >>> sub = cancel_subscription(db, "org_123")
        >>> if sub:
        ...     print(sub["cancel_at_period_end"])
        True
    """
    return _update_subscription_fields(
        db, organization_id, {"cancel_at_period_end": True}
    )
