"""Tier 1 unit tests for :class:`SecurityDefinerBuilder`.

Covers:

- Four invariants emitted (SECURITY DEFINER, search_path, REVOKE/GRANT,
  multi-tenant filter inside body)
- Snapshot byte-shape for the canonical multi-tenant recipe (cross-SDK
  parity with the Rust reference impl)
- Identifier-injection rejection (function name, schema, role, table,
  primary_lookup_column, active_column)
- Required-field errors (function_name, search_path, return_column,
  param)
- Multi-tenant filter consistency (tenant_column without p_tenant_id)
- Extended ALLOWED_PG_TYPES coverage (#583 cross-SDK parity)
- ``primary_lookup_column`` override + derivation (#585)
- Opt-in ``active_column`` guard (#586)
- ``pg_type`` whitespace + casing normalization at insert time
"""

from __future__ import annotations

import pytest

from dataflow.migration import SecurityDefinerBuilder, SecurityDefinerBuilderError


def _canonical_multi_tenant_builder() -> SecurityDefinerBuilder:
    return (
        SecurityDefinerBuilder("resolve_user_by_email")
        .search_path("app")
        .authenticator_role("app_role")
        .user_table("users")
        .password_column("password_hash")
        .tenant_column("tenant_id")
        .active_column("is_active")
        .param("p_email", "text")
        .param("p_tenant_id", "bigint")
        .return_column("id", "bigint")
        .return_column("email", "text")
        .return_column("password_hash", "text")
        .return_column("is_active", "boolean")
    )


def _minimal_builder_with_return_type(ty: str) -> SecurityDefinerBuilder:
    return (
        SecurityDefinerBuilder("f")
        .search_path("app")
        .authenticator_role("r")
        .user_table("t")
        .password_column("c")
        .param("p_email", "text")
        .return_column("id", ty)
    )


def _minimal_builder_with_param_type(ty: str) -> SecurityDefinerBuilder:
    return (
        SecurityDefinerBuilder("f")
        .search_path("app")
        .authenticator_role("r")
        .user_table("t")
        .password_column("c")
        .param("p_key", ty)
        .return_column("id", "bigint")
    )


# ----------------------------------------------------------------------
# 1. Four invariants emitted.
# ----------------------------------------------------------------------


def test_emits_four_invariants() -> None:
    stmts = _canonical_multi_tenant_builder().build()
    assert len(stmts) == 4, "expected 4 statements: create, comment, revoke, grant"

    create = stmts[0]
    # Invariant 1: pinned search_path.
    assert "SET search_path = app, pg_temp" in create
    # Invariant 2: REVOKE + GRANT exist (in stmts 2 and 3).
    assert "REVOKE ALL" in stmts[2]
    assert "FROM PUBLIC" in stmts[2]
    assert "GRANT EXECUTE" in stmts[3]
    assert '"app_role"' in stmts[3]
    # Invariant 3: SECURITY DEFINER and timing-note.
    assert "SECURITY DEFINER" in create
    assert "STABLE STRICT" in create
    assert "LANGUAGE sql" in create
    assert (
        "dummy bcrypt" in stmts[1]
    ), "comment must remind caller of T7 timing-safe discipline"
    # Invariant 4: multi-tenant filter in body.
    assert '"tenant_id" = p_tenant_id' in create


# ----------------------------------------------------------------------
# 2. Snapshot byte-shape — cross-SDK parity with Rust ref impl.
# ----------------------------------------------------------------------


def test_snapshot_matches_recipe_byte_shape() -> None:
    stmts = _canonical_multi_tenant_builder().build()
    create = stmts[0]
    assert "CREATE OR REPLACE FUNCTION" in create
    assert '"app"."resolve_user_by_email"' in create
    # Param names + RETURNS TABLE column names are double-quoted per
    # dataflow-identifier-safety.md MUST Rule 1.
    assert (
        'RETURNS TABLE ("id" bigint, "email" text, '
        '"password_hash" text, "is_active" boolean)' in create
    )
    assert '"p_email" text' in create
    assert '"p_tenant_id" bigint' in create
    assert '"email" = p_email' in create
    assert 'FROM "app"."users"' in create
    assert '"is_active" = true' in create
    assert "LIMIT 1" in create


def test_single_tenant_omits_tenant_clause() -> None:
    stmts = (
        SecurityDefinerBuilder("resolve_user_by_email")
        .search_path("app")
        .authenticator_role("app_role")
        .user_table("users")
        .password_column("password_hash")
        .active_column("is_active")
        .param("p_email", "text")
        .return_column("id", "bigint")
        .return_column("email", "text")
        .return_column("password_hash", "text")
        .return_column("is_active", "boolean")
        .build()
    )
    create = stmts[0]
    assert "tenant_id" not in create
    assert "p_tenant_id" not in create
    assert '"email" = p_email' in create
    assert '"is_active" = true' in create


# ----------------------------------------------------------------------
# 3. Identifier validation — rejects injection payloads.
# ----------------------------------------------------------------------


def test_rejects_sql_injection_in_function_name() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="invalid"):
        (
            SecurityDefinerBuilder('resolve"; DROP TABLE users; --')
            .search_path("app")
            .authenticator_role("app_role")
            .user_table("users")
            .password_column("password_hash")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_rejects_sql_injection_in_schema() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="invalid"):
        (
            SecurityDefinerBuilder("f")
            .search_path('app"; DROP TABLE users')
            .authenticator_role("r")
            .user_table("t")
            .password_column("c")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_rejects_sql_injection_in_role() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="invalid"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("role; GRANT SUPERUSER")
            .user_table("t")
            .password_column("c")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_rejects_sql_injection_in_user_table() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="invalid"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
            .user_table('users"; DROP TABLE customers; --')
            .password_column("c")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_rejects_digit_leading_identifier() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="invalid"):
        (
            SecurityDefinerBuilder("123abc")
            .search_path("app")
            .authenticator_role("r")
            .user_table("t")
            .password_column("c")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_rejects_space_in_identifier() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="invalid"):
        (
            SecurityDefinerBuilder("name WITH DATA")
            .search_path("app")
            .authenticator_role("r")
            .user_table("t")
            .password_column("c")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_rejects_unknown_pg_type() -> None:
    with pytest.raises(
        SecurityDefinerBuilderError, match="unsupported PostgreSQL type"
    ):
        _minimal_builder_with_return_type("my_custom_type").build()


def test_rejects_injection_via_pg_type() -> None:
    with pytest.raises(
        SecurityDefinerBuilderError, match="unsupported PostgreSQL type"
    ):
        _minimal_builder_with_return_type("bigint; DROP TABLE users").build()


# ----------------------------------------------------------------------
# 4. Builder contract — required fields, consistency invariants.
# ----------------------------------------------------------------------


def test_requires_function_name() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="function_name"):
        (
            SecurityDefinerBuilder()
            .search_path("app")
            .authenticator_role("r")
            .user_table("t")
            .password_column("c")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_requires_search_path() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="search_path"):
        (
            SecurityDefinerBuilder("f")
            .authenticator_role("r")
            .user_table("t")
            .password_column("c")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_requires_authenticator_role() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="authenticator_role"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .user_table("t")
            .password_column("c")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_requires_user_table() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="user_table"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
            .password_column("c")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_requires_password_column() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="password_column"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
            .user_table("t")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_requires_at_least_one_return_column() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="return_column"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
            .user_table("t")
            .password_column("c")
            .param("p_email", "text")
            .build()
        )


def test_requires_at_least_one_param() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="param"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
            .user_table("t")
            .password_column("c")
            .return_column("id", "bigint")
            .build()
        )


def test_tenant_column_without_p_tenant_id_rejected() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="p_tenant_id"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
            .user_table("t")
            .password_column("c")
            .tenant_column("tenant_id")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_comment_mentions_password_column() -> None:
    stmts = _canonical_multi_tenant_builder().build()
    assert "password_hash" in stmts[1]


def test_revoke_precedes_grant_and_targets_correct_signature() -> None:
    stmts = _canonical_multi_tenant_builder().build()
    # REVOKE comes at index 2, GRANT at index 3.
    assert stmts[2].startswith("REVOKE ALL ON FUNCTION")
    assert "(text, bigint)" in stmts[2]
    assert stmts[3].startswith("GRANT EXECUTE ON FUNCTION")
    assert "(text, bigint)" in stmts[3]


# ----------------------------------------------------------------------
# 5. Extended ALLOWED_PG_TYPES coverage (#583).
# ----------------------------------------------------------------------


def test_allows_smallserial_type() -> None:
    stmts = _minimal_builder_with_return_type("smallserial").build()
    assert "smallserial" in stmts[0]


def test_allows_inet_type() -> None:
    stmts = _minimal_builder_with_param_type("inet").build()
    assert '"p_key" inet' in stmts[0]


def test_allows_cidr_type() -> None:
    stmts = _minimal_builder_with_param_type("cidr").build()
    assert '"p_key" cidr' in stmts[0]


def test_allows_citext_type() -> None:
    stmts = _minimal_builder_with_return_type("citext").build()
    assert "citext" in stmts[0]


def test_allows_interval_type() -> None:
    stmts = _minimal_builder_with_param_type("interval").build()
    assert '"p_key" interval' in stmts[0]


def test_rejects_injection_via_new_type_inet() -> None:
    with pytest.raises(
        SecurityDefinerBuilderError, match="unsupported PostgreSQL type"
    ):
        _minimal_builder_with_param_type("inet; DROP TABLE users").build()


# ----------------------------------------------------------------------
# 6. Explicit primary_lookup_column override (#585).
# ----------------------------------------------------------------------


def test_primary_lookup_column_overrides_derived_name() -> None:
    # Param is `p_user_email` (would derive `user_email`), but the
    # actual schema column is `email`. Override pins it.
    stmts = (
        SecurityDefinerBuilder("f")
        .search_path("app")
        .authenticator_role("r")
        .user_table("t")
        .password_column("c")
        .primary_lookup_column("email")
        .param("p_user_email", "text")
        .return_column("id", "bigint")
        .build()
    )
    create = stmts[0]
    assert '"email" = p_user_email' in create
    assert '"user_email" = p_user_email' not in create


def test_primary_lookup_column_unset_preserves_derivation() -> None:
    # Backward-compat: callers who don't set primary_lookup_column
    # still get the p_-prefix-strip derivation.
    stmts = (
        SecurityDefinerBuilder("f")
        .search_path("app")
        .authenticator_role("r")
        .user_table("t")
        .password_column("c")
        .param("p_email", "text")
        .return_column("id", "bigint")
        .build()
    )
    assert '"email" = p_email' in stmts[0]


def test_primary_lookup_column_validates_identifier() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="invalid"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
            .user_table("t")
            .password_column("c")
            .primary_lookup_column('email"; DROP TABLE users; --')
            .param("p_user_email", "text")
            .return_column("id", "bigint")
            .build()
        )


# ----------------------------------------------------------------------
# 7. Opt-in active_column guard (#586).
# ----------------------------------------------------------------------


def test_omit_active_column_emits_no_activity_guard() -> None:
    stmts = (
        SecurityDefinerBuilder("f")
        .search_path("app")
        .authenticator_role("r")
        .user_table("t")
        .password_column("c")
        .param("p_email", "text")
        .return_column("id", "bigint")
        .build()
    )
    create = stmts[0]
    assert "is_active" not in create
    assert "= true" not in create


def test_active_column_emits_column_equals_true() -> None:
    stmts = (
        SecurityDefinerBuilder("f")
        .search_path("app")
        .authenticator_role("r")
        .user_table("t")
        .password_column("c")
        .active_column("enabled")
        .param("p_email", "text")
        .return_column("id", "bigint")
        .build()
    )
    assert '"enabled" = true' in stmts[0]


def test_active_column_validates_identifier() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="invalid"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
            .user_table("t")
            .password_column("c")
            .active_column('is_active"; DROP TABLE users; --')
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


# ----------------------------------------------------------------------
# 8. pg_type normalization — leading/trailing whitespace + casing
# stripped at insert time so emitted SQL matches allowlist byte-for-byte.
# ----------------------------------------------------------------------


def test_pg_type_normalized_at_insert_strips_whitespace_and_case() -> None:
    stmts = (
        SecurityDefinerBuilder("f")
        .search_path("app")
        .authenticator_role("r")
        .user_table("t")
        .password_column("c")
        .param("p_email", "  TEXT  ")
        .return_column("id", "  BIGINT  ")
        .build()
    )
    create = stmts[0]
    assert '"p_email" text' in create
    assert '"id" bigint' in create
    assert "TEXT" not in create
    assert "BIGINT" not in create


# ----------------------------------------------------------------------
# 9. Cross-SDK byte-shape vector — one canonical chain pinned against
# the JSON fixture shared with kailash-rs.
# ----------------------------------------------------------------------


def test_cross_sdk_byte_shape_canonical_multi_tenant() -> None:
    """The canonical multi-tenant builder MUST emit a fixed byte-shape.

    This is the cross-SDK parity test: kailash-rs runs the same fixture
    against its own Rust impl and asserts the same bytes. If either SDK
    drifts, both tests catch it.
    """
    stmts = _canonical_multi_tenant_builder().build()
    expected_create = (
        'CREATE OR REPLACE FUNCTION "app"."resolve_user_by_email"'
        '("p_email" text, "p_tenant_id" bigint)\n'
        'RETURNS TABLE ("id" bigint, "email" text, '
        '"password_hash" text, "is_active" boolean)\n'
        "LANGUAGE sql\n"
        "SECURITY DEFINER\n"
        "SET search_path = app, pg_temp\n"
        "STABLE STRICT\n"
        "AS $$\n"
        '  SELECT "id", "email", "password_hash", "is_active"\n'
        '  FROM "app"."users"\n'
        '  WHERE "email" = p_email\n'
        '    AND "tenant_id" = p_tenant_id\n'
        '    AND "is_active" = true\n'
        "  LIMIT 1;\n"
        "$$"
    )
    assert stmts[0] == expected_create
    expected_revoke = (
        'REVOKE ALL ON FUNCTION "app"."resolve_user_by_email"'
        "(text, bigint) FROM PUBLIC"
    )
    expected_grant = (
        'GRANT EXECUTE ON FUNCTION "app"."resolve_user_by_email"'
        '(text, bigint) TO "app_role"'
    )
    assert stmts[2] == expected_revoke
    assert stmts[3] == expected_grant


def test_revoke_grant_with_no_params_uses_empty_signature() -> None:
    """Edge case: signature with no params (single param required, but
    edge case test ensures no params edge handled if relaxed in
    future)."""
    # The builder requires at least one param; this is the contract.
    with pytest.raises(SecurityDefinerBuilderError, match="param"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
            .user_table("t")
            .password_column("c")
            .return_column("id", "bigint")
            .build()
        )
