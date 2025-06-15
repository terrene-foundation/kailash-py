"""
Base models and mixins for middleware database layer.

Provides common functionality for all database models.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, event
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.sql import func


class TenantMixin:
    """Multi-tenant support for all models."""

    @declared_attr
    def tenant_id(cls):
        return Column(String(255), nullable=False, default="default", index=True)


class AuditMixin:
    """Audit trail support for all models."""

    @declared_attr
    def created_at(cls):
        return Column(DateTime(timezone=True), nullable=False, default=func.now())

    @declared_attr
    def updated_at(cls):
        return Column(DateTime(timezone=True), onupdate=func.now())

    @declared_attr
    def created_by(cls):
        return Column(String(255))

    @declared_attr
    def updated_by(cls):
        return Column(String(255))


class SoftDeleteMixin:
    """Soft delete support for compliance."""

    @declared_attr
    def deleted_at(cls):
        return Column(DateTime(timezone=True))

    @declared_attr
    def deleted_by(cls):
        return Column(String(255))

    @property
    def is_deleted(self) -> bool:
        """Check if entity is soft deleted."""
        return self.deleted_at is not None

    def soft_delete(self, deleted_by: str):
        """Mark entity as deleted."""
        self.deleted_at = datetime.now(timezone.utc)
        self.deleted_by = deleted_by


class VersionMixin:
    """Version control support."""

    @declared_attr
    def version(cls):
        return Column(Integer, nullable=False, default=1)

    def increment_version(self):
        """Increment version number."""
        self.version = (self.version or 0) + 1


class SecurityMixin:
    """Security classification support."""

    @declared_attr
    def security_classification(cls):
        return Column(String(50), default="internal")

    @declared_attr
    def access_permissions(cls):
        return Column(String, default="{}")  # JSON stored as string for compatibility


class ComplianceMixin:
    """Compliance tracking support."""

    @declared_attr
    def compliance_requirements(cls):
        return Column(String, default="[]")  # JSON array as string

    @declared_attr
    def retention_until(cls):
        return Column(DateTime(timezone=True))


class BaseMixin(TenantMixin, AuditMixin):
    """Common mixins for most models."""

    pass


class EnterpriseBaseMixin(
    TenantMixin, AuditMixin, SoftDeleteMixin, VersionMixin, SecurityMixin
):
    """Full enterprise features for critical models."""

    pass
