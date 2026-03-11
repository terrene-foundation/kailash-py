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
    workflow = WorkflowBuilder()
    workflow.add_node(
        "SubscriptionListNode",
        "list_subscriptions",
        {"filters": {"organization_id": organization_id}, "limit": 1},
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    subscriptions = results.get("list_subscriptions", [])
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
    workflow = WorkflowBuilder()
    workflow.add_node(
        "SubscriptionUpdateNode",
        "update_subscription",
        {
            "filters": {"organization_id": organization_id},
            "fields": {"plan_id": new_tier, "status": "active"},
        },
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    return results.get("update_subscription")


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
    workflow = WorkflowBuilder()
    workflow.add_node(
        "SubscriptionUpdateNode",
        "update_subscription",
        {
            "filters": {"organization_id": organization_id},
            "fields": {"plan_id": new_tier},
        },
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    return results.get("update_subscription")


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
    workflow = WorkflowBuilder()
    workflow.add_node(
        "SubscriptionUpdateNode",
        "update_subscription",
        {
            "filters": {"organization_id": organization_id},
            "fields": {"cancel_at_period_end": True},
        },
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    return results.get("update_subscription")
