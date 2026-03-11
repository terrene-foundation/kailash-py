# ADR-010: Enterprise Configuration System Design

## Status
**Accepted** - 2025-09-24

## Context

The current `KaizenConfig` system (BLOCKER-001) lacks enterprise-level configuration support, causing all advanced feature configurations to fail. This prevents signature programming, MCP integration, multi-agent coordination, and transparency features from being properly configured.

### Problem Statement
- Current `KaizenConfig` only supports basic parameters (debug, memory_enabled, optimization_enabled)
- No support for complex nested configuration objects required by enterprise features
- Missing validation for enterprise feature requirements and dependencies
- No environment-specific configuration management (dev/staging/prod)
- No configuration schema validation or type safety
- No integration with existing Kailash enterprise infrastructure

### Decision Drivers
1. **Comprehensive Feature Support**: All documented enterprise features configurable
2. **Type Safety**: Pydantic-based validation with clear error messages
3. **Environment Management**: Dev/staging/prod configuration patterns
4. **Backward Compatibility**: Existing configurations continue to work
5. **Enterprise Integration**: Leverage existing Kailash infrastructure
6. **Developer Experience**: Intuitive configuration with sensible defaults

### Constraints
- Must maintain backward compatibility with current `KaizenConfig`
- Cannot break existing framework initialization patterns
- Must support both dict-based and object-based configuration
- Need integration with existing Kailash security and monitoring systems
- Must handle configuration validation without performance impact

## Decision

Implement a comprehensive enterprise configuration system with four configuration layers:

### Layer 1: Core Configuration Schema
```python
# Modern Pydantic-based configuration
@dataclass
class KaizenConfig:
    # Core framework settings
    debug: bool = False
    environment: str = "development"  # development, staging, production

    # Feature toggles
    signature_programming_enabled: bool = True
    mcp_integration_enabled: bool = True
    multi_agent_enabled: bool = True
    transparency_enabled: bool = False
    memory_enabled: bool = False
    optimization_enabled: bool = False

    # Advanced feature configurations
    signature_config: SignatureProgrammingConfig = field(default_factory=SignatureProgrammingConfig)
    mcp_integration: MCPIntegrationConfig = field(default_factory=MCPIntegrationConfig)
    multi_agent_config: MultiAgentConfig = field(default_factory=MultiAgentConfig)
    transparency_config: TransparencyConfig = field(default_factory=TransparencyConfig)
    memory_config: MemoryConfig = field(default_factory=MemoryConfig)
    optimization_config: OptimizationConfig = field(default_factory=OptimizationConfig)

    # Enterprise settings
    security_config: SecurityConfig = field(default_factory=SecurityConfig)
    monitoring_config: MonitoringConfig = field(default_factory=MonitoringConfig)
    performance_config: PerformanceConfig = field(default_factory=PerformanceConfig)

# Feature-specific configuration classes
@dataclass
class SignatureProgrammingConfig:
    compilation_cache_enabled: bool = True
    auto_prompt_optimization: bool = True
    validation_mode: str = "strict"  # strict, lenient, disabled
    max_signature_complexity: int = 100

@dataclass
class MCPIntegrationConfig:
    auto_discover: bool = True
    registry_url: str = "https://mcp-registry.kailash.io"
    max_connections: int = 10
    connection_timeout: int = 30
    security_policy: str = "standard"  # basic, standard, enterprise
```

### Layer 2: Environment-Specific Configuration
```python
# Environment-specific configuration loading
class ConfigurationManager:
    def load_config(self, environment: str = None) -> KaizenConfig:
        env = environment or os.getenv("KAIZEN_ENV", "development")

        # Load base configuration
        base_config = self._load_base_config()

        # Load environment-specific overrides
        env_config = self._load_environment_config(env)

        # Merge configurations with validation
        merged_config = self._merge_configurations(base_config, env_config)

        # Validate final configuration
        return self._validate_configuration(merged_config)

# Configuration file support
# kaizen.development.yaml
kaizen:
  debug: true
  signature_programming_enabled: true
  mcp_integration:
    auto_discover: true
    registry_url: "http://localhost:8080"
  security_config:
    encryption_enabled: false
    audit_logging: false

# kaizen.production.yaml
kaizen:
  debug: false
  transparency_enabled: true
  mcp_integration:
    security_policy: "enterprise"
    registry_url: "https://mcp-registry.company.com"
  security_config:
    encryption_enabled: true
    audit_logging: true
    compliance_mode: "SOX"
```

### Layer 3: Dynamic Configuration Management
```python
# Runtime configuration updates
config_manager = kaizen.get_config_manager()

# Update configuration at runtime
config_manager.update_config({
    "optimization_enabled": True,
    "optimization_config": {
        "auto_optimize_prompts": True,
        "optimization_interval": 3600
    }
})

# Feature flag management
feature_flags = kaizen.get_feature_flags()
if feature_flags.is_enabled("advanced_mcp_discovery"):
    # Use advanced MCP discovery
    agent.enable_advanced_mcp_discovery()

# Configuration validation and hot-reload
config_manager.enable_hot_reload()
config_manager.on_config_change(lambda config: kaizen.reload_configuration(config))
```

### Layer 4: Enterprise Integration
```python
# Integration with existing Kailash infrastructure
enterprise_config = KaizenConfig(
    environment="production",
    security_config=SecurityConfig(
        auth_provider="kailash_sso",
        encryption_key_source="kailash_vault",
        audit_target="kailash_audit_service"
    ),
    monitoring_config=MonitoringConfig(
        metrics_endpoint="kailash_metrics",
        alerting_service="kailash_alerts",
        dashboard_integration=True
    ),
    performance_config=PerformanceConfig(
        resource_limits=ResourceLimits.from_kailash_policy(),
        scaling_policy="kailash_autoscale"
    )
)
```

## Consequences

### Positive
- **Comprehensive Support**: All enterprise features properly configurable
- **Type Safety**: Pydantic validation prevents configuration errors
- **Environment Management**: Clean dev/staging/prod configuration separation
- **Enterprise Integration**: Leverages existing Kailash infrastructure
- **Developer Experience**: Sensible defaults with easy customization
- **Backward Compatibility**: Existing code continues to work

### Negative
- **Configuration Complexity**: Enterprise configurations can become complex
- **Validation Overhead**: Type validation adds initialization time
- **Learning Curve**: Developers need to understand new configuration schema
- **File Management**: Multiple configuration files require careful management

### Risks
- **Configuration Drift**: Different environments may have inconsistent configurations
- **Security Exposure**: Misconfigured security settings may create vulnerabilities
- **Performance Impact**: Complex validation may slow framework initialization
- **Dependency Complexity**: Enterprise integrations may create tight coupling

## Alternatives Considered

### Option 1: Simple Dict-Based Configuration
- **Pros**: Minimal changes, easy to understand, flexible
- **Cons**: No type safety, no validation, poor enterprise features
- **Why Rejected**: Insufficient for enterprise requirements, error-prone

### Option 2: YAML/JSON Configuration Files Only
- **Pros**: External configuration, environment management, version control
- **Cons**: No programmatic configuration, poor Python integration
- **Why Rejected**: Doesn't meet programmatic configuration needs

### Option 3: Separate Configuration Service
- **Pros**: Centralized configuration, hot updates, enterprise features
- **Cons**: Additional infrastructure, network dependencies, complexity
- **Why Rejected**: Overengineered for framework-level configuration

### Option 4: Dataclass-Only Configuration
- **Pros**: Type safety, Python native, good IDE support
- **Cons**: Limited validation, no file-based configuration, static
- **Why Rejected**: Insufficient flexibility for enterprise deployment

## Implementation Plan

### Phase 1: Core Configuration Schema (Week 1)
```python
# Enhanced KaizenConfig with full enterprise support
@dataclass
class KaizenConfig:
    # Basic settings (backward compatibility)
    debug: bool = False
    memory_enabled: bool = False
    optimization_enabled: bool = False

    # New enterprise settings
    environment: str = field(default="development")
    signature_programming_enabled: bool = field(default=True)
    mcp_integration_enabled: bool = field(default=True)
    multi_agent_enabled: bool = field(default=True)
    transparency_enabled: bool = field(default=False)

    # Complex configurations
    mcp_integration: MCPIntegrationConfig = field(default_factory=MCPIntegrationConfig)
    security_config: SecurityConfig = field(default_factory=SecurityConfig)
    monitoring_config: MonitoringConfig = field(default_factory=MonitoringConfig)

    def __post_init__(self):
        # Validate configuration dependencies
        self._validate_dependencies()
        # Apply environment-specific defaults
        self._apply_environment_defaults()

# Feature-specific configuration classes
@dataclass
class MCPIntegrationConfig:
    auto_discover: bool = True
    registry_url: str = "https://mcp-registry.kailash.io"
    max_connections: int = 10
    connection_timeout: int = 30
    security_policy: str = "standard"
    session_management: bool = True

    def validate(self) -> List[str]:
        errors = []
        if self.max_connections < 1:
            errors.append("max_connections must be positive")
        if self.connection_timeout < 1:
            errors.append("connection_timeout must be positive")
        return errors

@dataclass
class SecurityConfig:
    encryption_enabled: bool = False
    audit_logging: bool = False
    auth_provider: str = "local"
    access_control: str = "basic"  # basic, rbac, enterprise
    compliance_mode: Optional[str] = None  # SOX, HIPAA, GDPR

    def validate(self) -> List[str]:
        errors = []
        valid_auth_providers = ["local", "oauth2", "saml", "kailash_sso"]
        if self.auth_provider not in valid_auth_providers:
            errors.append(f"auth_provider must be one of {valid_auth_providers}")
        return errors
```

### Phase 2: Configuration Loading and Validation (Week 2)
```python
# Configuration manager with file support
class ConfigurationManager:
    def __init__(self):
        self.config_cache = {}
        self.file_watchers = {}

    def load_config(self, config_source: Union[Dict, str, Path, KaizenConfig] = None) -> KaizenConfig:
        if isinstance(config_source, KaizenConfig):
            return config_source
        elif isinstance(config_source, dict):
            return self._create_config_from_dict(config_source)
        elif isinstance(config_source, (str, Path)):
            return self._load_config_from_file(config_source)
        else:
            return self._load_default_config()

    def _load_config_from_file(self, config_path: Path) -> KaizenConfig:
        if config_path.suffix == '.yaml':
            data = yaml.safe_load(config_path.read_text())
        elif config_path.suffix == '.json':
            data = json.loads(config_path.read_text())
        else:
            raise ValueError(f"Unsupported config file format: {config_path.suffix}")

        return self._create_config_from_dict(data.get('kaizen', data))

    def _create_config_from_dict(self, config_dict: Dict) -> KaizenConfig:
        # Handle nested configuration objects
        processed_dict = self._process_nested_configs(config_dict)

        try:
            config = KaizenConfig(**processed_dict)
            self._validate_config(config)
            return config
        except Exception as e:
            raise ConfigurationError(f"Invalid configuration: {e}")

    def _validate_config(self, config: KaizenConfig):
        # Validate feature dependencies
        if config.transparency_enabled and not config.monitoring_config.enabled:
            raise ConfigurationError("Transparency requires monitoring to be enabled")

        if config.mcp_integration_enabled and config.mcp_integration.security_policy == "enterprise":
            if not config.security_config.encryption_enabled:
                raise ConfigurationError("Enterprise MCP policy requires encryption")

        # Validate environment-specific requirements
        if config.environment == "production":
            if not config.security_config.audit_logging:
                warnings.warn("Production environment should enable audit logging")
```

### Phase 3: Runtime Configuration Management (Week 3)
```python
# Hot-reload and dynamic configuration
class DynamicConfigurationManager:
    def __init__(self, kaizen_instance):
        self.kaizen = kaizen_instance
        self.current_config = kaizen_instance.config
        self.change_listeners = []

    def update_config(self, updates: Dict[str, Any]) -> bool:
        try:
            # Create new config with updates
            current_dict = asdict(self.current_config)
            updated_dict = self._deep_merge(current_dict, updates)
            new_config = KaizenConfig(**updated_dict)

            # Validate new configuration
            self._validate_config(new_config)

            # Apply configuration changes
            self._apply_config_changes(self.current_config, new_config)

            # Update current configuration
            self.current_config = new_config
            self.kaizen._config = new_config

            # Notify listeners
            self._notify_config_change(new_config)

            return True
        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            return False

    def _apply_config_changes(self, old_config: KaizenConfig, new_config: KaizenConfig):
        # Apply changes that require component reconfiguration
        if old_config.mcp_integration != new_config.mcp_integration:
            self.kaizen._reconfigure_mcp_integration(new_config.mcp_integration)

        if old_config.security_config != new_config.security_config:
            self.kaizen._reconfigure_security(new_config.security_config)

        if old_config.monitoring_config != new_config.monitoring_config:
            self.kaizen._reconfigure_monitoring(new_config.monitoring_config)

# Feature flag management
class FeatureFlagManager:
    def __init__(self, config: KaizenConfig):
        self.config = config
        self.flags = self._extract_feature_flags(config)

    def is_enabled(self, feature: str) -> bool:
        return self.flags.get(feature, False)

    def enable_feature(self, feature: str):
        self.flags[feature] = True

    def disable_feature(self, feature: str):
        self.flags[feature] = False

    def _extract_feature_flags(self, config: KaizenConfig) -> Dict[str, bool]:
        return {
            "signature_programming": config.signature_programming_enabled,
            "mcp_integration": config.mcp_integration_enabled,
            "multi_agent": config.multi_agent_enabled,
            "transparency": config.transparency_enabled,
            "memory": config.memory_enabled,
            "optimization": config.optimization_enabled,
            "advanced_mcp_discovery": config.mcp_integration.auto_discover,
            "audit_logging": config.security_config.audit_logging,
        }
```

### Phase 4: Enterprise Integration (Week 4)
```python
# Enterprise configuration integration
class EnterpriseConfigurationProvider:
    def __init__(self, kailash_infrastructure):
        self.kailash = kailash_infrastructure

    def create_enterprise_config(self) -> KaizenConfig:
        # Load configuration from Kailash infrastructure
        base_config = self._load_kailash_base_config()

        return KaizenConfig(
            environment="production",
            debug=False,
            transparency_enabled=True,

            security_config=SecurityConfig(
                encryption_enabled=True,
                audit_logging=True,
                auth_provider="kailash_sso",
                access_control="rbac",
                compliance_mode=base_config.compliance_requirements
            ),

            monitoring_config=MonitoringConfig(
                enabled=True,
                metrics_endpoint=base_config.metrics_service,
                alerting_service=base_config.alert_service,
                performance_tracking=True,
                cost_tracking=True
            ),

            mcp_integration=MCPIntegrationConfig(
                registry_url=base_config.internal_mcp_registry,
                security_policy="enterprise",
                session_management=True,
                connection_pooling=True
            ),

            performance_config=PerformanceConfig(
                resource_limits=base_config.compute_limits,
                auto_scaling=True,
                cost_optimization=True
            )
        )

    def integrate_with_kailash_services(self, config: KaizenConfig) -> KaizenConfig:
        # Update configuration to use Kailash services
        if config.security_config.auth_provider == "kailash_sso":
            config.security_config.auth_endpoint = self.kailash.sso_endpoint
            config.security_config.auth_keys = self.kailash.get_auth_keys()

        if config.monitoring_config.enabled:
            config.monitoring_config.metrics_client = self.kailash.metrics_client
            config.monitoring_config.alert_client = self.kailash.alert_client

        return config
```

## Implementation Guidance

### Core Components

#### 1. Enhanced KaizenConfig
```python
@dataclass
class KaizenConfig:
    """Comprehensive configuration for Kaizen framework with enterprise features."""

    # Core settings (backward compatibility)
    debug: bool = False
    memory_enabled: bool = False
    optimization_enabled: bool = False

    # Environment and feature toggles
    environment: str = "development"
    signature_programming_enabled: bool = True
    mcp_integration_enabled: bool = True
    multi_agent_enabled: bool = True
    transparency_enabled: bool = False

    # Feature-specific configurations
    signature_config: SignatureProgrammingConfig = field(default_factory=SignatureProgrammingConfig)
    mcp_integration: MCPIntegrationConfig = field(default_factory=MCPIntegrationConfig)
    multi_agent_config: MultiAgentConfig = field(default_factory=MultiAgentConfig)
    transparency_config: TransparencyConfig = field(default_factory=TransparencyConfig)
    memory_config: MemoryConfig = field(default_factory=MemoryConfig)
    optimization_config: OptimizationConfig = field(default_factory=OptimizationConfig)

    # Enterprise configurations
    security_config: SecurityConfig = field(default_factory=SecurityConfig)
    monitoring_config: MonitoringConfig = field(default_factory=MonitoringConfig)
    performance_config: PerformanceConfig = field(default_factory=PerformanceConfig)

    def __post_init__(self):
        """Post-initialization validation and environment setup."""
        self._validate_dependencies()
        self._apply_environment_defaults()
        self._setup_integrations()

    def _validate_dependencies(self):
        """Validate configuration dependencies and constraints."""
        errors = []

        # Transparency requires monitoring
        if self.transparency_enabled and not self.monitoring_config.enabled:
            errors.append("Transparency requires monitoring to be enabled")

        # Enterprise MCP requires security
        if (self.mcp_integration_enabled and
            self.mcp_integration.security_policy == "enterprise" and
            not self.security_config.encryption_enabled):
            errors.append("Enterprise MCP policy requires encryption")

        # Production environment requirements
        if self.environment == "production":
            if not self.security_config.audit_logging:
                warnings.warn("Production environment should enable audit logging")

        if errors:
            raise ConfigurationError(f"Configuration validation failed: {'; '.join(errors)}")

    def _apply_environment_defaults(self):
        """Apply environment-specific default configurations."""
        if self.environment == "production":
            # Production defaults
            self.debug = False
            self.security_config.encryption_enabled = True
            self.security_config.audit_logging = True
            self.monitoring_config.enabled = True

        elif self.environment == "development":
            # Development defaults
            self.debug = True
            self.security_config.encryption_enabled = False
            self.mcp_integration.registry_url = "http://localhost:8080"

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'KaizenConfig':
        """Create configuration from dictionary with nested object handling."""
        processed_dict = cls._process_nested_configs(config_dict)
        return cls(**processed_dict)

    @classmethod
    def from_file(cls, config_path: Union[str, Path]) -> 'KaizenConfig':
        """Load configuration from YAML or JSON file."""
        path = Path(config_path)

        if path.suffix == '.yaml' or path.suffix == '.yml':
            import yaml
            data = yaml.safe_load(path.read_text())
        elif path.suffix == '.json':
            import json
            data = json.loads(path.read_text())
        else:
            raise ValueError(f"Unsupported config file format: {path.suffix}")

        # Handle nested structure (kaizen: {...})
        config_data = data.get('kaizen', data)
        return cls.from_dict(config_data)

    @staticmethod
    def _process_nested_configs(config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Process nested configuration dictionaries into proper objects."""
        processed = config_dict.copy()

        # Process nested configuration objects
        config_mappings = {
            'signature_config': SignatureProgrammingConfig,
            'mcp_integration': MCPIntegrationConfig,
            'multi_agent_config': MultiAgentConfig,
            'transparency_config': TransparencyConfig,
            'memory_config': MemoryConfig,
            'optimization_config': OptimizationConfig,
            'security_config': SecurityConfig,
            'monitoring_config': MonitoringConfig,
            'performance_config': PerformanceConfig,
        }

        for key, config_class in config_mappings.items():
            if key in processed and isinstance(processed[key], dict):
                processed[key] = config_class(**processed[key])

        return processed
```

#### 2. Feature-Specific Configuration Classes
```python
@dataclass
class SignatureProgrammingConfig:
    compilation_cache_enabled: bool = True
    auto_prompt_optimization: bool = True
    validation_mode: str = "strict"  # strict, lenient, disabled
    max_signature_complexity: int = 100
    prompt_optimization_interval: int = 3600  # seconds

    def __post_init__(self):
        if self.validation_mode not in ["strict", "lenient", "disabled"]:
            raise ValueError("validation_mode must be 'strict', 'lenient', or 'disabled'")

@dataclass
class MCPIntegrationConfig:
    auto_discover: bool = True
    registry_url: str = "https://mcp-registry.kailash.io"
    max_connections: int = 10
    connection_timeout: int = 30
    security_policy: str = "standard"  # basic, standard, enterprise
    session_management: bool = True
    connection_pooling: bool = True
    cache_tool_results: bool = True

    def __post_init__(self):
        if self.security_policy not in ["basic", "standard", "enterprise"]:
            raise ValueError("security_policy must be 'basic', 'standard', or 'enterprise'")

@dataclass
class SecurityConfig:
    encryption_enabled: bool = False
    audit_logging: bool = False
    auth_provider: str = "local"  # local, oauth2, saml, kailash_sso
    access_control: str = "basic"  # basic, rbac, enterprise
    compliance_mode: Optional[str] = None  # SOX, HIPAA, GDPR
    rate_limiting: bool = True
    session_timeout: int = 3600  # seconds

    def __post_init__(self):
        valid_auth_providers = ["local", "oauth2", "saml", "kailash_sso"]
        if self.auth_provider not in valid_auth_providers:
            raise ValueError(f"auth_provider must be one of {valid_auth_providers}")

@dataclass
class MonitoringConfig:
    enabled: bool = False
    metrics_endpoint: Optional[str] = None
    alerting_service: Optional[str] = None
    performance_tracking: bool = True
    cost_tracking: bool = False
    dashboard_integration: bool = False
    log_level: str = "INFO"
```

### Usage Patterns

#### 1. Simple Configuration (Backward Compatible)
```python
# Basic configuration (existing pattern)
kaizen = Kaizen()  # Uses defaults

# Dict-based configuration (existing pattern)
kaizen = Kaizen(config={
    'debug': True,
    'memory_enabled': True
})

# New enterprise features with dict
kaizen = Kaizen(config={
    'signature_programming_enabled': True,
    'mcp_integration': {
        'auto_discover': True,
        'registry_url': 'http://localhost:8080'
    },
    'security_config': {
        'audit_logging': True
    }
})
```

#### 2. Object-Based Configuration
```python
# Object-based configuration
config = KaizenConfig(
    environment="production",
    signature_programming_enabled=True,
    mcp_integration=MCPIntegrationConfig(
        auto_discover=True,
        security_policy="enterprise"
    ),
    security_config=SecurityConfig(
        encryption_enabled=True,
        audit_logging=True,
        auth_provider="kailash_sso"
    )
)
kaizen = Kaizen(config=config)
```

#### 3. File-Based Configuration
```python
# YAML configuration file
config = KaizenConfig.from_file("kaizen.production.yaml")
kaizen = Kaizen(config=config)

# Environment-specific loading
env = os.getenv("KAIZEN_ENV", "development")
config = KaizenConfig.from_file(f"config/kaizen.{env}.yaml")
kaizen = Kaizen(config=config)
```

#### 4. Dynamic Configuration Updates
```python
# Runtime configuration updates
config_manager = kaizen.get_config_manager()
config_manager.update_config({
    "optimization_enabled": True,
    "optimization_config": {
        "auto_optimize_prompts": True
    }
})

# Feature flag management
if kaizen.feature_flags.is_enabled("advanced_analytics"):
    # Use advanced analytics features
    pass
```

This enterprise configuration system provides comprehensive support for all advanced features while maintaining backward compatibility and offering intuitive configuration patterns for different deployment scenarios.
