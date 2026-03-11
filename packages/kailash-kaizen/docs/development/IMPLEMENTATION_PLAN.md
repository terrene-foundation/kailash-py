# Implementation Plan: Structured Output Fix

**Version**: 1.0
**Date**: 2025-11-03
**Timeline**: 3 weeks (15 business days)
**Estimated Effort**: ~120 hours

---

## Quick Reference

**Total Changes**:
- 5 new files (~670 lines)
- 3 modified files (~170 line changes)
- 4 new test files (~2100 lines)
- 1 documentation guide (~100 lines)

**Dependencies**:
- Phase 1 → Phase 2 (extension points need type system)
- Phase 2 → Phase 3 (strict mode validator uses type system)
- All phases independent in implementation (can be developed in parallel, integrated sequentially)

---

## Phase 1: Core Type System (Days 1-5)

**Goal**: Fix Bug #1 (Literal validation) and Bug #2 (type system incomplete)

### Task 1.1: Create TypeIntrospector Class (Day 1, 8 hours)

**File**: `packages/kailash-kaizen/src/kaizen/core/type_introspection.py` (NEW, 200 lines)

**Implementation Steps**:

1. **Create file structure** (30 min)
   ```python
   """
   Type Introspection - Runtime type checking for typing constructs.

   Provides unified type introspection for both schema generation and validation.
   """
   from typing import Any, Dict, List, Type, get_origin, get_args, Literal, Union, Optional
   import sys

   class TypeIntrospector:
       """Unified type introspection for schema generation and validation."""
       pass
   ```

2. **Implement `is_valid_type()` method** (3 hours)
   - Handle Literal types (enum validation)
   - Handle Union types (any-of validation)
   - Handle Optional types (Union with None)
   - Handle List[T] with element validation
   - Handle Dict[K, V] with key/value validation
   - Handle basic Python types (str, int, float, bool)
   - Special case: int/float interchangeable
   - Return (is_valid, error_message) tuple

3. **Implement `to_json_schema_type()` method** (3 hours)
   - Handle Literal → enum schema
   - Handle Union → anyOf schema
   - Handle Optional[T] → nullable type schema
   - Handle List[T] → array with items schema
   - Handle Dict[K, V] → object with additionalProperties
   - Handle basic types → JSON schema types
   - Return complete JSON schema fragment

4. **Add TypedDict support** (1 hour)
   - Implement `is_typed_dict()` helper
   - Extend `to_json_schema_type()` for TypedDict
   - Use `get_type_hints()` for field introspection

5. **Add docstrings and examples** (30 min)
   - Comprehensive docstrings with examples
   - Document all supported typing constructs
   - Include edge cases

**Deliverables**:
- ✅ `type_introspection.py` with TypeIntrospector class
- ✅ 2 main methods: `is_valid_type()`, `to_json_schema_type()`
- ✅ TypedDict support
- ✅ Comprehensive docstrings

**Validation**:
- Manual testing with Literal["A", "B"]
- Manual testing with Union[str, int]
- Manual testing with Optional[str]
- Manual testing with List[int]

### Task 1.2: Update structured_output.py (Day 2, 4 hours)

**File**: `packages/kailash-kaizen/src/kaizen/core/structured_output.py` (MODIFY, 90 line changes)

**Changes Required**:

1. **Add import** (5 min)
   ```python
   from kaizen.core.type_introspection import TypeIntrospector
   ```

2. **Update `signature_to_json_schema()` method** (1.5 hours)
   - Replace lines 87-150 (old Literal handling)
   - Use `TypeIntrospector.to_json_schema_type()` instead
   - Keep validation constraint merging logic (lines 114-130)
   - Keep description extraction logic

   **Before** (lines 87-150):
   ```python
   origin = get_origin(field_type)
   if origin is Literal:
       enum_values = list(get_args(field_type))
       field_schema = {"type": "string", "description": field_desc, "enum": enum_values}
   else:
       json_type = StructuredOutputGenerator._python_type_to_json_type(field_type)
       field_schema = {"type": json_type, "description": field_desc}
       # ... validation constraints ...
   ```

   **After**:
   ```python
   # Use TypeIntrospector for consistent schema generation
   field_schema = TypeIntrospector.to_json_schema_type(field_type)
   field_schema["description"] = field_desc

   # Merge validation constraints from metadata (keep existing logic)
   metadata = field_info.get("metadata", {}).get("metadata", {})
   validation = metadata.get("validation", {})
   # ... existing validation constraint merging ...
   ```

3. **Update `validate_output()` method** (1.5 hours)
   - Replace lines 244-258 (old isinstance checks)
   - Use `TypeIntrospector.is_valid_type()` instead
   - Keep missing field checks (lines 238-242)
   - Improve error messages

   **Before** (lines 244-258):
   ```python
   expected_type = field_info.get("type", str)
   actual_value = output[field_name]

   if not isinstance(actual_value, expected_type):  # ❌ Fails for Literal
       # Special case: int/float are interchangeable
       if expected_type == float and isinstance(actual_value, int):
           pass
       elif expected_type == int and isinstance(actual_value, float):
           pass
       else:
           errors.append(f"Type mismatch for {field_name}: ...")
   ```

   **After**:
   ```python
   expected_type = field_info.get("type", str)
   actual_value = output[field_name]

   # Use TypeIntrospector for runtime type checking
   is_valid, error_msg = TypeIntrospector.is_valid_type(actual_value, expected_type)
   if not is_valid:
       errors.append(f"Type validation failed for {field_name}: {error_msg}")
   ```

4. **Remove `_python_type_to_json_type()` method** (15 min)
   - Delete lines 139-150 (replaced by TypeIntrospector)

5. **Update docstrings** (30 min)
   - Update method docstrings to mention TypeIntrospector
   - Add examples for new supported types

**Deliverables**:
- ✅ Updated `signature_to_json_schema()` using TypeIntrospector
- ✅ Updated `validate_output()` using TypeIntrospector
- ✅ Removed old `_python_type_to_json_type()` method
- ✅ 90 lines changed

**Validation**:
- Run failing test: `test_validate_literal_field_valid_value` should pass
- Run all Literal type tests (13 tests)
- Manual testing with complex signatures

### Task 1.3: Write Type Introspection Tests (Days 3-4, 12 hours)

**File**: `packages/kailash-kaizen/tests/unit/core/test_type_introspection.py` (NEW, 500 lines)

**Test Structure**:

1. **Test Suite 1: `TestTypeIntrospectorValidation`** (250 lines, 25 tests)
   - `test_literal_valid` - Valid Literal value
   - `test_literal_invalid` - Invalid Literal value
   - `test_literal_single_value` - Single value Literal
   - `test_union_str_int_valid_str` - Union[str, int] with str
   - `test_union_str_int_valid_int` - Union[str, int] with int
   - `test_union_str_int_invalid` - Union[str, int] with float
   - `test_optional_none` - Optional[str] with None
   - `test_optional_value` - Optional[str] with str
   - `test_optional_invalid` - Optional[str] with int
   - `test_list_int_valid` - List[int] with valid list
   - `test_list_int_invalid_element` - List[int] with string element
   - `test_list_int_empty` - List[int] with empty list
   - `test_dict_str_int_valid` - Dict[str, int] with valid dict
   - `test_dict_str_int_invalid_key` - Dict[str, int] with int key
   - `test_dict_str_int_invalid_value` - Dict[str, int] with str value
   - `test_basic_str_valid` - str type with valid string
   - `test_basic_str_invalid` - str type with int
   - `test_basic_int_float_interchangeable` - int accepts float
   - `test_basic_float_int_interchangeable` - float accepts int
   - `test_nested_list_dict` - List[Dict[str, int]]
   - `test_nested_optional_list` - Optional[List[str]]
   - `test_union_with_none` - Union[str, int, None]
   - `test_error_messages_descriptive` - Error messages clear
   - `test_complex_nested_structure` - Deep nesting
   - `test_typed_dict_validation` - TypedDict runtime check

2. **Test Suite 2: `TestTypeIntrospectorSchemaGeneration`** (200 lines, 20 tests)
   - `test_literal_to_enum` - Literal → enum schema
   - `test_literal_with_many_values` - Large enum
   - `test_union_to_any_of` - Union → anyOf schema
   - `test_optional_to_nullable` - Optional → nullable type
   - `test_list_int_to_array` - List[int] → array schema
   - `test_list_str_to_array` - List[str] → array schema
   - `test_dict_str_int_to_object` - Dict[str, int] → object schema
   - `test_dict_str_str_to_object` - Dict[str, str] → object schema
   - `test_basic_str_to_string` - str → string type
   - `test_basic_int_to_integer` - int → integer type
   - `test_basic_float_to_number` - float → number type
   - `test_basic_bool_to_boolean` - bool → boolean type
   - `test_nested_list_dict_schema` - List[Dict[str, int]] schema
   - `test_optional_list_schema` - Optional[List[str]] schema
   - `test_union_with_none_schema` - Union[str, None] schema
   - `test_typed_dict_to_object_schema` - TypedDict → object
   - `test_nested_typed_dict_schema` - Nested TypedDict
   - `test_complex_schema_generation` - Complex multi-level
   - `test_schema_with_descriptions` - Preserve descriptions
   - `test_schema_strict_mode_compatible` - Strict mode ready

**Implementation Steps**:

1. **Day 3 Morning**: Write validation tests (Suite 1, 15 tests) - 4 hours
2. **Day 3 Afternoon**: Write validation tests (Suite 1, 10 tests) - 4 hours
3. **Day 4 Morning**: Write schema generation tests (Suite 2, 12 tests) - 4 hours
4. **Day 4 Afternoon**: Write schema generation tests (Suite 2, 8 tests) - 4 hours

**Deliverables**:
- ✅ 45 comprehensive tests (25 validation + 20 schema generation)
- ✅ 500 lines of test code
- ✅ Edge cases covered
- ✅ All tests passing

### Task 1.4: Update Existing Tests (Day 5, 4 hours)

**Files to Update**:
1. `tests/unit/core/test_structured_output_literal.py` - Should pass without changes
2. `tests/unit/core/test_structured_output.py` - May need updates

**Steps**:

1. **Run all existing structured output tests** (1 hour)
   ```bash
   pytest tests/unit/core/test_structured_output*.py -v
   ```

2. **Fix any test failures** (2 hours)
   - Update test expectations if needed
   - Verify error message changes don't break tests
   - Ensure backward compatibility

3. **Run integration tests** (1 hour)
   ```bash
   pytest tests/integration/test_structured_output*.py -v
   ```

**Deliverables**:
- ✅ All 18 existing structured output tests pass
- ✅ All 45 new type introspection tests pass
- ✅ Integration tests pass

---

## Phase 2: Extension Points (Days 6-10)

**Goal**: Fix Bug #3 (extension points broken in workflow composition)

### Task 2.1: Create Extension Point Infrastructure (Day 6, 8 hours)

**File 1**: `packages/kailash-kaizen/src/kaizen/core/extension_points.py` (NEW, 50 lines)

**Implementation** (2 hours):
```python
"""
Extension Points - Callback interface for agent customization.

Provides type-safe callback interface for BaseAgent extension points.
"""
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

@dataclass
class ExtensionCallbacks:
    """
    Callback interface for agent extension points.

    Allows WorkflowGenerator to call agent-specific logic without
    tight coupling to BaseAgent class.

    Attributes:
        generate_system_prompt: Generate custom system prompt
        validate_signature_output: Validate agent output
        pre_execution_hook: Pre-processing hook
        post_execution_hook: Post-processing hook
        handle_error: Error handling hook
    """
    generate_system_prompt: Optional[Callable[[], str]] = None
    validate_signature_output: Optional[Callable[[Dict[str, Any]], tuple[bool, List[str]]]] = None
    pre_execution_hook: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    post_execution_hook: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    handle_error: Optional[Callable[[Exception], None]] = None
```

**File 2**: `packages/kailash-kaizen/src/kaizen/nodes/extension_point_nodes.py` (NEW, 120 lines)

**Implementation** (4 hours):

1. **Create ValidationNode** (1 hour)
   ```python
   from kailash.nodes.base import Node, NodeParameter
   from typing import Any, Callable, Dict, List

   class ValidationNode(Node):
       """Node that executes validation extension point."""

       def __init__(self, **kwargs):
           super().__init__("ValidationNode", **kwargs)
           self.validator: Optional[Callable] = kwargs.get("validator")

       def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
           """Execute validation callback."""
           if self.validator:
               is_valid, errors = self.validator(input)
               if not is_valid:
                   raise ValueError(f"Validation failed: {errors}")
           return input

       @staticmethod
       def get_parameters() -> List[NodeParameter]:
           return [
               NodeParameter(
                   name="input",
                   parameter_type="dict",
                   required=True,
                   description="Data to validate"
               )
           ]
   ```

2. **Create PreHookNode** (1 hour)
   ```python
   class PreHookNode(Node):
       """Node that executes pre-execution hook."""

       def __init__(self, **kwargs):
           super().__init__("PreHookNode", **kwargs)
           self.hook: Optional[Callable] = kwargs.get("hook")

       def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
           """Execute pre-hook callback."""
           if self.hook:
               return self.hook(input)
           return input

       @staticmethod
       def get_parameters() -> List[NodeParameter]:
           return [
               NodeParameter(
                   name="input",
                   parameter_type="dict",
                   required=True,
                   description="Input data to pre-process"
               )
           ]
   ```

3. **Create PostHookNode** (1 hour)
   ```python
   class PostHookNode(Node):
       """Node that executes post-execution hook."""

       def __init__(self, **kwargs):
           super().__init__("PostHookNode", **kwargs)
           self.hook: Optional[Callable] = kwargs.get("hook")

       def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
           """Execute post-hook callback."""
           if self.hook:
               return self.hook(input)
           return input

       @staticmethod
       def get_parameters() -> List[NodeParameter]:
           return [
               NodeParameter(
                   name="input",
                   parameter_type="dict",
                   required=True,
                   description="Output data to post-process"
               )
           ]
   ```

4. **Add docstrings and examples** (1 hour)

**Deliverables**:
- ✅ `extension_points.py` with ExtensionCallbacks dataclass
- ✅ `extension_point_nodes.py` with 3 node classes
- ✅ Comprehensive docstrings

**Validation**:
- Manual instantiation of nodes
- Manual callback execution

### Task 2.2: Update WorkflowGenerator (Day 7, 8 hours)

**File**: `packages/kailash-kaizen/src/kaizen/core/workflow_generator.py` (MODIFY, 40 line changes)

**Changes Required**:

1. **Add import** (5 min)
   ```python
   from kaizen.core.extension_points import ExtensionCallbacks
   from kaizen.nodes.extension_point_nodes import ValidationNode, PreHookNode, PostHookNode
   ```

2. **Update `__init__()` method** (30 min)
   ```python
   def __init__(
       self,
       config: BaseAgentConfig,
       signature: Optional[Signature] = None,
       callbacks: Optional[ExtensionCallbacks] = None  # NEW
   ):
       self.config = config
       self.signature = signature
       self.callbacks = callbacks  # Store callbacks
   ```

3. **Update `_generate_system_prompt()` method** (1 hour)
   ```python
   def _generate_system_prompt(self) -> str:
       """Generate system prompt using callback if available."""
       # Try callback first
       if self.callbacks and self.callbacks.generate_system_prompt:
           return self.callbacks.generate_system_prompt()

       # Fallback: existing default implementation
       if not self.signature:
           return "You are a helpful AI assistant."

       # ... keep existing logic (lines 230-310) ...
   ```

4. **Update `generate_signature_workflow()` method** (4 hours)
   - Add validation node after agent_exec
   - Add pre-hook node before agent_exec
   - Add post-hook node after agent_exec
   - Connect nodes properly

   ```python
   def generate_signature_workflow(self) -> WorkflowBuilder:
       """Generate workflow with extension point integration."""
       workflow = WorkflowBuilder()

       # ... existing LLMAgentNode creation (lines 115-164) ...

       # Add pre-execution hook if available
       if self.callbacks and self.callbacks.pre_execution_hook:
           workflow.add_node("PreHookNode", "pre_hook", {
               "hook": self.callbacks.pre_execution_hook
           })
           # Connect: workflow_input → pre_hook → agent_exec
           workflow.add_connection("workflow_input", "data", "pre_hook", "input")
           workflow.add_connection("pre_hook", "input", "agent_exec", "user_prompt")
       else:
           # Direct connection without hook
           workflow.add_connection("workflow_input", "data", "agent_exec", "user_prompt")

       # Add validation node if available
       if self.callbacks and self.callbacks.validate_signature_output:
           workflow.add_node("ValidationNode", "validate_output", {
               "validator": self.callbacks.validate_signature_output
           })
           workflow.add_connection("agent_exec", "output", "validate_output", "input")

           # Post-hook connects to validation output
           validation_output = "validate_output"
       else:
           # Post-hook connects to agent output directly
           validation_output = "agent_exec"

       # Add post-execution hook if available
       if self.callbacks and self.callbacks.post_execution_hook:
           workflow.add_node("PostHookNode", "post_hook", {
               "hook": self.callbacks.post_execution_hook
           })
           workflow.add_connection(validation_output, "output", "post_hook", "input")
           workflow.add_connection("post_hook", "input", "workflow_output", "result")
       else:
           # Direct connection without hook
           workflow.add_connection(validation_output, "output", "workflow_output", "result")

       return workflow
   ```

5. **Update docstrings** (30 min)

**Deliverables**:
- ✅ WorkflowGenerator accepts callbacks parameter
- ✅ Extension point nodes integrated into workflow
- ✅ Proper node connections
- ✅ 40 lines changed

**Validation**:
- Manual workflow generation with callbacks
- Verify workflow structure with debugging

### Task 2.3: Update BaseAgent (Day 8, 4 hours)

**File**: `packages/kailash-kaizen/src/kaizen/core/base_agent.py` (MODIFY, 40 line changes)

**Changes Required**:

1. **Add import** (5 min)
   ```python
   from kaizen.core.extension_points import ExtensionCallbacks
   ```

2. **Update `run()` method** (3 hours)
   - Create ExtensionCallbacks from agent methods
   - Pass callbacks to WorkflowGenerator
   - Integrate `_handle_error()` extension point

   **Before** (lines 675-937):
   ```python
   def run(self, **input_data) -> Dict[str, Any]:
       """Execute agent."""
       workflow_generator = WorkflowGenerator(
           config=self.config,
           signature=self.signature
       )
       workflow = workflow_generator.generate_signature_workflow()
       results, run_id = self.runtime.execute(workflow.build(), input_data)
       return results
   ```

   **After**:
   ```python
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
           # Execute workflow (extension points called via nodes)
           results, run_id = self.runtime.execute(workflow.build(), input_data)
           return results
       except Exception as e:
           # Call error handler extension point
           self._handle_error(e)
           raise
   ```

3. **Update docstrings** (30 min)
   - Document extension point integration
   - Add examples showing custom extension points

**Deliverables**:
- ✅ BaseAgent creates and passes callbacks
- ✅ Extension points work in workflow execution
- ✅ Error handling extension point integrated
- ✅ 40 lines changed

**Validation**:
- Create custom agent with overridden extension points
- Verify each extension point is called

### Task 2.4: Write Extension Point Tests (Days 9-10, 12 hours)

**File**: `packages/kailash-kaizen/tests/unit/core/test_extension_points.py` (NEW, 800 lines)

**Test Structure**:

1. **Test Suite 1: `TestExtensionCallbacks`** (100 lines, 8 tests)
   - Test ExtensionCallbacks dataclass creation
   - Test optional callbacks
   - Test callback signatures
   - Test callback execution

2. **Test Suite 2: `TestExtensionPointNodes`** (200 lines, 15 tests)
   - Test ValidationNode with valid data
   - Test ValidationNode with invalid data
   - Test ValidationNode without validator
   - Test PreHookNode with modification
   - Test PreHookNode passthrough
   - Test PostHookNode with modification
   - Test PostHookNode passthrough
   - Test node parameter definitions
   - Test node error handling

3. **Test Suite 3: `TestWorkflowGeneratorCallbacks`** (250 lines, 20 tests)
   - Test workflow generation with all callbacks
   - Test workflow generation with no callbacks
   - Test workflow generation with partial callbacks
   - Test custom system prompt callback
   - Test validation callback integration
   - Test pre-hook callback integration
   - Test post-hook callback integration
   - Test node connections correct
   - Test workflow execution order

4. **Test Suite 4: `TestBaseAgentExtensionPoints`** (250 lines, 17 tests)
   - Test custom _generate_system_prompt works
   - Test custom _validate_signature_output works
   - Test custom _pre_execution_hook works
   - Test custom _post_execution_hook works
   - Test custom _handle_error works
   - Test all extension points together
   - Test extension point execution order
   - Test extension point data flow
   - Test extension point error handling
   - Test extension point with real LLM (mock)

**Implementation**:

1. **Day 9 Morning**: Test Suites 1-2 (23 tests) - 4 hours
2. **Day 9 Afternoon**: Test Suite 3 (20 tests) - 4 hours
3. **Day 10 Morning**: Test Suite 4 first half (9 tests) - 4 hours
4. **Day 10 Afternoon**: Test Suite 4 second half (8 tests) - 4 hours

**Deliverables**:
- ✅ 60 comprehensive tests
- ✅ 800 lines of test code
- ✅ All extension points validated
- ✅ All tests passing

---

## Phase 3: Strict Mode Intelligence (Days 11-15)

**Goal**: Fix Bug #4 (OpenAI strict mode limitations cause cryptic errors)

### Task 3.1: Create StrictModeValidator (Days 11-12, 12 hours)

**File**: `packages/kailash-kaizen/src/kaizen/core/strict_mode_validator.py` (NEW, 200 lines)

**Implementation Steps**:

1. **Day 11 Morning**: Create file structure and StrictModeCompatibility dataclass (2 hours)
   ```python
   """
   Strict Mode Validator - Check OpenAI strict mode compatibility.

   Validates signatures against OpenAI strict mode constraints and provides
   actionable guidance when incompatibilities are detected.
   """
   from typing import Any, Dict, List, Type, get_origin, get_args, Union
   from dataclasses import dataclass

   @dataclass
   class StrictModeCompatibility:
       """Result of strict mode compatibility check."""
       is_compatible: bool
       errors: List[str]
       warnings: List[str]
       recommendations: List[str]
   ```

2. **Day 11 Afternoon**: Implement `check_signature_compatibility()` method (4 hours)
   - Check for unsupported validation constraints (pattern, min/max, etc.)
   - Check for optional fields (Union with None)
   - Check nesting depth (<= 5 levels)
   - Check total property count (<= 100)
   - Generate actionable error messages
   - Generate specific recommendations

3. **Day 12 Morning**: Implement helper methods (3 hours)
   - `_calculate_nesting_depth()` - Recursive depth calculation
   - `_count_total_properties()` - Count all properties across nested objects
   - `_check_validation_constraints()` - Check field-level constraints
   - `_check_optional_fields()` - Detect Optional[T] patterns

4. **Day 12 Afternoon**: Add docstrings and examples (3 hours)
   - Comprehensive docstrings
   - Real-world examples
   - Edge case documentation

**Deliverables**:
- ✅ `strict_mode_validator.py` with StrictModeValidator class
- ✅ Complete compatibility checking logic
- ✅ Actionable error messages and recommendations
- ✅ 200 lines of code

**Validation**:
- Manual testing with compatible signatures
- Manual testing with incompatible signatures
- Verify error messages are clear

### Task 3.2: Update create_structured_output_config() (Day 13, 6 hours)

**File**: `packages/kailash-kaizen/src/kaizen/core/structured_output.py` (MODIFY, 40 line changes)

**Changes Required**:

1. **Add import** (5 min)
   ```python
   from kaizen.core.strict_mode_validator import StrictModeValidator, StrictModeCompatibility
   import logging
   logger = logging.getLogger(__name__)
   ```

2. **Update function signature** (15 min)
   ```python
   def create_structured_output_config(
       signature: Any,
       strict: bool = True,
       name: str = "response",
       auto_fallback: bool = True  # NEW: Auto-fallback on incompatibility
   ) -> Dict[str, Any]:
   ```

3. **Add compatibility checking logic** (4 hours)
   ```python
   def create_structured_output_config(
       signature: Any,
       strict: bool = True,
       name: str = "response",
       auto_fallback: bool = True
   ) -> Dict[str, Any]:
       """
       Create OpenAI-compatible structured output configuration.

       With intelligent strict mode detection:
       - If signature compatible + strict=True → use strict mode
       - If incompatible + strict=True + auto_fallback=True → fallback with warning
       - If incompatible + strict=True + auto_fallback=False → raise error with guidance

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
           compatibility = StrictModeValidator.check_signature_compatibility(signature)

           if not compatibility.is_compatible:
               # Build error message with recommendations
               error_msg = "Signature incompatible with OpenAI strict mode:\n"
               error_msg += "\n".join(f"  - {err}" for err in compatibility.errors)

               if compatibility.warnings:
                   error_msg += "\n\nWarnings:\n"
                   error_msg += "\n".join(f"  - {warn}" for warn in compatibility.warnings)

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
                   # Raise error with full guidance
                   error_msg += "\n\nTo fix: Either adjust signature or use strict=False mode."
                   raise ValueError(error_msg)

       # Generate config based on final strict mode value
       if strict:
           return {
               "type": "json_schema",
               "json_schema": {"name": name, "strict": True, "schema": schema}
           }
       else:
           return {"type": "json_object", "schema": schema}
   ```

4. **Update docstrings** (1 hour)
   - Document auto_fallback behavior
   - Add examples showing compatibility checking
   - Document all error scenarios

**Deliverables**:
- ✅ Updated `create_structured_output_config()` with intelligent strict mode
- ✅ Auto-fallback logic
- ✅ Clear error messages with guidance
- ✅ 40 lines changed

**Validation**:
- Test with compatible signature (should use strict mode)
- Test with incompatible signature + auto_fallback=True (should fallback)
- Test with incompatible signature + auto_fallback=False (should raise error)

### Task 3.3: Write Strict Mode Tests (Day 14, 8 hours)

**File**: `packages/kailash-kaizen/tests/unit/core/test_strict_mode_validator.py` (NEW, 400 lines)

**Test Structure**:

1. **Test Suite 1: `TestStrictModeCompatibilityChecking`** (200 lines, 15 tests)
   - Test compatible signature
   - Test pattern validation incompatible
   - Test min/max validation incompatible
   - Test minLength/maxLength incompatible
   - Test optional fields warning
   - Test nesting depth exceeded
   - Test property count exceeded
   - Test multiple incompatibilities
   - Test edge cases

2. **Test Suite 2: `TestAutoFallbackBehavior`** (150 lines, 10 tests)
   - Test auto_fallback with compatible signature
   - Test auto_fallback with incompatible signature
   - Test no fallback raises error
   - Test fallback warning logged
   - Test error message contains recommendations

3. **Test Suite 3: `TestStrictModeIntegration`** (50 lines, 5 tests)
   - Test E2E with BaseAgent
   - Test E2E with real signature
   - Test strict mode used when compatible
   - Test fallback used when incompatible

**Implementation**:
1. **Morning**: Test Suite 1 (15 tests) - 4 hours
2. **Afternoon**: Test Suites 2-3 (15 tests) - 4 hours

**Deliverables**:
- ✅ 30 comprehensive tests
- ✅ 400 lines of test code
- ✅ All strict mode scenarios covered
- ✅ All tests passing

### Task 3.4: Write Documentation Guide (Day 15, 8 hours)

**File**: `packages/kailash-kaizen/docs/guides/strict-mode-compatibility.md` (NEW, ~2000 words)

**Document Structure**:

1. **Introduction** (300 words)
   - What is OpenAI strict mode?
   - Why is it important?
   - When to use strict mode vs legacy mode

2. **Strict Mode Constraints** (500 words)
   - Unsupported validation keywords (list all)
   - Required field constraints
   - Nesting depth limits
   - Property count limits
   - additionalProperties requirement

3. **Compatibility Checking** (400 words)
   - How Kaizen checks compatibility
   - What happens with incompatible signatures
   - Auto-fallback behavior
   - How to disable auto-fallback

4. **Common Incompatibilities & Solutions** (600 words)
   - Pattern validation → Use Literal enum instead
   - Min/max constraints → Remove or use strict=False
   - Optional fields → Use nullable types
   - Deep nesting → Flatten structure
   - Too many properties → Split into multiple calls

5. **Examples** (200 words)
   - Compatible signature example
   - Incompatible signature with auto-fallback
   - Fixing incompatible signature
   - Complex signature with workarounds

**Implementation**:
1. **Morning**: Sections 1-3 (4 hours)
2. **Afternoon**: Sections 4-5 (4 hours)

**Deliverables**:
- ✅ Complete strict mode compatibility guide
- ✅ Real-world examples
- ✅ Troubleshooting section
- ✅ ~2000 words

---

## Integration & Testing (Day 15 afternoon + Day 16-17)

### Task 4.1: Integration Testing (Day 15 afternoon, 4 hours)

**File**: `packages/kailash-kaizen/tests/integration/test_structured_output_e2e.py` (NEW, 400 lines)

**Test Structure**:

1. **E2E with real OpenAI API** (10 tests)
   - Test Literal type with strict mode
   - Test Union type with fallback
   - Test Optional type with strict mode
   - Test List[T] with strict mode
   - Test complex signature
   - Test extension points work
   - Test validation works
   - Test error handling
   - Test strict mode auto-fallback
   - Test performance (<500ms per call)

2. **E2E with mock provider** (10 tests)
   - Same tests as above but with mock
   - Faster execution for CI/CD

**Implementation**:
- Write 20 E2E tests
- Cover all 4 bugs fixed
- Test real-world scenarios

**Deliverables**:
- ✅ 20 E2E tests
- ✅ 400 lines of test code
- ✅ Real OpenAI API validation
- ✅ Mock provider validation

### Task 4.2: Regression Testing (Days 16-17, 8 hours)

**Steps**:

1. **Day 16 Morning**: Run full test suite (2 hours)
   ```bash
   pytest packages/kailash-kaizen/tests/unit/ -v
   pytest packages/kailash-kaizen/tests/integration/ -v
   ```

2. **Day 16 Afternoon**: Fix any test failures (2 hours)
   - Debug failures
   - Fix code or tests
   - Re-run until all pass

3. **Day 17 Morning**: Performance testing (2 hours)
   - Benchmark TypeIntrospector overhead
   - Benchmark extension point node latency
   - Benchmark strict mode validation
   - Ensure <5ms overhead per operation

4. **Day 17 Afternoon**: Documentation review (2 hours)
   - Review all docstrings
   - Test all code examples
   - Verify API docs accurate
   - Update CHANGELOG

**Deliverables**:
- ✅ All 215 tests passing (135 new + 80 existing)
- ✅ Performance benchmarks pass
- ✅ Documentation accurate
- ✅ CHANGELOG updated

---

## Deliverables Summary

### Code Files (8 files total)

**New Files (5)**:
1. ✅ `src/kaizen/core/type_introspection.py` (200 lines)
2. ✅ `src/kaizen/core/extension_points.py` (50 lines)
3. ✅ `src/kaizen/nodes/extension_point_nodes.py` (120 lines)
4. ✅ `src/kaizen/core/strict_mode_validator.py` (200 lines)
5. ✅ `docs/guides/strict-mode-compatibility.md` (~2000 words)

**Modified Files (3)**:
1. ✅ `src/kaizen/core/structured_output.py` (90 line changes)
2. ✅ `src/kaizen/core/workflow_generator.py` (40 line changes)
3. ✅ `src/kaizen/core/base_agent.py` (40 line changes)

### Test Files (4 files total)

**New Test Files (4)**:
1. ✅ `tests/unit/core/test_type_introspection.py` (500 lines, 45 tests)
2. ✅ `tests/unit/core/test_extension_points.py` (800 lines, 60 tests)
3. ✅ `tests/unit/core/test_strict_mode_validator.py` (400 lines, 30 tests)
4. ✅ `tests/integration/test_structured_output_e2e.py` (400 lines, 20 tests)

**Total Test Coverage**: 155 new tests (2100 lines)

---

## Timeline Summary

| Phase | Days | Tasks | Lines Added | Lines Changed | Tests Added |
|-------|------|-------|-------------|---------------|-------------|
| **Phase 1: Type System** | 1-5 | 4 tasks | 700 | 90 | 45 |
| **Phase 2: Extension Points** | 6-10 | 4 tasks | 970 | 80 | 60 |
| **Phase 3: Strict Mode** | 11-15 | 4 tasks | 600 | 40 | 30 |
| **Integration** | 15-17 | 2 tasks | 400 | 0 | 20 |
| **TOTAL** | **17 days** | **14 tasks** | **2670** | **210** | **155** |

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation Strategy |
|------|-------------|--------|---------------------|
| Tests fail after integration | Medium | High | Write tests first (TDD), continuous testing |
| Performance degradation | Low | Medium | Benchmark each phase, optimize hot paths |
| Breaking changes discovered | Low | High | Comprehensive regression testing |
| TypeIntrospector edge cases | Medium | Medium | 45 comprehensive tests, including edge cases |
| Extension point complexity | Low | Medium | Simple callback interface, thorough testing |
| Strict mode edge cases | Medium | Low | 30 tests covering all OpenAI constraints |

---

## Success Criteria Checklist

### Phase 1: Type System
- [ ] All 45 type introspection tests pass
- [ ] `test_validate_literal_field_valid_value` passes (Bug #1 fixed)
- [ ] All 13 Literal type tests pass
- [ ] Support for Union, Optional, List[T], Dict[K,V], TypedDict
- [ ] Performance: <1ms per type check

### Phase 2: Extension Points
- [ ] All 60 extension point tests pass
- [ ] All 7 extension points work in workflow path
- [ ] Custom prompts, validation, hooks work (Bug #3 fixed)
- [ ] No tight coupling between components
- [ ] Performance: <5ms per extension point call

### Phase 3: Strict Mode Intelligence
- [ ] All 30 strict mode tests pass
- [ ] Incompatible signatures detected
- [ ] Auto-fallback works correctly
- [ ] Clear, actionable error messages (Bug #4 fixed)
- [ ] Documentation guide complete

### Integration
- [ ] All 20 E2E tests pass
- [ ] All 215 total tests pass (155 new + 60 existing)
- [ ] Performance benchmarks pass
- [ ] Documentation accurate
- [ ] CHANGELOG updated
- [ ] 100% backward compatible

---

## Next Steps

1. **Review this plan** with team
2. **Assign tasks** to developers
3. **Set up development branch** (`feature/structured-output-fix`)
4. **Begin Phase 1** - Type System implementation
5. **Daily standups** to track progress
6. **Code reviews** after each phase
7. **Final integration** and release

---

**Document Status**: Ready for Implementation
**Estimated Completion**: 17 business days (3.4 weeks)
**Total Effort**: ~120 hours
