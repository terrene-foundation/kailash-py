"""
SaaS Starter Template - Data Models

Production-ready multi-tenant data models for SaaS applications.

Models:
- Organization: Tenant root entity
- User: Multi-tenant user with organization FK
- Subscription: Stripe subscription management
- APIKey: API key authentication for programmatic access
- WebhookEvent: Event tracking and delivery

Features:
- String ID preservation (UUID support)
- Multi-tenant isolation via organization_id FK
- Stripe integration fields
- Automatic created_at/updated_at timestamps
- Security-first design (hashed passwords, hashed API keys)
"""

from datetime import datetime
from typing import Dict, Optional

from dataflow import DataFlow


def register_models(db: DataFlow) -> None:
    """
    Register all SaaS starter models with DataFlow instance.

    Args:
        db: DataFlow instance

    Models Registered:
        - Organization: Tenant/organization model
        - User: User model with organization FK
        - Subscription: Subscription/billing model
        - APIKey: API key authentication model
        - WebhookEvent: Event tracking and delivery model

    Generated Nodes (per model):
        - {Model}CreateNode
        - {Model}ReadNode
        - {Model}UpdateNode
        - {Model}DeleteNode
        - {Model}ListNode
        - {Model}BulkCreateNode
        - {Model}BulkUpdateNode
        - {Model}BulkDeleteNode
        - {Model}UpsertNode
        - {Model}BulkUpsertNode
    """

    @db.model
    class Organization:
        """
        Organization model (multi-tenant root entity).

        Fields:
            id: str - Unique organization ID (UUID)
            name: str - Organization name
            slug: str - Unique subdomain/path slug
            plan_id: str - Subscription plan ID
            status: str - Organization status (active, suspended, cancelled)
            settings: dict - JSON settings (preferences, configuration)

        Indexes:
            - slug (unique) - For subdomain/path lookup
            - status - For filtering active organizations

        Multi-Tenancy:
            This is the root tenant entity. All other entities reference this
            via organization_id foreign key.

        Example:
            org = {
                "id": "org_abc123",
                "name": "Acme Corp",
                "slug": "acme-corp",
                "plan_id": "plan_pro",
                "status": "active",
                "settings": {"timezone": "America/New_York"}
            }
        """

        id: str
        name: str
        slug: str
        plan_id: str
        status: str  # active, suspended, cancelled
        settings: dict

        __dataflow__ = {
            "indexes": [
                {"name": "idx_org_slug", "fields": ["slug"], "unique": True},
                {"name": "idx_org_status", "fields": ["status"]},
            ]
        }

    @db.model
    class User:
        """
        User model with multi-tenant isolation.

        Fields:
            id: str - Unique user ID (UUID)
            organization_id: str - FK to Organization.id (tenant isolation)
            email: str - User email (unique)
            password_hash: str - Bcrypt password hash
            role: str - User role (owner, admin, member)
            status: str - User status (active, invited, suspended)

        Indexes:
            - email (unique) - For email lookup
            - organization_id - For tenant-scoped queries
            - organization_id + email - Composite for tenant-scoped email uniqueness

        Multi-Tenancy:
            organization_id FK ensures all queries can be tenant-scoped.
            List operations MUST filter by organization_id.

        Security:
            - Password stored as bcrypt hash (never plain text)
            - Email uniqueness constraint prevents duplicates
            - Role-based access control (owner, admin, member)

        Example:
            user = {
                "id": "user_xyz789",
                "organization_id": "org_abc123",
                "email": "alice@example.com",
                "password_hash": "$2b$12$...",
                "role": "owner",
                "status": "active"
            }
        """

        id: str
        organization_id: str  # FK to Organization.id
        email: str
        password_hash: str
        role: str  # owner, admin, member
        status: str  # active, invited, suspended

        __dataflow__ = {
            "indexes": [
                {"name": "idx_user_email", "fields": ["email"], "unique": True},
                {"name": "idx_user_org", "fields": ["organization_id"]},
                {
                    "name": "idx_user_org_email",
                    "fields": ["organization_id", "email"],
                    "unique": True,
                },
                {"name": "idx_user_status", "fields": ["status"]},
            ]
        }

    @db.model
    class Subscription:
        """
        Subscription model with Stripe integration.

        Fields:
            id: str - Unique subscription ID (UUID)
            organization_id: str - FK to Organization.id
            plan_id: str - Stripe price ID (price_xxx)
            stripe_customer_id: str - Stripe customer ID (cus_xxx)
            stripe_subscription_id: str - Stripe subscription ID (sub_xxx)
            status: str - Subscription status (active, cancelled, past_due)
            current_period_start: datetime - Current billing period start
            current_period_end: datetime - Current billing period end
            cancel_at_period_end: bool - Cancel at end of period flag

        Indexes:
            - organization_id - For tenant-scoped queries
            - stripe_customer_id - For Stripe webhook lookup
            - stripe_subscription_id - For Stripe webhook lookup
            - status - For filtering active subscriptions

        Stripe Integration:
            This model stores Stripe-specific IDs for webhook processing
            and subscription management. When Stripe sends webhooks, use
            stripe_customer_id or stripe_subscription_id to find the record.

        Billing Lifecycle:
            1. Create subscription → status=active
            2. Upgrade/downgrade → update plan_id
            3. Cancel → cancel_at_period_end=True
            4. Billing failure → status=past_due
            5. End of period → status=cancelled

        Example:
            subscription = {
                "id": "sub_local_123",
                "organization_id": "org_abc123",
                "plan_id": "price_1234",
                "stripe_customer_id": "cus_xyz789",
                "stripe_subscription_id": "sub_stripe_456",
                "status": "active",
                "current_period_start": datetime(2025, 1, 1),
                "current_period_end": datetime(2025, 2, 1),
                "cancel_at_period_end": False
            }
        """

        id: str
        organization_id: str  # FK to Organization.id
        plan_id: str  # Stripe price ID
        stripe_customer_id: str  # Stripe customer ID
        stripe_subscription_id: str  # Stripe subscription ID
        status: str  # active, cancelled, past_due
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

    @db.model
    class APIKey:
        """
        API Key model for programmatic access.

        Fields:
            id: str - Unique API key ID (UUID)
            organization_id: str - FK to Organization.id
            name: str - Human-readable name for the key
            key_hash: str - SHA256 hash of API key (never store plain key)
            scopes: list - List of permission scopes (read, write, admin, delete)
            status: str - Key status (active, revoked)
            rate_limit: int - Optional rate limit (requests per hour)
            expires_at: datetime - Optional expiration timestamp
            created_at: datetime - Auto-managed creation timestamp

        Indexes:
            - organization_id - For tenant-scoped queries
            - key_hash - For API key verification
            - status - For filtering active keys

        Security:
            - Plain API keys NEVER stored in database
            - Only SHA256 hash stored for verification
            - Keys shown to user only once at creation
            - Revoked keys cannot be reactivated (create new key instead)

        Example:
            api_key = {
                "id": "key_abc123",
                "organization_id": "org_abc123",
                "name": "Production API Key",
                "key_hash": "abc123...",
                "scopes": ["read", "write"],
                "status": "active",
                "rate_limit": 1000,
                "expires_at": None
            }
        """

        id: str
        organization_id: str  # FK to Organization.id
        name: str
        key_hash: str  # SHA256 hash
        scopes: list  # ["read", "write", "admin", "delete"]
        status: str  # active, revoked
        rate_limit: int  # Optional rate limit
        expires_at: datetime  # Optional expiration

        __dataflow__ = {
            "indexes": [
                {"name": "idx_apikey_org", "fields": ["organization_id"]},
                {"name": "idx_apikey_hash", "fields": ["key_hash"]},
                {"name": "idx_apikey_status", "fields": ["status"]},
            ]
        }

    @db.model
    class WebhookEvent:
        """
        Webhook Event model for event tracking and delivery.

        Fields:
            id: str - Unique event ID (UUID)
            organization_id: str - FK to Organization.id
            event_type: str - Event type (user.created, user.updated, etc.)
            payload: dict - Event payload data
            status: str - Event status (pending, delivered, failed)
            retry_count: int - Number of delivery attempts
            last_retry_at: datetime - Last retry timestamp
            delivered_at: datetime - Delivery timestamp
            delivery_attempts: list - Optional list of delivery attempt metadata
            created_at: datetime - Auto-managed creation timestamp

        Indexes:
            - organization_id - For tenant-scoped queries
            - event_type - For filtering by event type
            - status - For filtering by delivery status
            - created_at - For chronological ordering

        Webhook Lifecycle:
            1. Create event → status=pending, retry_count=0
            2. Delivery attempt → increment retry_count
            3. Successful delivery → status=delivered, delivered_at set
            4. Failed delivery → status=pending (retry) or failed (max retries)

        Example:
            webhook_event = {
                "id": "evt_abc123",
                "organization_id": "org_abc123",
                "event_type": "user.created",
                "payload": {"user_id": "user_123", "email": "alice@example.com"},
                "status": "delivered",
                "retry_count": 1,
                "delivered_at": datetime(2025, 1, 15, 10, 30),
                "delivery_attempts": [
                    {"timestamp": datetime(2025, 1, 15, 10, 29), "response_code": 500},
                    {"timestamp": datetime(2025, 1, 15, 10, 30), "response_code": 200}
                ]
            }
        """

        id: str
        organization_id: str  # FK to Organization.id
        event_type: str  # user.created, user.updated, etc.
        payload: dict
        status: str  # pending, delivered, failed
        retry_count: int
        last_retry_at: datetime  # Optional
        delivered_at: datetime  # Optional
        delivery_attempts: list  # Optional

        __dataflow__ = {
            "indexes": [
                {"name": "idx_webhook_org", "fields": ["organization_id"]},
                {"name": "idx_webhook_type", "fields": ["event_type"]},
                {"name": "idx_webhook_status", "fields": ["status"]},
            ]
        }


# Model validation helpers


def validate_organization_status(status: str) -> bool:
    """
    Validate organization status enum.

    Args:
        status: Organization status

    Returns:
        True if valid, raises ValueError otherwise

    Valid Statuses:
        - active: Normal operation
        - suspended: Temporarily suspended (billing issue, violation)
        - cancelled: Permanently cancelled

    Raises:
        ValueError: If status is invalid
    """
    valid_statuses = ["active", "suspended", "cancelled"]
    if status not in valid_statuses:
        raise ValueError(
            f"Invalid organization status: {status}. Must be one of: {valid_statuses}"
        )
    return True


def validate_user_role(role: str) -> bool:
    """
    Validate user role enum.

    Args:
        role: User role

    Returns:
        True if valid, raises ValueError otherwise

    Valid Roles:
        - owner: Full access, billing management (1 per org)
        - admin: Full access except billing
        - member: Limited access (read/write own data)

    Raises:
        ValueError: If role is invalid
    """
    valid_roles = ["owner", "admin", "member"]
    if role not in valid_roles:
        raise ValueError(f"Invalid user role: {role}. Must be one of: {valid_roles}")
    return True


def validate_user_status(status: str) -> bool:
    """
    Validate user status enum.

    Args:
        status: User status

    Returns:
        True if valid, raises ValueError otherwise

    Valid Statuses:
        - active: Normal operation
        - invited: Pending invitation acceptance
        - suspended: Temporarily suspended

    Raises:
        ValueError: If status is invalid
    """
    valid_statuses = ["active", "invited", "suspended"]
    if status not in valid_statuses:
        raise ValueError(
            f"Invalid user status: {status}. Must be one of: {valid_statuses}"
        )
    return True


def validate_subscription_status(status: str) -> bool:
    """
    Validate subscription status enum.

    Args:
        status: Subscription status

    Returns:
        True if valid, raises ValueError otherwise

    Valid Statuses:
        - active: Active subscription
        - cancelled: Cancelled subscription
        - past_due: Payment failed, retry in progress
        - unpaid: Payment failed, no retry
        - trialing: Trial period

    Raises:
        ValueError: If status is invalid
    """
    valid_statuses = ["active", "cancelled", "past_due", "unpaid", "trialing"]
    if status not in valid_statuses:
        raise ValueError(
            f"Invalid subscription status: {status}. Must be one of: {valid_statuses}"
        )
    return True


# Utility functions for model creation


def create_organization_data(
    id: str,
    name: str,
    slug: str,
    plan_id: str = "free",
    status: str = "active",
    settings: Optional[Dict] = None,
) -> Dict:
    """
    Create validated organization data dictionary.

    Args:
        id: Organization ID (UUID)
        name: Organization name
        slug: Unique slug
        plan_id: Plan ID (default: "free")
        status: Status (default: "active")
        settings: Settings dict (default: {})

    Returns:
        Validated organization data dict

    Raises:
        ValueError: If validation fails

    Example:
        org_data = create_organization_data(
            id="org_123",
            name="Acme Corp",
            slug="acme-corp",
            plan_id="plan_pro"
        )
    """
    validate_organization_status(status)

    return {
        "id": id,
        "name": name,
        "slug": slug,
        "plan_id": plan_id,
        "status": status,
        "settings": settings or {},
    }


def create_user_data(
    id: str,
    organization_id: str,
    email: str,
    password_hash: str,
    role: str = "member",
    status: str = "active",
) -> Dict:
    """
    Create validated user data dictionary.

    Args:
        id: User ID (UUID)
        organization_id: Organization FK
        email: User email
        password_hash: Bcrypt password hash
        role: User role (default: "member")
        status: User status (default: "active")

    Returns:
        Validated user data dict

    Raises:
        ValueError: If validation fails

    Example:
        user_data = create_user_data(
            id="user_123",
            organization_id="org_123",
            email="alice@example.com",
            password_hash="$2b$12$...",
            role="owner"
        )
    """
    validate_user_role(role)
    validate_user_status(status)

    return {
        "id": id,
        "organization_id": organization_id,
        "email": email,
        "password_hash": password_hash,
        "role": role,
        "status": status,
    }


def create_subscription_data(
    id: str,
    organization_id: str,
    plan_id: str,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    status: str,
    current_period_start: datetime,
    current_period_end: datetime,
    cancel_at_period_end: bool = False,
) -> Dict:
    """
    Create validated subscription data dictionary.

    Args:
        id: Subscription ID (UUID)
        organization_id: Organization FK
        plan_id: Stripe price ID
        stripe_customer_id: Stripe customer ID
        stripe_subscription_id: Stripe subscription ID
        status: Subscription status
        current_period_start: Period start date
        current_period_end: Period end date
        cancel_at_period_end: Cancel at end flag (default: False)

    Returns:
        Validated subscription data dict

    Raises:
        ValueError: If validation fails

    Example:
        sub_data = create_subscription_data(
            id="sub_123",
            organization_id="org_123",
            plan_id="price_xxx",
            stripe_customer_id="cus_xxx",
            stripe_subscription_id="sub_xxx",
            status="active",
            current_period_start=datetime.now(),
            current_period_end=datetime.now() + timedelta(days=30)
        )
    """
    validate_subscription_status(status)

    return {
        "id": id,
        "organization_id": organization_id,
        "plan_id": plan_id,
        "stripe_customer_id": stripe_customer_id,
        "stripe_subscription_id": stripe_subscription_id,
        "status": status,
        "current_period_start": current_period_start,
        "current_period_end": current_period_end,
        "cancel_at_period_end": cancel_at_period_end,
    }
