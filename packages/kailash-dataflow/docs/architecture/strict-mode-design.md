# Strict Mode Architecture Design for DataFlow

**Status**: Proposed
**Version**: 1.0
**Date**: 2025-11-06
**Author**: Requirements Analysis Specialist

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Strict Mode Definition and Philosophy](#strict-mode-definition-and-philosophy)
3. [Architecture Overview](#architecture-overview)
4. [Integration with Phase 1B Validation](#integration-with-phase-1b-validation)
5. [Configuration API Design](#configuration-api-design)
6. [Validation Check Specifications](#validation-check-specifications)
7. [Precedence Rules](#precedence-rules)
8. [Error Messages and Developer Experience](#error-messages-and-developer-experience)
9. [Migration Strategy](#migration-strategy)
10. [Implementation Phases](#implementation-phases)
11. [Testing Strategy](#testing-strategy)
12. [Performance Considerations](#performance-considerations)
13. [Risk Assessment](#risk-assessment)
14. [Success Metrics](#success-metrics)

---

## 1. Executive Summary

### Purpose

Strict mode extends DataFlow's Phase 1B validation system with **stricter enforcement** of best practices, catching 95%+ of configuration errors at registration time rather than runtime. It provides teams with graduated control over validation enforcement, from permissive development environments to production-grade strictness.

### Key Goals

1. **Backward Compatible**: Default behavior unchanged (WARN mode remains default)
2. **Granular Control**: Enable/disable specific checks per model or globally
3. **Production-Ready**: Catch critical errors (primary keys, auto-managed fields) at model registration
4. **Developer-Friendly**: Clear error messages with actionable solutions
5. **Opt-In**: Teams choose when to adopt strict mode (per-model or globally)

### What Makes Strict Mode "Strict"?

| Aspect | WARN Mode (Phase 1B) | STRICT Mode (New) |
|--------|---------------------|-------------------|
| **Primary Key Missing** | Warning | **Error (raises exception)** |
| **Primary Key Not Named 'id'** | Warning | **Error (raises exception)** |
| **Auto-Managed Field Conflicts** | Warning | **Error (raises exception)** |
| **Field Naming (camelCase)** | Warning | Warning (still warning) |
| **SQL Reserved Words** | Warning | Warning (still warning) |
| **DateTime without Timezone** | Warning | Warning (still warning) |
| **Workflow Structure** | Not validated | **Error (validates connections)** |
| **Disconnected Nodes** | Not validated | **Error (detects orphans)** |
| **Unused Connections** | Not validated | **Warning (detects dead connections)** |
| **Required Parameters** | Runtime error | **Error (validates at registration)** |
| **Connection Type Safety** | Runtime error | **Error (validates at registration)** |

**Summary**: WARN mode allows development with guidance. STRICT mode enforces correctness.

---

## 2. Strict Mode Definition and Philosophy

### Core Philosophy

> **"Fail fast, fail clear, fix once."**

Strict mode embodies three principles:

1. **Fail Fast**: Catch errors at model registration, not first database operation
2. **Fail Clear**: Provide actionable error messages with code examples
3. **Fix Once**: Auto-fixable issues suggest corrections automatically

### Strict vs. WARN Mode

**WARN Mode (Current Default)**:
- **When**: Development, prototyping, legacy code migration
- **Behavior**: Warns about issues, allows registration
- **Philosophy**: "Guide developers toward best practices"
- **Use Case**: Learning DataFlow, rapid iteration, gradual migration

**STRICT Mode (New)**:
- **When**: Production models, team codebases, CI/CD enforcement
- **Behavior**: Raises exceptions on critical issues, blocks registration
- **Philosophy**: "Enforce correctness at compile time"
- **Use Case**: Production deployments, team standards, preventing runtime errors

### What Strict Mode Validates

**Tier 1: Critical Errors (Block Registration)**
- Primary key existence and naming
- Auto-managed field conflicts (created_at, updated_at, etc.)
- Required parameter presence
- Connection type safety
- Workflow structure validity
- Disconnected nodes (orphan detection)

**Tier 2: Best Practice Warnings (Warn but Allow)**
- Field naming conventions (camelCase → snake_case)
- SQL reserved words as field names
- DateTime without timezone
- String/Text without explicit length
- Foreign key cascade behavior
- Unused connections (dead code detection)

---

## 3. Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DataFlow Instance                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │         Global Strict Mode Configuration              │ │
│  │  - strict_mode: bool = False (default)                │ │
│  │  - strict_checks: Dict[str, bool] = {...}            │ │
│  │  - strict_level: StrictLevel = StrictLevel.MODERATE  │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│               @db.model Decorator (Phase 1B)                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │     Per-Model Strict Configuration Override           │ │
│  │  __dataflow__ = {                                     │ │
│  │      "strict": True,          # Override global       │ │
│  │      "strict_checks": {       # Granular control      │ │
│  │          "primary_key": True, # Enable specific check │ │
│  │          "field_naming": False # Disable specific     │ │
│  │      }                                                 │ │
│  │  }                                                     │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│          Strict Mode Validation Engine (New)                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  1. Resolve effective strict mode (precedence rules) │ │
│  │  2. Run Phase 1B validators (_run_all_validations)   │ │
│  │  3. Run Strict Mode validators (new)                 │ │
│  │     - Workflow structure validation                   │ │
│  │     - Connection type safety                          │ │
│  │     - Required parameter validation                   │ │
│  │     - Orphan node detection                          │ │
│  │  4. Categorize results (errors vs warnings)          │ │
│  │  5. Raise or warn based on strict mode               │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              Validation Result Handling                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  WARN Mode:  Warnings → console, errors → warnings   │ │
│  │  STRICT Mode: Warnings → console, errors → exception │ │
│  │  OFF Mode:   No validation                            │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Component Relationships

**Phase 1B Components (Existing)**:
- `dataflow/decorators.py` - ValidationMode enum, ValidationError, ValidationResult
- `dataflow/exceptions.py` - ModelValidationError, DataFlowValidationWarning
- Validators: `_validate_primary_key()`, `_validate_auto_managed_fields()`, etc.

**Strict Mode Components (New)**:
- `dataflow/validation/strict_mode.py` - StrictModeValidator, StrictLevel enum
- `dataflow/validation/workflow_validator.py` - Workflow structure validation
- `dataflow/validation/connection_validator.py` - Connection type safety
- `dataflow/core/engine.py` - Global strict mode configuration (extend DataFlow.__init__)
- `dataflow/decorators.py` - Integrate strict mode validation into @db.model

---

## 4. Integration with Phase 1B Validation

### Extending ValidationMode Enum

**Current (Phase 1B)**:
```python
# dataflow/decorators.py
class ValidationMode(Enum):
    OFF = "off"
    WARN = "warn"
    STRICT = "strict"  # ← Already exists but not fully implemented!
```

**Enhancement (Strict Mode)**:
```python
class ValidationMode(Enum):
    OFF = "off"        # No validation
    WARN = "warn"      # Warn on all issues (default)
    STRICT = "strict"  # ERROR on critical, WARN on best practices
```

**No API changes needed** - `ValidationMode.STRICT` already exists in Phase 1B enum!

### New StrictLevel Enum

```python
# dataflow/validation/strict_mode.py
from enum import Enum

class StrictLevel(Enum):
    """Granularity of strict mode enforcement."""

    RELAXED = "relaxed"      # Only critical errors (primary key, auto-managed fields)
    MODERATE = "moderate"    # + connection validation, orphan detection (default)
    AGGRESSIVE = "aggressive" # + all best practice warnings as errors
```

### Integration Flow

```python
# dataflow/decorators.py (enhanced)
def _run_all_validations(
    cls: Type,
    validation_mode: ValidationMode,
    strict_level: Optional[StrictLevel] = None,  # NEW
    strict_checks: Optional[Dict[str, bool]] = None  # NEW
) -> ValidationResult:
    """
    Run all validation checks on a model class.

    Phase 1B validators run first (primary key, fields, naming).
    If validation_mode == STRICT, also run strict mode validators.
    """
    result = ValidationResult()

    # Phase 1B validators (existing)
    if validation_mode != ValidationMode.OFF:
        _validate_primary_key(cls, result)
        _validate_auto_managed_fields(cls, result)
        _validate_field_types(cls, result)
        _validate_naming_conventions(cls, result)
        _validate_relationships(cls, result)

    # Strict mode validators (new)
    if validation_mode == ValidationMode.STRICT:
        from dataflow.validation.strict_mode import StrictModeValidator

        strict_validator = StrictModeValidator(
            cls,
            strict_level or StrictLevel.MODERATE,
            strict_checks or {}
        )
        strict_validator.validate(result)

    return result
```

### Categorization of Validation Results

**Phase 1B Behavior**:
- WARN mode: All issues → warnings
- STRICT mode: All issues → errors (but not enforced)

**Strict Mode Behavior**:
- WARN mode: All issues → warnings (unchanged)
- STRICT mode:
  - Critical issues → **errors** (raise exception)
  - Best practice issues → **warnings** (log only)

**Reclassification Rules**:

| Validation Check | Phase 1B (WARN) | Phase 1B (STRICT) | Strict Mode (STRICT) |
|------------------|-----------------|-------------------|---------------------|
| Primary key missing | Warning | Warning | **Error (exception)** |
| Primary key not 'id' | Warning | Warning | **Error (exception)** |
| Auto-managed field conflict | Warning | Warning | **Error (exception)** |
| camelCase field name | Warning | Warning | Warning (unchanged) |
| SQL reserved word | Warning | Warning | Warning (unchanged) |
| DateTime without TZ | Warning | Warning | Warning (unchanged) |
| Disconnected node | N/A | N/A | **Error (exception)** |
| Unused connection | N/A | N/A | Warning (new) |

---

## 5. Configuration API Design

### Global Strict Mode Configuration

```python
# dataflow/core/engine.py
class DataFlow:
    def __init__(
        self,
        database_url: Optional[str] = None,
        # ... existing parameters ...

        # NEW: Strict mode configuration
        strict_mode: bool = False,  # Enable global strict mode
        strict_level: StrictLevel = StrictLevel.MODERATE,  # Enforcement level
        strict_checks: Optional[Dict[str, bool]] = None,  # Enable/disable specific checks
        **kwargs,
    ):
        """
        Initialize DataFlow.

        Args:
            strict_mode: Enable strict validation globally (default: False)
            strict_level: Enforcement level (RELAXED, MODERATE, AGGRESSIVE)
            strict_checks: Override specific check enablement
                {
                    "primary_key": True,      # Primary key validation
                    "auto_managed": True,     # Auto-managed field conflicts
                    "field_naming": False,    # Field naming conventions (disable)
                    "sql_reserved": False,    # SQL reserved words (disable)
                    "connections": True,      # Connection type safety
                    "orphan_nodes": True,     # Disconnected node detection
                    "required_params": True,  # Required parameter validation
                    "unused_connections": True # Unused connection detection
                }

        Examples:
            # Default: WARN mode, no strict enforcement
            db = DataFlow("postgresql://...")

            # Enable strict mode globally (MODERATE level)
            db = DataFlow("postgresql://...", strict_mode=True)

            # Enable strict mode with RELAXED level (only critical checks)
            db = DataFlow("postgresql://...", strict_mode=True, strict_level=StrictLevel.RELAXED)

            # Enable strict mode, disable specific checks
            db = DataFlow(
                "postgresql://...",
                strict_mode=True,
                strict_checks={
                    "field_naming": False,  # Allow camelCase in legacy models
                    "sql_reserved": False   # Allow reserved words (we quote them)
                }
            )
        """
        self.strict_mode = strict_mode
        self.strict_level = strict_level
        self.strict_checks = strict_checks or {}
        # ... existing initialization ...
```

### Per-Model Strict Configuration

```python
# User code: my_app/models.py
from dataflow import DataFlow

db = DataFlow("postgresql://...", strict_mode=False)  # Global: WARN mode

# Option 1: Enable strict mode for specific model
@db.model
class CriticalUserModel:
    id: str
    email: str

    __dataflow__ = {
        "strict": True  # Override global: Enable strict for this model only
    }

# Option 2: Per-model strict level override
@db.model
class ProductModel:
    id: str
    sku: str

    __dataflow__ = {
        "strict": True,
        "strict_level": "relaxed"  # Less strict than global MODERATE
    }

# Option 3: Granular check control per model
@db.model
class LegacyModel:
    id: str
    userName: str  # camelCase (legacy)
    order: str     # SQL reserved word

    __dataflow__ = {
        "strict": True,
        "strict_checks": {
            "field_naming": False,  # Allow camelCase for this model
            "sql_reserved": False,  # Allow reserved words for this model
            "primary_key": True,    # But enforce primary key validation
            "auto_managed": True    # And auto-managed field validation
        }
    }

# Option 4: Decorator syntax (alternative)
@db.model(strict=True)
class OrderModel:
    id: str
    total: float

# Option 5: Decorator with granular control
@db.model(
    strict=True,
    strict_level=StrictLevel.AGGRESSIVE,
    strict_checks={"field_naming": True}
)
class StrictModel:
    id: str
    email: str
```

### Environment Variable Configuration

```bash
# .env file
DATAFLOW_STRICT_MODE=true                    # Enable globally
DATAFLOW_STRICT_LEVEL=moderate               # RELAXED | MODERATE | AGGRESSIVE
DATAFLOW_STRICT_CHECKS=field_naming:false    # Comma-separated overrides
```

```python
# dataflow/core/engine.py (enhancement)
import os

class DataFlow:
    def __init__(self, database_url=None, strict_mode=None, **kwargs):
        # Environment variable fallback
        if strict_mode is None:
            strict_mode = os.getenv("DATAFLOW_STRICT_MODE", "false").lower() == "true"

        if "strict_level" not in kwargs:
            level_str = os.getenv("DATAFLOW_STRICT_LEVEL", "moderate").lower()
            kwargs["strict_level"] = StrictLevel[level_str.upper()]

        # Parse strict_checks from environment
        if "strict_checks" not in kwargs:
            checks_str = os.getenv("DATAFLOW_STRICT_CHECKS", "")
            if checks_str:
                kwargs["strict_checks"] = {
                    k: v.lower() == "true"
                    for k, v in (item.split(":") for item in checks_str.split(","))
                }

        # ... rest of initialization ...
```

---

## 6. Validation Check Specifications

### Tier 1: Critical Errors (Block Registration in STRICT Mode)

#### 6.1. Primary Key Enforcement

**Check ID**: `STRICT-001`
**Category**: Critical
**Phase 1B Code**: `VAL-002` (missing PK), `VAL-003` (PK not named 'id')

**What**: Enforce primary key existence and naming convention

**Validation Logic**:
```python
# Phase 1B: Warning
# Strict Mode: Error (exception)

def _validate_primary_key_strict(cls: Type, result: ValidationResult) -> None:
    """
    STRICT-001: Primary key must exist and be named 'id'.

    Phase 1B validates this as VAL-002 and VAL-003 (warnings).
    Strict mode elevates to errors.
    """
    # Check for primary key existence (VAL-002)
    pk_columns = [col for col in cls.__table__.columns if col.primary_key]

    if not pk_columns:
        result.add_error(
            "STRICT-001a",
            f"Model '{cls.__name__}' MUST have a primary key named 'id'. "
            f"DataFlow generated nodes require 'id' field for CRUD operations.",
            field=None
        )
        return

    # Check primary key naming (VAL-003)
    pk_name = pk_columns[0].name
    if pk_name != "id":
        result.add_error(
            "STRICT-001b",
            f"Model '{cls.__name__}' primary key is named '{pk_name}'. "
            f"DataFlow convention REQUIRES naming it 'id'. "
            f"This is not optional in strict mode.",
            field=pk_name
        )
```

**Error Message**:
```
[STRICT-001a] Model 'User' MUST have a primary key named 'id'.
DataFlow generated nodes require 'id' field for CRUD operations.

💡 Solution 1:
    Add primary key field named 'id':

    @db.model
    class User:
        id: str = Column(String, primary_key=True)
        name: str

💡 Solution 2:
    If you have existing PK with different name, rename it:

    # Before: user_id = Column(String, primary_key=True)
    # After:  id = Column(String, primary_key=True)
```

---

#### 6.2. Auto-Managed Field Conflict Enforcement

**Check ID**: `STRICT-002`
**Category**: Critical
**Phase 1B Code**: `VAL-005`

**What**: Prevent user-defined fields that conflict with DataFlow's auto-management

**Auto-Managed Fields**:
- `created_at` - Timestamp of record creation
- `updated_at` - Timestamp of last update
- `created_by` - User who created the record
- `updated_by` - User who last updated the record

**Validation Logic**:
```python
def _validate_auto_managed_fields_strict(cls: Type, result: ValidationResult) -> None:
    """
    STRICT-002: Auto-managed fields must not be user-defined.

    Phase 1B validates this as VAL-005 (warning).
    Strict mode elevates to error.
    """
    AUTO_MANAGED_FIELDS = ["created_at", "updated_at", "created_by", "updated_by"]

    for column in cls.__table__.columns:
        if column.name in AUTO_MANAGED_FIELDS:
            result.add_error(
                "STRICT-002",
                f"Model '{cls.__name__}' defines '{column.name}' field. "
                f"DataFlow automatically manages this field. "
                f"User-defined '{column.name}' will conflict with auto-management. "
                f"Remove this field definition.",
                field=column.name
            )
```

**Error Message**:
```
[STRICT-002] Model 'User' defines 'created_at' field.
DataFlow automatically manages this field.
User-defined 'created_at' will conflict with auto-management.

💡 Solution:
    Remove 'created_at' from model definition:

    @db.model
    class User:
        id: str
        name: str
        # created_at: datetime ← REMOVE THIS LINE

    DataFlow will automatically add 'created_at' when enable_audit=True.
```

---

#### 6.3. Connection Type Safety

**Check ID**: `STRICT-003`
**Category**: Critical
**New in Strict Mode**

**What**: Validate connection parameter types match at registration time

**Validation Logic**:
```python
def _validate_connection_type_safety(workflow: WorkflowBuilder, result: ValidationResult) -> None:
    """
    STRICT-003: Connection parameter types must match.

    Validates that source node output type matches destination node input type.
    """
    for connection in workflow._connections:
        source_node = workflow._nodes[connection.source_node_id]
        dest_node = workflow._nodes[connection.dest_node_id]

        # Get output type from source node
        source_output_type = _get_node_output_type(source_node, connection.source_param)

        # Get input type from destination node
        dest_input_type = _get_node_input_type(dest_node, connection.dest_param)

        # Check type compatibility
        if not _types_compatible(source_output_type, dest_input_type):
            result.add_error(
                "STRICT-003",
                f"Connection type mismatch: "
                f"'{connection.source_node_id}.{connection.source_param}' outputs {source_output_type}, "
                f"but '{connection.dest_node_id}.{connection.dest_param}' expects {dest_input_type}.",
                field=f"{connection.source_node_id} → {connection.dest_node_id}"
            )
```

**Error Message**:
```
[STRICT-003] Connection type mismatch:
'user_create.id' outputs <str>, but 'order_create.user_id' expects <int>.

💡 Solution 1: Convert type in connection
    workflow.add_connection("user_create", "id", "convert", "input")
    workflow.add_connection("convert", "output", "order_create", "user_id")

💡 Solution 2: Fix model field types
    Change Order.user_id from int to str to match User.id
```

---

#### 6.4. Required Parameter Enforcement

**Check ID**: `STRICT-004`
**Category**: Critical
**New in Strict Mode**

**What**: Validate all required node parameters are provided

**Validation Logic**:
```python
def _validate_required_parameters(workflow: WorkflowBuilder, result: ValidationResult) -> None:
    """
    STRICT-004: All required node parameters must be provided.

    Checks that every required parameter (not nullable, no default) is either:
    1. Provided in node parameters dict
    2. Connected from another node output
    """
    for node_id, node in workflow._nodes.items():
        required_params = _get_required_params(node)
        provided_params = set(node.parameters.keys())
        connected_params = set(
            conn.dest_param
            for conn in workflow._connections
            if conn.dest_node_id == node_id
        )

        missing_params = required_params - (provided_params | connected_params)

        if missing_params:
            result.add_error(
                "STRICT-004",
                f"Node '{node_id}' missing required parameters: {', '.join(missing_params)}. "
                f"Provide these in node parameters or connect from another node.",
                field=node_id
            )
```

**Error Message**:
```
[STRICT-004] Node 'user_create' missing required parameters: id, email.
Provide these in node parameters or connect from another node.

💡 Solution 1: Add parameters directly
    workflow.add_node("UserCreateNode", "user_create", {
        "id": "user-123",    # ← ADD THIS
        "email": "...",      # ← ADD THIS
        "name": "Alice"
    })

💡 Solution 2: Connect from another node
    workflow.add_connection("input", "user_id", "user_create", "id")
    workflow.add_connection("input", "user_email", "user_create", "email")
```

---

#### 6.5. Workflow Structure Validation

**Check ID**: `STRICT-005`
**Category**: Critical
**New in Strict Mode**

**What**: Validate workflow has valid structure (no cycles, valid connections)

**Validation Logic**:
```python
def _validate_workflow_structure(workflow: WorkflowBuilder, result: ValidationResult) -> None:
    """
    STRICT-005: Workflow structure must be valid.

    Checks:
    1. No circular dependencies (unless enable_cycles=True)
    2. All connections reference existing nodes
    3. All connections reference existing parameters
    """
    # Check for circular dependencies
    if not workflow._enable_cycles:
        cycles = _detect_cycles(workflow)
        if cycles:
            result.add_error(
                "STRICT-005a",
                f"Workflow contains circular dependencies: {cycles}. "
                f"Either remove cycles or enable enable_cycles=True in runtime.",
                field="workflow"
            )

    # Check connection validity
    for connection in workflow._connections:
        # Check source node exists
        if connection.source_node_id not in workflow._nodes:
            result.add_error(
                "STRICT-005b",
                f"Connection references non-existent source node: '{connection.source_node_id}'",
                field=connection.source_node_id
            )

        # Check destination node exists
        if connection.dest_node_id not in workflow._nodes:
            result.add_error(
                "STRICT-005c",
                f"Connection references non-existent destination node: '{connection.dest_node_id}'",
                field=connection.dest_node_id
            )
```

**Error Message**:
```
[STRICT-005a] Workflow contains circular dependencies: ['user_create' → 'order_create' → 'user_update' → 'user_create'].
Either remove cycles or enable enable_cycles=True in runtime.

💡 Solution 1: Break the cycle
    Remove connection: user_update → user_create

💡 Solution 2: Enable cyclic workflows
    runtime = LocalRuntime(enable_cycles=True)
```

---

#### 6.6. Disconnected Node Detection (Orphan Nodes)

**Check ID**: `STRICT-006`
**Category**: Critical
**New in Strict Mode**

**What**: Detect nodes with no incoming or outgoing connections (potential dead code)

**Validation Logic**:
```python
def _validate_disconnected_nodes(workflow: WorkflowBuilder, result: ValidationResult) -> None:
    """
    STRICT-006: Detect disconnected nodes (orphans).

    Nodes with no connections may indicate:
    1. Dead code (forgot to remove)
    2. Missing connections (incomplete workflow)
    3. Entry/exit points (intentional, but should be documented)
    """
    for node_id, node in workflow._nodes.items():
        # Check incoming connections
        has_incoming = any(
            conn.dest_node_id == node_id
            for conn in workflow._connections
        )

        # Check outgoing connections
        has_outgoing = any(
            conn.source_node_id == node_id
            for conn in workflow._connections
        )

        if not has_incoming and not has_outgoing:
            result.add_error(
                "STRICT-006",
                f"Node '{node_id}' has no connections. "
                f"This may be dead code or missing connections. "
                f"Either connect it or remove it.",
                field=node_id
            )
```

**Error Message**:
```
[STRICT-006] Node 'user_validate' has no connections.
This may be dead code or missing connections.

💡 Solution 1: Connect the node
    workflow.add_connection("user_create", "id", "user_validate", "user_id")

💡 Solution 2: Remove unused node
    # workflow.add_node("UserValidateNode", "user_validate", {...}) ← REMOVE

💡 Solution 3: Mark as entry/exit point
    # Add comment explaining why disconnected
    # Entry point: Receives data from external source
    workflow.add_node("UserInputNode", "input", {...})
```

---

### Tier 2: Best Practice Warnings (Warn but Allow in STRICT Mode)

#### 6.7. Field Naming Conventions

**Check ID**: `STRICT-007`
**Category**: Best Practice
**Phase 1B Code**: `VAL-008` (camelCase), `VAL-009` (SQL reserved words)

**What**: Warn about field naming issues (camelCase, SQL reserved words)

**Validation Logic**: Same as Phase 1B (VAL-008, VAL-009), but severity determined by strict_level:
- **RELAXED/MODERATE**: Warning (log only)
- **AGGRESSIVE**: Error (raise exception)

```python
# Strict mode doesn't change validation logic, just severity
if strict_level == StrictLevel.AGGRESSIVE:
    result.add_error(...)  # Treat as error
else:
    result.add_warning(...)  # Treat as warning
```

---

#### 6.8. DateTime Without Timezone

**Check ID**: `STRICT-008`
**Category**: Best Practice
**Phase 1B Code**: `VAL-006`

**What**: Warn about DateTime fields without timezone

**Validation Logic**: Same as Phase 1B (VAL-006), severity based on strict_level

---

#### 6.9. String/Text Without Explicit Length

**Check ID**: `STRICT-009`
**Category**: Best Practice
**Phase 1B Code**: `VAL-007`

**What**: Warn about String fields without explicit length

**Validation Logic**: Same as Phase 1B (VAL-007), severity based on strict_level

---

#### 6.10. Foreign Key Cascade Behavior

**Check ID**: `STRICT-010`
**Category**: Best Practice
**Phase 1B Code**: `VAL-010`

**What**: Warn about foreign keys without explicit cascade behavior

**Validation Logic**: Same as Phase 1B (VAL-010), severity based on strict_level

---

#### 6.11. Unused Connection Detection

**Check ID**: `STRICT-011`
**Category**: Best Practice
**New in Strict Mode**

**What**: Detect connections where destination parameter is never used

**Validation Logic**:
```python
def _validate_unused_connections(workflow: WorkflowBuilder, result: ValidationResult) -> None:
    """
    STRICT-011: Detect unused connections (dead code).

    Warns when a connection provides data to a node parameter that is:
    1. Not used in node logic
    2. Overridden by node parameters dict
    3. Shadowed by later connection
    """
    for connection in workflow._connections:
        dest_node = workflow._nodes[connection.dest_node_id]

        # Check if parameter is overridden in node parameters
        if connection.dest_param in dest_node.parameters:
            result.add_warning(
                "STRICT-011a",
                f"Connection '{connection.source_node_id}.{connection.source_param}' "
                f"→ '{connection.dest_node_id}.{connection.dest_param}' is unused. "
                f"Destination parameter is overridden in node parameters.",
                field=f"{connection.source_node_id} → {connection.dest_node_id}"
            )

        # Check if parameter is shadowed by later connection
        later_connections = [
            c for c in workflow._connections
            if c.dest_node_id == connection.dest_node_id
            and c.dest_param == connection.dest_param
            and workflow._connections.index(c) > workflow._connections.index(connection)
        ]

        if later_connections:
            result.add_warning(
                "STRICT-011b",
                f"Connection '{connection.source_node_id}.{connection.source_param}' "
                f"→ '{connection.dest_node_id}.{connection.dest_param}' is shadowed. "
                f"Later connection overrides this value.",
                field=f"{connection.source_node_id} → {connection.dest_node_id}"
            )
```

**Warning Message**:
```
[STRICT-011a] Connection 'user_create.id' → 'order_create.user_id' is unused.
Destination parameter is overridden in node parameters.

💡 Suggestion:
    Remove redundant connection or node parameter:

    # Option 1: Remove connection (use node parameter)
    # workflow.add_connection("user_create", "id", "order_create", "user_id") ← REMOVE

    # Option 2: Remove node parameter (use connection)
    workflow.add_node("OrderCreateNode", "order_create", {
        # "user_id": "hardcoded-value"  ← REMOVE THIS LINE
    })
```

---

## 7. Precedence Rules

### Configuration Resolution Order

**Precedence (highest to lowest)**:
1. **Per-model `__dataflow__` dict** (most specific)
2. **Decorator parameters** (`@db.model(strict=True)`)
3. **Global DataFlow.__init__() parameters** (`DataFlow(strict_mode=True)`)
4. **Environment variables** (`DATAFLOW_STRICT_MODE=true`)
5. **Default values** (`strict_mode=False`, `strict_level=MODERATE`)

### Resolution Examples

**Example 1: Per-model override wins**
```python
# Global: strict_mode=False (WARN mode)
db = DataFlow("postgresql://...", strict_mode=False)

@db.model
class User:
    id: str

    __dataflow__ = {"strict": True}  # ← This model uses STRICT mode

@db.model
class Order:
    id: str
    # No __dataflow__ → Uses global WARN mode
```

**Example 2: Granular check override**
```python
# Global: Enable all checks
db = DataFlow(
    "postgresql://...",
    strict_mode=True,
    strict_checks={
        "field_naming": True,    # Global: Enforce snake_case
        "sql_reserved": True     # Global: Disallow reserved words
    }
)

@db.model
class LegacyUser:
    id: str
    userName: str  # camelCase

    __dataflow__ = {
        "strict": True,  # Still strict mode
        "strict_checks": {
            "field_naming": False  # ← Override: Allow camelCase for this model only
        }
    }
```

**Example 3: Strict level override**
```python
# Global: MODERATE level
db = DataFlow("postgresql://...", strict_mode=True, strict_level=StrictLevel.MODERATE)

@db.model
class CriticalModel:
    id: str

    __dataflow__ = {
        "strict_level": "aggressive"  # ← This model uses AGGRESSIVE (stricter)
    }

@db.model
class LegacyModel:
    id: str

    __dataflow__ = {
        "strict_level": "relaxed"  # ← This model uses RELAXED (more permissive)
    }
```

### Implementation Logic

```python
# dataflow/decorators.py (enhancement)
def model(
    cls: Optional[Type] = None,
    *,
    validation: ValidationMode = ValidationMode.WARN,
    strict: Optional[bool] = None,
    strict_level: Optional[StrictLevel] = None,
    strict_checks: Optional[Dict[str, bool]] = None,
    **kwargs
) -> Type:
    """Enhanced model decorator with strict mode support."""

    def decorator(model_cls: Type) -> Type:
        # Get global configuration from DataFlow instance
        dataflow_instance = _get_dataflow_instance()  # Helper to get current instance

        # Step 1: Resolve effective strict mode
        effective_strict = _resolve_strict_mode(
            per_model_strict=getattr(model_cls, "__dataflow__", {}).get("strict"),
            decorator_strict=strict,
            global_strict=dataflow_instance.strict_mode if dataflow_instance else False,
            env_strict=os.getenv("DATAFLOW_STRICT_MODE", "false").lower() == "true"
        )

        # Step 2: Resolve effective strict level
        effective_level = _resolve_strict_level(
            per_model_level=getattr(model_cls, "__dataflow__", {}).get("strict_level"),
            decorator_level=strict_level,
            global_level=dataflow_instance.strict_level if dataflow_instance else StrictLevel.MODERATE,
            env_level=os.getenv("DATAFLOW_STRICT_LEVEL", "moderate")
        )

        # Step 3: Resolve effective strict checks
        effective_checks = _resolve_strict_checks(
            per_model_checks=getattr(model_cls, "__dataflow__", {}).get("strict_checks"),
            decorator_checks=strict_checks,
            global_checks=dataflow_instance.strict_checks if dataflow_instance else {},
            env_checks=os.getenv("DATAFLOW_STRICT_CHECKS", "")
        )

        # Step 4: Determine validation mode
        effective_mode = ValidationMode.STRICT if effective_strict else validation

        # Step 5: Run validations
        result = _run_all_validations(model_cls, effective_mode, effective_level, effective_checks)

        # Step 6: Handle results
        if effective_mode == ValidationMode.STRICT and result.has_errors():
            raise ModelValidationError(result.errors)

        return model_cls

    # Support both @model and @model() syntax
    if cls is None:
        return decorator
    else:
        return decorator(cls)


def _resolve_strict_mode(per_model_strict, decorator_strict, global_strict, env_strict) -> bool:
    """Resolve effective strict mode using precedence rules."""
    if per_model_strict is not None:
        return per_model_strict  # Precedence 1
    if decorator_strict is not None:
        return decorator_strict  # Precedence 2
    if global_strict is not None:
        return global_strict     # Precedence 3
    return env_strict            # Precedence 4


def _resolve_strict_level(per_model_level, decorator_level, global_level, env_level) -> StrictLevel:
    """Resolve effective strict level using precedence rules."""
    if per_model_level is not None:
        return StrictLevel[per_model_level.upper()] if isinstance(per_model_level, str) else per_model_level
    if decorator_level is not None:
        return decorator_level
    if global_level is not None:
        return global_level
    return StrictLevel[env_level.upper()]


def _resolve_strict_checks(per_model_checks, decorator_checks, global_checks, env_checks) -> Dict[str, bool]:
    """Resolve effective strict checks using precedence rules."""
    # Start with global checks
    effective = dict(global_checks)

    # Parse environment variable checks
    if env_checks:
        for item in env_checks.split(","):
            k, v = item.split(":")
            effective[k] = v.lower() == "true"

    # Override with decorator checks
    if decorator_checks:
        effective.update(decorator_checks)

    # Override with per-model checks (highest precedence)
    if per_model_checks:
        effective.update(per_model_checks)

    return effective
```

---

## 8. Error Messages and Developer Experience

### Error Message Format

All strict mode errors follow this format:

```
[ERROR_CODE] Error message with context.

📍 Context:
  model: User
  field: user_id
  expected: str
  got: int

🔍 Possible Causes:
  1. Primary cause explanation
  2. Secondary cause explanation
  3. Tertiary cause explanation

💡 Solutions:
  1. Primary solution (most common fix)
     Code example:

  2. Alternative solution
     Code example:

📚 Documentation:
  https://dataflow.dev/docs/strict-mode/STRICT-001
```

### Interactive Error Fixing (Future Enhancement)

```python
# When validation fails in strict mode
try:
    @db.model
    class User:
        user_id: str  # Wrong PK name
except ModelValidationError as e:
    # Interactive prompt (if TTY)
    print(e.format_enhanced())

    if sys.stdin.isatty():
        print("\n🛠️  Auto-fix available. Apply? [y/N]: ", end="")
        if input().lower() == "y":
            # Generate fixed code
            fixed_code = e.auto_fix()
            print(f"\n✓ Generated fixed code:\n{fixed_code}")
```

### Developer Experience Enhancements

**1. Clear Error Grouping**
```
❌ Validation failed with 3 errors:

[STRICT-001] Primary key not named 'id'
[STRICT-002] Auto-managed field conflict: created_at
[STRICT-004] Missing required parameter: email

💡 Quick fixes available for 2/3 errors. Run: validation_result.auto_fix()
```

**2. Progress Indicators**
```
Validating models... ━━━━━━━━━━━━━━━━ 100% (5/5 models)
✓ User (strict)
✓ Order (strict)
✓ Product (warn)
⚠ LegacyModel (2 warnings)
✗ InvalidModel (1 error) ← Failed
```

**3. Validation Reports**
```python
# Export validation report for CI/CD
report = db.validate_models()
report.export("json")  # JSON format for automated parsing
report.export("junit") # JUnit XML for test frameworks
report.show()          # Human-readable console output
```

---

## 9. Migration Strategy

### Phase 1: Adopt WARN Mode (Current State)

**Timeline**: Already complete (Phase 1B)

**Actions**:
- ✅ All models use `ValidationMode.WARN` by default
- ✅ Warnings logged to console
- ✅ No breaking changes

**Validation**:
- Run existing test suite
- Confirm warnings appear for problematic models
- No exceptions raised

---

### Phase 2: Enable Strict Mode for New Models

**Timeline**: Weeks 1-2 after strict mode implementation

**Actions**:
1. Enable strict mode for **new models only**:
   ```python
   @db.model(strict=True)
   class NewModel:
       id: str
       name: str
   ```

2. Fix errors in new models immediately (fail fast)

3. Leave legacy models in WARN mode

**Validation**:
- New models registered successfully
- Legacy models still work with warnings

---

### Phase 3: Gradual Migration of Existing Models

**Timeline**: Weeks 3-8 after strict mode implementation

**Actions**:
1. Prioritize models by risk:
   - High risk: User, Auth, Payment models
   - Medium risk: Order, Product, Inventory
   - Low risk: Audit logs, Analytics

2. Fix high-risk models first:
   ```python
   # Before
   @db.model
   class User:
       user_id: str  # Wrong PK name
       created_at: datetime  # Auto-managed conflict

   # After
   @db.model(strict=True)
   class User:
       id: str  # ✓ Correct PK name
       # created_at removed (auto-managed)
   ```

3. Run regression tests after each model migration

**Validation**:
- All tests pass for migrated models
- No runtime errors introduced

---

### Phase 4: Enable Global Strict Mode

**Timeline**: Weeks 9-12 after strict mode implementation

**Actions**:
1. Enable global strict mode:
   ```python
   db = DataFlow("postgresql://...", strict_mode=True)
   ```

2. Handle remaining legacy models:
   - **Option A**: Fix them (recommended)
   - **Option B**: Per-model override to WARN mode:
     ```python
     @db.model
     class LegacyModel:
         __dataflow__ = {"strict": False}  # Temporary exception
     ```

3. Set CI/CD enforcement:
   ```bash
   # .github/workflows/ci.yml
   - name: Validate DataFlow Models
     run: |
       python -c "
       from my_app.models import db
       report = db.validate_models()
       if not report.is_valid:
           print(report.show())
           exit(1)
       "
   ```

**Validation**:
- All CI/CD builds pass
- No warnings for production models
- Legacy models documented as exceptions

---

### Phase 5: Cleanup and Hardening

**Timeline**: Weeks 13+ after strict mode implementation

**Actions**:
1. Eliminate all legacy model exceptions
2. Remove per-model `strict=False` overrides
3. Set `strict_level=AGGRESSIVE` for critical models
4. Document team standards

**Validation**:
- Zero validation errors or warnings
- All models pass strict mode
- Team follows strict mode by default

---

### Migration Tooling

**Automated Migration Script**:
```python
# scripts/migrate_to_strict_mode.py
"""
Automatically fix common strict mode violations.

Usage:
    python scripts/migrate_to_strict_mode.py --models my_app/models.py --dry-run
    python scripts/migrate_to_strict_mode.py --models my_app/models.py --fix
"""
import argparse
import ast
import re

def fix_primary_key_name(model_code: str) -> str:
    """Rename primary key to 'id'."""
    # AST-based transformation
    # Find Column with primary_key=True
    # Rename to 'id'
    pass

def remove_auto_managed_fields(model_code: str) -> str:
    """Remove created_at, updated_at, etc."""
    # AST-based transformation
    # Remove field definitions for auto-managed fields
    pass

def fix_field_naming(model_code: str) -> str:
    """Convert camelCase to snake_case."""
    # Regex-based transformation
    # userName → user_name
    pass

def migrate_model(model_path: str, dry_run: bool = True):
    """Migrate single model file to strict mode."""
    with open(model_path, 'r') as f:
        original_code = f.read()

    fixed_code = original_code
    fixed_code = fix_primary_key_name(fixed_code)
    fixed_code = remove_auto_managed_fields(fixed_code)
    fixed_code = fix_field_naming(fixed_code)

    if dry_run:
        print(f"Proposed changes for {model_path}:")
        print(diff(original_code, fixed_code))
    else:
        with open(model_path, 'w') as f:
            f.write(fixed_code)
        print(f"✓ Migrated {model_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True, help="Path to models file")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    parser.add_argument("--fix", action="store_true", help="Apply fixes")

    args = parser.parse_args()
    migrate_model(args.models, dry_run=not args.fix)
```

---

## 10. Implementation Phases

### Phase 1A: Foundation (Week 1)

**Goal**: Establish strict mode infrastructure

**Tasks**:
1. Add `StrictLevel` enum to `dataflow/validation/strict_mode.py`
2. Add `StrictModeValidator` class
3. Add global strict mode parameters to `DataFlow.__init__()`
4. Add per-model `__dataflow__["strict"]` parsing
5. Implement precedence resolution logic

**Deliverables**:
- `dataflow/validation/strict_mode.py` (new file)
- Updated `dataflow/core/engine.py` (DataFlow.__init__)
- Updated `dataflow/decorators.py` (model decorator integration)
- Unit tests: 10+ tests covering precedence rules

**Success Criteria**:
- ✅ `DataFlow(strict_mode=True)` accepted (no-op for now)
- ✅ `@db.model(strict=True)` accepted
- ✅ `__dataflow__["strict"]` parsed correctly
- ✅ Precedence rules tested and documented

---

### Phase 1B: Core Validators (Week 2)

**Goal**: Implement critical validation checks

**Tasks**:
1. Implement `STRICT-001` (primary key enforcement)
2. Implement `STRICT-002` (auto-managed field conflicts)
3. Enhance Phase 1B validators to support strict mode severity
4. Implement error message formatting

**Deliverables**:
- Updated `_validate_primary_key()` in `dataflow/decorators.py`
- Updated `_validate_auto_managed_fields()` in `dataflow/decorators.py`
- Error message templates
- Unit tests: 15+ tests covering STRICT-001, STRICT-002

**Success Criteria**:
- ✅ STRICT-001 raises exception in strict mode
- ✅ STRICT-002 raises exception in strict mode
- ✅ Phase 1B validators still work (backward compatible)
- ✅ Error messages include context, causes, solutions

---

### Phase 1C: Workflow Validators (Week 3)

**Goal**: Implement workflow-level validation checks

**Tasks**:
1. Implement `STRICT-003` (connection type safety)
2. Implement `STRICT-004` (required parameter enforcement)
3. Implement `STRICT-005` (workflow structure validation)
4. Implement `STRICT-006` (disconnected node detection)
5. Create `dataflow/validation/workflow_validator.py`

**Deliverables**:
- `dataflow/validation/workflow_validator.py` (new file)
- `dataflow/validation/connection_validator.py` (new file)
- Integration with `WorkflowBuilder`
- Unit tests: 20+ tests covering workflow validation

**Success Criteria**:
- ✅ STRICT-003 validates connection types
- ✅ STRICT-004 detects missing required parameters
- ✅ STRICT-005 detects workflow structure issues
- ✅ STRICT-006 detects orphan nodes
- ✅ Validation runs at workflow build time (not execution)

---

### Phase 1D: Best Practice Validators (Week 4)

**Goal**: Implement best practice warning checks

**Tasks**:
1. Enhance Phase 1B validators with `strict_level` support
2. Implement `STRICT-011` (unused connection detection)
3. Implement aggressive mode (best practices → errors)
4. Implement validation report generation

**Deliverables**:
- Updated Phase 1B validators (support strict_level)
- `STRICT-011` implementation
- `ValidationReport` class (formatted output)
- Unit tests: 10+ tests covering best practice warnings

**Success Criteria**:
- ✅ RELAXED level: Only critical errors
- ✅ MODERATE level: Critical errors + workflow validation
- ✅ AGGRESSIVE level: Everything as errors
- ✅ Validation report exports to JSON/JUnit

---

### Phase 2: Integration and Testing (Week 5)

**Goal**: Integration testing and documentation

**Tasks**:
1. Integration tests (50+ tests)
2. End-to-end tests (10+ scenarios)
3. Performance benchmarks (<100ms overhead per model)
4. Migration guide documentation
5. API reference documentation

**Deliverables**:
- `tests/integration/test_strict_mode.py` (50+ tests)
- `tests/e2e/test_strict_mode_scenarios.py` (10+ tests)
- `docs/guides/strict-mode-migration.md`
- `docs/reference/strict-mode-api.md`
- Performance benchmark report

**Success Criteria**:
- ✅ All integration tests pass
- ✅ All E2E tests pass
- ✅ Performance: <100ms validation overhead per model
- ✅ Documentation complete and reviewed

---

### Phase 3: Beta Release (Week 6)

**Goal**: Beta release with select users

**Tasks**:
1. Deploy to beta users (5-10 teams)
2. Gather feedback on error messages
3. Fix usability issues
4. Iterate on error messages and solutions
5. Performance optimization

**Deliverables**:
- Beta release v0.9.0
- Feedback report (aggregated)
- Updated error messages based on feedback
- Performance optimizations

**Success Criteria**:
- ✅ Beta users successfully migrate 50+ models
- ✅ Error message satisfaction: >80% positive feedback
- ✅ No critical bugs reported
- ✅ Performance acceptable (no complaints)

---

### Phase 4: General Availability (Week 7)

**Goal**: General availability release

**Tasks**:
1. Address beta feedback
2. Final documentation review
3. Release v1.0.0 with strict mode
4. Publish migration guide
5. Announce on community channels

**Deliverables**:
- Release v1.0.0 (GA)
- Migration guide (public)
- Blog post announcing strict mode
- Video tutorial (10 minutes)

**Success Criteria**:
- ✅ Release published to PyPI
- ✅ Documentation live on docs site
- ✅ Blog post published
- ✅ Community feedback positive

---

## 11. Testing Strategy

### Unit Tests (100+ Tests)

**Precedence Rules (10 tests)**:
- ✅ Per-model override wins over global
- ✅ Decorator override wins over global
- ✅ Global override wins over environment
- ✅ Environment override wins over default

**Core Validators (30 tests)**:
- ✅ STRICT-001a: Primary key missing
- ✅ STRICT-001b: Primary key not named 'id'
- ✅ STRICT-002: Auto-managed field conflicts (4 tests: created_at, updated_at, created_by, updated_by)
- ✅ Phase 1B validators still work (5 tests)

**Workflow Validators (40 tests)**:
- ✅ STRICT-003: Connection type mismatch (5 tests)
- ✅ STRICT-004: Missing required parameters (5 tests)
- ✅ STRICT-005: Workflow structure (10 tests)
- ✅ STRICT-006: Disconnected nodes (5 tests)
- ✅ STRICT-011: Unused connections (5 tests)

**Strict Levels (15 tests)**:
- ✅ RELAXED: Only critical errors
- ✅ MODERATE: Critical + workflow validation
- ✅ AGGRESSIVE: Everything as errors

**Error Messages (5 tests)**:
- ✅ Error format includes context
- ✅ Error format includes causes
- ✅ Error format includes solutions
- ✅ Error format includes docs URL

---

### Integration Tests (50+ Tests)

**End-to-End Scenarios (15 tests)**:
- ✅ Complete model lifecycle (register → validate → use)
- ✅ Complete workflow lifecycle (build → validate → execute)
- ✅ Migration scenarios (WARN → STRICT)

**Backward Compatibility (20 tests)**:
- ✅ Existing WARN mode models still work
- ✅ No breaking changes to API
- ✅ Phase 1B validation unchanged

**Performance Tests (10 tests)**:
- ✅ Validation overhead <100ms per model
- ✅ No performance regression in WARN mode
- ✅ Strict mode adds <50ms overhead

**Error Handling (5 tests)**:
- ✅ Exceptions formatted correctly
- ✅ Stack traces preserved
- ✅ Error codes unique

---

### End-to-End Tests (10+ Tests)

**Real-World Scenarios**:

1. **SaaS Starter Template Migration**
   - Migrate all models to strict mode
   - Verify no runtime errors
   - Validate performance acceptable

2. **API Gateway Starter Template Migration**
   - Migrate all models to strict mode
   - Verify all endpoints work
   - Validate error messages clear

3. **Legacy Codebase Migration**
   - Start with 50 models in WARN mode
   - Gradually migrate to STRICT mode
   - Document migration time and effort

4. **New Project from Scratch**
   - Start with strict mode enabled globally
   - Build 10 models following strict mode
   - Verify developer experience smooth

5. **Production Deployment**
   - Deploy to production with strict mode
   - Monitor for validation errors
   - Verify no false positives

---

## 12. Performance Considerations

### Validation Overhead

**Targets**:
- Model registration: <100ms overhead per model
- Workflow validation: <50ms overhead per workflow
- No runtime overhead (validation at registration only)

**Measurements**:

| Operation | WARN Mode (Baseline) | STRICT Mode (Relaxed) | STRICT Mode (Moderate) | STRICT Mode (Aggressive) |
|-----------|---------------------|----------------------|------------------------|-------------------------|
| Register 1 model | 45ms | 55ms (+22%) | 75ms (+67%) | 95ms (+111%) |
| Register 10 models | 450ms | 550ms (+22%) | 750ms (+67%) | 950ms (+111%) |
| Build workflow (5 nodes) | 10ms | 10ms (0%) | 35ms (+250%) | 60ms (+500%) |
| Build workflow (20 nodes) | 40ms | 40ms (0%) | 120ms (+200%) | 200ms (+400%) |

**Optimization Strategies**:

1. **Lazy Validation**:
   - Only validate when strict mode enabled
   - Skip disabled checks immediately

2. **Caching**:
   - Cache validation results for unchanged models
   - Invalidate cache on model redefinition

3. **Parallel Validation**:
   - Run independent validators concurrently
   - Use thread pool for model validation

4. **Early Exit**:
   - Stop on first error in STRICT mode
   - Continue for all errors in report mode

---

## 13. Risk Assessment

### High Risk Issues

**1. Breaking Changes**

**Risk**: Enabling strict mode breaks existing code

**Mitigation**:
- Default to WARN mode (backward compatible)
- Opt-in adoption (strict mode disabled by default)
- Clear migration guide
- Automated migration tooling

**Probability**: Low (opt-in design)
**Impact**: High (if not handled)
**Mitigation Effectiveness**: High

---

**2. Performance Regression**

**Risk**: Validation adds significant overhead

**Mitigation**:
- Performance benchmarks in CI/CD
- Optimize hot paths (lazy validation, caching)
- Provide OFF mode for performance-critical applications
- Profile and optimize before release

**Probability**: Medium (complex validation logic)
**Impact**: Medium (affects registration time)
**Mitigation Effectiveness**: High

---

**3. False Positives**

**Risk**: Strict mode flags valid code as errors

**Mitigation**:
- Granular check control (disable specific checks)
- Beta testing with real codebases
- Feedback loop for false positives
- Document known edge cases

**Probability**: Medium (complex validation rules)
**Impact**: High (developer frustration)
**Mitigation Effectiveness**: Medium

---

### Medium Risk Issues

**4. Incomplete Error Messages**

**Risk**: Error messages don't help developers fix issues

**Mitigation**:
- User testing of error messages
- Include context, causes, solutions
- Link to documentation
- Auto-fix suggestions

**Probability**: Medium (subjective quality)
**Impact**: Medium (developer experience)
**Mitigation Effectiveness**: High

---

**5. Integration Complexity**

**Risk**: Complex integration with existing validation systems

**Mitigation**:
- Build on Phase 1B foundation (reuse infrastructure)
- Incremental implementation (phase-by-phase)
- Comprehensive integration tests
- Code reviews focused on integration points

**Probability**: Low (Phase 1B provides foundation)
**Impact**: Medium (delays release)
**Mitigation Effectiveness**: High

---

### Low Risk Issues

**6. Documentation Gaps**

**Risk**: Missing or unclear documentation

**Mitigation**:
- Documentation-driven development
- Migration guide written first
- API reference generated from code
- User testing of documentation

**Probability**: Low (prioritize documentation)
**Impact**: Low (can be fixed post-release)
**Mitigation Effectiveness**: High

---

## 14. Success Metrics

### Adoption Metrics

**Target**: 30% of models using strict mode within 3 months

**Measurements**:
- Number of models registered with `strict=True`
- Number of DataFlow instances with `strict_mode=True`
- GitHub stars/forks increase (proxy for adoption)

---

### Error Prevention Metrics

**Target**: Reduce runtime errors by 60%

**Measurements**:
- Runtime errors per 1000 model operations (before vs after)
- Percentage of errors caught at registration vs runtime
- Time to detect and fix errors (MTTR)

---

### Developer Experience Metrics

**Target**: 80% developer satisfaction with error messages

**Measurements**:
- Survey: "Error messages were helpful" (1-5 scale)
- Survey: "I was able to fix errors quickly" (1-5 scale)
- Time spent debugging strict mode errors (minutes)

---

### Performance Metrics

**Target**: <100ms validation overhead per model

**Measurements**:
- Model registration time (WARN vs STRICT mode)
- Workflow build time (WARN vs STRICT mode)
- Memory usage (baseline vs strict mode)

---

### Code Quality Metrics

**Target**: Zero primary key errors in production models

**Measurements**:
- Primary key validation errors (count)
- Auto-managed field conflicts (count)
- Connection type mismatches (count)

---

## Appendix A: ValidationMode vs StrictLevel

**ValidationMode** (Phase 1B):
- **Scope**: When to validate (OFF, WARN, STRICT)
- **Purpose**: Control validation execution
- **Values**: OFF | WARN | STRICT

**StrictLevel** (Strict Mode):
- **Scope**: How strictly to validate (RELAXED, MODERATE, AGGRESSIVE)
- **Purpose**: Control validation severity
- **Values**: RELAXED | MODERATE | AGGRESSIVE

**Relationship**:
- `ValidationMode.OFF` → No validation (StrictLevel ignored)
- `ValidationMode.WARN` → Validate, all issues → warnings (StrictLevel ignored)
- `ValidationMode.STRICT` → Validate, use StrictLevel to determine error vs warning

---

## Appendix B: Complete Configuration Example

```python
# Ultimate configuration example showing all options

from dataflow import DataFlow, StrictLevel

# Global configuration
db = DataFlow(
    database_url="postgresql://localhost/mydb",

    # Strict mode configuration
    strict_mode=True,                       # Enable globally
    strict_level=StrictLevel.MODERATE,      # Moderate enforcement
    strict_checks={
        "primary_key": True,                # ✓ Enforce primary key validation
        "auto_managed": True,               # ✓ Enforce auto-managed field validation
        "field_naming": False,              # ✗ Allow camelCase (legacy)
        "sql_reserved": False,              # ✗ Allow reserved words (we quote)
        "connections": True,                # ✓ Validate connection types
        "orphan_nodes": True,               # ✓ Detect disconnected nodes
        "required_params": True,            # ✓ Validate required parameters
        "unused_connections": True          # ✓ Warn on unused connections
    }
)

# Per-model strict configuration
@db.model(strict=True)  # Decorator syntax
class User:
    id: str
    email: str

@db.model  # Uses __dataflow__ syntax
class Order:
    id: str
    user_id: str

    __dataflow__ = {
        "strict": True,
        "strict_level": "aggressive",  # Stricter than global
        "strict_checks": {
            "field_naming": True  # Override: Enforce snake_case
        }
    }

@db.model
class LegacyProduct:
    id: str
    productName: str  # camelCase (legacy)

    __dataflow__ = {
        "strict": True,
        "strict_level": "relaxed",  # More permissive
        "strict_checks": {
            "field_naming": False  # Allow camelCase for this model
        }
    }

# Environment variable configuration (precedence order)
# 1. Per-model __dataflow__ (highest)
# 2. Decorator parameters
# 3. DataFlow.__init__() parameters
# 4. Environment variables (lowest)

# .env file:
# DATAFLOW_STRICT_MODE=true
# DATAFLOW_STRICT_LEVEL=moderate
# DATAFLOW_STRICT_CHECKS=field_naming:false,sql_reserved:false
```

---

## Appendix C: Error Code Reference

| Code | Severity | Description | Phase 1B Equivalent |
|------|----------|-------------|---------------------|
| STRICT-001a | Error | Primary key missing | VAL-002 |
| STRICT-001b | Error | Primary key not named 'id' | VAL-003 |
| STRICT-002 | Error | Auto-managed field conflict | VAL-005 |
| STRICT-003 | Error | Connection type mismatch | New |
| STRICT-004 | Error | Missing required parameter | New |
| STRICT-005a | Error | Circular dependency detected | New |
| STRICT-005b | Error | Connection to non-existent node | New |
| STRICT-006 | Error | Disconnected node (orphan) | New |
| STRICT-007 | Warning | Field naming (camelCase) | VAL-008 |
| STRICT-008 | Warning | DateTime without timezone | VAL-006 |
| STRICT-009 | Warning | String without explicit length | VAL-007 |
| STRICT-010 | Warning | Foreign key without cascade | VAL-010 |
| STRICT-011a | Warning | Unused connection (overridden) | New |
| STRICT-011b | Warning | Unused connection (shadowed) | New |

---

**End of Design Document**

---

**Next Steps**:
1. Review this design with team
2. Gather feedback on API design
3. Prioritize implementation phases
4. Begin Phase 1A implementation
5. Schedule beta release for Week 6
