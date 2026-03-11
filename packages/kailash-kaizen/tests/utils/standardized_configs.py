"""
Standardized Configuration Patterns for Kaizen Test Suite

This module provides unified configuration patterns, validation, and management
across all three test tiers, ensuring consistency and eliminating duplication.

Key Features:
- Standardized timeout values per tier
- Unified error handling patterns
- Centralized test data management
- Consistent mock strategies for unit tests
- Performance optimization patterns
"""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

try:
    from kaizen.core.config import KaizenConfig

    KAIZEN_AVAILABLE = True
except ImportError:
    KAIZEN_AVAILABLE = False

try:
    import sys

    sys.path.append("./repos/projects/kailash_python_sdk/tests/utils")
    from docker_config import DATABASE_CONFIG, MYSQL_CONFIG, OLLAMA_CONFIG, REDIS_CONFIG

    INFRASTRUCTURE_AVAILABLE = True
except ImportError:
    INFRASTRUCTURE_AVAILABLE = False


class ConfigurationTier(Enum):
    """Configuration tier with specific requirements."""

    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"


@dataclass
class StandardTimeout:
    """Standardized timeout configuration for all test operations."""

    # Core tier limits (milliseconds)
    unit_test_max_ms: int = 1000
    integration_test_max_ms: int = 5000
    e2e_test_max_ms: int = 10000

    # Framework operations
    framework_init_ms: int = 100
    agent_creation_ms: int = 200
    signature_creation_ms: int = 10
    workflow_compilation_ms: int = 200

    # Infrastructure operations
    database_connection_ms: int = 500
    redis_operation_ms: int = 50
    ollama_model_load_ms: int = 2000

    # Execution operations
    simple_execution_ms: int = 1000
    complex_execution_ms: int = 5000
    multi_agent_coordination_ms: int = 8000

    def get_tier_limit(self, tier: ConfigurationTier) -> int:
        """Get the maximum allowed time for a tier."""
        limits = {
            ConfigurationTier.UNIT: self.unit_test_max_ms,
            ConfigurationTier.INTEGRATION: self.integration_test_max_ms,
            ConfigurationTier.E2E: self.e2e_test_max_ms,
        }
        return limits[tier]

    def to_seconds(self) -> "StandardTimeout":
        """Convert all timeouts to seconds for easier use."""
        seconds_config = StandardTimeout()
        for field_name in asdict(self).keys():
            ms_value = getattr(self, field_name)
            if isinstance(ms_value, int):
                setattr(
                    seconds_config,
                    field_name.replace("_ms", "_seconds"),
                    ms_value / 1000,
                )
        return seconds_config


@dataclass
class StandardMemoryLimits:
    """Standardized memory limits for test tiers."""

    unit_test_mb: int = 50
    integration_test_mb: int = 200
    e2e_test_mb: int = 500

    # Component-specific limits
    framework_init_mb: int = 20
    agent_instance_mb: int = 10
    workflow_execution_mb: int = 100
    database_connection_pool_mb: int = 50

    def get_tier_limit(self, tier: ConfigurationTier) -> int:
        """Get memory limit for specific tier."""
        limits = {
            ConfigurationTier.UNIT: self.unit_test_mb,
            ConfigurationTier.INTEGRATION: self.integration_test_mb,
            ConfigurationTier.E2E: self.e2e_test_mb,
        }
        return limits[tier]


@dataclass
class StandardAgentConfig:
    """Standardized agent configuration template."""

    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 1000
    timeout_seconds: int = 30
    retry_attempts: int = 3
    stream: bool = False

    # Tier-specific optimizations
    tier_optimizations: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: {
            "unit": {
                "timeout_seconds": 5,
                "max_tokens": 100,
                "retry_attempts": 1,
                "stream": False,
                "enable_caching": False,
            },
            "integration": {
                "timeout_seconds": 15,
                "max_tokens": 500,
                "retry_attempts": 2,
                "stream": False,
                "enable_caching": True,
            },
            "e2e": {
                "timeout_seconds": 30,
                "max_tokens": 2000,
                "retry_attempts": 3,
                "stream": False,
                "enable_caching": True,
                "enable_monitoring": True,
            },
        }
    )

    def for_tier(self, tier: ConfigurationTier) -> Dict[str, Any]:
        """Get agent config optimized for specific tier."""
        base_config = asdict(self)
        base_config.pop("tier_optimizations", None)

        tier_opts = self.tier_optimizations.get(tier.value, {})
        base_config.update(tier_opts)

        return base_config


@dataclass
class StandardKaizenConfig:
    """Standardized Kaizen configuration template."""

    debug: bool = True
    signature_validation: bool = True

    # Tier-specific configurations
    tier_configs: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: {
            "unit": {
                "memory_enabled": False,
                "optimization_enabled": False,
                "monitoring_enabled": False,
                "cache_enabled": False,
                "startup_timeout_seconds": 1,
                "max_concurrent_operations": 1,
                "lazy_loading": True,
            },
            "integration": {
                "memory_enabled": True,
                "optimization_enabled": True,
                "monitoring_enabled": True,
                "cache_enabled": True,
                "startup_timeout_seconds": 5,
                "max_concurrent_operations": 3,
                "retry_attempts": 2,
                "health_check_interval_seconds": 10,
            },
            "e2e": {
                "memory_enabled": True,
                "optimization_enabled": True,
                "monitoring_enabled": True,
                "cache_enabled": True,
                "audit_trail_enabled": True,
                "compliance_mode": "enterprise",
                "security_level": "high",
                "multi_agent_enabled": True,
                "startup_timeout_seconds": 10,
                "max_concurrent_operations": 5,
                "retry_attempts": 3,
                "enable_distributed_processing": True,
            },
        }
    )

    def for_tier(self, tier: ConfigurationTier) -> Dict[str, Any]:
        """Get Kaizen config for specific tier."""
        base_config = {
            "debug": self.debug,
            "signature_validation": self.signature_validation,
        }

        tier_config = self.tier_configs.get(tier.value, {})
        base_config.update(tier_config)

        return base_config

    def to_kaizen_config(self, tier: ConfigurationTier) -> Optional["KaizenConfig"]:
        """Convert to actual KaizenConfig instance if available."""
        if not KAIZEN_AVAILABLE:
            return None

        config_dict = self.for_tier(tier)
        return KaizenConfig(**config_dict)


@dataclass
class StandardTestData:
    """Standardized test data patterns."""

    # Simple test inputs
    simple_prompts: List[str] = field(
        default_factory=lambda: [
            "Hello, how are you?",
            "What is 2 + 2?",
            "Explain photosynthesis briefly.",
            "Generate a haiku about testing.",
        ]
    )

    # Complex test scenarios
    complex_scenarios: Dict[str, Any] = field(
        default_factory=lambda: {
            "data_analysis": {
                "input": {"data": [1, 2, 3, 4, 5], "operation": "statistics"},
                "expected_outputs": ["mean", "median", "std_dev"],
            },
            "multi_step_workflow": {
                "input": {"steps": ["validate", "transform", "analyze", "report"]},
                "expected_outputs": [
                    "validation_result",
                    "transformed_data",
                    "analysis",
                    "report",
                ],
            },
        }
    )

    # Error test cases
    error_scenarios: Dict[str, Any] = field(
        default_factory=lambda: {
            "invalid_input": {"input": None, "expected_error": "ValueError"},
            "timeout_scenario": {
                "input": {"delay": 10},
                "expected_error": "TimeoutError",
            },
            "resource_exhaustion": {
                "input": {"size": 10**9},
                "expected_error": "MemoryError",
            },
        }
    )

    # Mock responses for unit tests
    mock_responses: Dict[str, Any] = field(
        default_factory=lambda: {
            "simple_qa": {
                "answer": "This is a mock response for testing",
                "confidence": 0.95,
                "metadata": {"model": "mock", "tokens": 10},
            },
            "analysis_result": {
                "analysis": {"findings": ["test finding 1", "test finding 2"]},
                "recommendations": ["recommendation 1", "recommendation 2"],
                "confidence": 0.87,
            },
        }
    )

    def get_tier_appropriate_data(self, tier: ConfigurationTier) -> Dict[str, Any]:
        """Get test data appropriate for tier."""
        if tier == ConfigurationTier.UNIT:
            return {
                "prompts": self.simple_prompts[:2],  # Fewer for speed
                "mock_responses": self.mock_responses,
                "allow_mocking": True,
            }
        elif tier == ConfigurationTier.INTEGRATION:
            return {
                "prompts": self.simple_prompts,
                "scenarios": {
                    k: v
                    for k, v in self.complex_scenarios.items()
                    if "simple" in k.lower()
                },
                "allow_mocking": False,
            }
        else:  # E2E
            return {
                "prompts": self.simple_prompts,
                "scenarios": self.complex_scenarios,
                "error_scenarios": self.error_scenarios,
                "allow_mocking": False,
            }


class StandardConfigurationManager:
    """Manages standardized configurations across test tiers."""

    def __init__(self):
        self.timeouts = StandardTimeout()
        self.memory_limits = StandardMemoryLimits()
        self.agent_config = StandardAgentConfig()
        self.kaizen_config = StandardKaizenConfig()
        self.test_data = StandardTestData()

    def get_tier_configuration(self, tier: ConfigurationTier) -> Dict[str, Any]:
        """Get complete configuration for a specific tier."""
        return {
            "tier": tier.value,
            "timeouts": {
                "max_test_time_ms": self.timeouts.get_tier_limit(tier),
                "framework_init_ms": self.timeouts.framework_init_ms,
                "agent_creation_ms": self.timeouts.agent_creation_ms,
                "database_connection_ms": self.timeouts.database_connection_ms,
            },
            "memory_limits": {
                "max_memory_mb": self.memory_limits.get_tier_limit(tier),
                "framework_init_mb": self.memory_limits.framework_init_mb,
            },
            "agent_config": self.agent_config.for_tier(tier),
            "kaizen_config": self.kaizen_config.for_tier(tier),
            "test_data": self.test_data.get_tier_appropriate_data(tier),
            "infrastructure_requirements": self._get_infrastructure_requirements(tier),
        }

    def _get_infrastructure_requirements(
        self, tier: ConfigurationTier
    ) -> Dict[str, Any]:
        """Get infrastructure requirements for tier."""
        requirements = {
            ConfigurationTier.UNIT: {
                "required_services": [],
                "optional_services": [],
                "allow_mocking": True,
            },
            ConfigurationTier.INTEGRATION: {
                "required_services": ["postgres", "redis"],
                "optional_services": ["mysql", "ollama"],
                "allow_mocking": False,
            },
            ConfigurationTier.E2E: {
                "required_services": ["postgres", "redis"],
                "optional_services": ["mysql", "ollama"],
                "allow_mocking": False,
            },
        }

        base_req = requirements[tier]

        if INFRASTRUCTURE_AVAILABLE:
            base_req["infrastructure_config"] = {
                "database": DATABASE_CONFIG,
                "redis": REDIS_CONFIG,
                "mysql": MYSQL_CONFIG,
                "ollama": OLLAMA_CONFIG,
            }

        return base_req

    def validate_tier_configuration(self, tier: ConfigurationTier) -> List[str]:
        """Validate configuration for a tier and return any issues."""
        issues = []
        config = self.get_tier_configuration(tier)

        # Validate timeouts
        max_time = config["timeouts"]["max_test_time_ms"]
        if max_time <= 0:
            issues.append(f"Invalid max test time: {max_time}")

        # Validate memory limits
        max_memory = config["memory_limits"]["max_memory_mb"]
        if max_memory <= 0:
            issues.append(f"Invalid max memory: {max_memory}")

        # Validate agent config
        agent_config = config["agent_config"]
        if not agent_config.get("model"):
            issues.append("Missing model in agent config")

        temperature = agent_config.get("temperature", 0)
        if not (0 <= temperature <= 2):
            issues.append(f"Invalid temperature: {temperature}")

        # Validate infrastructure for non-unit tests
        if tier != ConfigurationTier.UNIT:
            infra = config["infrastructure_requirements"]
            if not INFRASTRUCTURE_AVAILABLE:
                issues.append(
                    "Infrastructure configuration not available for integration/e2e tests"
                )

            for service in infra.get("required_services", []):
                # This would need actual service checks, but we'll keep it simple
                pass

        return issues

    def export_configuration(
        self, tier: ConfigurationTier, file_path: Optional[str] = None
    ) -> str:
        """Export tier configuration to JSON format."""
        config = self.get_tier_configuration(tier)
        json_content = json.dumps(config, indent=2, default=str)

        if file_path:
            Path(file_path).write_text(json_content)

        return json_content

    def get_pytest_markers(self, tier: ConfigurationTier) -> List[str]:
        """Get appropriate pytest markers for tier."""
        markers = [tier.value]

        if tier == ConfigurationTier.UNIT:
            markers.extend(["fast", "isolated"])
        elif tier == ConfigurationTier.INTEGRATION:
            markers.extend(
                ["requires_docker", "requires_postgres", "requires_redis", "no_mocking"]
            )
        elif tier == ConfigurationTier.E2E:
            markers.extend(
                [
                    "requires_docker",
                    "requires_postgres",
                    "requires_redis",
                    "no_mocking",
                    "slow",
                ]
            )

        return markers

    def get_performance_assertions(
        self, tier: ConfigurationTier
    ) -> Dict[str, Callable]:
        """Get performance assertion functions for tier."""
        max_time_ms = self.timeouts.get_tier_limit(tier)

        def assert_tier_performance(duration_ms: float, operation: str = "operation"):
            assert duration_ms <= max_time_ms, (
                f"Tier {tier.value} {operation} took {duration_ms:.2f}ms, "
                f"exceeding {tier.value} limit of {max_time_ms}ms"
            )

        def assert_memory_usage(memory_mb: float):
            max_memory = self.memory_limits.get_tier_limit(tier)
            assert memory_mb <= max_memory, (
                f"Tier {tier.value} used {memory_mb:.2f}MB, "
                f"exceeding {tier.value} limit of {max_memory}MB"
            )

        return {
            "assert_performance": assert_tier_performance,
            "assert_memory": assert_memory_usage,
        }


# Global instance for easy access
standard_config = StandardConfigurationManager()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_tier_config(tier: Union[str, ConfigurationTier]) -> Dict[str, Any]:
    """Get configuration for a tier (convenience function)."""
    if isinstance(tier, str):
        tier = ConfigurationTier(tier)
    return standard_config.get_tier_configuration(tier)


def validate_tier_setup(tier: Union[str, ConfigurationTier]) -> bool:
    """Validate that tier setup is correct."""
    if isinstance(tier, str):
        tier = ConfigurationTier(tier)

    issues = standard_config.validate_tier_configuration(tier)
    if issues:
        print(f"Tier {tier.value} validation issues:")
        for issue in issues:
            print(f"  - {issue}")
        return False

    return True


def get_standardized_timeouts() -> StandardTimeout:
    """Get standardized timeout configuration."""
    return standard_config.timeouts


def get_standardized_memory_limits() -> StandardMemoryLimits:
    """Get standardized memory limit configuration."""
    return standard_config.memory_limits


# Export main classes and functions
__all__ = [
    "ConfigurationTier",
    "StandardTimeout",
    "StandardMemoryLimits",
    "StandardAgentConfig",
    "StandardKaizenConfig",
    "StandardTestData",
    "StandardConfigurationManager",
    "standard_config",
    "get_tier_config",
    "validate_tier_setup",
    "get_standardized_timeouts",
    "get_standardized_memory_limits",
]
