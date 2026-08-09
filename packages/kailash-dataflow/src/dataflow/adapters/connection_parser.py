"""
Connection String Parser

Utilities for parsing database connection strings.
"""

import logging
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, quote, urlparse

from kailash.utils.url_credentials import decode_userinfo_or_raise

from .exceptions import AdapterError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scheme -> database-type mapping (issue #1971 follow-up: fail CLOSED)
# ---------------------------------------------------------------------------
# Keyed by the BASE driver of a SQLAlchemy-style scheme: everything before the
# first "+". ``postgresql+asyncpg`` -> ``postgresql``, ``mariadb+pymysql`` ->
# ``mariadb``. Handling the base uniformly is what lets every driver variant
# resolve without a per-driver prefix test; the pre-fix code tested
# ``startswith("postgresql+")`` but NOT ``postgres+``, so the perfectly
# ordinary ``postgres+asyncpg://`` and ``postgres+psycopg2://`` DSNs fell
# through to the unknown-scheme path.
_SCHEME_TO_DATABASE_TYPE = {
    # PostgreSQL and its aliases
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "pgsql": "postgresql",
    # MySQL and wire-compatible forks. MariaDB speaks the MySQL protocol and
    # shares MySQL's 64-char identifier budget, so it maps to "mysql" — NOT to
    # the pre-fix "postgresql" that ``AutoMigrationSystem`` guessed for it.
    "mysql": "mysql",
    "mariadb": "mysql",
    # SQLite. ``file`` is SQLite's own URI-filename scheme
    # (https://sqlite.org/uri.html) and is the form issue #1502 injects for a
    # bare ``:memory:`` instance: ``file:df_mem_<id>?mode=memory&cache=shared``
    # — the one shared-cache DB the DDL, CRUD and model-registry paths all
    # open. It is an EXPLICIT allowlist entry, not a fallback: no other engine
    # DataFlow supports uses ``file:``, and every genuinely-unknown scheme
    # still raises below.
    #
    # This entry restores enforcement-surface parity
    # (``rules/security.md`` § Enforcement-Surface Parity). Six sibling
    # surfaces already recognise the ``file:`` form and open it with
    # ``uri=True`` — ``sync_ddl_executor._get_sqlite_connection``,
    # ``adapters/sqlite.py``, ``migration_connection_manager``,
    # ``migration_test_framework``, core ``nodes/data/sql.py`` and
    # ``nodes/data/async_sql.py``. Only this detector, the single source of
    # truth they all consult, had never learned it.
    "sqlite": "sqlite",
    "file": "sqlite",
    # MongoDB
    "mongodb": "mongodb",
}


def _base_scheme(scheme: str) -> str:
    """Return the base driver of a SQLAlchemy-style scheme.

    ``postgresql+asyncpg`` -> ``postgresql``; ``mysql`` -> ``mysql``.
    """
    return scheme.split("+", 1)[0].strip().lower()


class ConnectionParser:
    """Parser for database connection strings."""

    @staticmethod
    def parse_connection_string(connection_string: str) -> Dict[str, Any]:
        """
        Parse database connection string into components.

        Handles special characters in passwords (like #, $, @) by properly
        URL-encoding them before parsing.

        Args:
            connection_string: Database connection string

        Returns:
            Dictionary with connection components

        Raises:
            AdapterError: If connection string is invalid
        """
        try:
            # Handle special characters in passwords before parsing
            safe_connection_string = ConnectionParser._encode_password_special_chars(
                connection_string
            )

            parsed = urlparse(safe_connection_string)

            # Decode and validate userinfo through the shared helper.
            # decode_userinfo_or_raise unquotes both fields and rejects
            # null bytes, preventing the MySQL C client auth-bypass where
            # a crafted %00 in the password truncates to an empty string.
            decoded_username, decoded_password = decode_userinfo_or_raise(
                parsed, default_user=""
            )
            # Preserve None semantics for callers that distinguish
            # "no username provided" from an empty string.
            if not decoded_username and parsed.username is None:
                decoded_username = None
            if not decoded_password and parsed.password is None:
                decoded_password = None
            components = {
                "scheme": parsed.scheme,
                "host": parsed.hostname,
                "port": parsed.port,
                "database": parsed.path.lstrip("/") if parsed.path else None,
                "username": decoded_username,
                "password": decoded_password,
                "query_params": {},
            }

            # Parse query parameters
            if parsed.query:
                components["query_params"] = {
                    key: value[0] if len(value) == 1 else value
                    for key, value in parse_qs(parsed.query).items()
                }

            return components

        except Exception as e:
            raise AdapterError(f"Invalid connection string: {e}")

    @staticmethod
    def _encode_password_special_chars(connection_string: str) -> str:
        """Delegate to :func:`kailash.utils.url_credentials.preencode_password_special_chars`.

        Thin backward-compat wrapper so any external callers of
        ``ConnectionParser._encode_password_special_chars`` still work.
        The pre-encoder itself lives in ``kailash.utils.url_credentials``
        — all six dialect parse sites and this class delegate to the
        same helper so there is exactly one source of truth.

        Origin: ``workspaces/arbor-upstream-fixes`` red team round 2 —
        R2 finding E.1: the pre-encoding helper existed here but NOT at
        the five direct-dialect parse sites. Consolidating into
        ``kailash.utils.url_credentials`` eliminates the drift.
        """
        from kailash.utils.url_credentials import preencode_password_special_chars

        return preencode_password_special_chars(connection_string)

    @staticmethod
    def validate_postgresql_connection(components: Dict[str, Any]) -> None:
        """
        Validate PostgreSQL connection components.

        Args:
            components: Connection components from parse_connection_string

        Raises:
            AdapterError: If connection components are invalid
        """
        if not components.get("host"):
            raise AdapterError("PostgreSQL connection requires host")

        if not components.get("database"):
            raise AdapterError("PostgreSQL connection requires database name")

        # Validate SSL mode
        ssl_mode = components.get("query_params", {}).get("sslmode")
        if ssl_mode and ssl_mode not in [
            "disable",
            "allow",
            "prefer",
            "require",
            "verify-ca",
            "verify-full",
        ]:
            raise AdapterError(f"Invalid SSL mode: {ssl_mode}")

        # Validate port
        port = components.get("port")
        if port is not None and (port < 1 or port > 65535):
            raise AdapterError(f"Invalid port: {port}")

    @staticmethod
    def validate_mysql_connection(components: Dict[str, Any]) -> None:
        """
        Validate MySQL connection components.

        Args:
            components: Connection components from parse_connection_string

        Raises:
            AdapterError: If connection components are invalid
        """
        if not components.get("host"):
            raise AdapterError("MySQL connection requires host")

        if not components.get("database"):
            raise AdapterError("MySQL connection requires database name")

        # Validate charset
        charset = components.get("query_params", {}).get("charset")
        if charset and charset not in ["utf8", "utf8mb4", "latin1"]:
            logger.warning(
                "connection_parser.non_standard_charset", extra={"charset": charset}
            )

        # Validate port
        port = components.get("port")
        if port is not None and (port < 1 or port > 65535):
            raise AdapterError(f"Invalid port: {port}")

    @staticmethod
    def validate_sqlite_connection(components: Dict[str, Any]) -> None:
        """
        Validate SQLite connection components.

        Args:
            components: Connection components from parse_connection_string

        Raises:
            AdapterError: If connection components are invalid
        """
        # For SQLite, the path is the database file
        if components.get("host") and components.get("host") != "":
            raise AdapterError("SQLite connection should not specify host")

        if components.get("port"):
            raise AdapterError("SQLite connection should not specify port")

        # Database path is required (can be :memory: for in-memory)
        if not components.get("database"):
            raise AdapterError("SQLite connection requires database path")

    @staticmethod
    def extract_connection_parameters(connection_string: str) -> Dict[str, Any]:
        """
        Extract connection parameters from connection string.

        Args:
            connection_string: Database connection string

        Returns:
            Dictionary with extracted parameters
        """
        components = ConnectionParser.parse_connection_string(connection_string)

        # Extract standard parameters
        params = {
            "host": components.get("host"),
            "port": components.get("port"),
            "database": components.get("database"),
            "username": components.get("username"),
            "password": components.get("password"),
        }

        # Add query parameters
        params.update(components.get("query_params", {}))

        # Remove None values
        return {k: v for k, v in params.items() if v is not None}

    @staticmethod
    def build_connection_string(
        scheme: Optional[str],
        host: Optional[str],
        database: Optional[str],
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: Optional[int] = None,
        **params,
    ) -> str:
        """
        Build connection string from components.

        Automatically URL-encodes special characters in passwords to ensure
        the connection string can be parsed correctly by URL parsers.

        Args:
            scheme: Database scheme (postgresql, mysql, sqlite)
            host: Database host
            database: Database name
            username: Username (optional)
            password: Password (optional)
            port: Port (optional)
            **params: Additional query parameters

        Returns:
            Connection string with properly encoded password
        """
        # Build base URL
        if scheme == "sqlite":
            # SQLite format: sqlite:///path/to/db.sqlite
            return f"sqlite:///{database}"

        # Build authority part
        authority = ""
        if username:
            authority = username
            if password:
                # URL-encode the password to handle special characters
                encoded_password = quote(password, safe="")
                authority += f":{encoded_password}"
            authority += "@"

        # Only add host if it's not None (SQLite doesn't have host)
        if host is not None:
            authority += host

        if port:
            authority += f":{port}"

        # Build full URL
        url = f"{scheme}://{authority}/{database}"

        # Add query parameters
        if params:
            query_parts = []
            for key, value in params.items():
                if isinstance(value, list):
                    for v in value:
                        query_parts.append(f"{key}={v}")
                else:
                    query_parts.append(f"{key}={value}")

            if query_parts:
                url += "?" + "&".join(query_parts)

        return url

    @staticmethod
    def detect_database_type(connection_string: str) -> str:
        """
        Detect database type from connection string.

        Args:
            connection_string: Database connection string

        Returns:
            Database type: 'postgresql', 'mysql', 'sqlite', or 'mongodb'

        Raises:
            AdapterError: If the database type cannot be determined.

        Fail-closed contract (issue #1971 follow-up)
        --------------------------------------------
        An UNRECOGNISED scheme RAISES. It does NOT fall back to a default.

        Pre-fix, the deliberate ``AdapterError("Unsupported database
        scheme")`` below was raised INSIDE a ``try`` whose ``except
        Exception:`` swallowed it and returned ``"sqlite"`` — the exact
        silent-fallback shape ``rules/zero-tolerance.md`` Rule 3 blocks. The
        consequences were not merely cosmetic:

        * ``postgres+asyncpg://``, ``postgres+psycopg2://``, ``mariadb://``
          and ``mariadb+pymysql://`` are ordinary SQLAlchemy DSNs; every one
          of them resolved to ``"sqlite"``.
        * That answer selects the identifier budget used by
          ``_fit_identifier_to_dialect``: SQLite's 128 instead of
          PostgreSQL's 63 / MySQL's 64. Generated names then exceed the real
          server limit, PostgreSQL truncates server-side at 63, and two
          distinct models silently ALIAS onto one physical table (#1971
          verified this against real PostgreSQL 15.18).
        * The only signal was a ``logger.debug``.

        RAISING is the only disposition that cannot corrupt data. This
        function returns an ENGINE SELECTOR, not a length — it decides the
        adapter, the SQL dialect, the placeholder syntax and the DDL types.
        There is no "tightest" engine to fall back to: answering ``sqlite``
        makes DataFlow open a local file named after the DSN (writes land in
        the wrong database entirely), and answering ``postgresql`` emits
        PostgreSQL-only DDL against a server that rejects it. A loud raise
        naming the scheme is recoverable; either guess is not.
        """
        # Handle None connection string
        if connection_string is None:
            raise AdapterError("Connection string is None")

        if not isinstance(connection_string, str):
            raise AdapterError(
                f"Connection string must be a string, got "
                f"{type(connection_string).__name__}"
            )

        connection_lower = connection_string.lower()

        # MongoDB detection (before SQLite patterns)
        if connection_lower.startswith(("mongodb://", "mongodb+srv://")):
            return "mongodb"

        # Common SQLite indicators
        if (
            connection_string == ":memory:"
            or connection_lower.endswith((".db", ".sqlite", ".sqlite3"))
            or connection_lower.startswith("sqlite")
            or
            # File path without URL scheme (likely SQLite)
            ("/" in connection_string and "://" not in connection_string)
        ):
            return "sqlite"

        # URL parsing for everything else. A parse FAILURE and an
        # unsupported SCHEME are distinct outcomes and are raised
        # separately — neither is swallowed into a default.
        try:
            components = ConnectionParser.parse_connection_string(connection_string)
        except AdapterError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise AdapterError(
                f"Failed to detect database type: connection string could not "
                f"be parsed ({type(exc).__name__})"
            ) from exc

        scheme = components.get("scheme", "") or ""

        if not scheme:
            # No scheme at all - a bare file path, i.e. SQLite. This is an
            # explicit recognised case, NOT a fallback.
            return "sqlite"

        database_type = _SCHEME_TO_DATABASE_TYPE.get(_base_scheme(scheme))
        if database_type is None:
            raise AdapterError(
                f"Unsupported database scheme: {scheme}. Supported schemes: "
                f"{', '.join(sorted(_SCHEME_TO_DATABASE_TYPE))} "
                f"(optionally with a SQLAlchemy '+driver' suffix, e.g. "
                f"'postgresql+asyncpg'). Refusing to guess — an incorrect "
                f"engine emits SQL for the wrong database."
            )
        return database_type
