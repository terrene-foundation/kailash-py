"""Connection string builder for database connections."""

import re
from typing import Any, Dict, Optional
from urllib.parse import quote_plus


class ConnectionStringBuilder:
    """Builds database connection strings with security validation."""

    def __init__(self):
        self.components = {}
        self.security_rules = {
            "allow_special_chars": False,
            "validate_injection": True,
            "escape_values": True,
        }

    def set_driver(self, driver: str) -> "ConnectionStringBuilder":
        """Set the database driver."""
        if self._validate_component(driver):
            self.components["driver"] = driver
        return self

    def set_host(self, host: str) -> "ConnectionStringBuilder":
        """Set the database host."""
        if self._validate_component(host):
            self.components["host"] = host
        return self

    def set_port(self, port: int) -> "ConnectionStringBuilder":
        """Set the database port."""
        self.components["port"] = port
        return self

    def set_database(self, database: str) -> "ConnectionStringBuilder":
        """Set the database name."""
        if self._validate_component(database):
            self.components["database"] = database
        return self

    def set_username(self, username: str) -> "ConnectionStringBuilder":
        """Set the username."""
        if self._validate_component(username):
            self.components["username"] = quote_plus(username)
        return self

    def set_password(self, password: str) -> "ConnectionStringBuilder":
        """Set the password."""
        if self._validate_component(password):
            self.components["password"] = quote_plus(password)
        return self

    def add_parameter(self, key: str, value: str) -> "ConnectionStringBuilder":
        """Add a connection parameter."""
        if "parameters" not in self.components:
            self.components["parameters"] = {}

        if self._validate_component(key) and self._validate_component(value):
            self.components["parameters"][key] = value
        return self

    def build(self) -> str:
        """Build the connection string."""
        if "driver" not in self.components:
            raise ValueError("Driver is required")

        driver = self.components["driver"]

        if driver.startswith("postgresql"):
            return self._build_postgresql()
        elif driver.startswith("mysql"):
            return self._build_mysql()
        elif driver.startswith("sqlite"):
            return self._build_sqlite()
        else:
            return self._build_generic()

    def _build_postgresql(self) -> str:
        """Build PostgreSQL connection string."""
        parts = [self.components["driver"] + "://"]

        if "username" in self.components:
            parts.append(self.components["username"])
            if "password" in self.components:
                parts.append(":" + self.components["password"])
            parts.append("@")

        if "host" in self.components:
            parts.append(self.components["host"])
            if "port" in self.components:
                parts.append(":" + str(self.components["port"]))

        if "database" in self.components:
            parts.append("/" + self.components["database"])

        if "parameters" in self.components:
            params = "&".join(
                [f"{k}={v}" for k, v in self.components["parameters"].items()]
            )
            parts.append("?" + params)

        return "".join(parts)

    def _build_mysql(self) -> str:
        """Build MySQL connection string."""
        return self._build_postgresql()  # Similar format

    def _build_sqlite(self) -> str:
        """Build SQLite connection string."""
        if "database" not in self.components:
            raise ValueError("Database file path required for SQLite")

        return f"sqlite:///{self.components['database']}"

    def _build_generic(self) -> str:
        """Build generic connection string."""
        return self._build_postgresql()

    def _validate_component(self, value: str) -> bool:
        """Validate component for security issues."""
        if not self.security_rules["validate_injection"]:
            return True

        # Check for SQL injection patterns
        injection_patterns = [
            r"'.*'",
            r";.*--",
            r"union\s+select",
            r"drop\s+table",
            r"delete\s+from",
            r"update\s+.*\s+set",
        ]

        value_lower = value.lower()
        for pattern in injection_patterns:
            if re.search(pattern, value_lower):
                raise ValueError(f"Potential SQL injection detected: {value}")

        return True
