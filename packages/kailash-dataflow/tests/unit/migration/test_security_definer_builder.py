"""Tier 1 unit tests for :class:`SecurityDefinerBuilder`.

Covers:

- Five invariants emitted (SECURITY DEFINER, search_path, owner pin
  via ALTER FUNCTION ... OWNER TO, REVOKE/GRANT, multi-tenant filter
  inside body)
- Snapshot byte-shape for the canonical multi-tenant recipe (cross-SDK
  parity with the Rust reference impl)
- Identifier-injection rejection (function name, schema, role,
  function_owner, table, primary_lookup_column, active_column)
- Required-field errors (function_name, search_path,
  authenticator_role, function_owner, user_table, password_column,
  return_column, param)
- COMMENT body printable-ASCII allowlist enforcement
  (defense-in-depth on top of upstream identifier validation)
- Multi-tenant filter consistency (tenant_column without p_tenant_id)
- Extended ALLOWED_PG_TYPES coverage (#583 cross-SDK parity)
- ``primary_lookup_column`` override + derivation (#585)
- Opt-in ``active_column`` guard (#586)
- ``pg_type`` whitespace + casing normalization at insert time
"""

from __future__ import annotations

import pytest

from dataflow.migration import SecurityDefinerBuilder, SecurityDefinerBuilderError
from dataflow.migration.security_definer import _safe_comment_literal


def _canonical_multi_tenant_builder() -> SecurityDefinerBuilder:
    return (
        SecurityDefinerBuilder("resolve_user_by_email")
        .search_path("app")
        .authenticator_role("app_role")
        .function_owner("dataflow_app_owner")
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
        .function_owner("o")
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
        .function_owner("o")
        .user_table("t")
        .password_column("c")
        .param("p_key", ty)
        .return_column("id", "bigint")
    )


# ----------------------------------------------------------------------
# 1. Five invariants emitted (#607 Wave 4 hotfix added owner pinning).
# ----------------------------------------------------------------------


def test_emits_five_invariants() -> None:
    stmts = _canonical_multi_tenant_builder().build()
    assert (
        len(stmts) == 5
    ), "expected 5 statements: create, alter owner, comment, revoke, grant"

    create = stmts[0]
    alter_owner = stmts[1]
    comment = stmts[2]
    revoke = stmts[3]
    grant = stmts[4]
    # Invariant 1: pinned search_path.
    assert "SET search_path = app, pg_temp" in create
    # Invariant 2: REVOKE + GRANT exist (in stmts 3 and 4).
    assert "REVOKE ALL" in revoke
    assert "FROM PUBLIC" in revoke
    assert "GRANT EXECUTE" in grant
    assert '"app_role"' in grant
    # Invariant 3: SECURITY DEFINER and timing-note.
    assert "SECURITY DEFINER" in create
    assert "STABLE STRICT" in create
    assert "LANGUAGE sql" in create
    assert (
        "dummy bcrypt" in comment
    ), "comment must remind caller of T7 timing-safe discipline"
    # Invariant 4: multi-tenant filter in body.
    assert '"tenant_id" = p_tenant_id' in create
    # Invariant 5 (#607 Wave 4): pinned owner via ALTER FUNCTION ...
    # OWNER TO. Without this the function inherits the migration runner's
    # role at SECURITY DEFINER execute time (typically superuser-eq).
    assert "ALTER FUNCTION" in alter_owner
    assert "OWNER TO" in alter_owner
    assert '"dataflow_app_owner"' in alter_owner


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
        .function_owner("dataflow_app_owner")
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
            .function_owner("o")
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
            .function_owner("o")
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
            .function_owner("o")
            .user_table("t")
            .password_column("c")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_rejects_sql_injection_in_function_owner() -> None:
    """#607 Wave 4: function_owner identifier MUST be validated.

    Without validation, an attacker-controlled owner role would smuggle
    arbitrary SQL into the emitted ``ALTER FUNCTION ... OWNER TO`` line.
    Mirrors the authenticator_role defense.
    """
    with pytest.raises(SecurityDefinerBuilderError, match="invalid"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
            .function_owner('owner"; DROP TABLE users; --')
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
            .function_owner("o")
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
            .function_owner("o")
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
            .function_owner("o")
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


def test_build_raises_when_function_owner_unset() -> None:
    """#607 Wave 4 H3: function_owner is REQUIRED at build() time.

    SECURITY DEFINER without an explicit owner inherits the migration
    runner's role at execute time — typically a superuser-equivalent.
    The check MUST raise ``SecurityDefinerBuilderError`` with the exact
    "function_owner is required" phrase so the error message is
    grep-able across log aggregators (per
    ``rules/observability.md`` § 1).
    """
    with pytest.raises(SecurityDefinerBuilderError, match="function_owner is required"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
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
            .function_owner("o")
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
            .function_owner("o")
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
            .function_owner("o")
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
            .function_owner("o")
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
            .function_owner("o")
            .user_table("t")
            .password_column("c")
            .tenant_column("tenant_id")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


def test_comment_mentions_password_column() -> None:
    stmts = _canonical_multi_tenant_builder().build()
    # Statement order: [create=0, alter_owner=1, comment=2, revoke=3, grant=4].
    assert "password_hash" in stmts[2]


def test_revoke_precedes_grant_and_targets_correct_signature() -> None:
    stmts = _canonical_multi_tenant_builder().build()
    # REVOKE at index 3, GRANT at index 4 (post-#607 Wave 4 reordering).
    assert stmts[3].startswith("REVOKE ALL ON FUNCTION")
    assert "(text, bigint)" in stmts[3]
    assert stmts[4].startswith("GRANT EXECUTE ON FUNCTION")
    assert "(text, bigint)" in stmts[4]


def test_emitted_ddl_includes_alter_owner_to() -> None:
    """#607 Wave 4 H3: emitted DDL MUST include ``ALTER FUNCTION ...
    OWNER TO`` with the configured function_owner.

    Pins:
    - The ALTER OWNER statement exists in the returned list.
    - It sits at index 1 (immediately after CREATE) so the function
      never exists under the migration role for a non-trivial moment.
    - The owner identifier is double-quoted exactly per
      ``dataflow-identifier-safety.md`` MUST Rule 1.
    - The ALTER targets the same fully-qualified function signature as
      the CREATE / REVOKE / GRANT (no schema or argument-list drift).
    """
    stmts = _canonical_multi_tenant_builder().build()
    alter_owner = stmts[1]
    assert alter_owner.startswith(
        'ALTER FUNCTION "app"."resolve_user_by_email"(text, bigint) '
        'OWNER TO "dataflow_app_owner"'
    )
    # ALTER OWNER MUST NOT appear in any other statement (anti-drift).
    for i, s in enumerate(stmts):
        if i != 1:
            assert "ALTER FUNCTION" not in s
            assert "OWNER TO" not in s


def test_function_owner_validates_identifier() -> None:
    """#607 Wave 4 H3: function_owner routes through the same
    quote_identifier defense as authenticator_role.

    Mirrors :func:`test_rejects_sql_injection_in_function_owner` but
    pins the contract under the documented test name (the redteam
    finding mandated this test name).
    """
    with pytest.raises(SecurityDefinerBuilderError, match="invalid"):
        (
            SecurityDefinerBuilder("f")
            .search_path("app")
            .authenticator_role("r")
            .function_owner('role"; DROP --')
            .user_table("t")
            .password_column("c")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


# ----------------------------------------------------------------------
# 4b. _safe_comment_literal helper — defense-in-depth on COMMENT body.
# ----------------------------------------------------------------------


def test_safe_comment_literal_passes_printable_ascii() -> None:
    """Body containing only printable ASCII (no backslash) round-trips
    through the helper unchanged except for SQL-standard single-quote
    doubling."""
    assert _safe_comment_literal("Hello world.") == "Hello world.", "no `'` to double"
    assert (
        _safe_comment_literal("It's a comment.") == "It''s a comment."
    ), "single quote MUST be doubled per SQL spec"


def test_safe_comment_literal_rejects_backslash_and_control_chars() -> None:
    """#607 Wave 4 H4: helper enforces printable-ASCII allowlist.

    Defense-in-depth: a future refactor that allows an interpolant to
    bypass ``_quote()`` would land bytes in the COMMENT body that the
    inline ``chr(39).replace`` form silently let through. The helper
    raises ``SecurityDefinerBuilderError`` instead.

    Coverage:
    - Backslash (``\\``) — ambiguous under
      ``standard_conforming_strings = off``.
    - Control char (``\\n``) — outside ``0x20 <= ord(c) < 0x7F``.
    - Null byte (``\\x00``) — explicitly outside allowlist.
    - DEL (``\\x7F``) — boundary case, MUST be rejected.
    - Unicode smart quote (``\\u2019``) — non-ASCII rejected.
    """
    payloads = [
        "back\\slash inside body",
        "newline\nhere",
        "null\x00byte",
        "del\x7fchar",
        "smart\u2019quote",
    ]
    for body in payloads:
        with pytest.raises(
            SecurityDefinerBuilderError, match="printable-ASCII allowlist"
        ):
            _safe_comment_literal(body)


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
        .function_owner("o")
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
        .function_owner("o")
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
            .function_owner("o")
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
        .function_owner("o")
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
        .function_owner("o")
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
            .function_owner("o")
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
        .function_owner("o")
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

    #607 Wave 4: statement count grew from 4 to 5 with the addition of
    ``ALTER FUNCTION ... OWNER TO`` between CREATE and COMMENT. This
    test pins kailash-py's local byte-shape; cross-SDK parity with
    kailash-rs awaits the kailash-rs side of the cross-SDK align (see
    ``tests/regression/test_issue_607_cross_sdk_vectors.py`` for the
    fixture-driven contract).
    """
    stmts = _canonical_multi_tenant_builder().build()
    assert len(stmts) == 5
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
    expected_alter_owner = (
        'ALTER FUNCTION "app"."resolve_user_by_email"'
        '(text, bigint) OWNER TO "dataflow_app_owner"'
    )
    assert stmts[1] == expected_alter_owner
    expected_revoke = (
        'REVOKE ALL ON FUNCTION "app"."resolve_user_by_email"'
        "(text, bigint) FROM PUBLIC"
    )
    expected_grant = (
        'GRANT EXECUTE ON FUNCTION "app"."resolve_user_by_email"'
        '(text, bigint) TO "app_role"'
    )
    # COMMENT at index 2, REVOKE at 3, GRANT at 4 (post-Wave-4 reorder).
    assert stmts[3] == expected_revoke
    assert stmts[4] == expected_grant


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
            .function_owner("o")
            .user_table("t")
            .password_column("c")
            .return_column("id", "bigint")
            .build()
        )
