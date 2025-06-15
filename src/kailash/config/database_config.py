"""Typed configuration objects for database and security settings.

This module provides clean, typed configuration objects that replace
scattered parameters with structured, validated configuration.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    """Database connection pool configuration."""

    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    pool_pre_ping: bool = True

    def __post_init__(self):
        """Validate pool configuration."""
        if self.pool_size < 1:
            raise ValueError("pool_size must be at least 1")
        if self.max_overflow < 0:
            raise ValueError("max_overflow cannot be negative")
        if self.pool_timeout < 1:
            raise ValueError("pool_timeout must be at least 1 second")


@dataclass
class SecurityConfig:
    """Security and access control configuration."""

    access_control_manager: Optional[Any] = None
    masking_rules: Dict[str, Any] = field(default_factory=dict)
    audit_enabled: bool = True
    encryption_enabled: bool = False
    ssl_config: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate security configuration."""
        if self.encryption_enabled and not self.ssl_config:
            logger.warning("Encryption enabled but no SSL configuration provided")


@dataclass
class ValidationConfig:
    """Query validation configuration."""

    enabled: bool = True
    dangerous_keywords_blocked: bool = True
    custom_validators: List[Any] = field(default_factory=list)
    sql_injection_check: bool = True
    max_query_length: int = 100000

    def __post_init__(self):
        """Validate validation configuration."""
        if self.max_query_length < 1:
            raise ValueError("max_query_length must be positive")


@dataclass
class DatabaseConfig:
    """Comprehensive database configuration."""

    # Connection settings
    connection_string: str
    database_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    # Configuration objects
    pool_config: PoolConfig = field(default_factory=PoolConfig)
    security_config: SecurityConfig = field(default_factory=SecurityConfig)
    validation_config: ValidationConfig = field(default_factory=ValidationConfig)

    # Additional settings
    echo: bool = False
    connect_args: Dict[str, Any] = field(default_factory=dict)
    isolation_level: Optional[str] = None

    def __post_init__(self):
        """Validate database configuration."""
        if not self.connection_string:
            raise ValueError("connection_string is required")

        # Extract database type from connection string if not provided
        if not self.database_type and "://" in self.connection_string:
            self.database_type = self.connection_string.split("://")[0].split("+")[0]

        # Validate connection string format
        self._validate_connection_string()

    def _validate_connection_string(self):
        """Validate connection string format."""
        if not self.connection_string.startswith(
            ("postgresql://", "mysql://", "sqlite:///")
        ):
            # Allow driver specifications like postgresql+psycopg2://
            valid_prefixes = ("postgresql+", "mysql+", "sqlite+")
            if not any(
                self.connection_string.startswith(prefix) for prefix in valid_prefixes
            ):
                raise ValueError(
                    "connection_string must start with postgresql://, mysql://, or sqlite:///"
                )

    def get_sqlalchemy_config(self) -> Dict[str, Any]:
        """Get SQLAlchemy-compatible configuration."""
        config = {
            "poolclass": "QueuePool",  # Will be converted to actual class
            "pool_size": self.pool_config.pool_size,
            "max_overflow": self.pool_config.max_overflow,
            "pool_timeout": self.pool_config.pool_timeout,
            "pool_recycle": self.pool_config.pool_recycle,
            "pool_pre_ping": self.pool_config.pool_pre_ping,
            "echo": self.echo,
        }

        if self.isolation_level:
            config["isolation_level"] = self.isolation_level

        if self.connect_args:
            config["connect_args"] = self.connect_args

        return config

    def get_masked_connection_string(self) -> str:
        """Get connection string with password masked for logging."""
        import re

        pattern = r"(://[^:]+:)[^@]+(@)"
        return re.sub(pattern, r"\1***\2", self.connection_string)

    def is_encrypted(self) -> bool:
        """Check if connection uses encryption."""
        return (
            self.security_config.encryption_enabled
            or "sslmode=require" in self.connection_string
            or "ssl=true" in self.connection_string
        )


@dataclass
class AsyncDatabaseConfig(DatabaseConfig):
    """Configuration for async database operations."""

    # Async-specific settings
    min_size: int = 1
    max_size: int = 10
    command_timeout: int = 60
    server_settings: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Validate async database configuration."""
        super().__post_init__()

        if self.min_size < 1:
            raise ValueError("min_size must be at least 1")
        if self.max_size < self.min_size:
            raise ValueError("max_size must be >= min_size")
        if self.command_timeout < 1:
            raise ValueError("command_timeout must be positive")

    def get_asyncpg_config(self) -> Dict[str, Any]:
        """Get asyncpg-compatible configuration."""
        config = {
            "min_size": self.min_size,
            "max_size": self.max_size,
            "command_timeout": self.command_timeout,
        }

        if self.server_settings:
            config["server_settings"] = self.server_settings

        return config


@dataclass
class VectorDatabaseConfig(AsyncDatabaseConfig):
    """Configuration for vector database operations."""

    # Vector-specific settings
    dimension: int = 1536
    index_type: str = "hnsw"
    distance_metric: str = "cosine"
    index_params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate vector database configuration."""
        super().__post_init__()

        if self.dimension < 1:
            raise ValueError("dimension must be positive")

        valid_index_types = ["hnsw", "ivfflat"]
        if self.index_type not in valid_index_types:
            raise ValueError(f"index_type must be one of {valid_index_types}")

        valid_metrics = ["cosine", "euclidean", "manhattan", "dot_product"]
        if self.distance_metric not in valid_metrics:
            raise ValueError(f"distance_metric must be one of {valid_metrics}")

    def get_pgvector_config(self) -> Dict[str, Any]:
        """Get pgvector-specific configuration."""
        config = {
            "dimension": self.dimension,
            "index_type": self.index_type,
            "distance_metric": self.distance_metric,
        }

        if self.index_params:
            config["index_params"] = self.index_params

        return config


# Configuration builders for common scenarios
class DatabaseConfigBuilder:
    """Builder for database configurations."""

    @staticmethod
    def postgresql(
        host: str = "localhost",
        port: int = 5432,
        database: str = "postgres",
        username: str = "postgres",
        password: str = "",
        **kwargs,
    ) -> DatabaseConfig:
        """Build PostgreSQL configuration."""
        connection_string = (
            f"postgresql://{username}:{password}@{host}:{port}/{database}"
        )

        return DatabaseConfig(
            connection_string=connection_string,
            database_type="postgresql",
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            **kwargs,
        )

    @staticmethod
    def mysql(
        host: str = "localhost",
        port: int = 3306,
        database: str = "mysql",
        username: str = "root",
        password: str = "",
        **kwargs,
    ) -> DatabaseConfig:
        """Build MySQL configuration."""
        connection_string = f"mysql://{username}:{password}@{host}:{port}/{database}"

        return DatabaseConfig(
            connection_string=connection_string,
            database_type="mysql",
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            **kwargs,
        )

    @staticmethod
    def sqlite(database_path: str, **kwargs) -> DatabaseConfig:
        """Build SQLite configuration."""
        connection_string = f"sqlite:///{database_path}"

        return DatabaseConfig(
            connection_string=connection_string,
            database_type="sqlite",
            database=database_path,
            **kwargs,
        )


class AsyncDatabaseConfigBuilder:
    """Builder for async database configurations."""

    @staticmethod
    def postgresql(
        host: str = "localhost",
        port: int = 5432,
        database: str = "postgres",
        username: str = "postgres",
        password: str = "",
        **kwargs,
    ) -> AsyncDatabaseConfig:
        """Build async PostgreSQL configuration."""
        connection_string = (
            f"postgresql://{username}:{password}@{host}:{port}/{database}"
        )

        return AsyncDatabaseConfig(
            connection_string=connection_string,
            database_type="postgresql",
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            **kwargs,
        )

    @staticmethod
    def with_vector_support(
        base_config: AsyncDatabaseConfig, dimension: int = 1536, **vector_kwargs
    ) -> VectorDatabaseConfig:
        """Add vector support to async database configuration."""
        # Convert to vector config
        config_dict = {
            "connection_string": base_config.connection_string,
            "database_type": base_config.database_type,
            "host": base_config.host,
            "port": base_config.port,
            "database": base_config.database,
            "username": base_config.username,
            "password": base_config.password,
            "pool_config": base_config.pool_config,
            "security_config": base_config.security_config,
            "validation_config": base_config.validation_config,
            "echo": base_config.echo,
            "connect_args": base_config.connect_args,
            "isolation_level": base_config.isolation_level,
            "min_size": base_config.min_size,
            "max_size": base_config.max_size,
            "command_timeout": base_config.command_timeout,
            "server_settings": base_config.server_settings,
            "dimension": dimension,
            **vector_kwargs,
        }

        return VectorDatabaseConfig(**config_dict)


# Export components
__all__ = [
    "PoolConfig",
    "SecurityConfig",
    "ValidationConfig",
    "DatabaseConfig",
    "AsyncDatabaseConfig",
    "VectorDatabaseConfig",
    "DatabaseConfigBuilder",
    "AsyncDatabaseConfigBuilder",
]
