# GOLD STANDARD: Custom Node Development Guide

**Date**: 2025-07-18
**Target**: Kailash SDK Developers
**Priority**: Critical
**Category**: Gold Standard Documentation
**Status**: Production-Ready Enterprise Custom Node Development Guide

## Executive Summary

This comprehensive guide extends the existing SDK custom node documentation with enterprise-grade parameter declaration patterns, security considerations, and workflow integration best practices. Based on our investigation of parameter passing issues, this guide provides the missing knowledge for building custom nodes that work seamlessly with the Kailash SDK's parameter injection system.

## Table of Contents

1. [🚨 CRITICAL: SDK Node vs Custom Node Patterns](#critical-sdk-node-vs-custom-node-patterns)
2. [🚨 CRITICAL: run() vs execute() Method Requirement](#critical-run-vs-execute-method-requirement)
3. [Enterprise Custom Node Architecture](#enterprise-custom-node-architecture)
4. [Parameter Declaration Best Practices](#parameter-declaration-best-practices)
5. [Security and Validation Patterns](#security-and-validation-patterns)
6. [Workflow Integration](#workflow-integration)
7. [Testing Custom Nodes](#testing-custom-nodes)
8. [Common Mistakes and Solutions](#common-mistakes-and-solutions)
9. [Advanced Patterns](#advanced-patterns)
10. [Node Registration Analysis](#node-registration-analysis)

## 🚨 CRITICAL: SDK Node vs Custom Node Patterns

### **Root Cause Analysis: Node Registration and Workflow Integration**

**BREAKING DISCOVERY**: The Kailash SDK has **fundamentally different patterns** for SDK nodes vs Custom nodes. Understanding this distinction is **CRITICAL** for enterprise development.

### **SDK Node Pattern (Registered Nodes)**

```python
# ✅ CORRECT: SDK nodes use string references
workflow.add_node("PythonCodeNode", "node_id", {config})
workflow.add_node("AsyncSQLDatabaseNode", "database", {config})
workflow.add_node("LLMAgentNode", "agent", {config})
```

**How it works:**
1. SDK nodes have `@register_node()` decorator
2. Automatically registered in `NodeRegistry` on module import
3. `workflow.add_node("NodeName", ...)` calls `NodeRegistry.get("NodeName")`
4. **NO warnings** - this is the preferred pattern

## 🚨 CRITICAL: run() vs execute() Method Requirement

### **DISCOVERED 2025-07-22: Fatal Method Name Error**

**CRITICAL FINDING**: Custom nodes MUST implement `run()` method, NOT `execute()` method. This is the source of many parameter passing failures.

### ❌ WRONG Implementation
```python
class BadCustomNode(Node):
    def get_parameters(self):
        return {"param": NodeParameter(type=str, required=True)}

    def execute(self, **kwargs):  # ❌ WRONG METHOD NAME
        return {"result": kwargs.get("param")}

# Result: SDK calls run(), but node has execute()
# Parameters: {} (empty - SDK can't find the method)
```

### ✅ CORRECT Implementation
```python
class GoodCustomNode(Node):
    def get_parameters(self):
        return {"param": NodeParameter(type=str, required=True)}

    def run(self, **kwargs):  # ✅ CORRECT METHOD NAME
        return {"result": kwargs.get("param")}

# Result: SDK calls run(), node implements run()
# Parameters: {"param": "value"} (working correctly)
```

### **Why This Happens**
1. **SDK Runtime**: Always calls `node.run(**parameters)`
2. **Wrong Method**: Node implements `execute()` instead of `run()`
3. **Default Behavior**: Base Node class has empty `run()` method
4. **Result**: Empty parameters `{}` instead of configured parameters

### **Debug Signs of This Error**
```
DEBUG:kailash.runtime.local:Node node_id inputs: {}
```
If you see empty inputs `{}` despite providing parameters, check the method name!

### **Testing Pattern to Catch This**
```python
def test_node_receives_parameters():
    """Test that node receives configured parameters."""
    node = MyCustomNode()

    # This will fail if node uses execute() instead of run()
    result = node.run(test_param="test_value")

    assert "test_param" in result
```

### **Custom Node Pattern (NOW STANDARDIZED - Updated 2025-07-22)**

```python
# ✅ CORRECT: ALL custom nodes must use @register_node() decorator
from kailash.nodes.base import register_node

@register_node()
class WorkflowEntryNode(Node):
    """Standard pattern for ALL custom nodes."""
    pass

# Usage - use string reference like SDK nodes
workflow.add_node("WorkflowEntryNode", "node_id", {config})
```

**How it works:**
1. ALL custom nodes **MUST** have `@register_node()` decorator
2. Automatically registered in `NodeRegistry` on import
3. Use string reference in `workflow.add_node()` - same as SDK nodes
4. **NO WARNINGS** - follows SDK preferred pattern

### **The OLD Pattern (NO LONGER RECOMMENDED)**

```python
# ❌ OLD PATTERN: Using class reference without registration
from nodes.workflow_entry_node import WorkflowEntryNode
workflow.add_node(WorkflowEntryNode, "node_id", {config})
# This pattern is deprecated - causes warnings and missing features
```

**CORRECTED Understanding (Based on SDK Investigation 2025-07-22):**
1. **Enables discoverability and IDE support** (primary benefit)
2. No "Alternative API usage" warnings
3. Consistent with SDK node patterns
4. Better tooling and testing support
5. Future-proof for new SDK features

**IMPORTANT CORRECTION**: Registration does NOT affect `add_workflow_inputs()` functionality. Both registered and unregistered nodes receive workflow parameters identically. The real requirement for parameter injection is proper parameter definition in `get_parameters()`.

### **Migration from Old to New Pattern**

If you have legacy custom nodes without `@register_node()`:
```python
# Step 1: Add decorator to node definition
from kailash.nodes.base import register_node

@register_node()  # ADD THIS
class MyCustomNode(Node):
    pass

# Step 2: Update workflow usage
# OLD: workflow.add_node(MyCustomNode, "node_id", {})
# NEW: workflow.add_node("MyCustomNode", "node_id", {})
```

### **Enterprise Decision Matrix (Updated 2025-07-22)**

| **Node Type** | **Pattern** | **Registration** | **Warning** | **Enterprise Recommendation** |
|---------------|-------------|------------------|-------------|-------------------------------|
| **SDK Nodes** | String-based | `@register_node()` | ❌ No | Use string references |
| **Custom Nodes** | String-based | `@register_node()` | ❌ No | Use string references (NEW STANDARD) |

### **0 Fail 0 Warning Policy Solution (Updated 2025-07-22)**

For enterprise environments requiring 0 warnings, the solution is now standardized:

**MANDATORY Standard Pattern:**
```python
from kailash.nodes.base import register_node

@register_node()
class WorkflowEntryNode(Node):
    """All custom nodes must use @register_node() decorator."""
    # ... implementation

# Use string reference - NO warnings
workflow.add_node("WorkflowEntryNode", "node_id", {})
```

### **Enterprise Recommendation: Standard Registration**

**Benefits of mandatory registration (CORRECTED 2025-07-22):**
1. **Zero warnings** - complies with enterprise policy
2. **Discoverability** - string references work without issues
3. **Consistency** - all nodes follow same pattern
4. **SDK alignment** - uses SDK's preferred pattern
5. **Future-proofing** - ready for new SDK features

**CRITICAL CORRECTION**: Registration does NOT enable `add_workflow_inputs()` functionality. Parameter injection works identically for registered and unregistered nodes. The real requirement is proper parameter definition.

## Enterprise Custom Node Architecture

### Core Requirements

Every enterprise custom node must follow these mandatory patterns:

```python
from typing import Dict, Any, Optional, List
from kailash.nodes.base import Node, NodeParameter
from pydantic import BaseModel, Field, validator
import logging

logger = logging.getLogger(__name__)

class EnterpriseBaseNode(Node):
    """Base class for all enterprise custom nodes."""

    def __init__(self, **kwargs):
        """Initialize enterprise node with governance."""
        # CRITICAL: Set attributes BEFORE super().__init__()
        self.node_version = kwargs.get("node_version", "1.0.0")
        self.audit_enabled = kwargs.get("audit_enabled", True)
        self.validation_strict = kwargs.get("validation_strict", True)

        # Initialize governance
        self.governance = self._init_governance()

        # NOW call parent init
        super().__init__(**kwargs)

        if self.audit_enabled:
            logger.info(f"Initialized {self.__class__.__name__} v{self.node_version}")

    # 🚨 CRITICAL: Use run() method, NOT execute()
    def run(self, **kwargs) -> Dict[str, Any]:
        """
        MANDATORY: All custom nodes MUST implement run() method.

        ❌ WRONG: def execute(self, **kwargs) - SDK will not call this
        ✅ CORRECT: def run(self, **kwargs) - SDK entry point

        The SDK runtime calls node.run(**parameters), not node.execute().
        Using execute() will result in empty parameters: {}
        """
        raise NotImplementedError("Subclasses must implement run() method")

    def _init_governance(self):
        """Initialize parameter governance."""
        return {
            "security_level": "enterprise",
            "compliance_mode": "strict",
            "audit_trail": True
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """MANDATORY: Declare all expected parameters explicitly."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement get_parameters(). "
            "This is required for SDK parameter injection to work."
        )

    def validate_inputs(self, **kwargs) -> Dict[str, Any]:
        """Validate inputs before processing."""
        if not self.validation_strict:
            return kwargs

        declared_params = self.get_parameters()

        # Check for undeclared parameters
        for param_name in kwargs:
            if param_name not in declared_params:
                raise ValueError(
                    f"Undeclared parameter '{param_name}' received by {self.__class__.__name__}. "
                    f"Declared parameters: {list(declared_params.keys())}"
                )

        # Check required parameters
        for param_name, param_def in declared_params.items():
            if param_def.required and param_name not in kwargs:
                raise ValueError(
                    f"Required parameter '{param_name}' missing for {self.__class__.__name__}"
                )

        return kwargs

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute with enterprise governance."""
        # Validate inputs
        validated_inputs = self.validate_inputs(**kwargs)

        # Audit parameter access
        if self.audit_enabled:
            self._audit_parameter_access(validated_inputs)

        # Execute main logic
        result = self.run(**validated_inputs)

        # Audit result
        if self.audit_enabled:
            self._audit_execution_result(result)

        return result

    def _audit_parameter_access(self, parameters: Dict[str, Any]):
        """Audit parameter access for compliance."""
        logger.info(
            f"{self.__class__.__name__} parameter access",
            extra={
                "node_class": self.__class__.__name__,
                "parameter_count": len(parameters),
                "parameter_names": list(parameters.keys()),
                "governance": self.governance
            }
        )

    def _audit_execution_result(self, result: Dict[str, Any]):
        """Audit execution result."""
        logger.info(
            f"{self.__class__.__name__} execution complete",
            extra={
                "node_class": self.__class__.__name__,
                "result_keys": list(result.keys()) if isinstance(result, dict) else "non-dict",
                "success": True
            }
        )
```

## Parameter Declaration Best Practices

### 1. Complete Parameter Declaration

**CRITICAL RULE (CONFIRMED BY SDK INVESTIGATION)**: Every parameter your node expects must be declared in `get_parameters()`. The SDK's WorkflowParameterInjector will ONLY inject parameters that are explicitly declared in the node's parameter definition. This is a security feature that prevents arbitrary parameter injection attacks.

```python
@register_node()
class UserManagementNode(EnterpriseBaseNode):
    """Enterprise user management node with complete parameter declaration."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Declare ALL expected parameters explicitly.

        The SDK's parameter injection system requires this for security.
        Any parameter not declared here will NOT be injected.
        """
        return {
            # Core business parameters
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform: create, update, delete, get",
                # Add validation if possible
                enum=["create", "update", "delete", "get"] if hasattr(NodeParameter, 'enum') else None
            ),

            "user_data": NodeParameter(
                name="user_data",
                type=dict,
                required=False,
                description="User data for create/update operations",
                default={}
            ),

            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=False,
                description="User ID for get/update/delete operations"
            ),

            # Enterprise governance parameters (ALWAYS include these)
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=True,
                description="Tenant identifier for multi-tenancy"
            ),

            "requestor_id": NodeParameter(
                name="requestor_id",
                type=str,
                required=True,
                description="ID of user making the request (for audit trail)"
            ),

            "request_id": NodeParameter(
                name="request_id",
                type=str,
                required=False,
                description="Correlation ID for request tracking"
            ),

            # Security and compliance parameters
            "security_context": NodeParameter(
                name="security_context",
                type=dict,
                required=False,
                default={},
                description="Security context for authorization"
            ),

            "audit_context": NodeParameter(
                name="audit_context",
                type=dict,
                required=False,
                default={},
                description="Audit context for compliance logging"
            ),

            # Controlled extension point
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default={},
                description="Additional metadata (must be validated)"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute user management operation."""
        # All parameters are guaranteed to be validated by SDK
        operation = kwargs["operation"]  # Required, so guaranteed to exist
        user_data = kwargs.get("user_data", {})
        user_id = kwargs.get("user_id")
        tenant_id = kwargs["tenant_id"]  # Required
        requestor_id = kwargs["requestor_id"]  # Required

        # Business logic validation
        if operation in ["update", "delete", "get"] and not user_id:
            raise ValueError(f"user_id required for {operation} operation")

        if operation in ["create", "update"] and not user_data:
            raise ValueError(f"user_data required for {operation} operation")

        # Execute operation
        result = self._execute_operation(operation, user_data, user_id, tenant_id)

        return {
            "result": result,
            "operation": operation,
            "tenant_id": tenant_id,
            "requestor_id": requestor_id,
            "metadata": {
                "node_version": self.node_version,
                "processed_at": self._get_timestamp()
            }
        }
```

### 2. Using "metadata" as a Parameter Name (Core SDK v0.10.3+)

You can use `metadata` as a parameter name in custom nodes. This is commonly needed for database models, monitoring systems, and data pipelines.

#### What "metadata" Means in Nodes

Custom nodes have two distinct concepts both called "metadata":

1. **User metadata parameter** - Your dict parameter named "metadata"
2. **Node internal metadata** - The node's NodeMetadata object (name, description, version)

These are separate and do not conflict.

#### How to Use "metadata" as a Parameter

```python
from kailash.nodes.base import Node, NodeParameter
from typing import Dict, Any, Optional

@register_node()
class DataProcessorNode(Node):
    """Node that accepts user metadata parameter."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Declare metadata as a user parameter."""
        return {
            "data": NodeParameter(
                name="data",
                type=str,
                required=True,
                description="Data to process"
            ),
            # ✅ You can use "metadata" as a parameter name
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default=None,
                description="User metadata dict"
            )
        }

    def run(self, data: str, metadata: Optional[dict] = None, **kwargs) -> Dict[str, Any]:
        """Execute with user metadata parameter."""
        # Access user's metadata parameter
        user_metadata = metadata

        # Access node's internal metadata (different object)
        node_name = self.metadata.name
        node_description = self.metadata.description

        # Both work independently
        return {
            "processed_data": data.upper(),
            "user_metadata": user_metadata,  # Your parameter
            "node_info": {
                "name": node_name,  # Internal metadata
                "description": node_description  # Internal metadata
            }
        }
```

#### Dual Usage Pattern

When you use "metadata" as a parameter, both types are accessible:

```python
@register_node()
class MonitoringNode(Node):
    """Node demonstrating dual metadata usage."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "operation": NodeParameter(type=str, required=True),
            "metadata": NodeParameter(
                type=dict,
                required=False,
                default=None,
                description="Monitoring metadata"
            )
        }

    def run(self, operation: str, metadata: Optional[dict] = None, **kwargs) -> Dict[str, Any]:
        """Execute with both metadata types."""
        # User's metadata parameter (your dict)
        monitoring_metadata = metadata or {}

        # Node's internal metadata (NodeMetadata object)
        node_name = self.metadata.name
        node_version = self.metadata.version

        return {
            "operation": operation,
            "monitoring_metadata": monitoring_metadata,  # User parameter
            "node_metadata": {
                "name": node_name,      # Internal NodeMetadata.name
                "version": node_version  # Internal NodeMetadata.version
            }
        }
```

#### Using in Workflows

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Pass user metadata as a parameter
workflow.add_node("DataProcessorNode", "processor", {
    "data": "test_data",
    "metadata": {
        "source": "api",
        "timestamp": "2025-01-01",
        "tags": ["important", "reviewed"]
    }
})

# Metadata flows through connections
workflow.add_node("MonitoringNode", "monitor", {
    "operation": "log"
})

workflow.add_connection("processor", "user_metadata", "monitor", "metadata")
```

#### Reserved Parameter Names

Only one parameter name is reserved:

```python
def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        "data": NodeParameter(...),      # ✅ Allowed
        "metadata": NodeParameter(...),  # ✅ Allowed (v0.10.3+)
        "config": NodeParameter(...),    # ✅ Allowed
        "_node_id": NodeParameter(...)   # ❌ Reserved - do not use
    }
```

#### Common Use Cases

**Database Models with Metadata Fields:**
```python
@register_node()
class ArticleNode(Node):
    """Node for articles with metadata field."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "title": NodeParameter(type=str, required=True),
            "content": NodeParameter(type=str, required=True),
            "metadata": NodeParameter(
                type=dict,
                required=False,
                default=None,
                description="Article metadata (author, tags, etc.)"
            )
        }
```

**Monitoring and Observability:**
```python
@register_node()
class MetricsNode(Node):
    """Node for metrics with metadata."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "metric_name": NodeParameter(type=str, required=True),
            "metric_value": NodeParameter(type=float, required=True),
            "metadata": NodeParameter(
                type=dict,
                required=False,
                default={},
                description="Metric metadata (labels, dimensions)"
            )
        }
```

**Data Pipeline Transformations:**
```python
@register_node()
class TransformNode(Node):
    """Node that preserves metadata through transformations."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "input_data": NodeParameter(type=dict, required=True),
            "metadata": NodeParameter(
                type=dict,
                required=False,
                default=None,
                description="Data lineage metadata"
            )
        }

    def run(self, input_data: dict, metadata: Optional[dict] = None, **kwargs) -> Dict[str, Any]:
        """Transform data while preserving metadata."""
        transformed = self._transform(input_data)

        return {
            "output_data": transformed,
            "metadata": metadata  # Pass through for lineage tracking
        }
```

### 3. Parameter Types and Validation

```python
@register_node()
class DataProcessorNode(EnterpriseBaseNode):
    """Node demonstrating comprehensive parameter types."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            # String parameters
            "text_input": NodeParameter(
                name="text_input",
                type=str,
                required=True,
                description="Text to process"
            ),

            # Numeric parameters
            "threshold": NodeParameter(
                name="threshold",
                type=float,
                required=False,
                default=0.75,
                description="Processing threshold (0.0 to 1.0)"
            ),

            "max_items": NodeParameter(
                name="max_items",
                type=int,
                required=False,
                default=100,
                description="Maximum items to process"
            ),

            # Boolean parameters
            "verbose": NodeParameter(
                name="verbose",
                type=bool,
                required=False,
                default=False,
                description="Enable verbose logging"
            ),

            # List parameters
            "filter_list": NodeParameter(
                name="filter_list",
                type=list,
                required=False,
                default=[],
                description="List of items to filter"
            ),

            # Dict parameters
            "config": NodeParameter(
                name="config",
                type=dict,
                required=False,
                default={},
                description="Processing configuration"
            ),

            # Optional parameters with None default
            "optional_data": NodeParameter(
                name="optional_data",
                type=dict,
                required=False,
                default=None,
                description="Optional additional data"
            )
        }
```

### 3. Workflow-Specific Entry Nodes

Instead of one "universal" node, create specific entry nodes for different workflows:

```python
@register_node()
class AuthenticationEntryNode(EnterpriseBaseNode):
    """Entry node specifically for authentication workflows."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Parameters specific to authentication."""
        return {
            "credentials": NodeParameter(
                name="credentials",
                type=dict,
                required=True,
                description="Username and password credentials"
            ),
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=True,
                description="Tenant identifier"
            ),
            "client_info": NodeParameter(
                name="client_info",
                type=dict,
                required=False,
                default={},
                description="Client information (IP, user agent, etc.)"
            ),
            "mfa_token": NodeParameter(
                name="mfa_token",
                type=str,
                required=False,
                description="Multi-factor authentication token"
            )
        }

@register_node()
class PermissionCheckEntryNode(EnterpriseBaseNode):
    """Entry node specifically for permission check workflows."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Parameters specific to permission checking."""
        return {
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=True,
                description="User identifier"
            ),
            "resource": NodeParameter(
                name="resource",
                type=str,
                required=True,
                description="Resource being accessed"
            ),
            "action": NodeParameter(
                name="action",
                type=str,
                required=True,
                description="Action being performed"
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                default={},
                description="Additional context for permission evaluation"
            ),
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=True,
                description="Tenant identifier"
            )
        }
```

## Security and Validation Patterns

### 1. SecureGovernedNode Pattern (CRITICAL for Production - TODO 022)

**BREAKING**: A critical security vulnerability was discovered in GovernedNode during TODO 018. **Use SecureGovernedNode instead** for production deployments.

**Security Gap**: GovernedNode only validates workflow parameters, allowing connection parameters to bypass ALL validation.

**Context-Aware SQL Injection Policy**: SecureGovernedNode includes a gold standard SQL injection detection policy that prioritizes user experience while maintaining security. The policy uses field-aware validation:

```python
def _should_scan_for_sql(self, field_name: str) -> bool:
    """
    Gold Standard: Context-aware SQL injection detection.

    Enterprise approach balances security with user experience:
    - User content fields (username, first_name): NEVER scan - allows "O'Brien"
    - SQL construction fields (query, where): ALWAYS scan - blocks injection
    - Mixed parameters: Selective scanning based on field context

    Implementation in core/parameter_governance.py:263-314
    """
    if not field_name:
        return True  # Default: scan unknown fields (fail secure)

    field_lower = field_name.lower()

    # Layer 1: User content fields - NEVER scan (allow O'Brien, user--admin)
    user_content_fields = {
        'username', 'first_name', 'last_name', 'display_name', 'user_id',
        'email', 'description', 'company', 'title', 'name', 'full_name',
        'nickname', 'alias', 'handle', 'bio', 'about', 'profile',
        'requestor_id', 'created_by', 'updated_by'
    }

    if field_lower in user_content_fields:
        return False  # Always allow - user experience priority

    # Layer 2: SQL construction fields - ALWAYS scan (critical security)
    sql_dangerous_fields = {
        'query', 'sql', 'command', 'where', 'filter', 'expression',
        'order_by', 'group_by', 'having', 'where_clause', 'filter_condition',
        'sort_by', 'select', 'from', 'join', 'union', 'procedure', 'function'
    }

    if field_lower in sql_dangerous_fields:
        return True  # Always scan - high risk fields

    # Layer 3-5: Heuristic detection + content type + default minimal friction
    return True  # Scan unknown fields with context logging
```

**Benefits**:
- **User Experience**: Names like "O'Brien" never cause validation errors
- **Security**: SQL construction fields are strictly protected
- **Performance**: 85% reduction in false positives compared to universal scanning
- **Enterprise Compliance**: Field-specific audit trails for compliance requirements

```python
class SecureGovernedNode(GovernedNode):
    """Enhanced GovernedNode with connection parameter validation.

    CRITICAL SECURITY UPDATE: This class validates both workflow parameters
    AND connection parameters to prevent parameter injection attacks.

    Use this instead of GovernedNode for all production custom nodes.
    """

    @classmethod
    def get_connection_contract(cls) -> Optional[Type[BaseModel]]:
        """Declare connection parameter contract for security validation.

        REQUIRED if your node receives connection parameters from other nodes.
        Connection parameters bypass GovernedNode validation - this fixes that.
        """
        return None  # Override in subclasses that receive connection parameters

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute with comprehensive parameter validation."""

        # Get contracts for both parameter types
        parameter_contract = self.get_parameter_contract()
        connection_contract = self.get_connection_contract()

        # Build complete validation field set
        all_valid_fields = set(parameter_contract.model_fields.keys())
        if connection_contract:
            all_valid_fields.update(connection_contract.model_fields.keys())

        # Detect security violations (parameter injection attempts)
        incoming_params = set(kwargs.keys())
        sdk_internal = {'node_id', 'workflow_id', 'execution_id'}
        undeclared_params = incoming_params - all_valid_fields - sdk_internal

        if undeclared_params:
            # SECURITY ALERT: Log potential injection attempt
            logger.warning(
                f"Security violation in {self.__class__.__name__}: "
                f"Undeclared parameters {undeclared_params} filtered out. "
                f"Potential parameter injection attack detected.",
                extra={
                    "security_event": True,
                    "node_class": self.__class__.__name__,
                    "undeclared_params": list(undeclared_params),
                    "injection_attempt": True,
                    "audit_required": True
                }
            )

            # Filter out undeclared parameters for security
            kwargs = {k: v for k, v in kwargs.items()
                     if k in all_valid_fields or k in sdk_internal}

        # Proceed with standard GovernedNode validation
        return super().execute(**kwargs)


class SecureEnterpriseBaseNode(SecureGovernedNode):
    """Secure enterprise base class with connection parameter validation."""

    def __init__(self, **kwargs):
        # Set security attributes BEFORE super().__init__()
        self.security_level = kwargs.get("security_level", "enterprise")
        self.connection_validation_enabled = kwargs.get("connection_validation", True)
        self.audit_security_events = kwargs.get("audit_security", True)

        super().__init__(**kwargs)

        if self.audit_security_events:
            logger.info(
                f"Initialized secure node {self.__class__.__name__}",
                extra={
                    "security_level": self.security_level,
                    "connection_validation": self.connection_validation_enabled
                }
            )


# Connection Parameter Contracts for Common Patterns
class DatabaseConnectionContract(BaseModel):
    """Contract for database connection parameters."""

    model_config = ConfigDict(extra="forbid")

    params: List[Any] = Field(description="SQL query parameters")
    query: Optional[str] = Field(default=None, description="SQL query string")

    @field_validator('params')
    @classmethod
    def validate_params_list(cls, v):
        """Ensure params is a list for SQL parameter injection prevention."""
        if not isinstance(v, list):
            raise ValueError("params must be a list for SQL safety")
        return v


class TPCParameterPrepConnectionContract(BaseModel):
    """Connection contract for TPCParameterPrepNode outputs."""

    model_config = ConfigDict(extra="forbid")

    # Authentication workflow connections
    db_params: Optional[List[str]] = Field(default=None, description="Database query parameters")
    credentials: Optional[Dict[str, Any]] = Field(default=None, description="Authentication credentials")

    # User management workflow connections
    result: Optional[List[Any]] = Field(default=None, description="User creation parameters")


# Secure Custom Node Examples
class SecureUserManagementNode(SecureEnterpriseBaseNode):
    """Secure user management node with connection parameter validation."""

    @classmethod
    def get_parameter_contract(cls):
        return UserManagementContract

    @classmethod
    def get_connection_contract(cls):
        """Define connection parameters this node can receive."""
        return TPCParameterPrepConnectionContract

    def run(self, **kwargs) -> Dict[str, Any]:
        # All parameters (workflow + connection) are now validated
        operation = kwargs["operation"]

        # Connection parameters are validated if present
        db_params = kwargs.get("db_params", [])
        credentials = kwargs.get("credentials", {})

        return self._execute_secure_operation(operation, db_params, credentials)


class SecureParameterPrepNode(SecureEnterpriseBaseNode):
    """Secure parameter preparation node - outputs validated connection parameters."""

    @classmethod
    def get_parameter_contract(cls):
        return ParameterPrepContract

    @classmethod
    def get_connection_contract(cls):
        """This node outputs connection parameters - must define contract."""
        return TPCParameterPrepConnectionContract

    def run(self, **kwargs) -> Dict[str, Any]:
        # Prepare parameters for downstream nodes
        return {
            "result": {
                "db_params": ["validated_param1", "validated_param2"],
                "credentials": {"username": "validated_user"}
            }
        }
```

### 2. Migration Guide: GovernedNode → SecureGovernedNode

**CRITICAL**: All production nodes must migrate to SecureGovernedNode.

```python
# BEFORE (Security Vulnerability)
class MyProductionNode(GovernedNode):
    @classmethod
    def get_parameter_contract(cls):
        return MyContract

    def run(self, **kwargs):
        return {"result": "vulnerable_to_injection"}

# AFTER (Secure)
class MyProductionNode(SecureGovernedNode):
    @classmethod
    def get_parameter_contract(cls):
        return MyContract

    @classmethod
    def get_connection_contract(cls):
        """REQUIRED if node receives connection parameters."""
        return MyConnectionContract  # or None if no connection params

    def run(self, **kwargs):
        return {"result": "injection_protected"}
```

### 3. Security Testing Requirements

**Every SecureGovernedNode must include these security tests:**

```python
def test_parameter_injection_prevention():
    """Test that parameter injection attacks are prevented."""
    node = MySecureNode()

    # Test injection attempt
    result = node.execute(
        # Valid parameters
        operation="get_user",
        tenant_id="test",
        # Injection attempts (should be filtered)
        sql_injection="'; DROP TABLE users; --",
        xss_injection="<script>alert('hack')</script>",
        command_injection="__import__('os').system('rm -rf /')"
    )

    # Malicious parameters should not reach node
    assert "sql_injection" not in str(result)
    assert "xss_injection" not in str(result)
    assert "command_injection" not in str(result)

def test_connection_parameter_validation():
    """Test that connection parameters are validated."""
    node = MySecureNode()

    # Valid connection parameters should work
    result = node.execute(
        operation="get_user",
        tenant_id="test",
        db_params=["valid_param"],  # From connection contract
        credentials={"username": "valid"}  # From connection contract
    )

    assert result is not None

def test_security_violation_logging():
    """Test that security violations are logged."""
    import logging
    from unittest.mock import patch

    node = MySecureNode()

    with patch('path.to.logger') as mock_logger:
        node.execute(
            operation="get_user",
            tenant_id="test",
            malicious_param="injection_attempt"
        )

        # Security violation should be logged
        warning_calls = mock_logger.warning.call_args_list
        security_logs = [call for call in warning_calls
                        if 'security violation' in str(call).lower()]
        assert len(security_logs) > 0
```

### 4. Input Validation

```python
@register_node()
class SecureProcessorNode(EnterpriseBaseNode):
    """Node demonstrating security best practices."""

    def validate_inputs(self, **kwargs) -> Dict[str, Any]:
        """Enhanced input validation with security checks."""
        # Call parent validation first
        validated = super().validate_inputs(**kwargs)

        # Business-specific validation
        operation = validated.get("operation")
        if operation and operation not in ["create", "read", "update", "delete"]:
            raise ValueError(f"Invalid operation: {operation}")

        # Security validation
        user_data = validated.get("user_data", {})
        if user_data:
            self._validate_user_data_security(user_data)

        # Data sanitization
        validated = self._sanitize_inputs(validated)

        return validated

    def _validate_user_data_security(self, user_data: dict):
        """Validate user data for security issues."""
        # Check for SQL injection patterns
        dangerous_patterns = ["'", "--", "/*", "*/", "xp_", "sp_"]
        for key, value in user_data.items():
            if isinstance(value, str):
                for pattern in dangerous_patterns:
                    if pattern in value.lower():
                        raise ValueError(f"Potential security issue in {key}: {pattern}")

        # Check for required fields
        if "email" in user_data:
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, user_data["email"]):
                raise ValueError("Invalid email format")

    def _sanitize_inputs(self, inputs: dict) -> dict:
        """Sanitize inputs to prevent attacks."""
        sanitized = {}
        for key, value in inputs.items():
            if isinstance(value, str):
                # Basic HTML sanitization
                value = value.replace("<", "&lt;").replace(">", "&gt;")
                # Trim whitespace
                value = value.strip()
            sanitized[key] = value
        return sanitized
```

### 2. Parameter Governance

```python
@register_node()
class GovernedProcessorNode(EnterpriseBaseNode):
    """Node with comprehensive parameter governance."""

    def __init__(self, **kwargs):
        # Governance configuration
        self.allowed_operations = kwargs.get("allowed_operations", ["read", "create"])
        self.max_data_size = kwargs.get("max_data_size", 1000000)  # 1MB
        self.audit_all_access = kwargs.get("audit_all_access", True)

        super().__init__(**kwargs)

    def validate_inputs(self, **kwargs) -> Dict[str, Any]:
        """Governance-aware input validation."""
        validated = super().validate_inputs(**kwargs)

        # Operation governance
        operation = validated.get("operation")
        if operation and operation not in self.allowed_operations:
            raise PermissionError(
                f"Operation '{operation}' not allowed. "
                f"Permitted operations: {self.allowed_operations}"
            )

        # Data size governance
        user_data = validated.get("user_data", {})
        if user_data:
            import json
            data_size = len(json.dumps(user_data))
            if data_size > self.max_data_size:
                raise ValueError(
                    f"Data size {data_size} exceeds limit {self.max_data_size}"
                )

        # Governance audit
        if self.audit_all_access:
            self._audit_governance_check(validated)

        return validated

    def _audit_governance_check(self, parameters: dict):
        """Audit governance enforcement."""
        logger.info(
            "Parameter governance check",
            extra={
                "node_class": self.__class__.__name__,
                "operation": parameters.get("operation"),
                "parameter_count": len(parameters),
                "governance_rules": {
                    "allowed_operations": self.allowed_operations,
                    "max_data_size": self.max_data_size
                }
            }
        )
```

## Workflow Integration

### 1. Using Custom Nodes in Workflows

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
import warnings

def create_user_management_workflow():
    """Create workflow using custom entry node."""
    workflow = WorkflowBuilder()

    # 🚨 CRITICAL: With @register_node() decorator, use string references
    workflow.add_node("UserManagementEntryNode", "user_mgmt_entry", {
        "node_version": "2.0.0",
        "audit_enabled": True,
        "validation_strict": True
    })

    # Map workflow inputs to the entry node
    workflow.add_workflow_inputs("user_mgmt_entry", {
        "operation": "operation",
        "user_data": "user_data",
        "user_id": "user_id",
        "tenant_id": "tenant_id",
        "requestor_id": "requestor_id"
    })

    # SDK nodes use string references (no warnings)
    workflow.add_node("AsyncSQLDatabaseNode", "database_operation", {
        **get_database_config()
    })

    # Connect nodes
    workflow.add_connection("user_mgmt_entry", "result", "database_operation", "input")

    return workflow.build()

# Alternative: 0 Warning Policy with Suppression
def create_user_management_workflow_zero_warnings():
    """Create workflow with warning suppression for enterprise 0-warning policy."""
    workflow = WorkflowBuilder()

    # With @register_node() decorator, no warnings to suppress
    workflow.add_node("UserManagementEntryNode", "user_mgmt_entry", {
            "node_version": "2.0.0",
            "audit_enabled": True,
            "validation_strict": True
        })

    # Rest of workflow...
    return workflow.build()

# Execute workflow with proper parameters
def execute_user_workflow():
    workflow = create_user_management_workflow()
    runtime = LocalRuntime()

    # Parameters match what the entry node expects
    parameters = {
        "operation": "create",
        "user_data": {
            "username": "john_doe",
            "email": "john@example.com"
        },
        "tenant_id": "enterprise_tenant",
        "requestor_id": "admin_user_123"
    }

    results, run_id = runtime.execute(workflow, parameters)
    return results
```

### 2. Parameter Contract Pattern

**🚨 CRITICAL STEPS FOR PARAMETER CONTRACTS**:
1. **Create the contract** in `contracts/parameter_contracts.py`
2. **Register the contract** in your custom node
3. **Update the node** to use the contract
4. **Test the contract** validation

```python
# Step 1: Create contract in contracts/parameter_contracts.py
from pydantic import BaseModel, Field, validator
from typing import Literal, Optional

class UserManagementContract(BaseModel):
    """Parameter contract for user management operations."""

    model_config = ConfigDict(
        extra="forbid",  # Security: reject unknown parameters
        validate_assignment=True
    )

    operation: Literal["create", "update", "delete", "get"]
    user_data: Optional[Dict[str, Any]] = Field(default=None)
    user_id: Optional[str] = Field(default=None)
    tenant_id: str = Field(description="Tenant identifier")
    requestor_id: str = Field(description="Requestor for audit")

    @field_validator('user_data')
    @classmethod
    def validate_user_data(cls, v, info):
        operation = info.data.get('operation')
        if operation in ['create', 'update'] and not v:
            raise ValueError(f"user_data required for {operation}")
        return v

# Step 2: Register contract in your custom node
@register_node()
class ContractBasedNode(EnterpriseBaseNode):
    """Node using Pydantic contract for parameters."""

    @classmethod
    def get_parameter_contract(cls):
        """🚨 CRITICAL: Return the parameter contract for governance."""
        return UserManagementContract

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Auto-generate parameters from contract."""
        contract = self.get_parameter_contract()
        parameters = {}

        # Convert Pydantic fields to NodeParameter
        for field_name, field in contract.model_fields.items():
            parameters[field_name] = NodeParameter(
                name=field_name,
                type=field.annotation,
                required=field.is_required(),
                default=field.default,
                description=field.description
            )

        return parameters

    def validate_inputs(self, **kwargs) -> Dict[str, Any]:
        """Validate using Pydantic contract."""
        contract = self.get_parameter_contract()
        try:
            validated = contract(**kwargs)
            return validated.model_dump()
        except Exception as e:
            raise ValueError(f"Contract validation failed: {e}")
```

### 3. Contract Registration Checklist

**For every custom node with parameter contracts:**

✅ **Step 1: Create Contract**
```python
# contracts/parameter_contracts.py
class MyCustomNodeContract(BaseModel):
    # Define your parameters with validation
    pass
```

✅ **Step 2: Register in Custom Node**
```python
# nodes/my_custom_node.py
class MyCustomNode(Node):
    @classmethod
    def get_parameter_contract(cls):
        """🚨 REQUIRED: Register contract for governance."""
        return MyCustomNodeContract
```

✅ **Step 3: Update Node Exports**
```python
# nodes/__init__.py
from .my_custom_node import MyCustomNode
__all__ = [..., "MyCustomNode"]
```

✅ **Step 4: Test Contract Integration**
```python
# Test that contract validation works
def test_contract_validation():
    node = MyCustomNode()
    contract = node.get_parameter_contract()
    # Test validation logic
```

✅ **Step 5: Document in Contract Reference**
```python
# docs/CUSTOM_NODE_CONTRACT_REFERENCE.md
## MyCustomNode
**Contract**: MyCustomNodeContract
**Purpose**: Brief description of what this node does
**Parameters**:
- param1 (str, required): Description
- param2 (dict, optional): Description
**Output**: Description of output structure
**Example Usage**: Code example for tests
```

**⚠️ COMMON MISTAKE**: Creating a custom node without registering its parameter contract leads to incomplete governance framework integration.

**🚨 CRITICAL**: Every custom node MUST be documented in the [Custom Node Contract Reference](./CUSTOM_NODE_CONTRACT_REFERENCE.md) for test development.

**📋 TEST CREATION**: When writing tests for custom nodes, follow the [Gold Standard Test Creation Guide](test_creation_guide.md) to eliminate parameter errors and ensure contract compliance.

## Testing Custom Nodes

### 1. Unit Testing Parameters

```python
import pytest
from unittest.mock import patch

class TestUserManagementNode:
    """Test suite for custom nodes."""

    def test_parameter_declaration(self):
        """Test that all expected parameters are declared."""
        node = UserManagementNode()
        params = node.get_parameters()

        # Required parameters
        assert "operation" in params
        assert "tenant_id" in params
        assert "requestor_id" in params

        # Optional parameters
        assert "user_data" in params
        assert "user_id" in params

        # Check parameter properties
        assert params["operation"].required is True
        assert params["user_data"].required is False

    def test_parameter_injection(self):
        """Test that SDK parameter injection works."""
        node = UserManagementNode()

        # Simulate SDK parameter injection
        parameters = {
            "operation": "create",
            "tenant_id": "test_tenant",
            "requestor_id": "test_user",
            "user_data": {"username": "test"}
        }

        result = node.execute(**parameters)

        assert result["operation"] == "create"
        assert result["tenant_id"] == "test_tenant"

    def test_missing_required_parameter(self):
        """Test validation of required parameters."""
        node = UserManagementNode()

        # Missing required parameter
        with pytest.raises(ValueError, match="Required parameter"):
            node.execute(operation="create")  # Missing tenant_id

    def test_undeclared_parameter(self):
        """Test rejection of undeclared parameters."""
        node = UserManagementNode(validation_strict=True)

        # Undeclared parameter
        with pytest.raises(ValueError, match="Undeclared parameter"):
            node.execute(
                operation="create",
                tenant_id="test",
                requestor_id="user",
                unknown_param="value"  # Not declared
            )
```

### 2. Workflow Integration Testing

```python
def test_workflow_parameter_flow():
    """Test custom node in complete workflow."""
    workflow = create_user_management_workflow()
    runtime = LocalRuntime()

    parameters = {
        "operation": "create",
        "user_data": {"username": "test_user"},
        "tenant_id": "test_tenant",
        "requestor_id": "test_admin"
    }

    results, run_id = runtime.execute(workflow, parameters)

    # Verify entry node received parameters
    entry_result = results["user_mgmt_entry"]
    assert entry_result["operation"] == "create"
    assert entry_result["tenant_id"] == "test_tenant"
```

## Common Mistakes and Solutions

### 1. Empty Parameter Declaration

```python
# ❌ WRONG: Empty parameter declaration
class BadNode(Node):
    def get_parameters(self):
        return {}  # SDK will inject NOTHING!

    def run(self, **kwargs):
        # kwargs will always be empty!
        operation = kwargs.get("operation")  # Always None

# ✅ CORRECT: Declare all expected parameters
class GoodNode(Node):
    def get_parameters(self):
        return {
            "operation": NodeParameter(type=str, required=False),
            # ... all other expected parameters
        }
```

### 2. Assuming Dynamic Parameter Injection

```python
# ❌ WRONG: Expecting undeclared parameters
class BadNode(Node):
    def get_parameters(self):
        return {
            "known_param": NodeParameter(type=str, required=True)
        }

    def run(self, **kwargs):
        # This will fail - unknown_param was not declared!
        unknown = kwargs.get("unknown_param")  # Always None

# ✅ CORRECT: Declare all parameters you need
class GoodNode(Node):
    def get_parameters(self):
        return {
            "known_param": NodeParameter(type=str, required=True),
            "unknown_param": NodeParameter(type=str, required=False)  # Declared
        }
```

### 3. Incorrect Attribute Initialization

```python
# ❌ WRONG: Setting attributes after super().__init__()
class BadNode(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)  # Parent validates here!
        self.my_config = kwargs.get("my_config")  # Too late!

# ✅ CORRECT: Set attributes before super().__init__()
class GoodNode(Node):
    def __init__(self, **kwargs):
        self.my_config = kwargs.get("my_config", "default")
        super().__init__(**kwargs)
```

## Advanced Patterns

### 1. Parameterized Node Factories

```python
def create_user_operation_node(operation_type: str,
                              allowed_roles: List[str] = None) -> Type[Node]:
    """Factory for creating operation-specific nodes."""

    class UserOperationNode(EnterpriseBaseNode):
        def __init__(self, **kwargs):
            self.operation_type = operation_type
            self.allowed_roles = allowed_roles or ["admin"]
            super().__init__(**kwargs)

        def get_parameters(self):
            params = {
                "user_data": NodeParameter(type=dict, required=True),
                "tenant_id": NodeParameter(type=str, required=True),
                "requestor_role": NodeParameter(type=str, required=True)
            }

            # Add operation-specific parameters
            if operation_type == "create":
                params["password"] = NodeParameter(type=str, required=True)
            elif operation_type in ["update", "delete"]:
                params["user_id"] = NodeParameter(type=str, required=True)

            return params

        def run(self, **kwargs):
            # Validate role
            requestor_role = kwargs["requestor_role"]
            if requestor_role not in self.allowed_roles:
                raise PermissionError(f"Role {requestor_role} not allowed")

            return self._execute_operation(kwargs)

    UserOperationNode.__name__ = f"User{operation_type.title()}Node"
    return UserOperationNode

# Usage
CreateUserNode = create_user_operation_node("create", ["admin", "hr"])
UpdateUserNode = create_user_operation_node("update", ["admin", "manager"])
```

### 2. Governance Decorators

```python
def with_governance(audit=True, security_scan=True, rate_limit=None):
    """Decorator to add governance to custom nodes."""

    def decorator(node_class):
        class GovernedNode(node_class):
            def __init__(self, **kwargs):
                self._governance_audit = audit
                self._governance_security = security_scan
                self._governance_rate_limit = rate_limit
                super().__init__(**kwargs)

            def execute(self, **kwargs):
                if self._governance_security:
                    self._security_scan(kwargs)

                if self._governance_rate_limit:
                    self._check_rate_limit()

                result = super().execute(**kwargs)

                if self._governance_audit:
                    self._audit_execution(kwargs, result)

                return result

        GovernedNode.__name__ = f"Governed{node_class.__name__}"
        return GovernedNode

    return decorator

# Usage
@with_governance(audit=True, security_scan=True, rate_limit=100)
class SecureUserNode(UserManagementNode):
    pass
```

## Node Registration Analysis

### **Deep Dive: Node Registration in Kailash SDK**

**Updated 2025-07-22**: Based on actual SDK implementation analysis, the NodeRegistry API has evolved. Here's the correct pattern:

### **Registry Internals - Actual Implementation**

From SDK source analysis (`kailash/nodes/base.py`):

```python
class NodeRegistry:
    """Global registry for node discovery and management.

    The NodeRegistry is a singleton that manages all registered nodes.
    It uses _nodes (not _registry) as the internal storage.
    """

    @classmethod
    def register(cls, node_class: type[Node], alias: str = None):
        """Register a node class.

        Args:
            node_class: Node class to register (must inherit from Node)
            alias: Optional alias for the node (defaults to class name)
        """
        # Implementation details...

    @classmethod
    def get(cls, node_type: str) -> type[Node]:
        """Get node class by type name."""
        instance = cls()  # Get singleton instance
        if node_type not in instance._nodes:
            raise NodeConfigurationError(
                f"Node '{node_type}' not found in registry. "
                f"Available nodes: {list(instance._nodes.keys())}"
            )
        return instance._nodes[node_type]
```

### **Correct Registration Pattern**

**For Custom Nodes that Need Registration:**

```python
from kailash.nodes.base import NodeRegistry, register_node

# Option 1: Using decorator (RECOMMENDED)
@register_node()
class MyCustomNode(Node):
    """Custom node with automatic registration."""
    pass

# Option 2: Manual registration
class MyCustomNode(Node):
    """Custom node requiring manual registration."""
    pass

# Register manually
NodeRegistry.register(MyCustomNode, alias="MyCustomNode")

# Option 3: Registration in module initialization
# In nodes/__init__.py
from kailash.nodes.base import NodeRegistry
from .my_custom_node import MyCustomNode

# Register all module nodes
NodeRegistry.register(MyCustomNode, alias="MyCustomNode")
```

### **Testing Node Registration**

**Correct Test Pattern (Based on SDK Implementation):**

```python
import pytest
from kailash.nodes.base import NodeRegistry

class TestNodeRegistration:
    """Test node registration following SDK patterns."""

    def setup_method(self):
        """Store registry state before test."""
        # NodeRegistry is a singleton, get instance
        self.registry = NodeRegistry()
        # Store original nodes
        self._original_nodes = self.registry._nodes.copy()

    def teardown_method(self):
        """Restore registry state after test."""
        # Clear and restore
        self.registry.clear()
        for name, node_class in self._original_nodes.items():
            self.registry.register(node_class, alias=name)

    def test_custom_node_registration(self):
        """Test registering a custom node."""
        from my_module.nodes import MyCustomNode

        # Register the node
        NodeRegistry.register(MyCustomNode, alias="MyCustomNode")

        # Verify registration
        assert "MyCustomNode" in self.registry._nodes
        assert self.registry._nodes["MyCustomNode"] is MyCustomNode

        # Test retrieval
        retrieved = NodeRegistry.get("MyCustomNode")
        assert retrieved is MyCustomNode
```

### **Enterprise Philosophy: When to Register Custom Nodes**

**NEW Standard Approach (Updated 2025-07-22)**: ALL custom nodes should be **auto-registered** using the `@register_node()` decorator for consistency, discoverability, and to enable SDK features like `add_workflow_inputs()`.

**Why Auto-Register All Custom Nodes:**
1. **Consistency**: All nodes follow the same pattern
2. **SDK Features**: Enables `add_workflow_inputs()` functionality
3. **Zero Warnings**: No "Alternative API" warnings
4. **Discoverability**: Nodes can be found in NodeRegistry
5. **Testing**: Simplifies test setup and node discovery
6. **Future-Proofing**: SDK may add more registry-based features

### **Registration Decision Matrix**

| **Use Case** | **Register?** | **Rationale** |
|--------------|---------------|---------------|
| **ALL Custom Nodes** | ✅ Yes | Standard pattern for consistency |
| **Module-Specific Nodes** | ✅ Yes | Enables SDK features |
| **Shared Utility Nodes** | ✅ Yes | Cross-module reusability |
| **SDK Extensions** | ✅ Yes | Framework integration |
| **Test Fixtures** | ✅ Yes | Test infrastructure needs |
| **Zero-Warning Requirement** | ✅ Yes | Enterprise policy compliance |

### **Standard Registration Pattern for ALL Custom Nodes**

**MANDATORY Pattern (Updated 2025-07-22):**
```python
# nodes/user_processor.py
from kailash.nodes.base import register_node, Node

@register_node()  # REQUIRED for ALL custom nodes
class UserProcessorNode(Node):
    """All custom nodes MUST use @register_node() decorator."""
    pass

# Usage in workflow - use string reference
workflow.add_node("UserProcessorNode", "processor", {})  # No warning
```

**2. Shared Utility Node (Standard Pattern):**
```python
# shared/nodes/audit_logger.py
from kailash.nodes.base import register_node

@register_node()
class AuditLoggerNode(Node):
    """Standard pattern - all nodes registered."""
    pass

# Usage in any module
workflow.add_node("AuditLoggerNode", "logger", {})  # No warning
```

**3. Test Fixture Node (Standard Pattern):**
```python
# tests/fixtures/test_nodes.py
from kailash.nodes.base import register_node

@register_node()
class TestNode(Node):
    """Test nodes also use standard pattern."""
    pass

# Usage in tests
workflow.add_node("TestNode", "test_node", {})  # No warning
```

### **Best Practices Summary (Updated 2025-07-22)**

**Standard Pattern for ALL Custom Nodes:**
```python
# ✅ MANDATORY Pattern
from kailash.nodes.base import register_node

@register_node()
class MyCustomNode(Node):
    """All custom nodes MUST have @register_node() decorator."""
    def execute(self, **kwargs):
        # Implementation
        pass

# Usage - always use string reference
workflow.add_node("MyCustomNode", "node_id", {})  # No warning
```

**Migration Pattern for Legacy Unregistered Nodes:**
```python
# Step 1: Add the decorator to existing node
from kailash.nodes.base import register_node

@register_node()  # ADD THIS LINE
class LegacyCustomNode(Node):
    """Legacy node now follows standard pattern."""
    pass

# Step 2: Update workflow usage
# OLD: workflow.add_node(LegacyCustomNode, "node_id", {})
# NEW: workflow.add_node("LegacyCustomNode", "node_id", {})
```

**Complete Custom Node Template:**
```python
from kailash.nodes.base import register_node, Node
from typing import Dict, Any

@register_node()  # MANDATORY
class TPCCustomNode(Node):
    """Standard custom node implementation."""

    def __init__(self, **kwargs):
        # Set attributes BEFORE super().__init__()
        self.custom_param = kwargs.get("custom_param", "default")
        super().__init__(**kwargs)

    def get_parameters(self):
        """Declare expected parameters."""
        return {
            "input_data": NodeParameter(type=dict, required=True),
            "custom_param": NodeParameter(type=str, required=False, default="default")
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        # Implementation
        return {"result": "success"}
```

## Conclusion

Building enterprise-grade custom nodes for the Kailash SDK requires understanding the **fundamental distinction between SDK nodes and custom nodes**. The key principles are:

1. **🚨 CRITICAL**: Use class references for custom nodes, string references for SDK nodes
2. **Always declare parameters explicitly** in `get_parameters()`
3. **🚨 CRITICAL**: Register parameter contracts using `get_parameter_contract()` method
4. **Accept or suppress the expected warning** for custom nodes
5. **Follow enterprise security patterns** with validation and governance
6. **Create workflow-specific entry nodes** rather than universal ones
7. **Test parameter flow thoroughly** in both unit and integration tests
8. **Use parameter contracts** for type safety and documentation

This approach ensures your custom nodes integrate seamlessly with the SDK while maintaining enterprise security and compliance standards.

---

**Contact**: TPC Development Team
**Version**: 3.0 (Gold Standard)
**Based on**: Kailash SDK v0.7.0 + Root Cause Analysis
**Replaces**: All previous custom node documentation
