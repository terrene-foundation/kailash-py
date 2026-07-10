"""
SQL Dialect Abstraction Layer

Provides database-specific SQL generation for DataFlow operations.
Eliminates inline database type checks and consolidates SQL generation logic.

Architecture:
    SQLDialectFactory.get_dialect(database_type)
          ↓
    ┌─────────┬─────────┬────────┐
    ▼         ▼         ▼        ▼
PostgreSQL  SQLite   MySQL   MongoDB
Dialect     Dialect  Dialect  Dialect
"""

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# Issue #1546: the ``VALUES(col)`` reference inside ``ON DUPLICATE KEY UPDATE`` is
# DEPRECATED as of MySQL 8.0.20. MySQL 8.0.19 introduced the replacement row-alias
# form ``INSERT ... VALUES (...) AS alias ON DUPLICATE KEY UPDATE col = alias.col``.
# The row-alias form is NOT supported by MariaDB (any version) nor MySQL < 8.0.19,
# so the emitter version-gates on this floor.
_MYSQL_ROW_ALIAS_MIN_VERSION: Tuple[int, int, int] = (8, 0, 19)

_MYSQL_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def parse_mysql_server_version(
    version_string: str,
) -> Tuple[Tuple[int, int, int], bool]:
    """Parse a MySQL/MariaDB ``SELECT VERSION()`` string.

    Returns ``((major, minor, patch), is_mariadb)``. MariaDB advertises itself in
    the version string (e.g. ``"10.11.2-MariaDB"`` or the compat-prefixed
    ``"5.5.5-10.11.2-MariaDB"``); the flavor flag is decided by that substring, not
    the numeric tuple. An unparseable string yields ``((0, 0, 0), is_mariadb)`` —
    which fails the row-alias floor closed (legacy ``VALUES()`` form).
    """
    is_mariadb = "mariadb" in (version_string or "").lower()
    match = _MYSQL_VERSION_RE.search(version_string or "")
    if not match:
        return ((0, 0, 0), is_mariadb)
    return (
        (int(match.group(1)), int(match.group(2)), int(match.group(3))),
        is_mariadb,
    )


def mysql_supports_row_alias_upsert(version_string: str) -> bool:
    """Whether this MySQL server emits the 8.0.19+ row-alias upsert form.

    ``True`` only for non-MariaDB MySQL >= 8.0.19. MariaDB (which does not support
    the ``VALUES (...) AS alias`` syntax) and MySQL < 8.0.19 keep the legacy
    ``VALUES(col)`` form. Fails closed (legacy form) on an unparseable version.
    """
    version, is_mariadb = parse_mysql_server_version(version_string)
    if is_mariadb:
        return False
    return version >= _MYSQL_ROW_ALIAS_MIN_VERSION


# Issue #1546: process-level cache of per-server row-alias support, keyed by a
# credential-safe hash of the connection string. Shared by ALL upsert paths
# (single-record + the three bulk paths) so a given MySQL server is version-probed
# with exactly one ``SELECT VERSION()`` round-trip per process.
_MYSQL_ROW_ALIAS_SUPPORT_CACHE: Dict[str, bool] = {}


def mysql_row_alias_cache_key(connection_string: str) -> str:
    """Credential-safe process-cache key for a MySQL server.

    Hashes the connection string so no raw password sits in the in-memory cache key
    (``observability.md`` Rule 6.3). Distinct servers → distinct keys.
    """
    return hashlib.sha256((connection_string or "").encode("utf-8")).hexdigest()[:16]


def mysql_row_alias_support_cached(cache_key: str) -> Optional[bool]:
    """Return the cached row-alias support for ``cache_key`` without a round-trip.

    ``None`` = not yet probed. Lets callers that must construct their own version
    node (the standalone bulk nodes, which have no DataFlow instance) skip node
    creation entirely on a cache hit.
    """
    return _MYSQL_ROW_ALIAS_SUPPORT_CACHE.get(cache_key)


def _extract_mysql_version_string(version_result: Any) -> str:
    """Pull the ``VERSION()`` string out of an AsyncSQLDatabaseNode result dict."""
    if not isinstance(version_result, dict):
        return ""
    payload = version_result.get("result")
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        return str(data.get("version") or data.get("VERSION") or "")
    return ""


async def resolve_mysql_row_alias_support(async_sql_node: Any, cache_key: str) -> bool:
    """Whether this MySQL server supports the 8.0.19+ row-alias upsert form.

    THE single shared version-detection helper. Runs ONE ``SELECT VERSION()``
    round-trip per distinct ``cache_key`` per process and caches the result, so the
    single-record upsert path and all three bulk upsert paths version-probe a given
    server exactly once. ``cache_key`` MUST be a stable per-server token — use
    :func:`mysql_row_alias_cache_key` on the connection string.
    """
    cached = _MYSQL_ROW_ALIAS_SUPPORT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    version_result = await async_sql_node.async_run(
        query="SELECT VERSION() AS version",
        fetch_mode="one",
        validate_queries=False,
        transaction_mode="auto",
    )
    support = mysql_supports_row_alias_upsert(
        _extract_mysql_version_string(version_result)
    )
    _MYSQL_ROW_ALIAS_SUPPORT_CACHE[cache_key] = support
    return support


def resolve_mysql_row_alias_support_sync(cache_key: str, fetch_version_string) -> bool:
    """Sync sibling of :func:`resolve_mysql_row_alias_support` for the SYNC registry
    write path (SQLDatabaseNode). ``fetch_version_string`` is a zero-arg callable
    returning the server's ``VERSION()`` string; it is invoked at most once per
    distinct ``cache_key`` per process. Shares the SAME process cache as the async
    paths, so a server keyed identically is version-probed exactly once regardless
    of which path (single-record, bulk, or registry) probes first.
    """
    cached = _MYSQL_ROW_ALIAS_SUPPORT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    support = mysql_supports_row_alias_upsert(fetch_version_string() or "")
    _MYSQL_ROW_ALIAS_SUPPORT_CACHE[cache_key] = support
    return support


@dataclass
class UpsertQuery:
    """
    Result of building an upsert query.

    Attributes:
        query: The SQL query string
        params: Query parameters as a dictionary
        supports_native_flag: Whether database natively detects INSERT vs UPDATE
                             True for PostgreSQL (xmax), False for SQLite (requires pre-check)
    """

    query: str
    params: Dict[str, Any]
    supports_native_flag: bool


class SQLDialect(ABC):
    """
    Abstract base class for database-specific SQL dialects.

    Each database dialect implements its own SQL generation logic
    for operations like upsert, bulk operations, etc.
    """

    @abstractmethod
    def build_upsert_query(
        self,
        table_name: str,
        insert_data: Dict[str, Any],
        update_data: Dict[str, Any],
        conflict_columns: List[str],
        has_updated_at: bool = False,
        use_row_alias: bool = False,
    ) -> UpsertQuery:
        """
        Build database-specific upsert query.

        Args:
            table_name: Name of the table
            insert_data: Data to insert if record doesn't exist
            update_data: Data to update if record exists
            conflict_columns: Columns that define uniqueness for conflict detection
            has_updated_at: Whether the model has an updated_at timestamp field
            use_row_alias: MySQL-only (issue #1546). When True, emit the 8.0.19+
                ``VALUES (...) AS alias`` row-alias upsert form instead of the
                deprecated ``VALUES(col)`` reference. Ignored by non-MySQL dialects.

        Returns:
            UpsertQuery with query string, parameters, and native flag support info
        """
        pass

    def build_precheck_upsert_query(
        self,
        table_name: str,
        insert_data: Dict[str, Any],
        update_data: Dict[str, Any],
        where: Dict[str, Any],
        row_exists: bool,
        has_updated_at: bool = False,
    ) -> UpsertQuery:
        """Build an upsert as an explicit INSERT or UPDATE from a caller-supplied
        existence pre-check result, instead of ``INSERT ... ON CONFLICT``.

        ``ON CONFLICT (target)`` requires the conflict target to be backed by a
        PRIMARY KEY or UNIQUE constraint; a ``conflict_on`` field that is not
        declared unique is rejected with "ON CONFLICT clause does not match any
        PRIMARY KEY or UNIQUE constraint" (issue #1508). Dialects that lack
        native INSERT/UPDATE detection (SQLite has no PostgreSQL ``xmax``) already
        run a WHERE-based pre-check to detect INSERT vs UPDATE; that same result
        lets us emit a plain INSERT (row absent) or UPDATE ... WHERE (row present)
        with no reliance on a unique constraint. Values are parameter-bound; the
        interpolated identifiers are model field names resolved from the schema.

        Concrete on the base because the pattern is dialect-agnostic. It is only
        invoked on the pre-check path (SQLite today); native-detection dialects
        (PostgreSQL) keep ``build_upsert_query``'s atomic ``ON CONFLICT`` form.

        Placeholders use the ``:p<i>`` sequence and ``params`` is built in the
        same order, because AsyncSQLDatabaseNode rebuilds the parameter dict
        positionally from ``list(params.values())`` — placeholder index MUST
        match value order (see ``build_upsert_query``).
        """
        if not row_exists:
            insert_columns = list(insert_data.keys())
            placeholders = [f":p{i}" for i in range(len(insert_columns))]
            query = (
                f"INSERT INTO {table_name} ({', '.join(insert_columns)})\n"
                f"            VALUES ({', '.join(placeholders)})\n"
                f"            RETURNING *"
            )
            params = {f"p{i}": insert_data[col] for i, col in enumerate(insert_columns)}
            return UpsertQuery(
                query=query.strip(), params=params, supports_native_flag=False
            )

        # Row exists → UPDATE ... WHERE <where>. Exclude the primary key and the
        # where/identity columns from the SET clause (updating the identity would
        # move the row out from under the WHERE match).
        if not where:
            # Defensive: the UPDATE branch needs a non-empty WHERE to identify the
            # row (an empty WHERE would emit invalid SQL and, worse, an unscoped
            # UPDATE). Unreachable via the upsert node — the pre-check SELECT and
            # upsert semantics both require a key — but guarded because this is a
            # public base-class method.
            raise ValueError(
                "build_precheck_upsert_query: UPDATE branch requires a non-empty "
                "'where' to identify the row"
            )
        set_clauses: List[str] = []
        params: Dict[str, Any] = {}
        idx = 0
        for col in update_data.keys():
            if col == "id" or col in where:
                continue
            params[f"p{idx}"] = update_data[col]
            set_clauses.append(f"{col} = :p{idx}")
            idx += 1

        if has_updated_at:
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")

        if not set_clauses:
            # Nothing substantive to update (update payload only named id/where
            # keys). Emit a no-op self-assignment on the first where column so the
            # UPDATE still matches the row and RETURNING yields it.
            first_col = next(iter(where))
            set_clauses.append(f"{first_col} = {first_col}")

        where_clauses: List[str] = []
        for col in where.keys():
            params[f"p{idx}"] = where[col]
            where_clauses.append(f"{col} = :p{idx}")
            idx += 1

        query = (
            f"UPDATE {table_name} SET {', '.join(set_clauses)}\n"
            f"            WHERE {' AND '.join(where_clauses)}\n"
            f"            RETURNING *"
        )
        return UpsertQuery(
            query=query.strip(), params=params, supports_native_flag=False
        )


class PostgreSQLDialect(SQLDialect):
    """
    PostgreSQL dialect with xmax-based INSERT/UPDATE detection.

    PostgreSQL natively provides xmax column for MVCC which allows
    detecting whether an upsert performed an INSERT or UPDATE:
    - xmax = 0: INSERT occurred (new row)
    - xmax > 0: UPDATE occurred (existing row modified)
    """

    def build_upsert_query(
        self,
        table_name: str,
        insert_data: Dict[str, Any],
        update_data: Dict[str, Any],
        conflict_columns: List[str],
        has_updated_at: bool = False,
        use_row_alias: bool = False,
        tenant_guard: Optional[str] = None,
    ) -> UpsertQuery:
        """Build PostgreSQL upsert with xmax detection (``use_row_alias`` is
        MySQL-only and ignored here).

        Cross-tenant WRITE breach fix: when ``tenant_guard`` (the bound tenant id)
        is supplied, the DO UPDATE carries ``WHERE {table}.tenant_id = :pN`` (the
        bound tenant, parameter-bound) and ``tenant_id`` is excluded from the SET
        so a cross-tenant ``id`` collision never overwrites — nor re-owns —
        another tenant's row (rules/tenant-isolation.md).
        """

        # Build INSERT clause
        insert_columns = list(insert_data.keys())
        insert_placeholders = [f":p{i}" for i in range(len(insert_columns))]

        # Build ON CONFLICT clause
        conflict_cols_str = ", ".join(conflict_columns)

        # Build UPDATE clause.
        # `update_data` (the `update` payload) is DISTINCT from `insert_data`
        # (the `create` payload) in the DataFlow upsert API. EXCLUDED.<col>
        # resolves to the value proposed for INSERT (the `create` value), so it
        # MUST NOT be used to apply the `update` values; bind them as parameters,
        # continuing the :p<i> sequence (AsyncSQLDatabaseNode rebuilds the param
        # dict positionally as {p0, p1, ...} from list(params.values())).
        _tenant_guarded = tenant_guard is not None
        update_clauses = []
        update_params = {}
        _poff = len(insert_columns)
        for col in update_data.keys():
            if col in conflict_columns or col == "id":
                continue
            if _tenant_guarded and col == "tenant_id":
                continue  # never re-assign the owning tenant
            pkey = f"p{_poff}"
            update_clauses.append(f"{col} = :{pkey}")
            update_params[pkey] = update_data[col]
            _poff += 1

        # Add updated_at if present
        if has_updated_at:
            update_clauses.append("updated_at = CURRENT_TIMESTAMP")

        update_clause_str = (
            ", ".join(update_clauses) if update_clauses else "id = EXCLUDED.id"
        )

        # Cross-tenant DO-UPDATE guard: only overwrite when the existing row
        # belongs to the SAME tenant as the caller.
        tenant_where = ""
        if _tenant_guarded:
            pkey = f"p{_poff}"
            tenant_where = f"\n            WHERE {table_name}.tenant_id = :{pkey}"
            update_params[pkey] = tenant_guard
            _poff += 1

        # Build complete query with xmax flag
        query = f"""
            INSERT INTO {table_name} ({", ".join(insert_columns)})
            VALUES ({", ".join(insert_placeholders)})
            ON CONFLICT ({conflict_cols_str})
            DO UPDATE SET {update_clause_str}{tenant_where}
            RETURNING *, (xmax = 0) AS _upsert_inserted
        """

        # Build parameters (insert values + bound update values)
        params = {f"p{i}": insert_data[col] for i, col in enumerate(insert_columns)}
        params.update(update_params)

        return UpsertQuery(
            query=query.strip(),
            params=params,
            supports_native_flag=True,  # PostgreSQL has xmax
        )


class SQLiteDialect(SQLDialect):
    """
    SQLite dialect without xmax support.

    SQLite doesn't have PostgreSQL's xmax column, so we use:
    1. Pre-check query to determine if record exists
    2. Standard upsert without INSERT/UPDATE detection in RETURNING clause
    """

    def build_upsert_query(
        self,
        table_name: str,
        insert_data: Dict[str, Any],
        update_data: Dict[str, Any],
        conflict_columns: List[str],
        has_updated_at: bool = False,
        use_row_alias: bool = False,
        tenant_guard: Optional[str] = None,
    ) -> UpsertQuery:
        """Build SQLite upsert without xmax (``use_row_alias`` is MySQL-only and
        ignored here).

        ``tenant_guard`` (bound tenant id) adds the cross-tenant
        ``WHERE {table}.tenant_id = :pN`` DO-UPDATE predicate and excludes
        ``tenant_id`` from the SET — see :meth:`PostgreSQLDialect.build_upsert_query`.
        """

        # Build INSERT clause
        insert_columns = list(insert_data.keys())
        insert_placeholders = [f":p{i}" for i in range(len(insert_columns))]

        # Build ON CONFLICT clause
        conflict_cols_str = ", ".join(conflict_columns)

        # Build UPDATE clause.
        # The conflict/update payload (`update_data`) is DISTINCT from the
        # insert payload (`insert_data`) — the DataFlow upsert API takes
        # separate `create` and `update` dicts. EXCLUDED.<col> resolves to the
        # value proposed for INSERT (the `create` value), so it MUST NOT be used
        # to apply the `update` values; bind the update values as parameters.
        # Placeholders continue the :p<i> sequence (offset by the insert-column
        # count) because AsyncSQLDatabaseNode rebuilds the param dict positionally
        # as {p0, p1, ...} from list(params.values()) — the names MUST match index.
        _tenant_guarded = tenant_guard is not None
        update_clauses = []
        update_params = {}
        _poff = len(insert_columns)
        for col in update_data.keys():
            if col in conflict_columns or col == "id":
                continue
            if _tenant_guarded and col == "tenant_id":
                continue  # never re-assign the owning tenant
            pkey = f"p{_poff}"
            update_clauses.append(f"{col} = :{pkey}")
            update_params[pkey] = update_data[col]
            _poff += 1

        # Add updated_at if present
        if has_updated_at:
            update_clauses.append("updated_at = CURRENT_TIMESTAMP")

        update_clause_str = (
            ", ".join(update_clauses) if update_clauses else "id = EXCLUDED.id"
        )

        # Cross-tenant DO-UPDATE guard (see PostgreSQLDialect.build_upsert_query).
        tenant_where = ""
        if _tenant_guarded:
            pkey = f"p{_poff}"
            tenant_where = f"\n            WHERE {table_name}.tenant_id = :{pkey}"
            update_params[pkey] = tenant_guard
            _poff += 1

        # Build complete query WITHOUT xmax (SQLite doesn't support it)
        query = f"""
            INSERT INTO {table_name} ({", ".join(insert_columns)})
            VALUES ({", ".join(insert_placeholders)})
            ON CONFLICT ({conflict_cols_str})
            DO UPDATE SET {update_clause_str}{tenant_where}
            RETURNING *
        """

        # Build parameters (insert values + bound update values)
        params = {f"p{i}": insert_data[col] for i, col in enumerate(insert_columns)}
        params.update(update_params)

        return UpsertQuery(
            query=query.strip(),
            params=params,
            supports_native_flag=False,  # SQLite needs pre-check for INSERT/UPDATE detection
        )


class MySQLDialect(SQLDialect):
    """
    MySQL dialect using ON DUPLICATE KEY UPDATE.

    MySQL uses ON DUPLICATE KEY UPDATE instead of ON CONFLICT.
    Uses ROW_COUNT() function to detect INSERT (1) vs UPDATE (2).
    """

    def build_upsert_query(
        self,
        table_name: str,
        insert_data: Dict[str, Any],
        update_data: Dict[str, Any],
        conflict_columns: List[str],
        has_updated_at: bool = False,
        use_row_alias: bool = False,
        tenant_guard: Optional[str] = None,
    ) -> UpsertQuery:
        """Build MySQL upsert with ON DUPLICATE KEY UPDATE.

        Issue #1546: ``VALUES(col)`` inside ``ON DUPLICATE KEY UPDATE`` is
        DEPRECATED as of MySQL 8.0.20. When ``use_row_alias`` is True (resolved by
        the caller to non-MariaDB MySQL >= 8.0.19), emit the replacement row-alias
        form ``INSERT ... VALUES (...) AS new_row ON DUPLICATE KEY UPDATE
        col = new_row.col``. Otherwise (MariaDB / MySQL < 8.0.19) keep the legacy
        ``VALUES(col)`` form, which those servers still require. The INSERT-side
        alias declaration and the ODKU-side reference are built together here so
        the two halves can never drift.

        Cross-tenant WRITE breach fix (``tenant_guard``): MySQL's ODKU has no
        WHERE, so each SET is guarded with ``col = IF(tenant_id = <new_tenant>,
        <new_col>, col)`` and ``tenant_id`` is excluded — a cross-tenant ``id``
        collision keeps every existing value AND the owning tenant unchanged
        (rules/tenant-isolation.md).
        """

        # Build INSERT clause.
        # MySQL's adapter (aiomysql) binds POSITIONAL %s placeholders — it does
        # NOT understand the :p<i> named style the PostgreSQL/SQLite builders
        # emit (AsyncSQLDatabaseNode's MySQL branch keeps the query verbatim and
        # passes params as a tuple, so a :p0 query yields "not all arguments
        # converted during string formatting"). Emit %s here, matching the
        # hand-built %s create/update SQL in core/nodes.py. nodes.py passes
        # ``list(upsert_query.params.values())`` — an ordered list — which lines
        # up positionally with these %s placeholders. (#1537)
        insert_columns = list(insert_data.keys())
        insert_placeholders = ["%s" for _ in range(len(insert_columns))]

        # The row alias is a table alias in a distinct namespace, so it cannot
        # collide with a column named the same (``new_row.new_row`` is still valid).
        alias = "new_row"
        _tenant_guarded = tenant_guard is not None

        def _new_ref(c: str) -> str:
            return f"{alias}.{c}" if use_row_alias else f"VALUES({c})"

        # Build UPDATE clause. Reference the row alias (8.0.19+) or fall back to
        # the deprecated VALUES(col) form. updated_at is a literal, not a value
        # reference, in both branches.
        update_clauses = []
        for col in update_data.keys():
            if col in conflict_columns or col == "id":
                continue
            if _tenant_guarded and col == "tenant_id":
                continue  # never re-assign the owning tenant
            if _tenant_guarded:
                # Keep the existing value unless the row belongs to the caller's
                # tenant. ``tenant_id`` (bare) = the EXISTING row's owner.
                update_clauses.append(
                    f"{col} = IF(tenant_id = {_new_ref('tenant_id')}, "
                    f"{_new_ref(col)}, {col})"
                )
            elif use_row_alias:
                update_clauses.append(f"{col} = {alias}.{col}")
            else:
                update_clauses.append(f"{col} = VALUES({col})")

        if has_updated_at:
            if _tenant_guarded:
                # Do not even bump the victim row's timestamp on a cross-tenant
                # collision — the guard keeps updated_at unchanged unless the row
                # belongs to the caller's tenant.
                update_clauses.append(
                    f"updated_at = IF(tenant_id = {_new_ref('tenant_id')}, "
                    f"CURRENT_TIMESTAMP, updated_at)"
                )
            else:
                update_clauses.append("updated_at = CURRENT_TIMESTAMP")

        if update_clauses:
            update_clause_str = ", ".join(update_clauses)
        elif use_row_alias:
            update_clause_str = f"id = {alias}.id"
        else:
            update_clause_str = "id = VALUES(id)"

        # Build complete query
        # Note: MySQL doesn't have RETURNING clause, needs separate SELECT
        if use_row_alias:
            query = f"""
            INSERT INTO {table_name} ({", ".join(insert_columns)})
            VALUES ({", ".join(insert_placeholders)}) AS {alias}
            ON DUPLICATE KEY UPDATE {update_clause_str}
        """
        else:
            query = f"""
            INSERT INTO {table_name} ({", ".join(insert_columns)})
            VALUES ({", ".join(insert_placeholders)})
            ON DUPLICATE KEY UPDATE {update_clause_str}
        """

        # Build parameters
        params = {f"p{i}": insert_data[col] for i, col in enumerate(insert_columns)}

        return UpsertQuery(
            query=query.strip(),
            params=params,
            supports_native_flag=False,  # MySQL needs ROW_COUNT() check
        )


class SQLDialectFactory:
    """
    Factory for creating SQL dialect instances.

    Usage:
        dialect = SQLDialectFactory.get_dialect("postgresql")
        upsert_query = dialect.build_upsert_query(...)
    """

    _dialects = {
        "postgresql": PostgreSQLDialect,
        "sqlite": SQLiteDialect,
        "mysql": MySQLDialect,
    }

    @classmethod
    def get_dialect(cls, database_type: str) -> SQLDialect:
        """
        Get SQL dialect instance for the specified database type.

        Args:
            database_type: Database type (postgresql, sqlite, mysql)

        Returns:
            SQLDialect instance for the database

        Raises:
            ValueError: If database type is not supported
        """
        database_type_lower = database_type.lower()

        if database_type_lower not in cls._dialects:
            raise ValueError(
                f"Unsupported database type: {database_type}. "
                f"Supported types: {', '.join(cls._dialects.keys())}"
            )

        return cls._dialects[database_type_lower]()

    @classmethod
    def register_dialect(cls, database_type: str, dialect_class: type) -> None:
        """
        Register a custom SQL dialect.

        Args:
            database_type: Database type identifier
            dialect_class: SQLDialect subclass

        Example:
            class MongoDBDialect(SQLDialect):
                ...

            SQLDialectFactory.register_dialect("mongodb", MongoDBDialect)
        """
        if not issubclass(dialect_class, SQLDialect):
            raise TypeError(
                f"dialect_class must be a subclass of SQLDialect, got {dialect_class}"
            )

        cls._dialects[database_type.lower()] = dialect_class

    @classmethod
    def get_supported_databases(cls) -> List[str]:
        """Get list of supported database types."""
        return list(cls._dialects.keys())
