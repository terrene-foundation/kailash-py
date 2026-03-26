"""
Kailash DataFlow - Clean Modular Architecture

This is the modernized DataFlow framework with proper modular structure.
The monolithic 526-line implementation has been refactored into focused modules:

- core/engine.py: Main DataFlow class
- core/models.py: Configuration and base models
- core/nodes.py: Dynamic node generation
- features/bulk.py: High-performance bulk operations
- features/transactions.py: Enterprise transaction management
- features/multi_tenant.py: Multi-tenant data isolation
- utils/connection.py: Connection pooling and management
- configuration/: Progressive disclosure configuration system
- migrations/: Auto-migration and visual builder system
- optimization/: Query optimization and performance system

This maintains 100% functional compatibility while providing:
- Better maintainability
- Improved testability
- Clear separation of concerns
- Easier contribution and extension
- Progressive complexity (zero-config to enterprise)
"""

# Progressive Configuration System
from .configuration import (
    ConfigurationLevel,
    FeatureFlag,
    ProgressiveConfiguration,
    basic_config,
    enterprise_config,
    production_config,
    zero_config,
)
from .core.config import DataFlowConfig, LoggingConfig, mask_sensitive
from .core.engine import DataFlow
from .engine import DataFlowEngine, HealthStatus, QueryEngine, ValidationLayer, DataClassificationPolicy
from .core.logging_config import DEFAULT_SENSITIVE_PATTERNS
from .core.logging_config import LoggingConfig as AdvancedLoggingConfig
from .core.logging_config import SensitiveMaskingFilter, mask_sensitive_values
from .core.model_registry import ModelRegistry
from .core.models import DataFlowModel
from .core.tenant_context import TenantContextSwitch, TenantInfo, get_current_tenant_id
from .core.type_processor import TypeAwareFieldProcessor
from .core.workflow_binding import DataFlowWorkflowBinder
# Field-level validation (issue #82)
from .validation import (
    FieldValidationError,
    ValidationResult,
    email_validator,
    field_validator,
    length_validator,
    pattern_validator,
    phone_validator,
    range_validator,
    url_validator,
    uuid_validator,
    validate_model,
)

# Data classification (issue #83)
from .classification import (
    ClassificationPolicy,
    DataClassification,
    FieldClassification,
    MaskingStrategy,
    RetentionPolicy,
    classify,
    get_field_classification,
)

from .utils.suppress_warnings import (
    configure_dataflow_logging,
    dataflow_logging_context,
    get_dataflow_logger,
    is_logging_configured,
    restore_dataflow_logging,
    suppress_core_sdk_warnings,
)

# Suppress verbose Core SDK warnings on import
suppress_core_sdk_warnings()

# Legacy compatibility - maintain the original imports
__version__ = "1.2.0"

__all__ = [
    "DataFlow",
    "DataFlowEngine",
    "QueryEngine",
    "HealthStatus",
    "ValidationLayer",
    "DataClassificationPolicy",
    "DataFlowConfig",
    "DataFlowModel",
    "LoggingConfig",
    "ModelRegistry",
    "ProgressiveConfiguration",
    "ConfigurationLevel",
    "FeatureFlag",
    "zero_config",
    "basic_config",
    "production_config",
    "enterprise_config",
    "configure_dataflow_logging",
    "is_logging_configured",
    "restore_dataflow_logging",
    "mask_sensitive",
    # Phase 7: Centralized Logging Configuration
    "mask_sensitive_values",
    "SensitiveMaskingFilter",
    "DEFAULT_SENSITIVE_PATTERNS",
    "AdvancedLoggingConfig",  # Phase 7C: Regex-based masking config
    # Phase 7B: Logging Utilities
    "get_dataflow_logger",
    "dataflow_logging_context",
    # TODO-153: Type-Aware Field Processor
    "TypeAwareFieldProcessor",
    # TODO-154: Workflow Binding Integration
    "DataFlowWorkflowBinder",
    # TODO-155: Context Switching Capabilities
    "TenantContextSwitch",
    "TenantInfo",
    "get_current_tenant_id",
    # Issue #82: Field-level validation
    "field_validator",
    "validate_model",
    "ValidationResult",
    "FieldValidationError",
    "email_validator",
    "url_validator",
    "uuid_validator",
    "length_validator",
    "range_validator",
    "pattern_validator",
    "phone_validator",
    # Issue #83: Data classification
    "DataClassification",
    "RetentionPolicy",
    "MaskingStrategy",
    "ClassificationPolicy",
    "FieldClassification",
    "classify",
    "get_field_classification",
]

# Backward compatibility note:
# All existing code using `from dataflow import DataFlow` will continue to work.
# The internal architecture is now modular, but the public API remains unchanged.
