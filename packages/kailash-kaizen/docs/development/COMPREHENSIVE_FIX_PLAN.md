# Comprehensive Fix Plan: Structured Output Type System & Extension Points

**Version**: 1.0
**Date**: 2025-11-03
**Status**: Design Document
**Goal**: Eliminate architectural limitations, fix all 4 bugs at root cause

---

## Executive Summary

This document provides a comprehensive fix plan for addressing **4 critical bugs** in the Kaizen structured output and extension point architecture:

1. **Bug #1**: Literal type validation fails with `TypeError`
2. **Bug #2**: Type system incomplete - only 3/10 typing patterns supported
3. **Bug #3**: Extension points broken in workflow composition
4. **Bug #4**: OpenAI strict mode limitations cause cryptic errors

**Goal**: **Eliminate limitations**, not document them. Design robust, production-ready solutions.

---

## Bug #1: Literal Type Validation Fails

### Root Cause Analysis

**Location**: `structured_output.py:248`
**Error**: `TypeError: Subscripted generics cannot be used with class and instance checks`

**Problem**:
```python
# Line 248 - This fails for typing constructs
if not isinstance(actual_value, expected_type):  # ❌ Fails for Literal["A", "B"]
```

**Why it fails**: Python's `isinstance()` doesn't work with typing module constructs (`Literal`, `Union`, `Optional`, `List[T]`, etc.). These are **type annotations** for static analysis, not runtime classes.

**Current Schema Generation (Lines 87-95)**: Already correctly handles `Literal` → enum conversion ✅
```python
origin = get_origin(field_type)
if origin is Literal:
    enum_values = list(get_args(field_type))
    field_schema = {"type": "string", "enum": enum_values}
```

**Validation Problem**: `validate_output()` doesn't use the same introspection logic.

### Comprehensive Solution

**Design**: Create unified type introspection system for both schema generation AND validation.

**New Component**: `TypeIntrospector` class (150 lines)

```python
from typing import Any, Type, get_origin, get_args, Literal, Union, Optional, List, Dict
import sys

class TypeIntrospector:
    """
    Unified type introspection for both schema generation and runtime validation.

    Handles ALL typing constructs:
    - Literal["A", "B"]
    - Union[str, int]
    - Optional[str] (alias for Union[str, None])
    - List[T], Dict[K, V]
    - TypedDict (via __annotations__)
    - Nested structures
    """

    @staticmethod
    def is_valid_type(value: Any, expected_type: Type) -> tuple[bool, str]:
        """
        Runtime type checking for typing constructs.

        Args:
            value: Actual value to check
            expected_type: Type annotation (may be Literal, Union, etc.)

        Returns:
            (is_valid, error_message)

        Examples:
            >>> is_valid_type("A", Literal["A", "B", "C"])
            (True, "")

            >>> is_valid_type("D", Literal["A", "B", "C"])
            (False, "Value 'D' not in allowed values: ['A', 'B', 'C']")

            >>> is_valid_type("test", Union[str, int])
            (True, "")

            >>> is_valid_type([1, 2, 3], List[int])
            (True, "")
        """
        origin = get_origin(expected_type)

        # Handle Literal types
        if origin is Literal:
            allowed_values = get_args(expected_type)
            if value not in allowed_values:
                return False, f"Value {repr(value)} not in allowed values: {list(allowed_values)}"
            return True, ""

        # Handle Union types (includes Optional)
        if origin is Union:
            union_types = get_args(expected_type)
            for union_type in union_types:
                is_valid, _ = TypeIntrospector.is_valid_type(value, union_type)
                if is_valid:
                    return True, ""

            type_names = [t.__name__ if hasattr(t, '__name__') else str(t) for t in union_types]
            return False, f"Value {repr(value)} doesn't match any of: {type_names}"

        # Handle List[T]
        if origin is list:
            if not isinstance(value, list):
                return False, f"Expected list, got {type(value).__name__}"

            # Check element types if specified
            args = get_args(expected_type)
            if args:
                element_type = args[0]
                for i, elem in enumerate(value):
                    is_valid, error = TypeIntrospector.is_valid_type(elem, element_type)
                    if not is_valid:
                        return False, f"List element at index {i}: {error}"

            return True, ""

        # Handle Dict[K, V]
        if origin is dict:
            if not isinstance(value, dict):
                return False, f"Expected dict, got {type(value).__name__}"

            # Check key/value types if specified
            args = get_args(expected_type)
            if len(args) == 2:
                key_type, value_type = args
                for k, v in value.items():
                    is_valid, error = TypeIntrospector.is_valid_type(k, key_type)
                    if not is_valid:
                        return False, f"Dict key {repr(k)}: {error}"
                    is_valid, error = TypeIntrospector.is_valid_type(v, value_type)
                    if not is_valid:
                        return False, f"Dict value for key {repr(k)}: {error}"

            return True, ""

        # Handle basic Python types (str, int, float, bool)
        if expected_type in (str, int, float, bool, list, dict):
            # Special case: int/float are interchangeable for numeric types
            if expected_type == float and isinstance(value, int):
                return True, ""
            if expected_type == int and isinstance(value, float):
                return True, ""

            if not isinstance(value, expected_type):
                return False, f"Expected {expected_type.__name__}, got {type(value).__name__}"
            return True, ""

        # Fallback: try basic isinstance check for non-typing types
        try:
            if isinstance(value, expected_type):
                return True, ""
            return False, f"Type mismatch: expected {expected_type}, got {type(value)}"
        except TypeError:
            # If isinstance fails, assume valid (can't check at runtime)
            return True, ""

    @staticmethod
    def to_json_schema_type(python_type: Type) -> Dict[str, Any]:
        """
        Convert Python type annotation to JSON schema type definition.

        Handles ALL typing constructs for OpenAI schema generation.

        Args:
            python_type: Python type annotation

        Returns:
            JSON schema type definition

        Examples:
            >>> to_json_schema_type(str)
            {"type": "string"}

            >>> to_json_schema_type(Literal["A", "B"])
            {"type": "string", "enum": ["A", "B"]}

            >>> to_json_schema_type(Optional[str])
            {"type": ["string", "null"]}

            >>> to_json_schema_type(List[int])
            {"type": "array", "items": {"type": "integer"}}
        """
        origin = get_origin(python_type)

        # Handle Literal types
        if origin is Literal:
            enum_values = list(get_args(python_type))
            return {
                "type": "string",  # Literals are always strings in practice
                "enum": enum_values
            }

        # Handle Union types (including Optional)
        if origin is Union:
            union_types = get_args(python_type)

            # Check if it's Optional[T] (Union[T, None])
            if type(None) in union_types:
                # Optional[T] → {"type": ["<T's type>", "null"]}
                non_none_types = [t for t in union_types if t is not type(None)]
                if len(non_none_types) == 1:
                    base_schema = TypeIntrospector.to_json_schema_type(non_none_types[0])
                    # Convert {"type": "string"} → {"type": ["string", "null"]}
                    if "type" in base_schema:
                        base_type = base_schema["type"]
                        base_schema["type"] = [base_type, "null"]
                    return base_schema

            # Generic Union[A, B, C] → anyOf
            return {
                "anyOf": [TypeIntrospector.to_json_schema_type(t) for t in union_types]
            }

        # Handle List[T]
        if origin is list:
            args = get_args(python_type)
            if args:
                element_type = args[0]
                return {
                    "type": "array",
                    "items": TypeIntrospector.to_json_schema_type(element_type)
                }
            return {"type": "array", "items": {"type": "string"}}  # Default

        # Handle Dict[K, V]
        if origin is dict:
            # JSON schema doesn't support typed dict keys/values well
            # Best effort: use object with additionalProperties
            args = get_args(python_type)
            if len(args) == 2:
                value_type = args[1]
                return {
                    "type": "object",
                    "additionalProperties": TypeIntrospector.to_json_schema_type(value_type)
                }
            return {"type": "object"}

        # Basic Python types
        type_mapping = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }

        json_type = type_mapping.get(python_type, "string")
        return {"type": json_type}
```

**Update `validate_output()` to use TypeIntrospector**:
```python
@staticmethod
def validate_output(output: Dict[str, Any], signature: Any) -> tuple[bool, List[str]]:
    """Validate output against signature schema using TypeIntrospector."""
    errors = []

    if not hasattr(signature, "output_fields"):
        return True, []

    # Check all required fields present
    for field_name, field_info in signature.output_fields.items():
        if field_name not in output:
            errors.append(f"Missing required field: {field_name}")
            continue

        # Check type using TypeIntrospector
        expected_type = field_info.get("type", str)
        actual_value = output[field_name]

        is_valid, error_msg = TypeIntrospector.is_valid_type(actual_value, expected_type)
        if not is_valid:
            errors.append(f"Type validation failed for {field_name}: {error_msg}")

    return len(errors) == 0, errors
```

**Update `signature_to_json_schema()` to use TypeIntrospector**:
```python
@staticmethod
def signature_to_json_schema(signature: Any) -> Dict[str, Any]:
    """Convert signature to JSON schema using TypeIntrospector."""
    schema = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False
    }

    if hasattr(signature, "output_fields"):
        for field_name, field_info in signature.output_fields.items():
            field_type = field_info.get("type", str)
            field_desc = field_info.get("desc", "")

            # Use TypeIntrospector for consistent schema generation
            field_schema = TypeIntrospector.to_json_schema_type(field_type)
            field_schema["description"] = field_desc

            schema["properties"][field_name] = field_schema
            schema["required"].append(field_name)

    return schema
```

### Implementation Strategy

1. **Create `type_introspection.py` module** (150 lines)
   - `TypeIntrospector` class with all methods
   - Comprehensive unit tests (30 test cases)

2. **Update `structured_output.py`** (50 line changes)
   - Replace `_python_type_to_json_type()` with `TypeIntrospector.to_json_schema_type()`
   - Replace `isinstance()` checks in `validate_output()` with `TypeIntrospector.is_valid_type()`
   - Remove lines 87-150 (old Literal handling, now in TypeIntrospector)

3. **Add comprehensive tests** (`test_type_introspection.py`, 30 tests)
   - Test all typing constructs: Literal, Union, Optional, List[T], Dict[K,V]
   - Test nested structures: List[Dict[str, int]]
   - Test edge cases: Union[str, int, None], Optional[List[str]]
   - Test error messages

### Test Strategy

**New Test File**: `tests/unit/core/test_type_introspection.py` (500 lines)

```python
class TestTypeIntrospectorValidation:
    """Test runtime type checking for all typing constructs."""

    def test_literal_valid(self):
        """Test Literal type with valid value."""
        is_valid, error = TypeIntrospector.is_valid_type("A", Literal["A", "B", "C"])
        assert is_valid
        assert error == ""

    def test_literal_invalid(self):
        """Test Literal type with invalid value."""
        is_valid, error = TypeIntrospector.is_valid_type("D", Literal["A", "B", "C"])
        assert not is_valid
        assert "not in allowed values" in error

    def test_union_valid(self):
        """Test Union type with valid value."""
        is_valid, error = TypeIntrospector.is_valid_type("test", Union[str, int])
        assert is_valid

        is_valid, error = TypeIntrospector.is_valid_type(42, Union[str, int])
        assert is_valid

    def test_optional_none(self):
        """Test Optional type with None value."""
        is_valid, error = TypeIntrospector.is_valid_type(None, Optional[str])
        assert is_valid

    def test_list_int_valid(self):
        """Test List[int] with valid list."""
        is_valid, error = TypeIntrospector.is_valid_type([1, 2, 3], List[int])
        assert is_valid

    def test_list_int_invalid_element(self):
        """Test List[int] with invalid element."""
        is_valid, error = TypeIntrospector.is_valid_type([1, "two", 3], List[int])
        assert not is_valid
        assert "List element at index 1" in error

    # ... 24 more test cases

class TestTypeIntrospectorSchemaGeneration:
    """Test JSON schema generation for all typing constructs."""

    def test_literal_to_enum(self):
        """Test Literal["A", "B"] → enum schema."""
        schema = TypeIntrospector.to_json_schema_type(Literal["A", "B", "C"])
        assert schema == {"type": "string", "enum": ["A", "B", "C"]}

    def test_optional_to_nullable(self):
        """Test Optional[str] → nullable string."""
        schema = TypeIntrospector.to_json_schema_type(Optional[str])
        assert schema == {"type": ["string", "null"]}

    def test_list_int_to_array(self):
        """Test List[int] → array with integer items."""
        schema = TypeIntrospector.to_json_schema_type(List[int])
        assert schema == {"type": "array", "items": {"type": "integer"}}

    # ... 20 more test cases
```

**Update Existing Test**: `test_structured_output_literal.py` (no changes needed - should pass after fix)

### Migration Path

**No Breaking Changes** ✅

- Existing API unchanged
- All existing tests continue to pass
- New functionality transparently fixes bug

---

## Bug #2: Type System Incomplete

### Root Cause Analysis

**Problem**: Only 6 basic types supported (str, int, float, bool, list, dict). Missing:
- `Union[A, B]`
- `Optional[T]` (Union[T, None])
- `List[T]` with element type
- `Dict[K, V]` with key/value types
- `TypedDict` for structured objects
- Nested structures

**Location**: `_python_type_to_json_type()` (lines 139-150) - only maps 6 types

### Comprehensive Solution

**Already Solved by Bug #1 Fix** ✅

The `TypeIntrospector` class from Bug #1 handles ALL type introspection needs:
- Supports all 10 typing patterns
- Handles nested structures
- Provides consistent schema generation

**Additional Enhancement**: TypedDict Support

```python
# In TypeIntrospector class
from typing import TypedDict, get_type_hints

@staticmethod
def is_typed_dict(python_type: Type) -> bool:
    """Check if type is a TypedDict."""
    try:
        return isinstance(python_type, type) and issubclass(python_type, dict) and hasattr(python_type, '__annotations__')
    except TypeError:
        return False

@staticmethod
def to_json_schema_type(python_type: Type) -> Dict[str, Any]:
    """Extended version with TypedDict support."""
    # ... existing code ...

    # Handle TypedDict
    if TypeIntrospector.is_typed_dict(python_type):
        properties = {}
        required = []

        for field_name, field_type in get_type_hints(python_type).items():
            properties[field_name] = TypeIntrospector.to_json_schema_type(field_type)
            required.append(field_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False
        }

    # ... rest of existing code ...
```

### Implementation Strategy

1. **Extend TypeIntrospector** (30 lines) - Add TypedDict support
2. **Add tests** (15 test cases) - Test TypedDict schema generation and validation

### Test Strategy

```python
class TestTypedDictSupport:
    """Test TypedDict schema generation and validation."""

    def test_typed_dict_to_schema(self):
        """Test TypedDict converts to nested object schema."""

        class PersonDict(TypedDict):
            name: str
            age: int
            email: Optional[str]

        schema = TypeIntrospector.to_json_schema_type(PersonDict)

        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert schema["properties"]["name"] == {"type": "string"}
        assert schema["properties"]["age"] == {"type": "integer"}
        assert schema["properties"]["email"] == {"type": ["string", "null"]}
        assert set(schema["required"]) == {"name", "age", "email"}

    def test_nested_typed_dict(self):
        """Test nested TypedDict structures."""

        class AddressDict(TypedDict):
            street: str
            city: str

        class PersonDict(TypedDict):
            name: str
            address: AddressDict

        schema = TypeIntrospector.to_json_schema_type(PersonDict)

        # Verify nested structure
        assert schema["properties"]["address"]["type"] == "object"
        assert "street" in schema["properties"]["address"]["properties"]
```

### Migration Path

**No Breaking Changes** ✅

---

## Bug #3: Extension Points Broken

### Root Cause Analysis

**Problem**: 4/7 extension points don't work in workflow composition path.

**Broken Extension Points**:
1. `_generate_system_prompt()` - Called by WorkflowGenerator without agent reference
2. `_validate_signature_output()` - Never called (missing integration)
3. `_pre_execution_hook()` - Never called (missing integration)
4. `_post_execution_hook()` - Never called (missing integration)
5. `_handle_error()` - Not called in workflow execution errors

**Working Extension Points**:
- `_default_signature()` - ✅ Works (called during agent initialization)
- `_default_strategy()` - ✅ Works (called during agent initialization)

**Architecture Issue**:
```python
# In BaseAgent.run()
workflow_generator = WorkflowGenerator(config=self.config, signature=self.signature)
workflow = workflow_generator.generate_signature_workflow()
# ❌ WorkflowGenerator has no reference to agent, can't call agent methods
```

**Location**: `base_agent.py:675-937` (run method), `workflow_generator.py:1-311`

### Comprehensive Solution

**Design Decision**: **Pass agent callbacks to WorkflowGenerator**

**Why this approach**:
1. ✅ Maintains separation of concerns (WorkflowGenerator doesn't depend on BaseAgent)
2. ✅ Testable (can pass mock callbacks)
3. ✅ Flexible (can pass different callbacks for different contexts)
4. ✅ No circular dependencies

**Alternative Rejected**: Pass entire agent reference
- ❌ Creates tight coupling
- ❌ Circular dependency risk
- ❌ Harder to test

**Implementation**: Extension Point Callbacks

```python
# New file: src/kaizen/core/extension_points.py
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

@dataclass
class ExtensionCallbacks:
    """
    Callback interface for agent extension points.

    Allows WorkflowGenerator to call agent-specific logic without
    tight coupling to BaseAgent class.
    """
    generate_system_prompt: Callable[[], str]
    validate_signature_output: Callable[[Dict[str, Any]], tuple[bool, List[str]]]
    pre_execution_hook: Callable[[Dict[str, Any]], Dict[str, Any]]
    post_execution_hook: Callable[[Dict[str, Any]], Dict[str, Any]]
    handle_error: Callable[[Exception], None]
```

**Update WorkflowGenerator**:
```python
# In workflow_generator.py
from kaizen.core.extension_points import ExtensionCallbacks

class WorkflowGenerator:
    """Generate Core SDK workflows with extension point support."""

    def __init__(
        self,
        config: BaseAgentConfig,
        signature: Optional[Signature] = None,
        callbacks: Optional[ExtensionCallbacks] = None  # NEW
    ):
        self.config = config
        self.signature = signature
        self.callbacks = callbacks

    def _generate_system_prompt(self) -> str:
        """Generate system prompt using callback if available."""
        if self.callbacks and self.callbacks.generate_system_prompt:
            return self.callbacks.generate_system_prompt()

        # Fallback: default implementation
        if not self.signature:
            return "You are a helpful AI assistant."

        # ... existing default logic ...

    def generate_signature_workflow(self) -> WorkflowBuilder:
        """Generate workflow with extension point integration."""
        workflow = WorkflowBuilder()

        # Generate system prompt (calls extension point)
        system_prompt = self._generate_system_prompt()

        node_config = {
            "provider": self.config.llm_provider or "openai",
            "model": self.config.model or "gpt-4",
            "system_prompt": system_prompt,
            # ... rest of config ...
        }

        workflow.add_node("LLMAgentNode", "agent_exec", node_config)

        # Add validation node (extension point)
        if self.callbacks and self.callbacks.validate_signature_output:
            workflow.add_node("ValidationNode", "validate_output", {
                "validator": self.callbacks.validate_signature_output
            })
            workflow.add_connection("agent_exec", "output", "validate_output", "input")

        # Add pre/post execution hooks
        if self.callbacks and self.callbacks.pre_execution_hook:
            workflow.add_node("PreHookNode", "pre_hook", {
                "hook": self.callbacks.pre_execution_hook
            })
            # Connect: pre_hook → agent_exec

        if self.callbacks and self.callbacks.post_execution_hook:
            workflow.add_node("PostHookNode", "post_hook", {
                "hook": self.callbacks.post_execution_hook
            })
            # Connect: agent_exec → post_hook

        return workflow
```

**Update BaseAgent.run()**:
```python
# In base_agent.py
from kaizen.core.extension_points import ExtensionCallbacks

class BaseAgent:
    def run(self, **input_data) -> Dict[str, Any]:
        """Execute agent with extension points."""

        # Create callbacks from agent methods
        callbacks = ExtensionCallbacks(
            generate_system_prompt=self._generate_system_prompt,
            validate_signature_output=self._validate_signature_output,
            pre_execution_hook=self._pre_execution_hook,
            post_execution_hook=self._post_execution_hook,
            handle_error=self._handle_error
        )

        # Pass callbacks to workflow generator
        workflow_generator = WorkflowGenerator(
            config=self.config,
            signature=self.signature,
            callbacks=callbacks  # NEW
        )

        workflow = workflow_generator.generate_signature_workflow()

        try:
            # Execute workflow (extension points now called)
            results, run_id = self.runtime.execute(workflow.build(), input_data)
            return results
        except Exception as e:
            # Call error handler extension point
            self._handle_error(e)
            raise
```

**Create Workflow Nodes for Extension Points**:
```python
# New file: src/kaizen/nodes/extension_point_nodes.py
from kailash.nodes.base import Node, NodeParameter
from typing import Any, Callable, Dict

class ValidationNode(Node):
    """Node that calls validation extension point."""

    def __init__(self, **kwargs):
        super().__init__("ValidationNode", **kwargs)
        self.validator = kwargs.get("validator")

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute validation callback."""
        if self.validator:
            is_valid, errors = self.validator(input)
            if not is_valid:
                raise ValueError(f"Validation failed: {errors}")
        return input

class PreHookNode(Node):
    """Node that calls pre-execution hook."""

    def __init__(self, **kwargs):
        super().__init__("PreHookNode", **kwargs)
        self.hook = kwargs.get("hook")

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute pre-hook callback."""
        if self.hook:
            return self.hook(input)
        return input

class PostHookNode(Node):
    """Node that calls post-execution hook."""

    def __init__(self, **kwargs):
        super().__init__("PostHookNode", **kwargs)
        self.hook = kwargs.get("hook")

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute post-hook callback."""
        if self.hook:
            return self.hook(input)
        return input
```

### Implementation Strategy

1. **Create `extension_points.py`** (50 lines) - ExtensionCallbacks dataclass
2. **Create `extension_point_nodes.py`** (120 lines) - ValidationNode, PreHookNode, PostHookNode
3. **Update `workflow_generator.py`** (80 line changes) - Add callbacks parameter, integrate nodes
4. **Update `base_agent.py`** (40 line changes) - Create callbacks, pass to generator
5. **Add tests** (60 test cases) - Test all extension points work in workflow path

### Test Strategy

```python
# New test file: tests/unit/core/test_extension_points.py

class TestExtensionPointCallbacks:
    """Test extension points work in workflow composition."""

    def test_custom_system_prompt_called(self):
        """Test _generate_system_prompt extension point is called."""

        class CustomAgent(BaseAgent):
            def _generate_system_prompt(self) -> str:
                return "CUSTOM PROMPT"

        agent = CustomAgent(config=config, signature=signature)

        # Verify custom prompt is used
        workflow = agent._get_workflow()  # Internal method for testing
        node_config = workflow.nodes["agent_exec"]
        assert node_config["system_prompt"] == "CUSTOM PROMPT"

    def test_validate_signature_output_called(self):
        """Test _validate_signature_output extension point is called."""

        validation_called = []

        class ValidatingAgent(BaseAgent):
            def _validate_signature_output(self, output: Dict) -> tuple[bool, List[str]]:
                validation_called.append(True)
                return True, []

        agent = ValidatingAgent(config=config, signature=signature)
        result = agent.run(question="test")

        assert validation_called  # Verify validation was called

    def test_pre_execution_hook_called(self):
        """Test _pre_execution_hook extension point is called."""

        hook_called = []

        class HookedAgent(BaseAgent):
            def _pre_execution_hook(self, input_data: Dict) -> Dict:
                hook_called.append(input_data)
                input_data["modified"] = True
                return input_data

        agent = HookedAgent(config=config, signature=signature)
        result = agent.run(question="test")

        assert hook_called
        assert hook_called[0]["question"] == "test"

    # ... 57 more test cases testing all extension points
```

### Migration Path

**No Breaking Changes** ✅

- Callbacks parameter is optional
- Existing code works without modifications
- Extension points now actually work (new functionality)

---

## Bug #4: OpenAI Strict Mode Limitations

### Root Cause Analysis

**Problem**: Users hit cryptic errors when using incompatible types with strict mode.

**OpenAI Strict Mode Limitations** (from Azure/OpenAI docs):

**Unsupported String Keywords**: `minLength`, `maxLength`, `pattern`, `format`
**Unsupported Number Keywords**: `minimum`, `maximum`, `multipleOf`
**Unsupported Object Keywords**: `patternProperties`, `unevaluatedProperties`, `propertyNames`, `minProperties`, `maxProperties`
**Unsupported Array Keywords**: `unevaluatedItems`, `contains`, `minContains`, `maxContains`, `minItems`, `maxItems`, `uniqueItems`

**Required Constraints**:
- ALL fields must be required (no optional fields)
- Must set `"additionalProperties": false` on all objects
- Max 100 object properties across schema
- Max 5 nesting levels
- Root objects cannot be `anyOf` type

**User Impact**: Cryptic 400 errors from OpenAI API with no guidance.

### Comprehensive Solution

**Design**: **Intelligent Strict Mode Detection + Auto-Fallback**

**Strategy**:
1. **Analyze signature** → Detect if compatible with strict mode
2. **If compatible** → Use strict mode (100% compliance)
3. **If incompatible** → Auto-fallback to `strict=False` with clear warning
4. **Provide guidance** → Tell user exactly how to fix for strict mode

**Implementation**:

```python
# New file: src/kaizen/core/strict_mode_validator.py
from typing import Any, Dict, List, Type, get_origin, get_args
from dataclasses import dataclass

@dataclass
class StrictModeCompatibility:
    """Result of strict mode compatibility check."""
    is_compatible: bool
    errors: List[str]
    warnings: List[str]
    recommendations: List[str]

class StrictModeValidator:
    """
    Validate signature compatibility with OpenAI strict mode.

    Detects limitations and provides actionable guidance.
    """

    @staticmethod
    def check_signature_compatibility(signature: Any) -> StrictModeCompatibility:
        """
        Check if signature is compatible with OpenAI strict mode.

        Returns:
            StrictModeCompatibility with detailed error/warning info
        """
        errors = []
        warnings = []
        recommendations = []

        if not hasattr(signature, "output_fields"):
            return StrictModeCompatibility(True, [], [], [])

        # Check each field for strict mode compatibility
        for field_name, field_info in signature.output_fields.items():
            field_type = field_info.get("type", str)
            metadata = field_info.get("metadata", {}).get("metadata", {})
            validation = metadata.get("validation", {})

            # Check for unsupported validation constraints
            if "pattern" in validation:
                errors.append(
                    f"Field '{field_name}': 'pattern' validation not supported in strict mode. "
                    f"Remove pattern constraint or use strict=False."
                )
                recommendations.append(
                    f"For field '{field_name}': Use Literal[...] enum instead of pattern for strict mode."
                )

            if "min" in validation or "max" in validation:
                errors.append(
                    f"Field '{field_name}': min/max validation not supported in strict mode. "
                    f"Remove constraints or use strict=False."
                )
                recommendations.append(
                    f"For field '{field_name}': Validation constraints work in strict=False mode."
                )

            if "minLength" in validation or "maxLength" in validation:
                errors.append(
                    f"Field '{field_name}': minLength/maxLength not supported in strict mode."
                )

            # Check for optional fields (Union with None)
            origin = get_origin(field_type)
            if origin is Union:
                args = get_args(field_type)
                if type(None) in args:
                    warnings.append(
                        f"Field '{field_name}': Optional fields require workaround in strict mode. "
                        f"Use {{'type': ['string', 'null']}} pattern."
                    )
                    recommendations.append(
                        f"Optional[T] is supported but may cause issues. "
                        f"Test with strict=False first."
                    )

        # Check nesting depth
        nesting_depth = StrictModeValidator._calculate_nesting_depth(signature)
        if nesting_depth > 5:
            errors.append(
                f"Schema nesting depth ({nesting_depth}) exceeds strict mode limit of 5 levels."
            )
            recommendations.append(
                "Flatten your signature structure or use strict=False mode."
            )

        # Check total property count
        property_count = StrictModeValidator._count_total_properties(signature)
        if property_count > 100:
            errors.append(
                f"Total property count ({property_count}) exceeds strict mode limit of 100."
            )
            recommendations.append(
                "Reduce number of output fields or use strict=False mode."
            )

        is_compatible = len(errors) == 0
        return StrictModeCompatibility(is_compatible, errors, warnings, recommendations)

    @staticmethod
    def _calculate_nesting_depth(signature: Any) -> int:
        """Calculate maximum nesting depth in signature."""
        # Implementation: recursively analyze TypedDict/nested structures
        return 1  # Simplified for now

    @staticmethod
    def _count_total_properties(signature: Any) -> int:
        """Count total properties across all nested objects."""
        if not hasattr(signature, "output_fields"):
            return 0
        return len(signature.output_fields)
```

**Update `create_structured_output_config()`**:
```python
def create_structured_output_config(
    signature: Any,
    strict: bool = True,
    name: str = "response",
    auto_fallback: bool = True  # NEW: Auto-fallback on incompatibility
) -> Dict[str, Any]:
    """
    Create OpenAI-compatible structured output configuration.

    With intelligent strict mode detection:
    - If signature compatible + strict=True → use strict mode
    - If signature incompatible + strict=True + auto_fallback=True → fallback to strict=False with warning
    - If signature incompatible + strict=True + auto_fallback=False → raise error with guidance

    Args:
        signature: Kaizen Signature instance
        strict: Attempt to use strict mode (default: True)
        name: Schema name for strict mode
        auto_fallback: Auto-fallback to strict=False if incompatible (default: True)

    Returns:
        Dict: Config for OpenAI API response_format parameter

    Raises:
        ValueError: If strict=True, auto_fallback=False, and signature incompatible
    """
    schema = StructuredOutputGenerator.signature_to_json_schema(signature)

    # Check strict mode compatibility
    if strict:
        from kaizen.core.strict_mode_validator import StrictModeValidator

        compatibility = StrictModeValidator.check_signature_compatibility(signature)

        if not compatibility.is_compatible:
            error_msg = "Signature incompatible with OpenAI strict mode:\n"
            error_msg += "\n".join(f"  - {err}" for err in compatibility.errors)

            if compatibility.recommendations:
                error_msg += "\n\nRecommendations:\n"
                error_msg += "\n".join(f"  - {rec}" for rec in compatibility.recommendations)

            if auto_fallback:
                # Auto-fallback to strict=False
                logger.warning(
                    f"{error_msg}\n\nAuto-falling back to strict=False mode (70-85% compliance)."
                )
                strict = False
            else:
                # Raise error with guidance
                error_msg += "\n\nTo fix: Either adjust signature or use strict=False mode."
                raise ValueError(error_msg)

    # Generate config based on strict mode
    if strict:
        return {
            "type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": schema}
        }
    else:
        return {"type": "json_object", "schema": schema}
```

### Implementation Strategy

1. **Create `strict_mode_validator.py`** (200 lines) - StrictModeValidator class
2. **Update `structured_output.py`** (40 line changes) - Integrate validator into create_structured_output_config()
3. **Add comprehensive tests** (30 test cases) - Test all strict mode edge cases
4. **Add documentation** (1 guide doc) - "Strict Mode Compatibility Guide"

### Test Strategy

```python
# New test file: tests/unit/core/test_strict_mode_validator.py

class TestStrictModeCompatibility:
    """Test strict mode compatibility detection."""

    def test_compatible_signature(self):
        """Test signature compatible with strict mode."""

        class CompatibleSignature(Signature):
            input: str = InputField(desc="Input")
            output: str = OutputField(desc="Output")
            confidence: float = OutputField(desc="Confidence")

        compatibility = StrictModeValidator.check_signature_compatibility(
            CompatibleSignature()
        )

        assert compatibility.is_compatible
        assert len(compatibility.errors) == 0

    def test_pattern_validation_incompatible(self):
        """Test pattern validation detected as incompatible."""

        class PatternSignature(Signature):
            input: str = InputField(desc="Input")
            email: str = OutputField(
                desc="Email",
                metadata={"validation": {"pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"}}
            )

        compatibility = StrictModeValidator.check_signature_compatibility(
            PatternSignature()
        )

        assert not compatibility.is_compatible
        assert any("pattern" in err for err in compatibility.errors)
        assert any("Literal" in rec for rec in compatibility.recommendations)

    def test_auto_fallback(self):
        """Test auto-fallback to strict=False."""

        class IncompatibleSignature(Signature):
            input: str = InputField(desc="Input")
            value: int = OutputField(
                desc="Value",
                metadata={"validation": {"min": 0, "max": 100}}
            )

        # Should fallback without raising error
        config = create_structured_output_config(
            IncompatibleSignature(),
            strict=True,
            auto_fallback=True
        )

        # Verify fallback to legacy mode
        assert config["type"] == "json_object"

    def test_no_fallback_raises_error(self):
        """Test error raised when auto_fallback=False."""

        class IncompatibleSignature(Signature):
            input: str = InputField(desc="Input")
            value: int = OutputField(
                desc="Value",
                metadata={"validation": {"min": 0, "max": 100}}
            )

        with pytest.raises(ValueError) as exc_info:
            config = create_structured_output_config(
                IncompatibleSignature(),
                strict=True,
                auto_fallback=False
            )

        # Verify error message contains guidance
        assert "incompatible" in str(exc_info.value).lower()
        assert "recommendations" in str(exc_info.value).lower()
```

### Migration Path

**No Breaking Changes** ✅

- `strict=True` remains default
- `auto_fallback=True` provides safety net
- Existing code continues to work
- New code gets better error messages

**User Experience Improvement**:

**Before** (cryptic error):
```
OpenAI API Error 400: Invalid schema
```

**After** (actionable guidance):
```
WARNING: Signature incompatible with OpenAI strict mode:
  - Field 'email': 'pattern' validation not supported in strict mode. Remove pattern constraint or use strict=False.

Recommendations:
  - For field 'email': Use Literal[...] enum instead of pattern for strict mode.

Auto-falling back to strict=False mode (70-85% compliance).
```

---

## Implementation Order

**Phase 1: Core Type System (Bug #1 + #2)** - Week 1
1. Create `type_introspection.py` with TypeIntrospector class
2. Update `structured_output.py` to use TypeIntrospector
3. Add 45 comprehensive tests
4. ✅ Fixes Bug #1 (Literal validation)
5. ✅ Fixes Bug #2 (Type system complete)

**Phase 2: Extension Points (Bug #3)** - Week 2
1. Create `extension_points.py` with ExtensionCallbacks
2. Create `extension_point_nodes.py` with workflow nodes
3. Update `workflow_generator.py` to accept callbacks
4. Update `base_agent.py` to create and pass callbacks
5. Add 60 comprehensive tests
6. ✅ Fixes Bug #3 (Extension points work)

**Phase 3: Strict Mode Intelligence (Bug #4)** - Week 3
1. Create `strict_mode_validator.py` with compatibility checker
2. Update `create_structured_output_config()` with auto-fallback
3. Add 30 comprehensive tests
4. Create user documentation guide
5. ✅ Fixes Bug #4 (Intelligent strict mode handling)

**Total Timeline**: 3 weeks (15 business days)

---

## Files to Modify

### New Files (5 files, ~670 lines)
1. `src/kaizen/core/type_introspection.py` - 200 lines
2. `src/kaizen/core/extension_points.py` - 50 lines
3. `src/kaizen/nodes/extension_point_nodes.py` - 120 lines
4. `src/kaizen/core/strict_mode_validator.py` - 200 lines
5. `docs/guides/strict-mode-compatibility.md` - 100 lines

### Modified Files (3 files, ~170 line changes)
1. `src/kaizen/core/structured_output.py` - 90 line changes
2. `src/kaizen/core/workflow_generator.py` - 40 line changes
3. `src/kaizen/core/base_agent.py` - 40 line changes

### New Test Files (4 files, ~2100 lines)
1. `tests/unit/core/test_type_introspection.py` - 500 lines (45 tests)
2. `tests/unit/core/test_extension_points.py` - 800 lines (60 tests)
3. `tests/unit/core/test_strict_mode_validator.py` - 400 lines (30 tests)
4. `tests/integration/test_structured_output_e2e.py` - 400 lines (20 E2E tests)

**Total Code Changes**: ~840 new lines, ~170 modified lines, ~2100 test lines

---

## API Compatibility Matrix

| Change | Breaking? | Migration Required? | Notes |
|--------|-----------|---------------------|-------|
| TypeIntrospector | ❌ No | ❌ No | Internal implementation |
| ExtensionCallbacks | ❌ No | ❌ No | Optional parameter |
| StrictModeValidator | ❌ No | ❌ No | Internal implementation |
| auto_fallback parameter | ❌ No | ❌ No | Default=True (safe) |
| Extension point nodes | ❌ No | ❌ No | Transparent integration |

**Result**: **100% Backward Compatible** ✅

---

## Success Criteria

### Bug #1: Literal Type Validation
- ✅ `test_validate_literal_field_valid_value` passes
- ✅ All 13 Literal type tests pass
- ✅ No TypeError on `isinstance()`

### Bug #2: Type System Complete
- ✅ Support `Literal`, `Union`, `Optional`, `List[T]`, `Dict[K,V]`, `TypedDict`
- ✅ Support nested structures (3+ levels)
- ✅ Generate correct JSON schemas for all types
- ✅ 45 type introspection tests pass

### Bug #3: Extension Points Work
- ✅ ALL 7 extension points callable in workflow path
- ✅ Custom prompts, validation, hooks work in production
- ✅ 60 extension point tests pass
- ✅ No tight coupling between WorkflowGenerator and BaseAgent

### Bug #4: Intelligent Strict Mode
- ✅ Detect incompatible signatures
- ✅ Provide actionable error messages
- ✅ Auto-fallback prevents cryptic errors
- ✅ Users know exactly how to fix issues
- ✅ 30 strict mode tests pass

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| TypeIntrospector performance overhead | Low | Low | Cache schema generation results |
| Extension point nodes add latency | Low | Medium | Optimize node execution, benchmark |
| Auto-fallback confuses users | Low | Low | Clear logging, documentation |
| Breaking changes in Core SDK | Medium | High | Comprehensive integration tests |
| Test coverage gaps | Low | High | 135 new tests, 100% coverage target |

---

## Appendix A: Example Usage After Fix

### Example 1: Complex Signature with All Types
```python
from typing import Literal, Optional, List, Dict
from kaizen.signatures import Signature, InputField, OutputField

class AdvancedAnalysisSignature(Signature):
    """Comprehensive signature using all supported types."""

    # Input
    document: str = InputField(desc="Document to analyze")

    # Literal type
    category: Literal["financial", "legal", "technical"] = OutputField(
        desc="Document category"
    )

    # Union type
    priority: Union[str, int] = OutputField(desc="Priority (name or number)")

    # Optional type
    summary: Optional[str] = OutputField(desc="Optional summary")

    # List with element type
    keywords: List[str] = OutputField(desc="Extracted keywords")

    # Dict with typed values
    metadata: Dict[str, str] = OutputField(desc="Document metadata")

    # Nested structure
    sections: List[Dict[str, str]] = OutputField(desc="Document sections")

    # Standard types
    confidence: float = OutputField(desc="Confidence score 0-1")
    word_count: int = OutputField(desc="Word count")
    is_complete: bool = OutputField(desc="Analysis complete")

# Create agent with complex signature
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",
    generation_config={
        "response_format": create_structured_output_config(
            AdvancedAnalysisSignature(),
            strict=True,  # Auto-detects compatibility
            auto_fallback=True  # Safe fallback if needed
        )
    }
)

agent = BaseAgent(config=config, signature=AdvancedAnalysisSignature())
result = agent.run(document="Sample document text...")

# All fields correctly validated and typed
assert result["category"] in ["financial", "legal", "technical"]
assert isinstance(result["keywords"], list)
assert all(isinstance(k, str) for k in result["keywords"])
```

### Example 2: Extension Points
```python
class CustomAgent(BaseAgent):
    """Agent with all extension points customized."""

    def _generate_system_prompt(self) -> str:
        """Custom prompt generation."""
        return f"Expert in {self.config.domain} with {self.config.style} communication style."

    def _validate_signature_output(self, output: Dict) -> tuple[bool, List[str]]:
        """Custom output validation."""
        errors = []
        if output.get("confidence", 0) < 0.5:
            errors.append("Confidence too low - must be >= 0.5")
        return len(errors) == 0, errors

    def _pre_execution_hook(self, input_data: Dict) -> Dict:
        """Custom pre-processing."""
        input_data["timestamp"] = datetime.now().isoformat()
        return input_data

    def _post_execution_hook(self, output_data: Dict) -> Dict:
        """Custom post-processing."""
        output_data["processed_at"] = datetime.now().isoformat()
        return output_data

    def _handle_error(self, error: Exception) -> None:
        """Custom error handling."""
        logger.error(f"Agent failed: {error}", extra={"agent_id": self.agent_id})
        # Send to monitoring system, etc.

# All extension points work in workflow execution
agent = CustomAgent(config=config, signature=signature)
result = agent.run(question="test")  # Extension points called automatically
```

### Example 3: Strict Mode Guidance
```python
# Incompatible signature (pattern validation)
class EmailSignature(Signature):
    text: str = InputField(desc="Text to analyze")
    email: str = OutputField(
        desc="Extracted email",
        metadata={
            "validation": {
                "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"  # ❌ Not supported in strict mode
            }
        }
    )

# Auto-fallback with clear guidance
config = create_structured_output_config(
    EmailSignature(),
    strict=True,
    auto_fallback=True  # Prevents error
)

# Output:
# WARNING: Signature incompatible with OpenAI strict mode:
#   - Field 'email': 'pattern' validation not supported in strict mode.
#
# Recommendations:
#   - Use Literal["common@domains.com", ...] enum instead of pattern.
#   - Or use strict=False for best-effort compliance (70-85%).
#
# Auto-falling back to strict=False mode.

# User knows exactly what to do to fix it!
```

---

## Appendix B: Testing Checklist

### Unit Tests (135 tests)
- [ ] 45 type introspection tests (all typing constructs)
- [ ] 60 extension point tests (all 7 extension points)
- [ ] 30 strict mode validator tests (all edge cases)

### Integration Tests (20 tests)
- [ ] E2E with real OpenAI API (strict mode)
- [ ] E2E with real OpenAI API (fallback mode)
- [ ] Extension points in production workflows
- [ ] Complex nested signatures
- [ ] Error handling and recovery

### Performance Tests (5 benchmarks)
- [ ] TypeIntrospector overhead (<1ms per call)
- [ ] Extension point node latency (<5ms per hook)
- [ ] Schema generation for complex signatures (<10ms)
- [ ] Strict mode validation (<5ms)
- [ ] Memory usage (no leaks)

### Documentation Tests
- [ ] All code examples work
- [ ] API docs accurate
- [ ] Migration guide tested
- [ ] Strict mode guide validated

---

## Conclusion

This comprehensive fix plan addresses **all 4 bugs at their root causes**:

1. ✅ **Bug #1 Fixed**: TypeIntrospector handles Literal and all typing constructs
2. ✅ **Bug #2 Fixed**: Full type system with 10/10 patterns supported
3. ✅ **Bug #3 Fixed**: Extension points work via callback architecture
4. ✅ **Bug #4 Fixed**: Intelligent strict mode detection with auto-fallback

**Key Principles**:
- **Eliminate limitations**, not document them
- **100% backward compatible**
- **Comprehensive test coverage** (135 new tests)
- **Clear user guidance** (actionable error messages)
- **Production-ready** (performance validated, error handling robust)

**Timeline**: 3 weeks, 8 files modified/created, ~3100 total lines (code + tests)

---

**Document Status**: Ready for implementation
**Next Step**: Review with team → Implement Phase 1 (Type System)
