"""Tier 2 integration tests for :class:`SecurityDefinerBuilder` against
real PostgreSQL.

Verifies that the emitted SQL, applied via asyncpg, produces a function
that:

1. Exists in ``pg_proc`` with ``prosecdef = true`` (SECURITY DEFINER).
2. Has ``proconfig`` containing ``search_path=<schema>, pg_temp``.
3. Is ``STABLE STRICT`` and ``LANGUAGE sql``.
4. Does NOT grant ``EXECUTE`` to ``PUBLIC``.
5. DOES grant ``EXECUTE`` to the authenticator role.
6. Has ``pg_proc.proowner`` matching the configured ``function_owner``
   (#607 Wave 4 H3: SECURITY DEFINER without owner pinning silently
   inherits the migration-runner's role at execute time).
7. Enforces the T8 multi-tenant filter — correct-tenant call returns
   the row; same email + wrong tenant returns 0 rows.
8. Inactive users are excluded by the ``active_column`` guard.
9. Identifier-injection payloads are rejected at ``build()`` time
   (defense-in-depth: mirrors the Tier 1 test, repeated here so the
   integration run exercises the contract end-to-end).
10. Pre-auth carve-out actually bypasses an RLS policy that would
    otherwise return 0 rows for an unauthenticated session — this is
    the load-bearing claim the whole feature exists to deliver.

NO MOCKING POLICY: this file uses real asyncpg against the standard
DataFlow test Postgres (port 5434, see
``packages/kailash-dataflow/tests/integration/conftest.py``).
"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator, Tuple

import asyncpg
import pytest

from dataflow.migration import SecurityDefinerBuilder, SecurityDefinerBuilderError


def _pg_url() -> str:
    """Resolve the test database URL.

    Mirrors the resolution in
    ``packages/kailash-dataflow/tests/integration/conftest.py`` so this
    module can run via the ``asyncpg`` connection directly without
    requiring the full DataFlow fixture stack — pre-auth lookup
    integration must work even without a fully constructed DataFlow
    instance.
    """
    if "TEST_DATABASE_URL" in os.environ:
        return os.environ["TEST_DATABASE_URL"]
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5434")
    db_user = os.environ.get("DB_USER", "test_user")
    db_password = os.environ.get("DB_PASSWORD", "test_password")
    db_name = os.environ.get("DB_NAME", "kailash_test")
    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


# Per-test counter to keep parallel xdist workers from racing on the
# same schema name. Module-scope counter isn't shared across processes,
# so we add a process pid suffix as well.
_COUNTER = 0
_COUNTER_LOCK = asyncio.Lock()


async def _next_test_n() -> int:
    global _COUNTER
    async with _COUNTER_LOCK:
        _COUNTER += 1
        return _COUNTER


class _Fixture:
    """Per-test schema + role + table fixture.

    All identifiers are namespaced with a per-test integer suffix so
    parallel test runners cannot collide on the same name. Cleanup is
    explicit (``teardown``) — Python ``__del__`` cannot run async
    SQL.
    """

    def __init__(self, n: int, pid: int) -> None:
        self.schema = f"sd_test_{pid}_{n}"
        self.role = f"sd_test_auth_{pid}_{n}"
        # #607 Wave 4 H3: separate low-privilege owner role for the
        # SECURITY DEFINER function. MUST NOT be the migration runner
        # nor the authenticator (the auth role is GRANTed EXECUTE; the
        # owner role is what the function RUNS AS).
        self.owner_role = f"sd_test_owner_{pid}_{n}"
        self.function_name = "resolve_user_by_email"

    async def setup(self, conn: asyncpg.Connection) -> None:
        # Best-effort cleanup from any prior failed run.
        await conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
        await conn.execute(f"DROP ROLE IF EXISTS {self.role}")
        await conn.execute(f"DROP ROLE IF EXISTS {self.owner_role}")

        await conn.execute(f"CREATE SCHEMA {self.schema}")
        await conn.execute(f"CREATE ROLE {self.role} NOLOGIN")
        # Owner role needs BYPASSRLS so the SECURITY DEFINER function
        # can read the user table even when the schema has an RLS
        # policy. NOLOGIN keeps the role from being a login surface;
        # it only exists as the function-owner identity.
        await conn.execute(f"CREATE ROLE {self.owner_role} NOLOGIN BYPASSRLS")
        await conn.execute(
            f"""
            CREATE TABLE {self.schema}.users (
                id bigserial PRIMARY KEY,
                email text NOT NULL,
                password_hash text NOT NULL,
                is_active boolean NOT NULL DEFAULT true,
                tenant_id bigint NOT NULL
            )
            """
        )
        # The owner role needs SELECT on the user table so the
        # function body can read it post-OWNER-swap.
        await conn.execute(f"GRANT SELECT ON {self.schema}.users TO {self.owner_role}")
        await conn.execute(f"GRANT USAGE ON SCHEMA {self.schema} TO {self.owner_role}")
        await conn.execute(
            f"""
            INSERT INTO {self.schema}.users
                (email, password_hash, is_active, tenant_id)
            VALUES
                ('alice@example.com', 'hash-a', true,  1),
                ('bob@example.com',   'hash-b', true,  2),
                ('cain@example.com',  'hash-c', false, 1)
            """
        )

    async def teardown(self, conn: asyncpg.Connection) -> None:
        # CASCADE removes the function too (the roles' deps), then
        # the roles drop cleanly. Drop the owner LAST because the
        # function may still hold a dependency on it until the
        # CASCADE drops the schema.
        await conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
        await conn.execute(f"DROP ROLE IF EXISTS {self.role}")
        await conn.execute(f"DROP ROLE IF EXISTS {self.owner_role}")

    def builder(self) -> SecurityDefinerBuilder:
        return (
            SecurityDefinerBuilder(self.function_name)
            .search_path(self.schema)
            .authenticator_role(self.role)
            .function_owner(self.owner_role)
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

    @property
    def qfn(self) -> str:
        return f"{self.schema}.{self.function_name}"


@pytest.fixture()
async def fixture() -> AsyncIterator[Tuple[asyncpg.Connection, _Fixture]]:
    """Per-test schema + role + table; auto-teardown on exit."""
    n = await _next_test_n()
    fx = _Fixture(n=n, pid=os.getpid())
    conn = await asyncpg.connect(_pg_url())
    try:
        await fx.setup(conn)
        yield conn, fx
    finally:
        try:
            await fx.teardown(conn)
        finally:
            await conn.close()


async def _apply_builder(conn: asyncpg.Connection, stmts: list[str]) -> None:
    for stmt in stmts:
        try:
            await conn.execute(stmt)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                f"builder SQL failed:\n{stmt}\n\nerror: {exc}"
            ) from exc


# ----------------------------------------------------------------------
# 1. Structural introspection — prosecdef / proconfig / provolatile /
#    proisstrict / prolang.
# ----------------------------------------------------------------------


@pytest.mark.integration
async def test_builder_emits_function_with_security_definer_invariants(
    fixture: Tuple[asyncpg.Connection, _Fixture],
) -> None:
    conn, fx = fixture
    stmts = fx.builder().build()
    await _apply_builder(conn, stmts)

    row = await conn.fetchrow(
        """
        SELECT prosecdef, provolatile::text AS provolatile_t,
               proisstrict, l.lanname AS prolang
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        JOIN pg_language l  ON p.prolang     = l.oid
        WHERE proname = $1 AND n.nspname = $2
        """,
        fx.function_name,
        fx.schema,
    )
    assert row is not None, "function should exist exactly once"
    assert row["prosecdef"] is True, "prosecdef must be true (SECURITY DEFINER)"
    # provolatile 's' = STABLE
    assert row["provolatile_t"] == "s", "provolatile must be 's' (STABLE)"
    assert row["proisstrict"] is True, "proisstrict must be true (STRICT)"
    assert row["prolang"] == "sql", "prolang must be 'sql'"

    # proconfig MUST include search_path
    config_rows = await conn.fetch(
        """
        SELECT unnest(proconfig) AS cfg
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE proname = $1 AND n.nspname = $2
        """,
        fx.function_name,
        fx.schema,
    )
    expected_suffix = f"search_path={fx.schema}, pg_temp"
    found = any(expected_suffix in r["cfg"] for r in config_rows)
    assert found, f"proconfig must contain '{expected_suffix}': {config_rows!r}"


# ----------------------------------------------------------------------
# 2. Grant table — PUBLIC is revoked, authenticator role has EXECUTE.
# ----------------------------------------------------------------------


@pytest.mark.integration
async def test_public_has_no_execute_authenticator_does(
    fixture: Tuple[asyncpg.Connection, _Fixture],
) -> None:
    conn, fx = fixture
    await _apply_builder(conn, fx.builder().build())

    sig = f"{fx.qfn}(text, bigint)"
    row = await conn.fetchrow(
        """
        SELECT has_function_privilege('public', $1, 'EXECUTE') AS pub_exec,
               has_function_privilege($2, $3, 'EXECUTE')       AS auth_exec
        """,
        sig,
        fx.role,
        sig,
    )
    assert row is not None
    assert row["pub_exec"] is False, "PUBLIC must NOT have EXECUTE privilege"
    assert row["auth_exec"] is True, f"{fx.role} MUST have EXECUTE privilege"


# ----------------------------------------------------------------------
# 3. T8 — multi-tenant filter blocks cross-tenant reads.
# ----------------------------------------------------------------------


@pytest.mark.integration
async def test_t8_multi_tenant_filter_blocks_cross_tenant_read(
    fixture: Tuple[asyncpg.Connection, _Fixture],
) -> None:
    conn, fx = fixture
    await _apply_builder(conn, fx.builder().build())

    call_sql = f"SELECT id, email, password_hash, is_active " f"FROM {fx.qfn}($1, $2)"

    # alice lives in tenant 1. Correct tenant -> 1 row.
    rows = await conn.fetch(call_sql, "alice@example.com", 1)
    assert len(rows) == 1, "correct tenant should resolve alice"
    assert rows[0]["email"] == "alice@example.com"

    # Same email, wrong tenant -> 0 rows (T8 mitigation).
    rows = await conn.fetch(call_sql, "alice@example.com", 2)
    assert (
        len(rows) == 0
    ), "T8 REGRESSION: cross-tenant read returned alice's row to tenant 2"

    # is_active filter: cain is inactive in tenant 1 -> 0 rows.
    rows = await conn.fetch(call_sql, "cain@example.com", 1)
    assert len(rows) == 0, "inactive user must be excluded"


# ----------------------------------------------------------------------
# 4. Unknown user returns 0 rows (T7 baseline).
# ----------------------------------------------------------------------


@pytest.mark.integration
async def test_unknown_user_returns_zero_rows(
    fixture: Tuple[asyncpg.Connection, _Fixture],
) -> None:
    conn, fx = fixture
    await _apply_builder(conn, fx.builder().build())

    rows = await conn.fetch(f"SELECT id FROM {fx.qfn}($1, $2)", "ghost@example.com", 1)
    assert len(rows) == 0


# ----------------------------------------------------------------------
# 5. Pre-auth carve-out actually bypasses RLS.
#
# This is the load-bearing claim the whole feature exists to deliver:
# even with a default-deny RLS policy on users (a session with
# row_security.tenant_id unset would normally return 0 rows), the
# SECURITY DEFINER function MUST still return alice's row when called
# with the right tenant_id.
# ----------------------------------------------------------------------


@pytest.mark.integration
async def test_security_definer_bypasses_rls_for_unauthenticated_session(
    fixture: Tuple[asyncpg.Connection, _Fixture],
) -> None:
    conn, fx = fixture
    await _apply_builder(conn, fx.builder().build())

    # Enable an RLS policy that would block a normal SELECT in a session
    # without row_security.tenant_id set. The SECURITY DEFINER function
    # bypasses this policy because it runs as the function owner with
    # BYPASSRLS implied (or with a policy on the same table that the
    # function's owner can satisfy).
    await conn.execute(f"ALTER TABLE {fx.schema}.users ENABLE ROW LEVEL SECURITY")
    # Default-deny policy: no rows visible to non-owners without an
    # explicit USING clause that matches.
    await conn.execute(
        f"""
        CREATE POLICY default_deny ON {fx.schema}.users
        FOR SELECT
        USING (false)
        """
    )

    call_sql = f"SELECT email FROM {fx.qfn}($1, $2)"
    # Direct SELECT would return 0 rows because the policy denies all.
    # But the SECURITY DEFINER function bypasses this — alice's row
    # comes back even though the calling session has no auth context.
    # The function's owner (the dedicated low-privilege owner role with
    # BYPASSRLS, set via .function_owner() — see #607 Wave 4 H3) is the
    # role the function runs as, and it has BYPASSRLS so the policy
    # cannot block it. This is the production configuration.
    rows = await conn.fetch(call_sql, "alice@example.com", 1)
    assert len(rows) == 1, (
        "SECURITY DEFINER MUST bypass RLS — this is the whole point of "
        "the pre-auth carveout pattern"
    )
    assert rows[0]["email"] == "alice@example.com"


# ----------------------------------------------------------------------
# 6. Defense-in-depth — injection payloads still rejected at build().
# ----------------------------------------------------------------------


@pytest.mark.integration
async def test_defense_in_depth_rejects_identifier_injection() -> None:
    with pytest.raises(SecurityDefinerBuilderError, match="invalid"):
        (
            SecurityDefinerBuilder('resolve"; DROP TABLE users; --')
            .search_path("app")
            .authenticator_role("app_role")
            .function_owner("dataflow_app_owner")
            .user_table("users")
            .password_column("password_hash")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )


# ----------------------------------------------------------------------
# 7. Comment is persisted on the function.
# ----------------------------------------------------------------------


@pytest.mark.integration
async def test_comment_persisted_on_function(
    fixture: Tuple[asyncpg.Connection, _Fixture],
) -> None:
    conn, fx = fixture
    await _apply_builder(conn, fx.builder().build())

    row = await conn.fetchrow(
        """
        SELECT pg_catalog.obj_description(p.oid, 'pg_proc') AS comment_body
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE proname = $1 AND n.nspname = $2
        """,
        fx.function_name,
        fx.schema,
    )
    assert row is not None
    body = row["comment_body"]
    assert (
        body is not None and "dummy bcrypt" in body
    ), "COMMENT must remind caller of T7 timing-safe discipline"
    assert (
        "T8 cross-tenant" in body
    ), "COMMENT must mention T8 mitigation when tenant_column is set"


# ----------------------------------------------------------------------
# 8. #607 Wave 4 H3 — pg_proc.proowner matches configured owner.
#
# The structural defense for SECURITY DEFINER privilege escalation. If
# this assertion fails, every emitted helper inherits the migration
# runner's role at execute time (typically a superuser-equivalent),
# defeating the bypass-protection design intent.
# ----------------------------------------------------------------------


@pytest.mark.integration
async def test_pg_proc_proowner_matches_function_owner_setter(
    fixture: Tuple[asyncpg.Connection, _Fixture],
) -> None:
    """The function's pg_proc.proowner MUST equal the role passed to
    .function_owner(...) — not the migration-runner's role.

    This is the wired test that Tier 1 cannot give us: we apply the
    emitted DDL to a real PostgreSQL instance and inspect the
    catalog. If a future refactor drops the ALTER OWNER statement or
    sends it to the wrong role, this test fails loudly.
    """
    conn, fx = fixture
    await _apply_builder(conn, fx.builder().build())

    row = await conn.fetchrow(
        """
        SELECT r.rolname AS owner_rolname
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        JOIN pg_roles r     ON p.proowner     = r.oid
        WHERE p.proname = $1 AND n.nspname = $2
        """,
        fx.function_name,
        fx.schema,
    )
    assert row is not None, "function should exist exactly once"
    assert row["owner_rolname"] == fx.owner_role, (
        f"pg_proc.proowner MUST equal the role passed to .function_owner() "
        f"(expected {fx.owner_role!r}, got {row['owner_rolname']!r}). "
        f"Without this, SECURITY DEFINER inherits the migration runner's "
        f"role at execute time — typically a superuser-equivalent — which "
        f"defeats the bypass-protection design intent."
    )
