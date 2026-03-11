"""
DataFlow models for API Gateway Example Application.

Defines User and Organization models with automatic node generation.
"""

from dataflow import DataFlow


def register_models(db: DataFlow):
    """
    Register DataFlow models for User and Organization.

    Args:
        db: DataFlow instance to register models with

    Example:
        >>> db = DataFlow(":memory:")
        >>> register_models(db)
        >>> # 11 nodes generated per model automatically
    """

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
