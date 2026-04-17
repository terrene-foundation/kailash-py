"""
DataFlow models for API Gateway Example Application.

Defines User and Organization models with automatic node generation.
"""

from dataflow import DataFlow


def register_models(db: DataFlow):
    """
    Register DataFlow models for User and Organization.

    Idempotent: if ``User`` / ``Organization`` are already registered on
    ``db`` (e.g. by the companion ``saas_starter`` template in a combined
    application), the existing registrations are preserved and this call
    is a no-op. Without this guard a composed setup that registers both
    templates raises ``Model 'User' is already registered`` and blocks
    the app from starting — the integration test suite's 30-error
    ``api_gateway_starter`` cluster surfaced the bug.

    Args:
        db: DataFlow instance to register models with

    Example:
        >>> db = DataFlow(":memory:")
        >>> register_models(db)
        >>> # 11 nodes generated per model automatically
    """
    existing = set(db.get_models().keys())
    if "User" in existing and "Organization" in existing:
        return

    @db.model
    class User:
        """
        User model with organization association.

        Generated nodes:
        - UserCreateNode
        - UserReadNode
        - UserUpdateNode
        - UserDeleteNode
        - UserListNode
        - UserBulkCreateNode
        - UserBulkUpdateNode
        - UserBulkDeleteNode
        - UserUpsertNode
        """

        id: str
        organization_id: str
        email: str
        name: str
        password_hash: str
        role: str  # owner, admin, member
        status: str  # active, inactive

    @db.model
    class Organization:
        """
        Organization model for multi-tenancy.

        Generated nodes:
        - OrganizationCreateNode
        - OrganizationReadNode
        - OrganizationUpdateNode
        - OrganizationDeleteNode
        - OrganizationListNode
        - OrganizationBulkCreateNode
        - OrganizationBulkUpdateNode
        - OrganizationBulkDeleteNode
        - OrganizationUpsertNode
        """

        id: str
        name: str
        status: str  # active, inactive
