"""Authentication models for Nexus.

SPEC-06 Migration: AuthenticatedUser now re-exports from kailash.trust.auth.models.
Import from kailash.trust.auth.models directly for new code.
"""

from __future__ import annotations

from kailash.trust.auth.models import AuthenticatedUser

__all__ = [
    "AuthenticatedUser",
]
