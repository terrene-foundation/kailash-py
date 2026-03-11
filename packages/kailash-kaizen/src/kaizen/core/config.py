"""
PERFORMANCE OPTIMIZED Core interfaces and base classes for the Kaizen framework.

This is a streamlined version of base.py that removes heavy imports to achieve
<100ms import performance as required for production deployment.

Heavy imports (AINodeBase, Node dependencies) moved to separate module.
"""

import json
import os

import yaml

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Fallback for Python < 3.11
    except ImportError:
        tomllib = None
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# PERFORMANCE OPTIMIZATION: Lazy import Pydantic to avoid 1.8s import delay
def _lazy_import_pydantic():
    """Lazy import Pydantic components when needed."""
    from pydantic import BaseModel, Field

    return BaseModel, Field


@dataclass
class BaseAgentConfig:
    """
    Base configuration for individual Kaizen agents.

    This is a simplified configuration focused on agent-specific settings
    rather than framework-wide settings. Domain-specific configs can be
    auto-converted to this format.
    """

    # LLM Configuration
    llm_provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = 0.1  # Default to 0.1 for deterministic responses
    max_tokens: Optional[int] = None
    provider_config: Optional[Dict[str, Any]] = None

    # Async LLM Configuration (for production FastAPI/async workflows)
    use_async_llm: bool = False  # Enable AsyncOpenAI client for non-blocking operations

    # Strategy Configuration
    strategy_type: str = "single_shot"  # "single_shot" or "multi_cycle"
    max_cycles: int = 5  # For multi_cycle strategy

    # Framework Features
    signature_programming_enabled: bool = True
    optimization_enabled: bool = True
    monitoring_enabled: bool = True

    # Feature Flags (Mixins)
    logging_enabled: bool = True
    performance_enabled: bool = True
    error_handling_enabled: bool = True
    batch_processing_enabled: bool = False
    memory_enabled: bool = False
    transparency_enabled: bool = False
    mcp_enabled: bool = False

    # Permission System Configuration (Week 5-6: BaseAgent Integration)
    permission_mode: "PermissionMode" = (
        None  # Type hint as string to avoid circular import
    )
    budget_limit_usd: Optional[float] = None  # Maximum budget in USD (None = unlimited)
    allowed_tools: set = field(default_factory=set)  # Explicitly allowed tools
    denied_tools: set = field(default_factory=set)  # Explicitly denied tools
    permission_rules: List = field(default_factory=list)  # List[PermissionRule]

    # Hooks System Configuration (Phase 3A: Hooks Integration)
    hooks_enabled: bool = False  # Opt-in: Enable hooks system
    hook_timeout: float = 5.0  # Timeout per hook execution (seconds)
    builtin_hooks: List[str] = field(default_factory=list)  # Built-in hooks to enable
    hooks_directory: Optional[str] = (
        None  # Directory for filesystem hooks (.kaizen/hooks/)
    )

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Set default permission_mode if not specified
        if self.permission_mode is None:
            # Import here to avoid circular dependency
            from kaizen.core.autonomy.permissions.types import PermissionMode

            self.permission_mode = PermissionMode.DEFAULT

        self._validate_parameters()

    def _validate_parameters(self):
        """Validate configuration parameters."""
        # Validate temperature
        if self.temperature is not None:
            if self.temperature < 0.0:
                raise ValueError("temperature must be >= 0.0")
            if self.temperature > 2.0:
                raise ValueError("temperature must be <= 2.0")

        # Validate max_tokens
        if self.max_tokens is not None:
            if self.max_tokens <= 0:
                raise ValueError("max_tokens must be positive")

        # Validate strategy_type
        valid_strategies = ["single_shot", "multi_cycle"]
        if self.strategy_type not in valid_strategies:
            raise ValueError(
                f"strategy_type must be one of {valid_strategies}, got '{self.strategy_type}'"
            )

        # Validate max_cycles
        if self.max_cycles <= 0:
            raise ValueError("max_cycles must be positive")

        # Validate use_async_llm parameter
        if not isinstance(self.use_async_llm, bool):
            raise TypeError("use_async_llm must be a boolean")

        # Validate async configuration compatibility
        if self.use_async_llm and self.llm_provider not in [None, "openai"]:
            raise ValueError(
                f"Async mode only supported for OpenAI provider, got: {self.llm_provider}"
            )

    @classmethod
    def from_domain_config(cls, config: Any) -> "BaseAgentConfig":
        """
        Auto-convert domain-specific config to BaseAgentConfig.

        Extracts common fields (llm_provider, model, temperature, max_tokens, provider_config)
        and creates BaseAgentConfig instance.

        Args:
            config: Domain-specific config object (dataclass or dict)

        Returns:
            BaseAgentConfig: Converted configuration

        Example:
            >>> @dataclass
            >>> class QAConfig:
            ...     llm_provider: str = "openai"
            ...     model: str = "gpt-4"
            ...     temperature: float = 0.7
            >>>
            >>> qa_config = QAConfig()
            >>> base_config = BaseAgentConfig.from_domain_config(qa_config)
        """
        # Handle dict input
        if isinstance(config, dict):
            return cls(
                llm_provider=config.get("llm_provider"),
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                provider_config=config.get("provider_config"),
                use_async_llm=config.get("use_async_llm", False),
                strategy_type=config.get("strategy_type", "single_shot"),
                max_cycles=config.get("max_cycles", 5),
            )

        # Handle dataclass or object input
        # Only pass values that exist on the config to preserve defaults
        kwargs = {}

        # Core LLM config - only set if present on domain config
        if hasattr(config, "llm_provider"):
            kwargs["llm_provider"] = getattr(config, "llm_provider")
        if hasattr(config, "model"):
            kwargs["model"] = getattr(config, "model")
        if hasattr(config, "temperature"):
            kwargs["temperature"] = getattr(config, "temperature")
        if hasattr(config, "max_tokens"):
            kwargs["max_tokens"] = getattr(config, "max_tokens")
        if hasattr(config, "provider_config"):
            kwargs["provider_config"] = getattr(config, "provider_config")

        # Async config
        if hasattr(config, "use_async_llm"):
            kwargs["use_async_llm"] = getattr(config, "use_async_llm")

        # Strategy config
        if hasattr(config, "strategy_type"):
            kwargs["strategy_type"] = getattr(config, "strategy_type")
        if hasattr(config, "max_cycles"):
            kwargs["max_cycles"] = getattr(config, "max_cycles")

        # Feature flags - only set if present to preserve defaults
        feature_flags = [
            "signature_programming_enabled",
            "optimization_enabled",
            "monitoring_enabled",
            "logging_enabled",
            "performance_enabled",
            "error_handling_enabled",
            "batch_processing_enabled",
            "memory_enabled",
            "transparency_enabled",
            "mcp_enabled",
        ]
        for flag in feature_flags:
            if hasattr(config, flag):
                kwargs[flag] = getattr(config, flag)

        return cls(**kwargs)


@dataclass
class KaizenConfig:
    """
    Configuration for Kaizen framework initialization.

    Supports comprehensive enterprise features including signature programming,
    MCP integration, multi-agent coordination, transparency, and compliance.
    """

    # Core configuration
    debug: bool = False
    memory_enabled: bool = False
    optimization_enabled: bool = False

    # Security settings
    security_config: Dict[str, Any] = field(default_factory=dict)
    encryption_key: Optional[str] = None

    # Performance settings
    monitoring_enabled: bool = False
    monitoring_level: str = "basic"  # basic, detailed, comprehensive
    cache_enabled: bool = True
    cache_ttl: int = 3600

    # Advanced features
    multi_modal_enabled: bool = True
    signature_validation: bool = True
    auto_optimization: bool = False

    # ENTERPRISE FEATURES - Master Control
    enterprise_features_enabled: bool = (
        False  # Master toggle for all enterprise features
    )

    # ENTERPRISE FEATURES - Signature Programming
    signature_programming_enabled: bool = False
    signature_validation_strict: bool = False
    signature_auto_optimization: bool = False
    signature_auto_generation: bool = False

    # ENTERPRISE FEATURES - MCP Integration
    mcp_enabled: bool = False
    mcp_auto_discovery: bool = False
    mcp_discovery_timeout: int = 30
    mcp_integration: Dict[str, Any] = field(
        default_factory=dict
    )  # Complex MCP configuration

    # ENTERPRISE FEATURES - Multi-Agent Coordination
    multi_agent_enabled: bool = False
    coordination_patterns: List[str] = field(
        default_factory=lambda: ["consensus", "debate", "hierarchical"]
    )

    # ENTERPRISE FEATURES - Transparency & Compliance
    transparency_enabled: bool = False
    audit_trail_enabled: bool = False
    compliance_mode: str = "standard"  # standard, enterprise, strict

    # ENTERPRISE FEATURES - Security
    security_level: str = "standard"  # standard, high, maximum
    encryption_enabled: bool = False
    multi_tenant: bool = False

    def __post_init__(self):
        """Post-initialization validation."""
        self._validate_parameters()

    def _validate_parameters(self):
        """Validate configuration parameters."""
        # Validate compliance mode
        valid_compliance = ["standard", "enterprise", "strict"]
        if self.compliance_mode not in valid_compliance:
            raise ValueError(
                f"Invalid compliance_mode: {self.compliance_mode}. Must be one of {valid_compliance}"
            )

        # Validate security level
        valid_security = ["standard", "high", "maximum"]
        if self.security_level not in valid_security:
            raise ValueError(
                f"Invalid security_level: {self.security_level}. Must be one of {valid_security}"
            )

        # Validate monitoring level (Fixed: use 'verbose' not 'comprehensive')
        valid_monitoring = ["basic", "detailed", "verbose"]
        if self.monitoring_level not in valid_monitoring:
            raise ValueError(
                f"Invalid monitoring_level '{self.monitoring_level}'. Must be one of: {valid_monitoring}"
            )

        # Validate MCP integration parameter type
        if self.mcp_integration is not None and not isinstance(
            self.mcp_integration, dict
        ):
            raise TypeError("mcp_integration must be a dict")

        # Validate boolean parameters (Required by tests)
        bool_params = [
            "signature_programming_enabled",
            "signature_validation_strict",
            "signature_auto_generation",
            "signature_auto_optimization",
            "multi_agent_enabled",
            "transparency_enabled",
            "audit_trail_enabled",
            "memory_enabled",
            "optimization_enabled",
            "mcp_enabled",
            "mcp_auto_discovery",
            "encryption_enabled",
            "multi_tenant",
        ]

        for param in bool_params:
            value = getattr(self, param)
            if not isinstance(value, bool):
                raise TypeError(f"{param} must be a boolean")

        # Auto-enable encryption for high security
        if self.security_level in ["high", "maximum"] and not self.encryption_enabled:
            self.encryption_enabled = True

        # Auto-enable audit trail for enterprise compliance
        if (
            self.compliance_mode in ["enterprise", "strict"]
            and not self.audit_trail_enabled
        ):
            self.audit_trail_enabled = True

        # Validate coordination patterns
        valid_patterns = [
            "consensus",
            "debate",
            "hierarchical",
            "collaborative",
            "competitive",
        ]
        invalid_patterns = [
            p for p in self.coordination_patterns if p not in valid_patterns
        ]
        if invalid_patterns:
            raise ValueError(f"Invalid coordination patterns: {invalid_patterns}")

        # Validate MCP timeout
        if self.mcp_discovery_timeout < 5 or self.mcp_discovery_timeout > 300:
            raise ValueError("mcp_discovery_timeout must be between 5 and 300 seconds")

        # Validate cache TTL
        if self.cache_ttl < 60 or self.cache_ttl > 86400:
            raise ValueError("cache_ttl must be between 60 and 86400 seconds")

        # CRITICAL RELATIONSHIP VALIDATIONS (Required by tests)
        if self.security_level == "high" and not self.audit_trail_enabled:
            raise ValueError("High security level requires audit trails to be enabled")

        if self.compliance_mode == "enterprise" and not self.transparency_enabled:
            raise ValueError(
                "Enterprise compliance requires transparency to be enabled"
            )

        # Enable debug for certain security levels
        if self.security_level == "maximum" and not self.debug:
            print("INFO: Debug logging auto-enabled for maximum security level")
            self.debug = True

    @classmethod
    def from_environment(cls, **explicit_kwargs):
        """
        Create configuration from environment variables.

        Args:
            **explicit_kwargs: Override specific parameters

        Returns:
            KaizenConfig: Configuration object

        Environment Variables:
            KAIZEN_DEBUG: Enable debug mode (true/false)
            KAIZEN_MEMORY_ENABLED: Enable memory systems (true/false)
            KAIZEN_OPTIMIZATION_ENABLED: Enable optimization (true/false)
            KAIZEN_SECURITY_LEVEL: Security level (standard/high/maximum)
            KAIZEN_COMPLIANCE_MODE: Compliance mode (standard/enterprise/strict)
            KAIZEN_ENCRYPTION_KEY: Encryption key for security
            KAIZEN_MULTI_TENANT: Enable multi-tenant mode (true/false)
            KAIZEN_MCP_ENABLED: Enable MCP integration (true/false)
            KAIZEN_SIGNATURE_PROGRAMMING: Enable signature programming (true/false)
        """
        env_config = {}

        # Map environment variables to config fields
        env_mapping = {
            "KAIZEN_DEBUG": ("debug", cls._parse_bool),
            "KAIZEN_MEMORY_ENABLED": ("memory_enabled", cls._parse_bool),
            "KAIZEN_OPTIMIZATION_ENABLED": ("optimization_enabled", cls._parse_bool),
            "KAIZEN_SECURITY_LEVEL": ("security_level", str),
            "KAIZEN_COMPLIANCE_MODE": ("compliance_mode", str),
            "KAIZEN_ENCRYPTION_KEY": ("encryption_key", str),
            "KAIZEN_MULTI_TENANT": ("multi_tenant", cls._parse_bool),
            "KAIZEN_MCP_ENABLED": ("mcp_enabled", cls._parse_bool),
            "KAIZEN_MCP_INTEGRATION_ENABLED": ("mcp_enabled", cls._parse_bool),
            "KAIZEN_SIGNATURE_PROGRAMMING": (
                "signature_programming_enabled",
                cls._parse_bool,
            ),
            "KAIZEN_SIGNATURE_PROGRAMMING_ENABLED": (
                "signature_programming_enabled",
                cls._parse_bool,
            ),
            "KAIZEN_MONITORING_ENABLED": ("monitoring_enabled", cls._parse_bool),
            "KAIZEN_MONITORING_LEVEL": ("monitoring_level", str),
            "KAIZEN_CACHE_ENABLED": ("cache_enabled", cls._parse_bool),
            "KAIZEN_CACHE_TTL": ("cache_ttl", int),
            "KAIZEN_MCP_DISCOVERY_TIMEOUT": ("mcp_discovery_timeout", int),
            "KAIZEN_TRANSPARENCY_ENABLED": ("transparency_enabled", cls._parse_bool),
            "KAIZEN_AUDIT_TRAIL_ENABLED": ("audit_trail_enabled", cls._parse_bool),
            "KAIZEN_ENCRYPTION_ENABLED": ("encryption_enabled", cls._parse_bool),
            "KAIZEN_MULTI_AGENT_ENABLED": ("multi_agent_enabled", cls._parse_bool),
            "KAIZEN_MCP_AUTO_DISCOVERY": ("mcp_auto_discovery", cls._parse_bool),
            "KAIZEN_SIGNATURE_VALIDATION": ("signature_validation", cls._parse_bool),
            "KAIZEN_AUTO_OPTIMIZATION": ("auto_optimization", cls._parse_bool),
            "KAIZEN_MULTI_MODAL_ENABLED": ("multi_modal_enabled", cls._parse_bool),
        }

        for env_var, (field_name, converter) in env_mapping.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                try:
                    env_config[field_name] = converter(env_value)
                except (ValueError, TypeError) as e:
                    raise ValueError(
                        f"Invalid value for {env_var}: {env_value}. Error: {e}"
                    )

        # Handle coordination patterns (comma-separated list)
        coordination_patterns_env = os.getenv("KAIZEN_COORDINATION_PATTERNS")
        if coordination_patterns_env:
            env_config["coordination_patterns"] = [
                p.strip() for p in coordination_patterns_env.split(",")
            ]

        # Override with explicit kwargs
        env_config.update(explicit_kwargs)

        return cls(**env_config)

    @classmethod
    def from_file(cls, file_path: str):
        """
        Load configuration from a YAML or JSON file.

        Args:
            file_path: Path to configuration file

        Returns:
            KaizenConfig: Configuration object

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        if file_path.endswith(".toml"):
            if tomllib is None:
                raise ImportError(
                    "TOML support requires 'tomli' package. Install with: pip install tomli"
                )
            with open(file_path, "rb") as f:
                config_dict = tomllib.load(f)
        else:
            with open(file_path, "r") as f:
                if file_path.endswith(".yaml") or file_path.endswith(".yml"):
                    config_dict = yaml.safe_load(f)
                elif file_path.endswith(".json"):
                    config_dict = json.load(f)
                else:
                    raise ValueError(
                        "Configuration file must be .yaml, .yml, .json, or .toml"
                    )

        return cls.from_dict(config_dict)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]):
        """
        Create configuration from dictionary.

        Args:
            config_dict: Configuration dictionary

        Returns:
            KaizenConfig: Configuration object
        """
        # Filter out unknown keys
        from dataclasses import fields

        valid_keys = {f.name for f in fields(cls)}
        filtered_config = {k: v for k, v in config_dict.items() if k in valid_keys}

        return cls(**filtered_config)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary representation of configuration
        """
        from dataclasses import asdict

        return asdict(self)

    def save(self, file_path: str):
        """
        Save configuration to file.

        Args:
            file_path: Output file path (.yaml, .yml, or .json)

        Raises:
            ValueError: If file extension is not supported
        """
        config_dict = self.to_dict()

        if file_path.endswith(".toml"):
            if tomllib is None:
                raise ImportError(
                    "TOML support requires 'tomli' package for reading and 'tomli-w' for writing. Install with: pip install tomli tomli-w"
                )
            try:
                import tomli_w

                with open(file_path, "wb") as f:
                    tomli_w.dump(config_dict, f)
            except ImportError:
                raise ImportError(
                    "TOML writing requires 'tomli-w' package. Install with: pip install tomli-w"
                )
        else:
            with open(file_path, "w") as f:
                if file_path.endswith(".yaml") or file_path.endswith(".yml"):
                    yaml.safe_dump(config_dict, f, default_flow_style=False)
                elif file_path.endswith(".json"):
                    json.dump(config_dict, f, indent=2)
                else:
                    raise ValueError(
                        "File must have .yaml, .yml, .json, or .toml extension"
                    )

    @classmethod
    def load(cls, file_path: str):
        """
        Load configuration from file (alias for from_file).

        Args:
            file_path: Configuration file path

        Returns:
            KaizenConfig: Configuration object
        """
        return cls.from_file(file_path)

    @staticmethod
    def _parse_bool(value: str) -> bool:
        """Parse boolean value from string."""
        if isinstance(value, bool):
            return value
        return value.lower() in ("true", "1", "yes", "on", "enabled")


# NOTE: SignatureBase removed - use kaizen.signatures.Signature (Option 3: DSPy-inspired)
# For class-based signatures with InputField/OutputField, import from: kaizen.signatures

# NOTE: AINodeBase removed from this optimized version
# For AINodeBase functionality, import from: kaizen.nodes.base_advanced
# This prevents heavy Kailash Node imports that cause 964ms startup time


class ConfigurationManager:
    """
    Global configuration manager for Kaizen framework.

    Implements configuration precedence system and provides convenient
    configuration methods for the entire application.
    """

    def __init__(self):
        self._global_config = {}
        self._env_config = {}
        self._file_config = {}
        self._precedence_order = [
            "file",
            "env",
            "global",
            "explicit",
        ]  # lowest to highest priority

    def configure(self, **kwargs):
        """
        Set global configuration parameters.

        Args:
            **kwargs: Configuration parameters

        Examples:
            >>> kaizen.configure(
            ...     signature_programming_enabled=True,
            ...     mcp_integration_enabled=True,
            ...     transparency_enabled=True
            ... )
        """
        self._global_config.update(kwargs)

    def load_from_env(self, prefix: str = "KAIZEN_"):
        """
        Load configuration from environment variables.

        Args:
            prefix: Environment variable prefix

        Returns:
            Dict of loaded configuration
        """
        env_config = {}

        # Map environment variables to config fields
        env_mapping = {
            f"{prefix}DEBUG": ("debug", self._parse_bool),
            f"{prefix}MEMORY_ENABLED": ("memory_enabled", self._parse_bool),
            f"{prefix}OPTIMIZATION_ENABLED": ("optimization_enabled", self._parse_bool),
            f"{prefix}SECURITY_LEVEL": ("security_level", str),
            f"{prefix}COMPLIANCE_MODE": ("compliance_mode", str),
            f"{prefix}ENCRYPTION_KEY": ("encryption_key", str),
            f"{prefix}MULTI_TENANT": ("multi_tenant", self._parse_bool),
            f"{prefix}MCP_ENABLED": ("mcp_enabled", self._parse_bool),
            f"{prefix}SIGNATURE_PROGRAMMING_ENABLED": (
                "signature_programming_enabled",
                self._parse_bool,
            ),
            f"{prefix}MONITORING_ENABLED": ("monitoring_enabled", self._parse_bool),
            f"{prefix}MONITORING_LEVEL": ("monitoring_level", str),
            f"{prefix}CACHE_ENABLED": ("cache_enabled", self._parse_bool),
            f"{prefix}CACHE_TTL": ("cache_ttl", int),
            f"{prefix}MCP_DISCOVERY_TIMEOUT": ("mcp_discovery_timeout", int),
            f"{prefix}TRANSPARENCY_ENABLED": ("transparency_enabled", self._parse_bool),
            f"{prefix}AUDIT_TRAIL_ENABLED": ("audit_trail_enabled", self._parse_bool),
            f"{prefix}ENCRYPTION_ENABLED": ("encryption_enabled", self._parse_bool),
            f"{prefix}MULTI_AGENT_ENABLED": ("multi_agent_enabled", self._parse_bool),
            f"{prefix}MCP_AUTO_DISCOVERY": ("mcp_auto_discovery", self._parse_bool),
            f"{prefix}SIGNATURE_VALIDATION": ("signature_validation", self._parse_bool),
            f"{prefix}AUTO_OPTIMIZATION": ("auto_optimization", self._parse_bool),
            f"{prefix}MULTI_MODAL_ENABLED": ("multi_modal_enabled", self._parse_bool),
        }

        for env_var, (field_name, converter) in env_mapping.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                try:
                    env_config[field_name] = converter(env_value)
                except (ValueError, TypeError) as e:
                    raise ValueError(
                        f"Invalid value for {env_var}: {env_value}. Error: {e}"
                    )

        # Handle coordination patterns (comma-separated list)
        coordination_patterns_env = os.getenv(f"{prefix}COORDINATION_PATTERNS")
        if coordination_patterns_env:
            env_config["coordination_patterns"] = [
                p.strip() for p in coordination_patterns_env.split(",")
            ]

        self._env_config = env_config
        return env_config

    def load_from_file(self, file_path: str):
        """
        Load configuration from file.

        Args:
            file_path: Path to configuration file

        Returns:
            Dict of loaded configuration
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        if file_path.endswith(".toml"):
            if tomllib is None:
                raise ImportError(
                    "TOML support requires 'tomli' package. Install with: pip install tomli"
                )
            with open(file_path, "rb") as f:
                config_dict = tomllib.load(f)
        else:
            with open(file_path, "r") as f:
                if file_path.endswith(".yaml") or file_path.endswith(".yml"):
                    config_dict = yaml.safe_load(f)
                elif file_path.endswith(".json"):
                    config_dict = json.load(f)
                else:
                    raise ValueError(
                        "Configuration file must be .yaml, .yml, .json, or .toml"
                    )

        self._file_config = config_dict
        return config_dict

    def auto_discover_config_files(self, search_paths: Optional[List[str]] = None):
        """
        Auto-discover and load configuration files.

        Args:
            search_paths: Paths to search for config files

        Returns:
            Path of loaded config file or None
        """
        if search_paths is None:
            search_paths = [
                ".",
                os.path.expanduser("~/.config/kaizen"),
                os.path.expanduser("~/.kaizen"),
                "/etc/kaizen",
            ]

        config_filenames = ["kaizen.toml", "kaizen.yaml", "kaizen.yml", "kaizen.json"]

        for search_path in search_paths:
            for filename in config_filenames:
                file_path = os.path.join(search_path, filename)
                if os.path.exists(file_path):
                    try:
                        self.load_from_file(file_path)
                        return file_path
                    except Exception:
                        continue  # Try next file

        return None

    def resolve_config(
        self, explicit_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Resolve final configuration with precedence.

        Precedence order (lowest to highest):
        1. File configuration
        2. Environment variables
        3. Global configuration (kaizen.configure())
        4. Explicit parameters

        Args:
            explicit_config: Explicitly provided configuration

        Returns:
            Final resolved configuration dict
        """
        final_config = {}

        # Apply in precedence order
        final_config.update(self._file_config)  # Lowest priority
        final_config.update(self._env_config)
        final_config.update(self._global_config)
        if explicit_config:
            final_config.update(explicit_config)  # Highest priority

        return final_config

    def create_kaizen_config(
        self, explicit_config: Optional[Dict[str, Any]] = None
    ) -> KaizenConfig:
        """
        Create KaizenConfig with resolved configuration.

        Args:
            explicit_config: Explicitly provided configuration

        Returns:
            KaizenConfig instance with resolved configuration
        """
        resolved = self.resolve_config(explicit_config)
        return KaizenConfig.from_dict(resolved)

    def clear(self):
        """Clear all configuration."""
        self._global_config.clear()
        self._env_config.clear()
        self._file_config.clear()

    @staticmethod
    def _parse_bool(value: str) -> bool:
        """Parse boolean value from string."""
        if isinstance(value, bool):
            return value
        return value.lower() in ("true", "1", "yes", "on", "enabled")


# Global configuration manager instance
_global_config_manager = ConfigurationManager()


class MemoryProvider(ABC):
    """
    Base interface for memory systems in AI workflows.

    Provides persistent storage and retrieval capabilities for AI agents,
    supporting various backends and query patterns.
    """

    @abstractmethod
    def store(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None):
        """
        Store a value with optional metadata.

        Args:
            key: Unique identifier
            value: Value to store
            metadata: Optional metadata dictionary
        """
        pass

    @abstractmethod
    def retrieve(self, key: str) -> Optional[Any]:
        """
        Retrieve a value by key.

        Args:
            key: Unique identifier

        Returns:
            Stored value or None if not found
        """
        pass

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[Any]:
        """
        Search stored values.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching values
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete a stored value.

        Args:
            key: Unique identifier

        Returns:
            True if deleted, False if not found
        """
        pass


class OptimizationEngine(ABC):
    """
    Base interface for AI workflow optimization engines.

    Provides automatic optimization of prompts, parameters, and workflow
    configurations based on performance feedback.
    """

    @abstractmethod
    def optimize_prompt(
        self,
        original_prompt: str,
        performance_data: Dict[str, Any],
        target_metrics: Dict[str, float],
    ) -> str:
        """
        Optimize a prompt based on performance data.

        Args:
            original_prompt: Original prompt text
            performance_data: Performance metrics
            target_metrics: Target performance metrics

        Returns:
            Optimized prompt
        """
        pass

    @abstractmethod
    def optimize_parameters(
        self, parameters: Dict[str, Any], performance_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Optimize workflow parameters.

        Args:
            parameters: Original parameters
            performance_data: Performance metrics

        Returns:
            Optimized parameters
        """
        pass

    @abstractmethod
    def suggest_improvements(self, workflow_data: Dict[str, Any]) -> List[str]:
        """
        Suggest workflow improvements.

        Args:
            workflow_data: Workflow configuration and performance data

        Returns:
            List of improvement suggestions
        """
        pass


class IntegrationPattern(ABC):
    """
    Base interface for framework integration patterns.

    Enables seamless integration with DataFlow, Nexus, and other
    Kailash SDK frameworks.
    """

    @abstractmethod
    def integrate_with_dataflow(self, dataflow_instance: Any) -> Dict[str, Any]:
        """
        Integrate with DataFlow framework.

        Args:
            dataflow_instance: DataFlow instance

        Returns:
            Integration configuration
        """
        pass

    @abstractmethod
    def integrate_with_nexus(self, nexus_instance: Any) -> Dict[str, Any]:
        """
        Integrate with Nexus platform.

        Args:
            nexus_instance: Nexus instance

        Returns:
            Integration configuration
        """
        pass
