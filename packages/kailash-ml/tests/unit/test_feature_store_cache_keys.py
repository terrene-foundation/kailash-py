# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests: tenant-scoped feature cache key helper.

Covers the canonical key shape, `TenantRequiredError` on missing /
forbidden tenants, invalidation wildcards, and keyspace-version
stability per rules/tenant-isolation.md.
"""
from __future__ import annotations

import pytest

from kailash_ml.errors import TenantRequiredError
from kailash_ml.features import (
    CANONICAL_SINGLE_TENANT_SENTINEL,
    make_feature_cache_key,
    make_feature_group_wildcard,
)
from kailash_ml.features.cache_keys import (
    FEATURE_KEY_VERSION,
    validate_tenant_id,
)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_cache_key_canonical_shape() -> None:
    key = make_feature_cache_key(
        tenant_id="acme",
        schema_name="user_churn",
        version=1,
        row_key="u42",
    )
    assert key == f"kailash_ml:{FEATURE_KEY_VERSION}:acme:feature:user_churn:1:u42"


def test_cache_key_single_tenant_sentinel_accepted() -> None:
    key = make_feature_cache_key(
        tenant_id=CANONICAL_SINGLE_TENANT_SENTINEL,
        schema_name="s",
        version=1,
        row_key="u1",
    )
    assert "_single" in key


def test_cache_key_tenant_dimension_separates_two_tenants() -> None:
    k1 = make_feature_cache_key(tenant_id="a", schema_name="s", version=1, row_key="u1")
    k2 = make_feature_cache_key(tenant_id="b", schema_name="s", version=1, row_key="u1")
    assert k1 != k2


# ---------------------------------------------------------------------------
# TenantRequiredError cases
# ---------------------------------------------------------------------------


def test_cache_key_missing_tenant_raises() -> None:
    with pytest.raises(TenantRequiredError) as ei:
        make_feature_cache_key(tenant_id=None, schema_name="s", version=1, row_key="u1")
    assert "tenant_id is required" in str(ei.value)


def test_cache_key_empty_tenant_raises() -> None:
    with pytest.raises(TenantRequiredError):
        make_feature_cache_key(tenant_id="", schema_name="s", version=1, row_key="u1")


@pytest.mark.parametrize("forbidden", ["default", "global"])
def test_cache_key_forbidden_sentinels_raise(forbidden: str) -> None:
    with pytest.raises(TenantRequiredError, match="forbidden sentinel"):
        make_feature_cache_key(
            tenant_id=forbidden, schema_name="s", version=1, row_key="u1"
        )


def test_cache_key_non_string_tenant_raises() -> None:
    with pytest.raises(TenantRequiredError, match="must be str"):
        make_feature_cache_key(
            tenant_id=42,  # type: ignore[arg-type]
            schema_name="s",
            version=1,
            row_key="u1",
        )


def test_cache_key_tenant_injection_not_echoed() -> None:
    try:
        make_feature_cache_key(
            tenant_id="acme:evil", schema_name="s", version=1, row_key="u1"
        )
    except TenantRequiredError as e:
        assert "acme:evil" not in str(e)
        assert "fingerprint=" in str(e)
    else:
        raise AssertionError("expected TenantRequiredError")


def test_tenant_required_error_is_kwarg_only_reason() -> None:
    # The canonical MLError/__init__ mandates `reason=` kwarg only.
    err = TenantRequiredError(reason="test reason")
    assert err.reason == "test reason"
    with pytest.raises(TypeError):
        # positional args BLOCKED by the MLError kwarg-only contract.
        TenantRequiredError("reason-as-positional")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Schema / version / row_key validation
# ---------------------------------------------------------------------------


def test_cache_key_invalid_schema_name_raises() -> None:
    with pytest.raises(ValueError, match="schema_name"):
        make_feature_cache_key(
            tenant_id="a", schema_name="1bad", version=1, row_key="u"
        )


def test_cache_key_rejects_zero_version() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        make_feature_cache_key(tenant_id="a", schema_name="s", version=0, row_key="u")


def test_cache_key_rejects_bool_version() -> None:
    with pytest.raises(TypeError, match="must be int"):
        make_feature_cache_key(
            tenant_id="a",
            schema_name="s",
            version=True,  # type: ignore[arg-type]
            row_key="u",
        )


def test_cache_key_empty_row_key_raises() -> None:
    with pytest.raises(ValueError, match="row_key"):
        make_feature_cache_key(tenant_id="a", schema_name="s", version=1, row_key="")


def test_cache_key_colon_in_row_key_raises() -> None:
    # A `:` in row_key would ambiguate the key shape — reject.
    with pytest.raises(ValueError, match="must not contain ':'"):
        make_feature_cache_key(
            tenant_id="a", schema_name="s", version=1, row_key="u:42"
        )


# ---------------------------------------------------------------------------
# Invalidation wildcards — keyspace-version-wildcard (Rule 3a)
# ---------------------------------------------------------------------------


def test_invalidation_pattern_single_version() -> None:
    pat = make_feature_group_wildcard(
        tenant_id="acme", schema_name="user_churn", version=2
    )
    # `v*` — survives future keyspace-version bumps per Rule 3a.
    assert pat == "kailash_ml:v*:acme:feature:user_churn:2:*"


def test_invalidation_pattern_all_versions() -> None:
    pat = make_feature_group_wildcard(tenant_id="acme", schema_name="user_churn")
    assert pat == "kailash_ml:v*:acme:feature:user_churn:*"


def test_invalidation_pattern_missing_tenant_raises() -> None:
    with pytest.raises(TenantRequiredError):
        make_feature_group_wildcard(tenant_id=None, schema_name="s")


# ---------------------------------------------------------------------------
# validate_tenant_id — operation-labelled error
# ---------------------------------------------------------------------------


def test_validate_tenant_id_returns_valid() -> None:
    assert validate_tenant_id("acme", operation="op") == "acme"


def test_validate_tenant_id_error_names_operation() -> None:
    with pytest.raises(TenantRequiredError, match="my_op:"):
        validate_tenant_id(None, operation="my_op")
