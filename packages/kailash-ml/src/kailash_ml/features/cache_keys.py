# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Canonical tenant-scoped feature cache key helper.

Per ``rules/tenant-isolation.md`` MUST Rule 1 every cache key for a
multi-tenant primitive carries ``tenant_id`` as a dimension. The
canonical form for FeatureStore (``specs/ml-feature-store.md §9``) is::

    kailash_ml:v1:{tenant_id}:feature:{schema_name}:{version}:{row_key}

Per MUST Rule 2 a missing ``tenant_id`` (None / empty string / the
forbidden sentinels ``"default"`` / ``"global"``) raises
:class:`~kailash_ml.errors.TenantRequiredError` — keyword-only
construction via ``reason=`` per ``MLError.__init__``.

The ``"_single"`` sentinel (``CANONICAL_SINGLE_TENANT_SENTINEL``) is
the cross-spec canonical tag for single-tenant deployments per
``ml-tracking.md §7.2``.
"""
from __future__ import annotations

import re

from kailash_ml.errors import TenantRequiredError

__all__ = [
    "CANONICAL_SINGLE_TENANT_SENTINEL",
    "FEATURE_KEY_VERSION",
    "FORBIDDEN_TENANT_SENTINELS",
    "make_feature_cache_key",
    "make_feature_group_wildcard",
    "validate_tenant_id",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Key-space version tag. Bump in coordination with every invalidator path —
#: see ``rules/tenant-isolation.md`` Rule 3a. The helper always emits ``v1``
#: until a coordinated sweep lands.
FEATURE_KEY_VERSION: str = "v1"

#: Canonical sentinel for single-tenant deployments. Matches
#: ``ml-tracking.md §7.2``. Accepted as a valid ``tenant_id``.
CANONICAL_SINGLE_TENANT_SENTINEL: str = "_single"

#: Strings that are NOT valid tenant_id values — they silently merge every
#: tenant's rows into a shared cache slot (``rules/tenant-isolation.md`` Rule 2).
FORBIDDEN_TENANT_SENTINELS: frozenset[str] = frozenset({"default", "global", ""})

# Tenant IDs must be safe to interpolate into cache keys. We accept
# alphanumerics, dash, underscore, and a leading underscore (for the
# `_single` sentinel). Colons are BLOCKED — they would split the key
# structure.
_TENANT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]*$")

# Schema names re-use the SQL identifier regex.
_SCHEMA_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_tenant_id(tenant_id: str | None, *, operation: str) -> str:
    """Validate a tenant_id kwarg, raising TenantRequiredError if missing.

    Parameters
    ----------
    tenant_id:
        The caller-supplied tenant_id. ``None``, empty string, or any
        entry in :data:`FORBIDDEN_TENANT_SENTINELS` raises.
    operation:
        Short operation name (e.g. ``"feature_store.get_features"``) used
        in the :class:`TenantRequiredError` message for debuggability.

    Returns
    -------
    str
        The validated tenant_id string.

    Raises
    ------
    kailash_ml.errors.TenantRequiredError
        If ``tenant_id`` is ``None``, empty, a forbidden sentinel, or
        fails the tenant-id regex. Constructed with keyword-only
        ``reason=`` per ``MLError.__init__``.
    """
    if tenant_id is None:
        raise TenantRequiredError(
            reason=(
                f"{operation}: tenant_id is required (missing). Pass "
                f"tenant_id=... explicitly; single-tenant deployments "
                f"use the canonical sentinel "
                f"{CANONICAL_SINGLE_TENANT_SENTINEL!r}."
            ),
        )
    if not isinstance(tenant_id, str):
        raise TenantRequiredError(
            reason=(
                f"{operation}: tenant_id must be str, got "
                f"{type(tenant_id).__name__}"
            ),
        )
    if tenant_id in FORBIDDEN_TENANT_SENTINELS:
        raise TenantRequiredError(
            reason=(
                f"{operation}: tenant_id {tenant_id!r} is a forbidden "
                f"sentinel (rules/tenant-isolation.md Rule 2). Use "
                f"{CANONICAL_SINGLE_TENANT_SENTINEL!r} for single-tenant "
                f"or supply an explicit tenant identifier."
            ),
            tenant_id=tenant_id,
        )
    if not _TENANT_RE.match(tenant_id):
        # Do NOT echo the raw tenant_id in the message — fingerprint only.
        raise TenantRequiredError(
            reason=(
                f"{operation}: tenant_id failed validation "
                f"(fingerprint={hash(tenant_id) & 0xFFFF:04x}); must match "
                f"^[A-Za-z_][A-Za-z0-9_\\-]*$"
            ),
        )
    return tenant_id


def _validate_schema_name(schema_name: str) -> str:
    if not isinstance(schema_name, str) or not schema_name:
        raise ValueError(
            "cache_keys.make_feature_cache_key: schema_name must be non-empty str"
        )
    if not _SCHEMA_RE.match(schema_name):
        raise ValueError(
            f"cache_keys.make_feature_cache_key: schema_name failed validation "
            f"(fingerprint={hash(schema_name) & 0xFFFF:04x}); must match "
            f"^[a-zA-Z_][a-zA-Z0-9_]*$"
        )
    return schema_name


def _validate_version(version: int) -> int:
    if isinstance(version, bool) or not isinstance(version, int):
        raise TypeError(
            f"cache_keys.make_feature_cache_key: version must be int, got "
            f"{type(version).__name__}"
        )
    if version < 1:
        raise ValueError(
            f"cache_keys.make_feature_cache_key: version must be >= 1, got {version}"
        )
    return version


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------


def make_feature_cache_key(
    *,
    tenant_id: str | None,
    schema_name: str,
    version: int,
    row_key: str,
) -> str:
    """Build the canonical feature-store cache key.

    Canonical form::

        kailash_ml:{FEATURE_KEY_VERSION}:{tenant_id}:feature:{schema_name}:{version}:{row_key}

    Per ``rules/tenant-isolation.md`` Rule 1 and ``specs/ml-feature-store.md
    §9.1``. Missing ``tenant_id`` raises
    :class:`~kailash_ml.errors.TenantRequiredError` (Rule 2).

    ``row_key`` is typically the entity identifier (``user_id`` value) but
    may be any non-empty string. It is NOT validated for SQL-identifier
    shape because it is never interpolated into SQL — only into the
    Redis-compatible cache key namespace.
    """
    tenant = validate_tenant_id(tenant_id, operation="feature_cache_key")
    _validate_schema_name(schema_name)
    _validate_version(version)
    if not isinstance(row_key, str) or not row_key:
        raise ValueError(
            "cache_keys.make_feature_cache_key: row_key must be non-empty str"
        )
    # Row key must not contain the canonical `:` separator; otherwise the
    # key shape becomes ambiguous. Reject rather than escape.
    if ":" in row_key:
        raise ValueError(
            "cache_keys.make_feature_cache_key: row_key must not contain ':'"
        )
    return (
        f"kailash_ml:{FEATURE_KEY_VERSION}:{tenant}:feature:"
        f"{schema_name}:{version}:{row_key}"
    )


def make_feature_group_wildcard(
    *,
    tenant_id: str | None,
    schema_name: str,
    version: int | None = None,
) -> str:
    """Build a tenant-scoped invalidation wildcard.

    Per ``rules/tenant-isolation.md`` Rule 3 (scoped invalidation) and
    Rule 3a (keyspace-version-wildcard sweep — we emit ``v*`` to survive
    any future ``FEATURE_KEY_VERSION`` bump). ``tenant_id`` is REQUIRED
    (there is no cross-tenant invalidation surface in this helper — a
    platform-wide wipe belongs to an admin migration).

    If ``version`` is omitted, the wildcard matches every version for
    the named schema.
    """
    tenant = validate_tenant_id(tenant_id, operation="feature_cache_invalidation")
    _validate_schema_name(schema_name)
    if version is None:
        return f"kailash_ml:v*:{tenant}:feature:{schema_name}:*"
    _validate_version(version)
    return f"kailash_ml:v*:{tenant}:feature:{schema_name}:{version}:*"
