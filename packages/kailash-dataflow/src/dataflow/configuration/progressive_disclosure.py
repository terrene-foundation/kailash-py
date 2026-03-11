"""
DataFlow Progressive Disclosure Configuration

Provides a zero-config to enterprise configuration system that allows users to start
simple and progressively enable more advanced features as their needs grow.

Design Philosophy:
- Zero configuration by default (just works)
- Progressive complexity (enable features as needed)
- Intelligent defaults (optimal settings for common use cases)
- Enterprise scalability (supports advanced features when required)
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class ConfigurationLevel(Enum):
    """Configuration complexity levels for progressive disclosure."""

    ZERO_CONFIG = "zero_config"  # No configuration required
    BASIC = "basic"  # Simple configuration options
    INTERMEDIATE = "intermediate"  # Moderate feature set
    ADVANCED = "advanced"  # Full feature control
    ENTERPRISE = "enterprise"  # All enterprise features


class FeatureFlag(Enum):
    """Feature flags for progressive enablement."""

    # Basic features (enabled by default)
    AUTO_MIGRATIONS = "auto_migrations"
    VISUAL_BUILDER = "visual_builder"
    BASIC_POOLING = "basic_pooling"

    # Intermediate features
    QUERY_OPTIMIZATION = "query_optimization"
    INDEX_RECOMMENDATIONS = "index_recommendations"
    CACHING = "caching"
    MONITORING = "monitoring"

    # Advanced features
    MULTI_TENANT = "multi_tenant"
    SOFT_DELETE = "soft_delete"
    AUDIT_LOGGING = "audit_logging"
    ENCRYPTION = "encryption"

    # Enterprise features
    DISTRIBUTED_TRANSACTIONS = "distributed_transactions"
    READ_REPLICAS = "read_replicas"
    SHARDING = "sharding"
    COMPLIANCE = "compliance"
    ADVANCED_SECURITY = "advanced_security"

    # Testing and Development features
    TDD_MODE = "tdd_mode"  # Test-driven development infrastructure


@dataclass
class DatabaseConfiguration:
    """Progressive database configuration."""

    # Zero-config defaults
    url: Optional[str] = None  # Auto-detects from environment or creates SQLite
    dialect: Optional[str] = None  # Auto-detected from URL

    # Basic configuration
    pool_size: Optional[int] = None  # Auto-sized based on usage
    echo: Optional[bool] = None  # False by default, True in development

    # Intermediate configuration
    pool_max_overflow: Optional[int] = None
    pool_recycle: Optional[int] = None
    slow_query_threshold: Optional[int] = None

    # Advanced configuration
    read_replica_urls: List[str] = field(default_factory=list)
    encryption_key: Optional[str] = None
    compression_enabled: bool = False

    # Enterprise configuration
    sharding_config: Optional[Dict[str, Any]] = None
    compliance_mode: Optional[str] = None
    security_policies: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CacheConfiguration:
    """Progressive cache configuration."""

    # Zero-config (no caching)
    enabled: bool = False

    # Basic configuration (in-memory cache)
    backend: str = "memory"
    ttl: int = 300  # 5 minutes

    # Intermediate configuration
    max_size: Optional[int] = None
    redis_url: Optional[str] = None

    # Advanced configuration
    distributed: bool = False
    invalidation_strategies: List[str] = field(default_factory=list)

    # Enterprise configuration
    multi_region: bool = False
    encryption_enabled: bool = False


@dataclass
class MonitoringConfiguration:
    """Progressive monitoring configuration."""

    # Zero-config (basic logging)
    enabled: bool = True
    log_level: str = "INFO"

    # Basic configuration
    slow_query_logging: bool = False
    performance_metrics: bool = False

    # Intermediate configuration
    prometheus_enabled: bool = False
    health_checks: bool = False
    alerting: bool = False

    # Advanced configuration
    distributed_tracing: bool = False
    custom_metrics: List[str] = field(default_factory=list)

    # Enterprise configuration
    sla_monitoring: bool = False
    compliance_reporting: bool = False
    audit_trail: bool = False


@dataclass
class SecurityConfiguration:
    """Progressive security configuration."""

    # Zero-config (basic security)
    enabled: bool = True

    # Basic configuration
    connection_encryption: bool = True
    basic_auth: bool = False

    # Intermediate configuration
    oauth2_enabled: bool = False
    rbac_enabled: bool = False

    # Advanced configuration
    field_level_encryption: bool = False
    data_masking: bool = False

    # Enterprise configuration
    compliance_mode: Optional[str] = None  # GDPR, HIPAA, SOC2
    advanced_threat_detection: bool = False
    zero_trust_network: bool = False


class ProgressiveConfiguration:
    """
    Main configuration manager that provides progressive disclosure of complexity.

    Users can start with zero configuration and progressively enable features
    as their needs grow from simple prototyping to enterprise deployment.
    """

    def __init__(
        self,
        level: Union[ConfigurationLevel, str] = ConfigurationLevel.ZERO_CONFIG,
        features: Optional[List[Union[FeatureFlag, str]]] = None,
        environment: Optional[str] = None,
    ):
        """
        Initialize progressive configuration.

        Args:
            level: Configuration complexity level
            features: Optional feature flags to enable
            environment: Environment (development, staging, production)
        """
        self.level = ConfigurationLevel(level) if isinstance(level, str) else level
        self.environment = environment or self._detect_environment()
        self.enabled_features = self._initialize_features(features)

        # Initialize configuration sections
        self.database = DatabaseConfiguration()
        self.cache = CacheConfiguration()
        self.monitoring = MonitoringConfiguration()
        self.security = SecurityConfiguration()

        # Apply configuration based on level
        self._apply_level_defaults()
        self._apply_environment_defaults()
        self._apply_feature_flags()

    def _detect_environment(self) -> str:
        """Auto-detect environment from various sources."""
        # Check environment variables
        env = os.getenv("ENVIRONMENT") or os.getenv("ENV") or os.getenv("NODE_ENV")
        if env:
            return env.lower()

        # Check for common development indicators
        if os.getenv("DEBUG") or os.getenv("DEVELOPMENT"):
            return "development"

        # Check for CI/CD indicators
        if any(os.getenv(var) for var in ["CI", "GITHUB_ACTIONS", "JENKINS_URL"]):
            return "testing"

        # Default to production for safety
        return "production"

    def _initialize_features(
        self, features: Optional[List[Union[FeatureFlag, str]]]
    ) -> set:
        """Initialize enabled features based on configuration level."""
        enabled = set()

        # Default features based on level (cumulative)
        # Basic features (always enabled)
        enabled.update(
            [
                FeatureFlag.AUTO_MIGRATIONS,
                FeatureFlag.VISUAL_BUILDER,
                FeatureFlag.BASIC_POOLING,
            ]
        )

        # Intermediate features
        if self.level in [
            ConfigurationLevel.INTERMEDIATE,
            ConfigurationLevel.ADVANCED,
            ConfigurationLevel.ENTERPRISE,
        ]:
            enabled.update(
                [
                    FeatureFlag.QUERY_OPTIMIZATION,
                    FeatureFlag.INDEX_RECOMMENDATIONS,
                    FeatureFlag.CACHING,
                    FeatureFlag.MONITORING,
                ]
            )

        if self.level in [ConfigurationLevel.ADVANCED, ConfigurationLevel.ENTERPRISE]:
            enabled.update(
                [
                    FeatureFlag.MULTI_TENANT,
                    FeatureFlag.SOFT_DELETE,
                    FeatureFlag.AUDIT_LOGGING,
                    FeatureFlag.ENCRYPTION,
                ]
            )

        if self.level == ConfigurationLevel.ENTERPRISE:
            enabled.update(
                [
                    FeatureFlag.DISTRIBUTED_TRANSACTIONS,
                    FeatureFlag.READ_REPLICAS,
                    FeatureFlag.SHARDING,
                    FeatureFlag.COMPLIANCE,
                    FeatureFlag.ADVANCED_SECURITY,
                ]
            )

        # Add explicitly requested features
        if features:
            for feature in features:
                if isinstance(feature, str):
                    try:
                        enabled.add(FeatureFlag(feature))
                    except ValueError:
                        logger.warning(f"Unknown feature flag: {feature}")
                else:
                    enabled.add(feature)

        return enabled

    def _apply_level_defaults(self):
        """Apply configuration defaults based on complexity level."""
        if self.level == ConfigurationLevel.ZERO_CONFIG:
            self._apply_zero_config_defaults()
        elif self.level == ConfigurationLevel.BASIC:
            self._apply_basic_defaults()
        elif self.level == ConfigurationLevel.INTERMEDIATE:
            self._apply_intermediate_defaults()
        elif self.level == ConfigurationLevel.ADVANCED:
            self._apply_advanced_defaults()
        elif self.level == ConfigurationLevel.ENTERPRISE:
            self._apply_enterprise_defaults()

    def _apply_zero_config_defaults(self):
        """Apply zero-configuration defaults (just works)."""
        # Database: Auto-create SQLite if no configuration
        if not self.database.url:
            self.database.url = "sqlite:///dataflow.db"
        self.database.echo = self.environment == "development"
        self.database.pool_size = 5  # Small pool for simplicity

        # Cache: Disabled by default
        self.cache.enabled = False

        # Monitoring: Basic logging only
        self.monitoring.log_level = "INFO"
        self.monitoring.slow_query_logging = False

        # Security: Basic protection
        self.security.connection_encryption = True

    def _apply_basic_defaults(self):
        """Apply basic configuration defaults."""
        self._apply_zero_config_defaults()  # Start with zero-config

        # Database: Slightly larger pool
        self.database.pool_size = 10
        self.database.slow_query_threshold = 1000  # 1 second

        # Cache: Simple in-memory cache
        self.cache.enabled = True
        self.cache.backend = "memory"
        self.cache.max_size = 1000

        # Monitoring: Add basic metrics
        self.monitoring.performance_metrics = True
        self.monitoring.slow_query_logging = True

    def _apply_intermediate_defaults(self):
        """Apply intermediate configuration defaults."""
        self._apply_basic_defaults()  # Start with basic

        # Database: Production-ready pooling
        self.database.pool_size = 20
        self.database.pool_max_overflow = 30
        self.database.pool_recycle = 3600  # 1 hour

        # Cache: Redis support
        self.cache.backend = "redis"
        self.cache.ttl = 600  # 10 minutes

        # Monitoring: Health checks and alerting
        self.monitoring.health_checks = True
        self.monitoring.alerting = True
        self.monitoring.prometheus_enabled = True

        # Security: OAuth2 support
        self.security.oauth2_enabled = True
        self.security.rbac_enabled = True

    def _apply_advanced_defaults(self):
        """Apply advanced configuration defaults."""
        self._apply_intermediate_defaults()  # Start with intermediate

        # Database: Advanced features
        self.database.compression_enabled = True

        # Cache: Distributed caching
        self.cache.distributed = True
        self.cache.invalidation_strategies = ["time_based", "event_driven"]

        # Monitoring: Distributed tracing
        self.monitoring.distributed_tracing = True

        # Security: Field-level encryption
        self.security.field_level_encryption = True
        self.security.data_masking = True

    def _apply_enterprise_defaults(self):
        """Apply enterprise configuration defaults."""
        self._apply_advanced_defaults()  # Start with advanced

        # Database: Enterprise scaling
        self.database.pool_size = 50
        self.database.pool_max_overflow = 100

        # Cache: Multi-region caching
        self.cache.multi_region = True
        self.cache.encryption_enabled = True

        # Monitoring: Full observability
        self.monitoring.sla_monitoring = True
        self.monitoring.compliance_reporting = True
        self.monitoring.audit_trail = True

        # Security: Enterprise security
        self.security.compliance_mode = "SOC2"
        self.security.advanced_threat_detection = True
        self.security.zero_trust_network = True

    def _apply_environment_defaults(self):
        """Apply environment-specific defaults."""
        if self.environment == "development":
            # Development: More verbose logging, smaller pools
            self.database.echo = True
            self.database.pool_size = min(self.database.pool_size or 5, 5)
            self.monitoring.log_level = "DEBUG"
            self.security.connection_encryption = False  # For easier debugging

        elif self.environment == "testing":
            # Testing: Fast but reliable
            self.database.echo = False
            self.database.pool_size = 3
            self.cache.enabled = False  # Avoid cache-related test issues
            self.monitoring.log_level = "WARNING"

        elif self.environment == "production":
            # Production: Performance and security focused
            self.database.echo = False
            self.monitoring.log_level = "INFO"
            self.security.connection_encryption = True

            # Auto-enable production features based on level
            if self.level in [
                ConfigurationLevel.INTERMEDIATE,
                ConfigurationLevel.ADVANCED,
                ConfigurationLevel.ENTERPRISE,
            ]:
                self.cache.enabled = True
                self.monitoring.health_checks = True

    def _apply_feature_flags(self):
        """Apply feature-specific configuration."""
        if FeatureFlag.CACHING in self.enabled_features and not self.cache.enabled:
            # Don't enable cache in testing environment
            if self.environment != "testing":
                self.cache.enabled = True

        if FeatureFlag.MONITORING in self.enabled_features:
            self.monitoring.performance_metrics = True
            self.monitoring.slow_query_logging = True

        if FeatureFlag.ENCRYPTION in self.enabled_features:
            self.security.field_level_encryption = True

        if FeatureFlag.COMPLIANCE in self.enabled_features:
            # Only set compliance mode if not already set by level defaults
            if not self.security.compliance_mode:
                self.security.compliance_mode = "GDPR"
            self.monitoring.audit_trail = True

    def is_feature_enabled(self, feature: Union[FeatureFlag, str]) -> bool:
        """Check if a feature is enabled."""
        if isinstance(feature, str):
            try:
                feature = FeatureFlag(feature)
            except ValueError:
                return False
        return feature in self.enabled_features

    def enable_feature(self, feature: Union[FeatureFlag, str]):
        """Enable a specific feature."""
        if isinstance(feature, str):
            try:
                feature = FeatureFlag(feature)
            except ValueError:
                logger.warning(f"Unknown feature flag: {feature}")
                return

        self.enabled_features.add(feature)
        self._apply_feature_flags()
        logger.info(f"Enabled feature: {feature.value}")

    def disable_feature(self, feature: Union[FeatureFlag, str]):
        """Disable a specific feature."""
        if isinstance(feature, str):
            try:
                feature = FeatureFlag(feature)
            except ValueError:
                return

        self.enabled_features.discard(feature)
        logger.info(f"Disabled feature: {feature.value}")

    def upgrade_level(self, new_level: Union[ConfigurationLevel, str]):
        """Upgrade to a higher configuration level."""
        new_level = (
            ConfigurationLevel(new_level) if isinstance(new_level, str) else new_level
        )

        # Define level ordering
        level_order = {
            ConfigurationLevel.ZERO_CONFIG: 0,
            ConfigurationLevel.BASIC: 1,
            ConfigurationLevel.INTERMEDIATE: 2,
            ConfigurationLevel.ADVANCED: 3,
            ConfigurationLevel.ENTERPRISE: 4,
        }

        if level_order[new_level] >= level_order[self.level]:
            old_level = self.level
            self.level = new_level
            self.enabled_features = self._initialize_features(None)
            self._apply_level_defaults()
            self._apply_environment_defaults()
            self._apply_feature_flags()
            logger.info(
                f"Upgraded configuration from {old_level.value} to {new_level.value}"
            )
        else:
            logger.warning(
                f"Cannot downgrade from {self.level.value} to {new_level.value}"
            )

    def get_database_url(self) -> str:
        """Get the resolved database URL."""
        # Check environment variables first
        url = (
            os.getenv("DATABASE_URL")
            or os.getenv("DB_URL")
            or os.getenv("DATAFLOW_DATABASE_URL")
        )

        if url:
            return url

        # Then check configured URL
        if self.database.url:
            return self.database.url

        # Default to SQLite
        return "sqlite:///dataflow.db"

    def get_configuration_summary(self) -> Dict[str, Any]:
        """Get a summary of current configuration."""
        return {
            "level": self.level.value,
            "environment": self.environment,
            "enabled_features": [f.value for f in self.enabled_features],
            "database": {
                "url": self.get_database_url(),
                "pool_size": self.database.pool_size,
                "echo": self.database.echo,
            },
            "cache": {
                "enabled": self.cache.enabled,
                "backend": self.cache.backend if self.cache.enabled else None,
            },
            "monitoring": {
                "log_level": self.monitoring.log_level,
                "performance_metrics": self.monitoring.performance_metrics,
            },
            "security": {
                "connection_encryption": self.security.connection_encryption,
                "compliance_mode": self.security.compliance_mode,
            },
        }

    def generate_documentation(self) -> str:
        """Generate user-friendly documentation for current configuration."""
        doc = f"""
# DataFlow Configuration Summary

**Configuration Level**: {self.level.value.replace('_', ' ').title()}
**Environment**: {self.environment.title()}

## Enabled Features
"""
        for feature in sorted(self.enabled_features, key=lambda f: f.value):
            doc += f"- {feature.value.replace('_', ' ').title()}\n"

        doc += f"""
## Database Configuration
- URL: {self.get_database_url()}
- Pool Size: {self.database.pool_size}
- SQL Logging: {"Enabled" if self.database.echo else "Disabled"}

## Caching
- Status: {"Enabled" if self.cache.enabled else "Disabled"}
"""
        if self.cache.enabled:
            doc += f"- Backend: {self.cache.backend.title()}\n"
            doc += f"- TTL: {self.cache.ttl} seconds\n"

        doc += f"""
## Monitoring
- Log Level: {self.monitoring.log_level}
- Performance Metrics: {"Enabled" if self.monitoring.performance_metrics else "Disabled"}
- Health Checks: {"Enabled" if self.monitoring.health_checks else "Disabled"}

## Security
- Connection Encryption: {"Enabled" if self.security.connection_encryption else "Disabled"}
"""
        if self.security.compliance_mode:
            doc += f"- Compliance Mode: {self.security.compliance_mode}\n"

        doc += """
## Next Steps
"""
        if self.level == ConfigurationLevel.ZERO_CONFIG:
            doc += "- Consider upgrading to 'basic' level for caching and monitoring\n"
        elif self.level == ConfigurationLevel.BASIC:
            doc += (
                "- Consider upgrading to 'intermediate' level for production features\n"
            )
        elif self.level == ConfigurationLevel.INTERMEDIATE:
            doc += "- Consider upgrading to 'advanced' level for enterprise features\n"

        return doc


def create_configuration(
    level: Union[ConfigurationLevel, str] = "zero_config",
    features: Optional[List[str]] = None,
    environment: Optional[str] = None,
    **kwargs,
) -> ProgressiveConfiguration:
    """
    Create a progressive configuration with smart defaults.

    Args:
        level: Configuration complexity level
        features: Optional feature flags to enable
        environment: Environment (auto-detected if not provided)
        **kwargs: Additional configuration overrides

    Returns:
        Configured ProgressiveConfiguration instance
    """
    config = ProgressiveConfiguration(level, features, environment)

    # Apply any override parameters
    for key, value in kwargs.items():
        if hasattr(config.database, key):
            setattr(config.database, key, value)
        elif hasattr(config.cache, key):
            setattr(config.cache, key, value)
        elif hasattr(config.monitoring, key):
            setattr(config.monitoring, key, value)
        elif hasattr(config.security, key):
            setattr(config.security, key, value)

    return config


# Convenience functions for common configurations
def zero_config() -> ProgressiveConfiguration:
    """Create zero-configuration setup (just works)."""
    return create_configuration("zero_config")


def basic_config() -> ProgressiveConfiguration:
    """Create basic configuration (simple caching and monitoring)."""
    return create_configuration("basic")


def production_config() -> ProgressiveConfiguration:
    """Create production-ready configuration."""
    return create_configuration("intermediate")


def enterprise_config() -> ProgressiveConfiguration:
    """Create enterprise configuration (all features)."""
    return create_configuration("enterprise")
