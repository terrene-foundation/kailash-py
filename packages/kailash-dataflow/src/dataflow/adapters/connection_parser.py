"""
Connection String Parser

Utilities for parsing database connection strings.
"""

import logging
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

from .exceptions import AdapterError

logger = logging.getLogger(__name__)


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

            # Basic components with proper password decoding
            components = {
                "scheme": parsed.scheme,
                "host": parsed.hostname,
                "port": parsed.port,
                "database": parsed.path.lstrip("/") if parsed.path else None,
                "username": parsed.username,
                "password": (
                    unquote(parsed.password)
                    if parsed.password is not None
                    else parsed.password
                ),  # Manually decode password, preserve empty string
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
        """
        Encode special characters in password portion of connection string.

        This handles the case where passwords contain characters like # or $
        that have special meaning in URLs.

        Args:
            connection_string: Original connection string

        Returns:
            Connection string with password special characters encoded
        """
        # Handle None connection string
        if connection_string is None:
            return ""

        if "://" not in connection_string:
            return connection_string

        # Split into protocol and rest
        protocol_part, rest = connection_string.split("://", 1)

        # Check if there's an @ symbol indicating credentials
        if "@" not in rest:
            return connection_string

        # Find the LAST @ symbol, which separates credentials from host
        # This handles passwords that contain @ characters
        last_at_index = rest.rfind("@")
        creds_part = rest[:last_at_index]
        host_part = rest[last_at_index + 1 :]

        # Check if credentials contain a colon (indicating username:password)
        if ":" not in creds_part:
            return connection_string

        # Split username and password on FIRST colon only
        # This handles usernames or passwords that contain : characters
        colon_index = creds_part.find(":")
        username = creds_part[:colon_index]
        password = creds_part[colon_index + 1 :]

        # Encode special characters in password
        # Only encode characters that cause URL parsing issues
        special_chars = {"#": "%23", "$": "%24", "@": "%40", "?": "%3F"}
        encoded_password = password
        for char, encoded in special_chars.items():
            encoded_password = encoded_password.replace(char, encoded)

        # Reconstruct the connection string
        return f"{protocol_part}://{username}:{encoded_password}@{host_part}"

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
            logger.warning(f"Non-standard charset: {charset}")

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
        scheme: str,
        host: str,
        database: str,
        username: str = None,
        password: str = None,
        port: int = None,
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
            AdapterError: If database type cannot be determined
        """
        try:
            # Handle None connection string
            if connection_string is None:
                raise AdapterError("Connection string is None")

            # Enhanced SQLite pattern detection
            connection_lower = connection_string.lower()

            # MongoDB detection (before SQLite patterns)
            if connection_lower.startswith("mongodb://") or connection_lower.startswith(
                "mongodb+srv://"
            ):
                return "mongodb"

            # Common SQLite indicators
            if (
                connection_string == ":memory:"
                or connection_lower.endswith(".db")
                or connection_lower.endswith(".sqlite")
                or connection_lower.endswith(".sqlite3")
                or connection_lower.startswith("sqlite")
                or
                # File path without URL scheme (likely SQLite)
                ("/" in connection_string and "://" not in connection_string)
            ):
                return "sqlite"

            # Try URL parsing for other databases
            try:
                components = ConnectionParser.parse_connection_string(connection_string)
                scheme = components.get("scheme", "").lower()

                # Map database schemes to AsyncSQLDatabaseNode database types
                # Handle SQLAlchemy-style schemes like mysql+pymysql, postgresql+asyncpg, etc.
                if scheme in ["postgresql", "postgres"] or scheme.startswith(
                    "postgresql+"
                ):
                    return "postgresql"
                elif scheme == "mysql" or scheme.startswith("mysql+"):
                    return "mysql"
                elif scheme in ["sqlite"]:
                    return "sqlite"
                elif scheme in ["mongodb"] or scheme.startswith("mongodb+"):
                    return "mongodb"
                elif not scheme:
                    # No scheme found - likely a file path (SQLite)
                    return "sqlite"
                else:
                    raise AdapterError(f"Unsupported database scheme: {scheme}")
            except Exception:
                # If URL parsing fails, check if it's a MongoDB URI
                if "mongodb" in connection_lower:
                    return "mongodb"
                # Otherwise assume it's a file path (SQLite)
                return "sqlite"

        except Exception as e:
            raise AdapterError(f"Failed to detect database type: {e}")
