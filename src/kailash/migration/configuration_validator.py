"""Configuration validator for LocalRuntime migration validation.

This module provides comprehensive validation of LocalRuntime configurations
to ensure they are correct, secure, and optimized for the target environment.
It validates parameters, detects conflicts, and provides optimization recommendations.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from kailash.runtime.local import LocalRuntime


class ValidationLevel(Enum):
    """Validation severity levels."""

    ERROR = "error"  # Configuration is invalid/dangerous
    WARNING = "warning"  # Configuration may cause issues
    INFO = "info"  # Informational/optimization suggestion
    DEBUG = "debug"  # Debug information


class ValidationCategory(Enum):
    """Categories of validation checks."""

    SYNTAX = "syntax"  # Basic syntax and type validation
    COMPATIBILITY = "compatibility"  # Parameter compatibility
    SECURITY = "security"  # Security-related validation
    PERFORMANCE = "performance"  # Performance optimization
    RESOURCE = "resource"  # Resource management
    ENTERPRISE = "enterprise"  # Enterprise features
    BEST_PRACTICE = "best_practice"  # Best practice recommendations


@dataclass
class ValidationIssue:
    """Represents a configuration validation issue."""

    level: ValidationLevel
    category: ValidationCategory
    parameter: str
    message: str
    suggestion: str
    auto_fixable: bool = False
    enterprise_feature: bool = False
    impact: str = "low"  # low, medium, high, critical


@dataclass
class ValidationResult:
    """Results of configuration validation."""

    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    optimized_config: Optional[Dict[str, Any]] = None
    security_score: int = 0  # 0-100
    performance_score: int = 0  # 0-100
    enterprise_readiness: int = 0  # 0-100


class ConfigurationValidator:
    """Comprehensive LocalRuntime configuration validator."""

    def __init__(self):
        """Initialize the configuration validator."""
        # Valid parameter definitions with types and constraints
        self.valid_parameters = {
            "debug": {"type": bool, "default": False},
            "enable_cycles": {"type": bool, "default": True},
            "enable_async": {"type": bool, "default": True},
            "max_concurrency": {"type": int, "min": 1, "max": 1000, "default": 10},
            "user_context": {"type": object, "optional": True},
            "enable_monitoring": {"type": bool, "default": True},
            "enable_security": {"type": bool, "default": False},
            "enable_audit": {"type": bool, "default": False},
            "resource_limits": {"type": dict, "optional": True},
            "secret_provider": {"type": object, "optional": True},
            "connection_validation": {
                "type": str,
                "values": ["strict", "warn", "disable"],
                "default": "warn",
            },
            "conditional_execution": {
                "type": str,
                "values": ["route_data", "skip_node"],
                "default": "route_data",
            },
            "content_aware_success_detection": {"type": bool, "default": True},
            "persistent_mode": {"type": bool, "default": False},
            "enable_connection_sharing": {"type": bool, "default": True},
            "max_concurrent_workflows": {
                "type": int,
                "min": 1,
                "max": 100,
                "default": 10,
            },
            "connection_pool_size": {"type": int, "min": 1, "max": 1000, "default": 20},
            "enable_enterprise_monitoring": {"type": bool, "default": False},
            "enable_health_monitoring": {"type": bool, "default": False},
            "enable_resource_coordination": {"type": bool, "default": True},
            "circuit_breaker_config": {"type": dict, "optional": True},
            "retry_policy_config": {"type": dict, "optional": True},
            "connection_pool_config": {"type": dict, "optional": True},
        }

        # Deprecated parameters
        self.deprecated_parameters = {
            "enable_parallel": "Use max_concurrency instead",
            "thread_pool_size": "Use max_concurrency instead",
            "memory_limit": "Use resource_limits parameter instead",
            "timeout": "Use resource_limits parameter instead",
            "log_level": "Use debug parameter or logging configuration",
            "cache_enabled": "Use enterprise caching nodes instead",
            "retry_count": "Use retry_policy_config parameter",
        }

        # Parameter dependencies
        self.parameter_dependencies = {
            "enable_security": ["user_context"],
            "enable_audit": ["enable_security"],
            "enable_enterprise_monitoring": ["enable_monitoring"],
            "persistent_mode": ["enable_connection_sharing"],
            "circuit_breaker_config": ["enable_resource_coordination"],
            "retry_policy_config": ["enable_resource_coordination"],
        }

        # Conflicting parameters
        self.parameter_conflicts = {
            ("debug", True): [
                ("enable_security", True)
            ],  # Debug mode conflicts with security
        }

        # Security validations
        self.security_validations = [
            self._validate_debug_security_conflict,
            self._validate_audit_requirements,
            self._validate_user_context_security,
            self._validate_connection_security,
        ]

        # Performance validations
        self.performance_validations = [
            self._validate_concurrency_settings,
            self._validate_resource_limits,
            self._validate_connection_pooling,
            self._validate_monitoring_overhead,
        ]

        # Enterprise validations
        self.enterprise_validations = [
            self._validate_enterprise_features,
            self._validate_monitoring_configuration,
            self._validate_resilience_configuration,
        ]

    def validate_configuration(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate a LocalRuntime configuration.

        Args:
            config: Configuration dictionary to validate

        Returns:
            Comprehensive validation results
        """
        result = ValidationResult(valid=True, issues=[])

        # Basic syntax validation
        self._validate_syntax(config, result)

        # Parameter validation
        self._validate_parameters(config, result)

        # Dependency validation
        self._validate_dependencies(config, result)

        # Conflict validation
        self._validate_conflicts(config, result)

        # Security validation
        for validator in self.security_validations:
            validator(config, result)

        # Performance validation
        for validator in self.performance_validations:
            validator(config, result)

        # Enterprise validation
        for validator in self.enterprise_validations:
            validator(config, result)

        # Generate optimized configuration
        result.optimized_config = self._generate_optimized_config(config, result)

        # Calculate scores
        self._calculate_scores(result)

        # Determine overall validity
        error_issues = [i for i in result.issues if i.level == ValidationLevel.ERROR]
        result.valid = len(error_issues) == 0

        return result

    def _validate_syntax(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate basic syntax and structure."""
        if not isinstance(config, dict):
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SYNTAX,
                    parameter="config",
                    message="Configuration must be a dictionary",
                    suggestion="Ensure configuration is passed as a dictionary",
                    impact="critical",
                )
            )
            return

        # Check for invalid parameter names
        for param_name in config.keys():
            if (
                param_name not in self.valid_parameters
                and param_name not in self.deprecated_parameters
            ):
                result.issues.append(
                    ValidationIssue(
                        level=ValidationLevel.WARNING,
                        category=ValidationCategory.SYNTAX,
                        parameter=param_name,
                        message=f"Unknown parameter '{param_name}'",
                        suggestion="Remove unknown parameter or check spelling",
                        impact="medium",
                    )
                )

    def _validate_parameters(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate individual parameters."""
        for param_name, param_value in config.items():
            # Check deprecated parameters
            if param_name in self.deprecated_parameters:
                result.issues.append(
                    ValidationIssue(
                        level=ValidationLevel.WARNING,
                        category=ValidationCategory.COMPATIBILITY,
                        parameter=param_name,
                        message=f"Parameter '{param_name}' is deprecated",
                        suggestion=self.deprecated_parameters[param_name],
                        auto_fixable=True,
                        impact="medium",
                    )
                )
                continue

            # Validate known parameters
            if param_name in self.valid_parameters:
                param_def = self.valid_parameters[param_name]

                # Type validation
                expected_type = param_def["type"]
                if expected_type != object and not isinstance(
                    param_value, expected_type
                ):
                    result.issues.append(
                        ValidationIssue(
                            level=ValidationLevel.ERROR,
                            category=ValidationCategory.SYNTAX,
                            parameter=param_name,
                            message=f"Parameter '{param_name}' must be of type {expected_type.__name__}, got {type(param_value).__name__}",
                            suggestion=f"Convert value to {expected_type.__name__}",
                            impact="high",
                        )
                    )

                # Range validation for integers
                if expected_type == int and isinstance(param_value, int):
                    if "min" in param_def and param_value < param_def["min"]:
                        result.issues.append(
                            ValidationIssue(
                                level=ValidationLevel.ERROR,
                                category=ValidationCategory.SYNTAX,
                                parameter=param_name,
                                message=f"Parameter '{param_name}' value {param_value} is below minimum {param_def['min']}",
                                suggestion=f"Set value to at least {param_def['min']}",
                                impact="high",
                            )
                        )

                    if "max" in param_def and param_value > param_def["max"]:
                        result.issues.append(
                            ValidationIssue(
                                level=ValidationLevel.WARNING,
                                category=ValidationCategory.PERFORMANCE,
                                parameter=param_name,
                                message=f"Parameter '{param_name}' value {param_value} is above recommended maximum {param_def['max']}",
                                suggestion=f"Consider reducing to {param_def['max']} or below",
                                impact="medium",
                            )
                        )

                # Value validation for strings with restricted values
                if "values" in param_def and param_value not in param_def["values"]:
                    result.issues.append(
                        ValidationIssue(
                            level=ValidationLevel.ERROR,
                            category=ValidationCategory.SYNTAX,
                            parameter=param_name,
                            message=f"Parameter '{param_name}' value '{param_value}' is not valid. Valid values: {param_def['values']}",
                            suggestion=f"Use one of: {', '.join(param_def['values'])}",
                            impact="high",
                        )
                    )

    def _validate_dependencies(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate parameter dependencies."""
        for param_name, dependencies in self.parameter_dependencies.items():
            if config.get(param_name):
                for dep_param in dependencies:
                    if not config.get(dep_param):
                        result.issues.append(
                            ValidationIssue(
                                level=ValidationLevel.WARNING,
                                category=ValidationCategory.COMPATIBILITY,
                                parameter=param_name,
                                message=f"Parameter '{param_name}' requires '{dep_param}' to be set",
                                suggestion=f"Set '{dep_param}' parameter or disable '{param_name}'",
                                impact="medium",
                            )
                        )

    def _validate_conflicts(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate parameter conflicts."""
        for conflict_param, conflict_conditions in self.parameter_conflicts.items():
            param_name, param_value = conflict_param

            if config.get(param_name) == param_value:
                for conflict_condition in conflict_conditions:
                    conflict_name, conflict_value = conflict_condition
                    if config.get(conflict_name) == conflict_value:
                        result.issues.append(
                            ValidationIssue(
                                level=ValidationLevel.WARNING,
                                category=ValidationCategory.SECURITY,
                                parameter=param_name,
                                message=f"Parameter '{param_name}={param_value}' conflicts with '{conflict_name}={conflict_value}'",
                                suggestion=f"Disable either '{param_name}' or '{conflict_name}' to resolve conflict",
                                impact="medium",
                            )
                        )

    def _validate_debug_security_conflict(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate debug and security configuration conflicts."""
        if config.get("debug") and config.get("enable_security"):
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category=ValidationCategory.SECURITY,
                    parameter="debug",
                    message="Debug mode enabled with security features may expose sensitive information",
                    suggestion="Disable debug mode in production or when security is enabled",
                    impact="high",
                )
            )

    def _validate_audit_requirements(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate audit logging requirements."""
        if config.get("enable_audit") and not config.get("enable_security"):
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SECURITY,
                    parameter="enable_audit",
                    message="Audit logging requires security features to be enabled",
                    suggestion="Enable security with 'enable_security=True'",
                    auto_fixable=True,
                    impact="high",
                )
            )

    def _validate_user_context_security(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate user context security configuration."""
        if config.get("user_context") and not config.get("enable_security"):
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.INFO,
                    category=ValidationCategory.SECURITY,
                    parameter="user_context",
                    message="User context provided but security features are disabled",
                    suggestion="Enable security with 'enable_security=True' to utilize user context",
                    enterprise_feature=True,
                    impact="low",
                )
            )

    def _validate_connection_security(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate connection security settings."""
        connection_validation = config.get("connection_validation", "warn")
        if connection_validation == "disable":
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category=ValidationCategory.SECURITY,
                    parameter="connection_validation",
                    message="Connection validation is disabled, which may allow invalid connections",
                    suggestion="Use 'warn' or 'strict' for better security",
                    impact="medium",
                )
            )

    def _validate_concurrency_settings(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate concurrency and performance settings."""
        max_concurrency = config.get("max_concurrency", 10)
        max_workflows = config.get("max_concurrent_workflows", 10)
        pool_size = config.get("connection_pool_size", 20)

        # Check for reasonable concurrency settings
        if max_concurrency > 50:
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category=ValidationCategory.PERFORMANCE,
                    parameter="max_concurrency",
                    message=f"High concurrency setting ({max_concurrency}) may cause resource contention",
                    suggestion="Consider reducing concurrency or increasing resource limits",
                    impact="medium",
                )
            )

        # Check workflow to concurrency ratio
        if max_workflows > max_concurrency * 5:
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.INFO,
                    category=ValidationCategory.PERFORMANCE,
                    parameter="max_concurrent_workflows",
                    message="High workflow concurrency relative to node concurrency",
                    suggestion="Consider increasing max_concurrency or reducing max_concurrent_workflows",
                    impact="low",
                )
            )

        # Check connection pool sizing
        if pool_size < max_concurrency:
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category=ValidationCategory.PERFORMANCE,
                    parameter="connection_pool_size",
                    message="Connection pool size is smaller than max concurrency",
                    suggestion=f"Increase connection_pool_size to at least {max_concurrency}",
                    auto_fixable=True,
                    impact="medium",
                )
            )

    def _validate_resource_limits(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate resource limit configurations."""
        resource_limits = config.get("resource_limits", {})

        if isinstance(resource_limits, dict):
            # Validate memory limits
            if "memory_mb" in resource_limits:
                memory_mb = resource_limits["memory_mb"]
                if memory_mb < 256:
                    result.issues.append(
                        ValidationIssue(
                            level=ValidationLevel.WARNING,
                            category=ValidationCategory.RESOURCE,
                            parameter="resource_limits.memory_mb",
                            message=f"Low memory limit ({memory_mb}MB) may cause performance issues",
                            suggestion="Consider increasing memory limit to at least 512MB",
                            impact="medium",
                        )
                    )

            # Validate timeout settings
            if "timeout_seconds" in resource_limits:
                timeout = resource_limits["timeout_seconds"]
                if timeout > 3600:  # 1 hour
                    result.issues.append(
                        ValidationIssue(
                            level=ValidationLevel.INFO,
                            category=ValidationCategory.RESOURCE,
                            parameter="resource_limits.timeout_seconds",
                            message=f"Very high timeout setting ({timeout}s)",
                            suggestion="Consider if such a long timeout is necessary",
                            impact="low",
                        )
                    )

    def _validate_connection_pooling(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate connection pooling configuration."""
        enable_sharing = config.get("enable_connection_sharing", True)
        persistent_mode = config.get("persistent_mode", False)

        if persistent_mode and not enable_sharing:
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category=ValidationCategory.PERFORMANCE,
                    parameter="enable_connection_sharing",
                    message="Persistent mode without connection sharing reduces efficiency",
                    suggestion="Enable connection sharing for better performance in persistent mode",
                    auto_fixable=True,
                    impact="medium",
                )
            )

    def _validate_monitoring_overhead(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate monitoring configuration for performance impact."""
        monitoring_features = [
            "enable_monitoring",
            "enable_enterprise_monitoring",
            "enable_health_monitoring",
        ]

        enabled_monitoring = [f for f in monitoring_features if config.get(f)]

        if len(enabled_monitoring) > 2:
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.INFO,
                    category=ValidationCategory.PERFORMANCE,
                    parameter="monitoring",
                    message="Multiple monitoring features enabled may impact performance",
                    suggestion="Consider enabling only necessary monitoring features for production",
                    impact="low",
                )
            )

    def _validate_enterprise_features(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate enterprise feature configurations."""
        enterprise_features = [
            "enable_security",
            "enable_audit",
            "enable_enterprise_monitoring",
            "enable_health_monitoring",
            "user_context",
        ]

        enabled_features = [f for f in enterprise_features if config.get(f)]

        if len(enabled_features) > 0:
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.INFO,
                    category=ValidationCategory.ENTERPRISE,
                    parameter="enterprise_features",
                    message=f"Enterprise features detected: {', '.join(enabled_features)}",
                    suggestion="Ensure enterprise license and proper configuration for production use",
                    enterprise_feature=True,
                    impact="low",
                )
            )

    def _validate_monitoring_configuration(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate monitoring configuration completeness."""
        if config.get("enable_enterprise_monitoring") and not config.get(
            "enable_monitoring"
        ):
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.ENTERPRISE,
                    parameter="enable_enterprise_monitoring",
                    message="Enterprise monitoring requires basic monitoring to be enabled",
                    suggestion="Enable basic monitoring with 'enable_monitoring=True'",
                    auto_fixable=True,
                    impact="high",
                )
            )

    def _validate_resilience_configuration(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate resilience and reliability configurations."""
        circuit_breaker = config.get("circuit_breaker_config")
        retry_policy = config.get("retry_policy_config")
        resource_coordination = config.get("enable_resource_coordination", True)

        if (circuit_breaker or retry_policy) and not resource_coordination:
            result.issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category=ValidationCategory.ENTERPRISE,
                    parameter="enable_resource_coordination",
                    message="Resilience features require resource coordination to be enabled",
                    suggestion="Enable resource coordination for circuit breaker and retry policies",
                    auto_fixable=True,
                    enterprise_feature=True,
                    impact="medium",
                )
            )

    def _generate_optimized_config(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> Dict[str, Any]:
        """Generate an optimized configuration based on validation results."""
        optimized = config.copy()

        # Apply auto-fixable improvements
        for issue in result.issues:
            if issue.auto_fixable:
                if issue.parameter == "connection_pool_size":
                    max_concurrency = config.get("max_concurrency", 10)
                    optimized["connection_pool_size"] = max(
                        optimized.get("connection_pool_size", 20), max_concurrency
                    )

                elif issue.parameter == "enable_monitoring" and config.get(
                    "enable_enterprise_monitoring"
                ):
                    optimized["enable_monitoring"] = True

                elif issue.parameter == "enable_security" and config.get(
                    "enable_audit"
                ):
                    optimized["enable_security"] = True

                elif issue.parameter == "enable_connection_sharing" and config.get(
                    "persistent_mode"
                ):
                    optimized["enable_connection_sharing"] = True

                elif issue.parameter == "enable_resource_coordination" and (
                    config.get("circuit_breaker_config")
                    or config.get("retry_policy_config")
                ):
                    optimized["enable_resource_coordination"] = True

        return optimized

    def _calculate_scores(self, result: ValidationResult) -> None:
        """Calculate security, performance, and enterprise readiness scores."""
        total_issues = len(result.issues)
        error_count = len(
            [i for i in result.issues if i.level == ValidationLevel.ERROR]
        )
        warning_count = len(
            [i for i in result.issues if i.level == ValidationLevel.WARNING]
        )

        # Security score (0-100)
        security_issues = [
            i for i in result.issues if i.category == ValidationCategory.SECURITY
        ]
        security_deduction = len(security_issues) * 10
        result.security_score = max(0, 100 - security_deduction)

        # Performance score (0-100)
        performance_issues = [
            i for i in result.issues if i.category == ValidationCategory.PERFORMANCE
        ]
        performance_deduction = len(performance_issues) * 15
        result.performance_score = max(0, 100 - performance_deduction)

        # Enterprise readiness score (0-100)
        enterprise_features = len([i for i in result.issues if i.enterprise_feature])
        enterprise_issues = [
            i
            for i in result.issues
            if i.category == ValidationCategory.ENTERPRISE
            and i.level in [ValidationLevel.ERROR, ValidationLevel.WARNING]
        ]

        base_score = 50 if enterprise_features > 0 else 20
        enterprise_deduction = len(enterprise_issues) * 20
        result.enterprise_readiness = max(
            0, base_score + (enterprise_features * 10) - enterprise_deduction
        )

    def generate_validation_report(
        self, result: ValidationResult, output_format: str = "text"
    ) -> str:
        """Generate a comprehensive validation report.

        Args:
            result: Validation results
            output_format: Report format ("text", "json", "markdown")

        Returns:
            Formatted validation report
        """
        if output_format == "json":
            return self._generate_json_report(result)
        elif output_format == "markdown":
            return self._generate_markdown_report(result)
        else:
            return self._generate_text_report(result)

    def _generate_text_report(self, result: ValidationResult) -> str:
        """Generate text format validation report."""
        lines = []
        lines.append("=" * 60)
        lines.append("LocalRuntime Configuration Validation Report")
        lines.append("=" * 60)
        lines.append("")

        # Summary
        lines.append("VALIDATION SUMMARY")
        lines.append("-" * 20)
        lines.append(f"Configuration Valid: {'Yes' if result.valid else 'No'}")
        lines.append(f"Total Issues: {len(result.issues)}")
        lines.append(f"Security Score: {result.security_score}/100")
        lines.append(f"Performance Score: {result.performance_score}/100")
        lines.append(f"Enterprise Readiness: {result.enterprise_readiness}/100")
        lines.append("")

        # Issues by level
        for level in ValidationLevel:
            level_issues = [i for i in result.issues if i.level == level]
            if level_issues:
                lines.append(f"{level.value.upper()} ISSUES ({len(level_issues)})")
                lines.append("-" * (len(level.value) + 15))

                for issue in level_issues:
                    lines.append(f"• {issue.message}")
                    lines.append(f"  Parameter: {issue.parameter}")
                    lines.append(f"  Category: {issue.category.value}")
                    lines.append(f"  Suggestion: {issue.suggestion}")
                    if issue.auto_fixable:
                        lines.append("  Auto-fixable: Yes")
                    lines.append("")

        return "\n".join(lines)

    def _generate_json_report(self, result: ValidationResult) -> str:
        """Generate JSON format validation report."""
        data = {
            "valid": result.valid,
            "scores": {
                "security": result.security_score,
                "performance": result.performance_score,
                "enterprise_readiness": result.enterprise_readiness,
            },
            "issues": [
                {
                    "level": issue.level.value,
                    "category": issue.category.value,
                    "parameter": issue.parameter,
                    "message": issue.message,
                    "suggestion": issue.suggestion,
                    "auto_fixable": issue.auto_fixable,
                    "enterprise_feature": issue.enterprise_feature,
                    "impact": issue.impact,
                }
                for issue in result.issues
            ],
            "optimized_config": result.optimized_config,
        }

        return json.dumps(data, indent=2)

    def _generate_markdown_report(self, result: ValidationResult) -> str:
        """Generate markdown format validation report."""
        lines = []
        lines.append("# LocalRuntime Configuration Validation Report")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Score |")
        lines.append("|--------|-------|")
        lines.append(
            f"| Configuration Valid | {'✅ Yes' if result.valid else '❌ No'} |"
        )
        lines.append(f"| Total Issues | {len(result.issues)} |")
        lines.append(f"| Security Score | {result.security_score}/100 |")
        lines.append(f"| Performance Score | {result.performance_score}/100 |")
        lines.append(f"| Enterprise Readiness | {result.enterprise_readiness}/100 |")
        lines.append("")

        # Issues
        if result.issues:
            lines.append("## Issues")
            lines.append("")

            for level in ValidationLevel:
                level_issues = [i for i in result.issues if i.level == level]
                if level_issues:
                    level_emoji = {
                        ValidationLevel.ERROR: "🚨",
                        ValidationLevel.WARNING: "⚠️",
                        ValidationLevel.INFO: "ℹ️",
                        ValidationLevel.DEBUG: "🔍",
                    }

                    lines.append(
                        f"### {level_emoji.get(level, '')} {level.value.title()} Issues"
                    )
                    lines.append("")

                    for issue in level_issues:
                        lines.append(f"**{issue.parameter}**: {issue.message}")
                        lines.append("")
                        lines.append(f"- **Suggestion**: {issue.suggestion}")
                        lines.append(f"- **Category**: {issue.category.value}")
                        lines.append(f"- **Impact**: {issue.impact}")
                        if issue.auto_fixable:
                            lines.append("- **Auto-fixable**: ✅ Yes")
                        if issue.enterprise_feature:
                            lines.append("- **Enterprise Feature**: 🏢 Yes")
                        lines.append("")

        return "\n".join(lines)
