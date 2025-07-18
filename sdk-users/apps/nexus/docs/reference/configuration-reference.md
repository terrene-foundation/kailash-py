# Configuration Reference

Complete configuration reference for Nexus's workflow-native platform, covering all settings, environment variables, deployment options, and enterprise features.

## Overview

Nexus provides comprehensive configuration capabilities spanning development, staging, and production environments. This reference covers all configuration parameters, environment variables, file formats, and advanced enterprise settings.

## Application Configuration

### Core Configuration Object

```python
from nexus import Nexus
from typing import Dict, Any, Optional, List
import os
import json
import yaml
from pathlib import Path
from enum import Enum

class EnvironmentType(Enum):
    """Supported environment types"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"

class NexusConfiguration:
    """Comprehensive Nexus configuration management"""

    def __init__(self, environment: EnvironmentType = EnvironmentType.DEVELOPMENT):
        self.environment = environment
        self.config = self._load_default_config()

    def _load_default_config(self) -> Dict[str, Any]:
        """Load default configuration based on environment"""

        base_config = {
            # Application Settings
            "app": {
                "name": "nexus-platform",
                "version": "1.0.0",
                "debug": self.environment == EnvironmentType.DEVELOPMENT,
                "log_level": "DEBUG" if self.environment == EnvironmentType.DEVELOPMENT else "INFO",
                "timezone": "UTC",
                "secret_key": os.getenv("NEXUS_SECRET_KEY", "dev-secret-key"),
                "environment": self.environment.value
            },

            # Server Configuration
            "server": {
                "host": "0.0.0.0",
                "port": int(os.getenv("NEXUS_PORT", "8000")),
                "workers": int(os.getenv("NEXUS_WORKERS", "4")),
                "max_connections": int(os.getenv("NEXUS_MAX_CONNECTIONS", "1000")),
                "keepalive_timeout": 65,
                "timeout": 300,
                "ssl_enabled": os.getenv("NEXUS_SSL_ENABLED", "false").lower() == "true",
                "ssl_cert_file": os.getenv("NEXUS_SSL_CERT"),
                "ssl_key_file": os.getenv("NEXUS_SSL_KEY")
            },

            # Database Configuration
            "database": {
                "url": os.getenv("DATABASE_URL", "postgresql://nexus:password@localhost:5432/nexus"),
                "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
                "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
                "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
                "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "3600")),
                "echo": self.environment == EnvironmentType.DEVELOPMENT,
                "isolation_level": "READ_COMMITTED",
                "retry_attempts": 3,
                "retry_delay": 1.0
            },

            # Redis Configuration
            "redis": {
                "url": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                "max_connections": int(os.getenv("REDIS_MAX_CONNECTIONS", "50")),
                "timeout": int(os.getenv("REDIS_TIMEOUT", "5")),
                "retry_on_timeout": True,
                "health_check_interval": 30,
                "decode_responses": True
            },

            # Security Configuration
            "security": {
                "enable_authentication": True,
                "enable_authorization": True,
                "jwt_secret": os.getenv("JWT_SECRET", "jwt-secret-key"),
                "jwt_algorithm": "HS256",
                "jwt_expiration": 3600,
                "bcrypt_rounds": 12,
                "rate_limiting": {
                    "enabled": True,
                    "default_per_minute": 60,
                    "burst_limit": 100
                },
                "cors": {
                    "enabled": True,
                    "origins": ["*"] if self.environment == EnvironmentType.DEVELOPMENT else [],
                    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                    "headers": ["*"]
                }
            },

            # Workflow Configuration
            "workflow": {
                "execution_timeout": int(os.getenv("WORKFLOW_TIMEOUT", "3600")),
                "max_concurrent_executions": int(os.getenv("MAX_CONCURRENT_WORKFLOWS", "100")),
                "retry_attempts": int(os.getenv("WORKFLOW_RETRY_ATTEMPTS", "3")),
                "retry_delay": float(os.getenv("WORKFLOW_RETRY_DELAY", "1.0")),
                "checkpoint_enabled": True,
                "checkpoint_interval": 60,
                "state_persistence": True,
                "execution_history_retention_days": 30
            },

            # Monitoring Configuration
            "monitoring": {
                "enabled": True,
                "metrics_enabled": True,
                "tracing_enabled": self.environment != EnvironmentType.TESTING,
                "logging_enabled": True,
                "health_check_interval": 30,
                "prometheus": {
                    "enabled": True,
                    "port": int(os.getenv("PROMETHEUS_PORT", "9090")),
                    "path": "/metrics"
                },
                "jaeger": {
                    "enabled": self.environment == EnvironmentType.PRODUCTION,
                    "agent_host": os.getenv("JAEGER_AGENT_HOST", "localhost"),
                    "agent_port": int(os.getenv("JAEGER_AGENT_PORT", "14268")),
                    "service_name": "nexus-platform"
                }
            },

            # Cache Configuration
            "cache": {
                "enabled": True,
                "backend": "redis",
                "default_ttl": int(os.getenv("CACHE_DEFAULT_TTL", "3600")),
                "max_size": int(os.getenv("CACHE_MAX_SIZE", "10000")),
                "compression_enabled": True,
                "key_prefix": "nexus:",
                "serialization": "pickle"
            }
        }

        # Environment-specific overrides
        if self.environment == EnvironmentType.PRODUCTION:
            base_config.update(self._production_overrides())
        elif self.environment == EnvironmentType.STAGING:
            base_config.update(self._staging_overrides())
        elif self.environment == EnvironmentType.TESTING:
            base_config.update(self._testing_overrides())

        return base_config

    def _production_overrides(self) -> Dict[str, Any]:
        """Production environment overrides"""
        return {
            "app": {
                "debug": False,
                "log_level": "WARNING"
            },
            "server": {
                "workers": 8,
                "max_connections": 5000
            },
            "database": {
                "pool_size": 20,
                "max_overflow": 50
            },
            "security": {
                "cors": {
                    "origins": os.getenv("ALLOWED_ORIGINS", "").split(",")
                }
            },
            "monitoring": {
                "tracing_enabled": True,
                "prometheus": {
                    "enabled": True
                },
                "jaeger": {
                    "enabled": True
                }
            }
        }

    def _staging_overrides(self) -> Dict[str, Any]:
        """Staging environment overrides"""
        return {
            "app": {
                "debug": False,
                "log_level": "INFO"
            },
            "server": {
                "workers": 4,
                "max_connections": 2000
            },
            "monitoring": {
                "tracing_enabled": True
            }
        }

    def _testing_overrides(self) -> Dict[str, Any]:
        """Testing environment overrides"""
        return {
            "app": {
                "log_level": "ERROR"
            },
            "database": {
                "url": "sqlite:///tmp/nexus_test.db",
                "echo": False
            },
            "redis": {
                "url": "redis://localhost:6379/15"  # Use different DB for tests
            },
            "monitoring": {
                "tracing_enabled": False,
                "prometheus": {
                    "enabled": False
                }
            }
        }

    def get_config(self) -> Dict[str, Any]:
        """Get complete configuration"""
        return self.config.copy()

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get specific configuration section"""
        return self.config.get(section, {}).copy()

    def update_config(self, updates: Dict[str, Any]) -> None:
        """Update configuration with new values"""
        self._deep_update(self.config, updates)

    def _deep_update(self, base_dict: Dict[str, Any], update_dict: Dict[str, Any]) -> None:
        """Deep update dictionary"""
        for key, value in update_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                self._deep_update(base_dict[key], value)
            else:
                base_dict[key] = value

    def load_from_file(self, config_file: str) -> None:
        """Load configuration from file"""
        config_path = Path(config_file)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")

        if config_path.suffix.lower() == '.json':
            with open(config_path, 'r') as f:
                file_config = json.load(f)
        elif config_path.suffix.lower() in ['.yml', '.yaml']:
            with open(config_path, 'r') as f:
                file_config = yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported configuration file format: {config_path.suffix}")

        self.update_config(file_config)

    def save_to_file(self, config_file: str, format: str = "yaml") -> None:
        """Save configuration to file"""
        config_path = Path(config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        if format.lower() == "json":
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=2, default=str)
        elif format.lower() in ["yml", "yaml"]:
            with open(config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, indent=2)
        else:
            raise ValueError(f"Unsupported configuration format: {format}")

# Configuration usage examples
config_manager = NexusConfiguration(EnvironmentType.DEVELOPMENT)

# Get complete configuration
full_config = config_manager.get_config()
print(f"App name: {full_config['app']['name']}")

# Get specific section
server_config = config_manager.get_section("server")
print(f"Server port: {server_config['port']}")

# Update configuration
config_manager.update_config({
    "server": {"port": 8080},
    "app": {"name": "custom-nexus"}
})

# Production configuration example
prod_config = NexusConfiguration(EnvironmentType.PRODUCTION)
prod_settings = prod_config.get_config()
print(f"Production workers: {prod_settings['server']['workers']}")
```

### Enterprise Configuration

```python
from typing import Dict, Any, Optional, List
import os
from dataclasses import dataclass, field
from enum import Enum

class SecurityLevel(Enum):
    """Security configuration levels"""
    BASIC = "basic"
    ENHANCED = "enhanced"
    MAXIMUM = "maximum"

class ScalingMode(Enum):
    """Auto-scaling modes"""
    DISABLED = "disabled"
    REACTIVE = "reactive"
    PREDICTIVE = "predictive"
    INTELLIGENT = "intelligent"

@dataclass
class EnterpriseSecurityConfig:
    """Enterprise security configuration"""

    security_level: SecurityLevel = SecurityLevel.ENHANCED
    encryption_at_rest: bool = True
    encryption_in_transit: bool = True
    key_rotation_enabled: bool = True
    key_rotation_interval_days: int = 30
    audit_logging: bool = True
    compliance_mode: str = "SOC2"  # SOC2, HIPAA, PCI-DSS, GDPR
    mfa_enabled: bool = True
    session_timeout_minutes: int = 60
    ip_whitelist: List[str] = field(default_factory=list)
    api_key_required: bool = True
    oauth_providers: List[str] = field(default_factory=lambda: ["google", "microsoft"])

@dataclass
class EnterprisePerformanceConfig:
    """Enterprise performance configuration"""

    auto_scaling: bool = True
    scaling_mode: ScalingMode = ScalingMode.INTELLIGENT
    min_instances: int = 2
    max_instances: int = 50
    target_cpu_utilization: int = 70
    target_memory_utilization: int = 80
    scale_up_cooldown_seconds: int = 300
    scale_down_cooldown_seconds: int = 600
    load_balancing_algorithm: str = "least_connections"
    circuit_breaker_enabled: bool = True
    bulkhead_isolation: bool = True
    connection_pooling: bool = True
    query_optimization: bool = True

@dataclass
class EnterpriseMonitoringConfig:
    """Enterprise monitoring configuration"""

    comprehensive_metrics: bool = True
    real_time_dashboards: bool = True
    alerting_enabled: bool = True
    log_aggregation: bool = True
    distributed_tracing: bool = True
    apm_enabled: bool = True
    business_metrics: bool = True
    sla_monitoring: bool = True
    capacity_planning: bool = True
    anomaly_detection: bool = True
    alert_channels: List[str] = field(default_factory=lambda: ["email", "slack", "pagerduty"])

class EnterpriseConfiguration:
    """Complete enterprise configuration management"""

    def __init__(self, organization_id: str, deployment_tier: str = "enterprise"):
        self.organization_id = organization_id
        self.deployment_tier = deployment_tier
        self.security = EnterpriseSecurityConfig()
        self.performance = EnterprisePerformanceConfig()
        self.monitoring = EnterpriseMonitoringConfig()

    def get_enterprise_config(self) -> Dict[str, Any]:
        """Get complete enterprise configuration"""

        base_config = {
            "organization": {
                "id": self.organization_id,
                "deployment_tier": self.deployment_tier,
                "features": {
                    "advanced_workflows": True,
                    "enterprise_nodes": True,
                    "custom_integrations": True,
                    "priority_support": True,
                    "dedicated_infrastructure": True,
                    "compliance_reporting": True,
                    "advanced_analytics": True,
                    "multi_tenancy": True
                }
            },

            "security": {
                "level": self.security.security_level.value,
                "encryption": {
                    "at_rest": self.security.encryption_at_rest,
                    "in_transit": self.security.encryption_in_transit,
                    "key_rotation": {
                        "enabled": self.security.key_rotation_enabled,
                        "interval_days": self.security.key_rotation_interval_days
                    }
                },
                "authentication": {
                    "mfa_enabled": self.security.mfa_enabled,
                    "session_timeout_minutes": self.security.session_timeout_minutes,
                    "oauth_providers": self.security.oauth_providers,
                    "api_key_required": self.security.api_key_required
                },
                "authorization": {
                    "rbac_enabled": True,
                    "abac_enabled": True,
                    "policy_engine": "advanced",
                    "fine_grained_permissions": True
                },
                "compliance": {
                    "mode": self.security.compliance_mode,
                    "audit_logging": self.security.audit_logging,
                    "data_retention_days": 2555,  # 7 years
                    "encryption_standards": ["AES-256", "RSA-4096"],
                    "compliance_reporting": True
                },
                "network": {
                    "ip_whitelist": self.security.ip_whitelist,
                    "vpc_isolation": True,
                    "private_endpoints": True,
                    "ddos_protection": True
                }
            },

            "performance": {
                "scaling": {
                    "auto_scaling": self.performance.auto_scaling,
                    "mode": self.performance.scaling_mode.value,
                    "instances": {
                        "min": self.performance.min_instances,
                        "max": self.performance.max_instances
                    },
                    "targets": {
                        "cpu_utilization": self.performance.target_cpu_utilization,
                        "memory_utilization": self.performance.target_memory_utilization
                    },
                    "cooldown": {
                        "scale_up_seconds": self.performance.scale_up_cooldown_seconds,
                        "scale_down_seconds": self.performance.scale_down_cooldown_seconds
                    }
                },
                "optimization": {
                    "load_balancing": self.performance.load_balancing_algorithm,
                    "circuit_breaker": self.performance.circuit_breaker_enabled,
                    "bulkhead_isolation": self.performance.bulkhead_isolation,
                    "connection_pooling": self.performance.connection_pooling,
                    "query_optimization": self.performance.query_optimization
                },
                "caching": {
                    "multi_tier": True,
                    "distributed": True,
                    "intelligent_eviction": True,
                    "cache_warming": True
                }
            },

            "monitoring": {
                "metrics": {
                    "comprehensive": self.monitoring.comprehensive_metrics,
                    "real_time": self.monitoring.real_time_dashboards,
                    "business_metrics": self.monitoring.business_metrics,
                    "custom_metrics": True
                },
                "observability": {
                    "distributed_tracing": self.monitoring.distributed_tracing,
                    "apm": self.monitoring.apm_enabled,
                    "log_aggregation": self.monitoring.log_aggregation,
                    "correlation_analysis": True
                },
                "alerting": {
                    "enabled": self.monitoring.alerting_enabled,
                    "channels": self.monitoring.alert_channels,
                    "intelligent_alerting": True,
                    "escalation_policies": True
                },
                "analytics": {
                    "sla_monitoring": self.monitoring.sla_monitoring,
                    "capacity_planning": self.monitoring.capacity_planning,
                    "anomaly_detection": self.monitoring.anomaly_detection,
                    "predictive_analytics": True
                }
            }
        }

        return base_config

    def apply_compliance_preset(self, compliance_standard: str) -> None:
        """Apply compliance preset configuration"""

        compliance_presets = {
            "SOC2": {
                "encryption_at_rest": True,
                "encryption_in_transit": True,
                "audit_logging": True,
                "mfa_enabled": True,
                "key_rotation_enabled": True
            },
            "HIPAA": {
                "encryption_at_rest": True,
                "encryption_in_transit": True,
                "audit_logging": True,
                "mfa_enabled": True,
                "key_rotation_enabled": True,
                "session_timeout_minutes": 30
            },
            "PCI-DSS": {
                "encryption_at_rest": True,
                "encryption_in_transit": True,
                "audit_logging": True,
                "mfa_enabled": True,
                "key_rotation_enabled": True,
                "session_timeout_minutes": 15
            },
            "GDPR": {
                "encryption_at_rest": True,
                "encryption_in_transit": True,
                "audit_logging": True,
                "mfa_enabled": True,
                "key_rotation_enabled": True
            }
        }

        if compliance_standard in compliance_presets:
            preset = compliance_presets[compliance_standard]
            for key, value in preset.items():
                if hasattr(self.security, key):
                    setattr(self.security, key, value)

            self.security.compliance_mode = compliance_standard

# Enterprise configuration examples
enterprise_config = EnterpriseConfiguration("org_12345", "enterprise_premium")

# Apply HIPAA compliance
enterprise_config.apply_compliance_preset("HIPAA")

# Get complete enterprise configuration
enterprise_settings = enterprise_config.get_enterprise_config()
print(f"Security level: {enterprise_settings['security']['level']}")
print(f"Auto scaling: {enterprise_settings['performance']['scaling']['auto_scaling']}")
print(f"Compliance mode: {enterprise_settings['security']['compliance']['mode']}")
```

## Environment Variables

### Core Environment Variables

```python
import os
from typing import Dict, Any, Optional

class EnvironmentVariables:
    """Complete environment variable reference"""

    # Core Application Variables
    NEXUS_ENV = os.getenv("NEXUS_ENV", "development")
    NEXUS_PORT = int(os.getenv("NEXUS_PORT", "8000"))
    NEXUS_HOST = os.getenv("NEXUS_HOST", "0.0.0.0")
    NEXUS_WORKERS = int(os.getenv("NEXUS_WORKERS", "4"))
    NEXUS_DEBUG = os.getenv("NEXUS_DEBUG", "false").lower() == "true"
    NEXUS_LOG_LEVEL = os.getenv("NEXUS_LOG_LEVEL", "INFO")
    NEXUS_SECRET_KEY = os.getenv("NEXUS_SECRET_KEY")
    NEXUS_CONFIG_FILE = os.getenv("NEXUS_CONFIG_FILE")

    # Database Variables
    DATABASE_URL = os.getenv("DATABASE_URL")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "nexus")
    DB_USER = os.getenv("DB_USER", "nexus")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_SSL_MODE = os.getenv("DB_SSL_MODE", "prefer")

    # Redis Variables
    REDIS_URL = os.getenv("REDIS_URL")
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
    REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
    REDIS_TIMEOUT = int(os.getenv("REDIS_TIMEOUT", "5"))

    # Security Variables
    JWT_SECRET = os.getenv("JWT_SECRET")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION = int(os.getenv("JWT_EXPIRATION", "3600"))
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
    SSL_CERT_FILE = os.getenv("SSL_CERT_FILE")
    SSL_KEY_FILE = os.getenv("SSL_KEY_FILE")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

    # Monitoring Variables
    PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "9090"))
    JAEGER_AGENT_HOST = os.getenv("JAEGER_AGENT_HOST", "localhost")
    JAEGER_AGENT_PORT = int(os.getenv("JAEGER_AGENT_PORT", "14268"))
    SENTRY_DSN = os.getenv("SENTRY_DSN")
    NEW_RELIC_LICENSE_KEY = os.getenv("NEW_RELIC_LICENSE_KEY")
    DATADOG_API_KEY = os.getenv("DATADOG_API_KEY")

    # Workflow Variables
    WORKFLOW_TIMEOUT = int(os.getenv("WORKFLOW_TIMEOUT", "3600"))
    MAX_CONCURRENT_WORKFLOWS = int(os.getenv("MAX_CONCURRENT_WORKFLOWS", "100"))
    WORKFLOW_RETRY_ATTEMPTS = int(os.getenv("WORKFLOW_RETRY_ATTEMPTS", "3"))
    WORKFLOW_RETRY_DELAY = float(os.getenv("WORKFLOW_RETRY_DELAY", "1.0"))
    CHECKPOINT_INTERVAL = int(os.getenv("CHECKPOINT_INTERVAL", "60"))

    # Cache Variables
    CACHE_BACKEND = os.getenv("CACHE_BACKEND", "redis")
    CACHE_DEFAULT_TTL = int(os.getenv("CACHE_DEFAULT_TTL", "3600"))
    CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "10000"))
    CACHE_KEY_PREFIX = os.getenv("CACHE_KEY_PREFIX", "nexus:")

    # Enterprise Variables
    ORGANIZATION_ID = os.getenv("ORGANIZATION_ID")
    DEPLOYMENT_TIER = os.getenv("DEPLOYMENT_TIER", "standard")
    LICENSE_KEY = os.getenv("LICENSE_KEY")
    ENTERPRISE_FEATURES = os.getenv("ENTERPRISE_FEATURES", "").split(",")

    # External Service Variables
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
    AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
    AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")
    GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    GCP_SERVICE_ACCOUNT_KEY = os.getenv("GCP_SERVICE_ACCOUNT_KEY")

    @classmethod
    def validate_required_variables(cls) -> Dict[str, Any]:
        """Validate required environment variables"""

        required_vars = {
            "production": [
                "NEXUS_SECRET_KEY",
                "DATABASE_URL",
                "REDIS_URL",
                "JWT_SECRET",
                "ENCRYPTION_KEY"
            ],
            "staging": [
                "NEXUS_SECRET_KEY",
                "DATABASE_URL",
                "JWT_SECRET"
            ],
            "development": []
        }

        environment = cls.NEXUS_ENV
        missing_vars = []

        for var in required_vars.get(environment, []):
            if not getattr(cls, var, None):
                missing_vars.append(var)

        return {
            "environment": environment,
            "missing_variables": missing_vars,
            "is_valid": len(missing_vars) == 0
        }

    @classmethod
    def get_database_url(cls) -> str:
        """Construct database URL from components"""

        if cls.DATABASE_URL:
            return cls.DATABASE_URL

        return (f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@"
                f"{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}")

    @classmethod
    def get_redis_url(cls) -> str:
        """Construct Redis URL from components"""

        if cls.REDIS_URL:
            return cls.REDIS_URL

        auth_part = f":{cls.REDIS_PASSWORD}@" if cls.REDIS_PASSWORD else ""
        return f"redis://{auth_part}{cls.REDIS_HOST}:{cls.REDIS_PORT}/{cls.REDIS_DB}"

# Environment validation example
validation_result = EnvironmentVariables.validate_required_variables()
print(f"Environment: {validation_result['environment']}")
print(f"Valid: {validation_result['is_valid']}")
if validation_result['missing_variables']:
    print(f"Missing variables: {validation_result['missing_variables']}")

# URL construction examples
db_url = EnvironmentVariables.get_database_url()
redis_url = EnvironmentVariables.get_redis_url()
print(f"Database URL: {db_url[:20]}...")  # Truncated for security
print(f"Redis URL: {redis_url[:20]}...")  # Truncated for security
```

## Configuration Files

### YAML Configuration Format

```python
import yaml
from pathlib import Path
from typing import Dict, Any

def create_example_config_files():
    """Create example configuration files in different formats"""

    # Development configuration
    dev_config = {
        "app": {
            "name": "nexus-development",
            "version": "1.0.0",
            "debug": True,
            "log_level": "DEBUG",
            "environment": "development"
        },
        "server": {
            "host": "127.0.0.1",
            "port": 8000,
            "workers": 1,
            "reload": True
        },
        "database": {
            "url": "postgresql://nexus:password@localhost:5432/nexus_dev",
            "echo": True,
            "pool_size": 5
        },
        "redis": {
            "url": "redis://localhost:6379/0",
            "timeout": 5
        },
        "security": {
            "enable_authentication": False,
            "cors": {
                "origins": ["*"],
                "methods": ["*"]
            }
        },
        "monitoring": {
            "enabled": True,
            "prometheus": {"enabled": False},
            "jaeger": {"enabled": False}
        }
    }

    # Production configuration
    prod_config = {
        "app": {
            "name": "nexus-production",
            "version": "1.0.0",
            "debug": False,
            "log_level": "WARNING",
            "environment": "production"
        },
        "server": {
            "host": "0.0.0.0",
            "port": 8000,
            "workers": 8,
            "max_connections": 5000,
            "ssl_enabled": True,
            "ssl_cert_file": "/etc/ssl/certs/nexus.crt",
            "ssl_key_file": "/etc/ssl/private/nexus.key"
        },
        "database": {
            "url": "${DATABASE_URL}",
            "pool_size": 20,
            "max_overflow": 50,
            "pool_timeout": 30,
            "echo": False
        },
        "redis": {
            "url": "${REDIS_URL}",
            "max_connections": 100,
            "timeout": 10
        },
        "security": {
            "enable_authentication": True,
            "enable_authorization": True,
            "jwt_secret": "${JWT_SECRET}",
            "encryption_key": "${ENCRYPTION_KEY}",
            "cors": {
                "origins": ["https://app.example.com", "https://admin.example.com"],
                "methods": ["GET", "POST", "PUT", "DELETE"]
            },
            "rate_limiting": {
                "enabled": True,
                "default_per_minute": 100,
                "burst_limit": 200
            }
        },
        "monitoring": {
            "enabled": True,
            "prometheus": {
                "enabled": True,
                "port": 9090
            },
            "jaeger": {
                "enabled": True,
                "agent_host": "jaeger-agent",
                "service_name": "nexus-production"
            }
        },
        "workflow": {
            "execution_timeout": 7200,
            "max_concurrent_executions": 500,
            "checkpoint_enabled": True,
            "state_persistence": True
        }
    }

    # Enterprise configuration
    enterprise_config = {
        "app": {
            "name": "nexus-enterprise",
            "version": "1.0.0",
            "debug": False,
            "log_level": "INFO",
            "environment": "production"
        },
        "organization": {
            "id": "${ORGANIZATION_ID}",
            "deployment_tier": "enterprise",
            "license_key": "${LICENSE_KEY}"
        },
        "server": {
            "host": "0.0.0.0",
            "port": 8000,
            "workers": 16,
            "max_connections": 10000
        },
        "security": {
            "level": "maximum",
            "encryption": {
                "at_rest": True,
                "in_transit": True,
                "key_rotation": {
                    "enabled": True,
                    "interval_days": 30
                }
            },
            "authentication": {
                "mfa_enabled": True,
                "oauth_providers": ["google", "microsoft", "okta"],
                "session_timeout_minutes": 60
            },
            "compliance": {
                "mode": "SOC2",
                "audit_logging": True,
                "data_retention_days": 2555
            }
        },
        "performance": {
            "auto_scaling": True,
            "scaling_mode": "intelligent",
            "instances": {"min": 5, "max": 100},
            "targets": {
                "cpu_utilization": 70,
                "memory_utilization": 80
            }
        },
        "monitoring": {
            "comprehensive_metrics": True,
            "real_time_dashboards": True,
            "distributed_tracing": True,
            "anomaly_detection": True,
            "alert_channels": ["email", "slack", "pagerduty"]
        }
    }

    return {
        "development": dev_config,
        "production": prod_config,
        "enterprise": enterprise_config
    }

# Create configuration files
configs = create_example_config_files()

# Example: Save development configuration
dev_config_path = Path("/tmp/nexus-development.yaml")
with open(dev_config_path, 'w') as f:
    yaml.dump(configs["development"], f, default_flow_style=False, indent=2)

print(f"Development config saved to: {dev_config_path}")

# Example: Save production configuration
prod_config_path = Path("/tmp/nexus-production.yaml")
with open(prod_config_path, 'w') as f:
    yaml.dump(configs["production"], f, default_flow_style=False, indent=2)

print(f"Production config saved to: {prod_config_path}")

# Example: Save enterprise configuration
enterprise_config_path = Path("/tmp/nexus-enterprise.yaml")
with open(enterprise_config_path, 'w') as f:
    yaml.dump(configs["enterprise"], f, default_flow_style=False, indent=2)

print(f"Enterprise config saved to: {enterprise_config_path}")
```

## Configuration Validation

### Schema Validation

```python
from typing import Dict, Any, List, Optional
import json
from jsonschema import validate, ValidationError
from dataclasses import dataclass

@dataclass
class ConfigurationValidator:
    """Validate Nexus configuration against schema"""

    def __init__(self):
        self.config_schema = self._get_config_schema()

    def _get_config_schema(self) -> Dict[str, Any]:
        """Get complete configuration schema"""

        return {
            "type": "object",
            "properties": {
                "app": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
                        "debug": {"type": "boolean"},
                        "log_level": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
                        "environment": {"type": "string", "enum": ["development", "staging", "production", "testing"]}
                    },
                    "required": ["name", "version", "environment"]
                },
                "server": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string"},
                        "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                        "workers": {"type": "integer", "minimum": 1, "maximum": 64},
                        "max_connections": {"type": "integer", "minimum": 1},
                        "ssl_enabled": {"type": "boolean"},
                        "ssl_cert_file": {"type": ["string", "null"]},
                        "ssl_key_file": {"type": ["string", "null"]}
                    },
                    "required": ["host", "port"]
                },
                "database": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "minLength": 1},
                        "pool_size": {"type": "integer", "minimum": 1, "maximum": 100},
                        "max_overflow": {"type": "integer", "minimum": 0},
                        "pool_timeout": {"type": "integer", "minimum": 1},
                        "echo": {"type": "boolean"}
                    },
                    "required": ["url"]
                },
                "redis": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "minLength": 1},
                        "max_connections": {"type": "integer", "minimum": 1},
                        "timeout": {"type": "integer", "minimum": 1}
                    },
                    "required": ["url"]
                },
                "security": {
                    "type": "object",
                    "properties": {
                        "enable_authentication": {"type": "boolean"},
                        "enable_authorization": {"type": "boolean"},
                        "jwt_secret": {"type": ["string", "null"]},
                        "jwt_algorithm": {"type": "string"},
                        "jwt_expiration": {"type": "integer", "minimum": 1},
                        "cors": {
                            "type": "object",
                            "properties": {
                                "enabled": {"type": "boolean"},
                                "origins": {"type": "array", "items": {"type": "string"}},
                                "methods": {"type": "array", "items": {"type": "string"}}
                            }
                        }
                    }
                },
                "monitoring": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "prometheus": {
                            "type": "object",
                            "properties": {
                                "enabled": {"type": "boolean"},
                                "port": {"type": "integer", "minimum": 1, "maximum": 65535}
                            }
                        },
                        "jaeger": {
                            "type": "object",
                            "properties": {
                                "enabled": {"type": "boolean"},
                                "agent_host": {"type": "string"},
                                "agent_port": {"type": "integer", "minimum": 1, "maximum": 65535}
                            }
                        }
                    }
                }
            },
            "required": ["app", "server"]
        }

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate configuration against schema

        Args:
            config: Configuration dictionary to validate

        Returns:
            Dict containing validation results

        Example:
            validator = ConfigurationValidator()
            result = validator.validate_config(my_config)
            if result['is_valid']:
                print("Configuration is valid")
            else:
                print(f"Errors: {result['errors']}")
        """

        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": []
        }

        try:
            validate(instance=config, schema=self.config_schema)
        except ValidationError as e:
            validation_result["is_valid"] = False
            validation_result["errors"].append({
                "path": list(e.absolute_path),
                "message": e.message,
                "invalid_value": e.instance
            })

        # Additional custom validations
        custom_errors = self._custom_validations(config)
        validation_result["errors"].extend(custom_errors)

        if custom_errors:
            validation_result["is_valid"] = False

        return validation_result

    def _custom_validations(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Perform custom validation logic"""

        errors = []

        # Validate SSL configuration
        server_config = config.get("server", {})
        if server_config.get("ssl_enabled", False):
            if not server_config.get("ssl_cert_file") or not server_config.get("ssl_key_file"):
                errors.append({
                    "path": ["server", "ssl"],
                    "message": "SSL enabled but certificate or key file not specified",
                    "invalid_value": None
                })

        # Validate production security requirements
        app_config = config.get("app", {})
        if app_config.get("environment") == "production":
            security_config = config.get("security", {})

            if not security_config.get("enable_authentication", False):
                errors.append({
                    "path": ["security", "enable_authentication"],
                    "message": "Authentication must be enabled in production",
                    "invalid_value": False
                })

            if not security_config.get("jwt_secret"):
                errors.append({
                    "path": ["security", "jwt_secret"],
                    "message": "JWT secret is required in production",
                    "invalid_value": None
                })

        # Validate database connection parameters
        db_config = config.get("database", {})
        if db_config.get("pool_size", 0) > db_config.get("max_overflow", 0) + 10:
            errors.append({
                "path": ["database"],
                "message": "Pool size should not be much larger than max_overflow",
                "invalid_value": None
            })

        return errors

# Configuration validation example
validator = ConfigurationValidator()

# Valid configuration
valid_config = {
    "app": {
        "name": "nexus-app",
        "version": "1.0.0",
        "environment": "development"
    },
    "server": {
        "host": "localhost",
        "port": 8000,
        "workers": 4
    },
    "database": {
        "url": "postgresql://user:pass@localhost/db"
    },
    "redis": {
        "url": "redis://localhost:6379/0"
    }
}

# Validate configuration
validation_result = validator.validate_config(valid_config)
print(f"Configuration valid: {validation_result['is_valid']}")
if not validation_result['is_valid']:
    print(f"Errors: {validation_result['errors']}")

# Invalid configuration example
invalid_config = {
    "app": {
        "name": "",  # Invalid: empty name
        "version": "1.0",  # Invalid: wrong version format
        "environment": "production"
    },
    "server": {
        "host": "localhost",
        "port": 70000,  # Invalid: port out of range
        "ssl_enabled": True
        # Missing ssl_cert_file and ssl_key_file
    }
}

invalid_result = validator.validate_config(invalid_config)
print(f"Invalid config result: {invalid_result['is_valid']}")
print(f"Errors found: {len(invalid_result['errors'])}")
```

This configuration reference provides comprehensive coverage of all Nexus configuration options, from basic development settings to enterprise-grade security and monitoring configurations. All examples demonstrate real configuration patterns and validation approaches used in production deployments.
